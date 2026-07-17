"""FMS 관제 — 공용 데이터 모델 (로봇·작업·색·락)
═══════════════════════════════════════════════════════════════════════
백엔드(turtlesim_source / sim2d)와 관제 로직(state.py)과 화면(ui/*) 이 모두
같은 모델을 본다. 이 모듈만 서로 의존 없이 아래에 두어 순환 import 를 막는다.
    models.py  ←─ turtlesim_source.py ─┐
        ↑                              ├─→ state.py ─→ ui/*
        └──────────────────────────────┘
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

# 배터리 임계치(%) — 이 아래로 떨어진 유휴 로봇은 자동으로 충전소로 복귀.
LOW_BATT = 20.0

# ─────────────────────────────────────────────────────────────────────
# 로봇 상태를 만지는 스레드가 둘이라 락이 필요하다:
#   ① ROS 실행기 스레드  : 20Hz 제어루프가 path/state/battery 를 갱신
#   ② 웹 GUI 스레드      : 버튼 클릭(send_goal/teleop) 이 path/state 를 교체
# 둘 다 이 락을 잡고 만진다. (RLock: 락 잡은 채 다른 메서드 호출 가능)
# ─────────────────────────────────────────────────────────────────────
FLEET_LOCK = threading.RLock()


# ─────────────────────────────────────────────────────────────────────
# 로봇(= turtlesim 거북이) 한 대의 상태 모델
# ─────────────────────────────────────────────────────────────────────
@dataclass
class RobotState:
    id: str                  # turtle1 등 — ROS 토픽 네임스페이스(/turtle1/cmd_vel)와 동일
    name: str                # 화면 표시명
    pen: tuple[int, int, int] = (255, 214, 10)   # 궤적 펜 색 (웹 맵뷰 ↔ turtlesim 창 공유)
    # 교통관제 우선순위(작을수록 우선). config 순서로 배정 — 전순서라 교착이 없다(traffic.py).
    prio: int = 0
    online: bool = False     # /pose 가 들어오고 있나(통신 살아있나)
    state: str = "idle"      # idle / driving / waiting / manual / charging / error
    battery: float = 100.0   # 0~100 % — turtlesim 엔 없는 개념(FMS 관제용 가상값)
    task: str = "-"          # 현재 작업 설명 (예: "PICK-A→DROP-B")
    x: float = 0.0           # turtlesim 좌표 (0~11.09)
    y: float = 0.0
    yaw: float = 0.0         # 방향 (rad) — turtlesim Pose.theta
    # 경로: A* 가 만든 웨이포인트 리스트 [(x,y), …]. 비면 목표 없음(정지).
    #   제어루프가 path[0] 로 향하다 도달하면 pop → 다 비면 도착.
    path: list[tuple[float, float]] = field(default_factory=list)
    goal_kind: str = ""      # 목표 스테이션 종류(도착 시 처리용): pickup/drop/charge
    # 지나온 궤적 [(x,y), …] — turtlesim 의 '펜' 을 웹 맵뷰에서 재현하기 위한 발자취.
    #   TRAIL_MAX 개까지만 보관(오래된 건 버림) → 메모리·SVG 크기 상한.
    trail: list[tuple[float, float]] = field(default_factory=list)
    # teleop: (전진속도, 회전속도) 를 manual_until 시각까지 발행. 놓으면 만료 → 정지.
    manual: tuple[float, float] | None = None
    manual_until: float = 0.0


# ─────────────────────────────────────────────────────────────────────
# 작업(Task): "픽업 스테이션 → 드롭 스테이션" 배송 1건
#   운영자가 GUI 에서 만들면 pending 으로 큐에 쌓이고, 배차기가 유휴 로봇에 할당.
# ─────────────────────────────────────────────────────────────────────
@dataclass
class Task:
    id: int
    pickup: str               # 픽업 스테이션 이름
    drop: str                 # 드롭 스테이션 이름
    state: str = "pending"    # pending(대기) / running(수행중) / done(완료)
    robot: str | None = None  # 배차된 로봇 id
    phase: str = ""           # to_pickup / to_drop (running 중 실행 단계)


# 궤적(펜) 색 팔레트 — 로봇 순서대로 배정.
#   같은 색을 turtlesim 창의 펜(set_pen)과 웹 맵뷰 궤적에 함께 써서 '누가 누군지'를 맞춘다.
#   ⚠ 고른 기준 2가지:
#     ① 파란 배경(TURTLESIM_BG) 위에서 잘 보일 것 → 밝고 따뜻한 색 위주.
#     ② STATE_COLORS 와 안 겹칠 것 → '색이 로봇을 뜻하는지 상태를 뜻하는지' 혼동 방지.
PEN_COLORS = [(255, 214, 10), (255, 105, 180), (0, 230, 195), (255, 138, 60)]

# 궤적 보관 개수 상한(로봇당). 넘으면 오래된 점부터 버린다.
TRAIL_MAX = 500

# turtlesim 창의 기본 배경색(파랑) — 웹 맵뷰가 같은 화면처럼 보이게 그대로 쓴다.
TURTLESIM_BG = "#4556ff"


def rgb_hex(c: tuple[int, int, int]) -> str:
    """(r,g,b) → '#rrggbb' (SVG 용)."""
    return "#%02x%02x%02x" % c


# 상태 → 색. GUI_설계.md 의 색 규칙과 공유(대시보드·맵뷰 공통).
STATE_COLORS = {
    "idle":     "#9aa7b0",  # 회색 : 대기
    "driving":  "#2e86de",  # 파랑 : 주행중(목표 추종)
    "waiting":  "#e67e22",  # 주황 : 충돌회피 양보 대기(교통관제가 세움)
    "manual":   "#16a085",  # 청록 : 수동 조작(teleop)
    "charging": "#27ae60",  # 초록 : 충전
    "error":    "#e74c3c",  # 빨강 : 에러
}

# 상태 → 화면에 보여줄 한글 라벨.
STATE_LABELS = {
    "idle": "대기", "driving": "주행중", "waiting": "양보대기",
    "manual": "수동조작", "charging": "충전중", "error": "에러",
}
