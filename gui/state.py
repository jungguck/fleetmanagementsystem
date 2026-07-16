"""FMS 관제 — 중앙 상태 (Fleet State)
═══════════════════════════════════════════════════════════════════════
이 파일의 역할 (plc_study_for_me/app/state.py 의 축소·차용판):
  1. config.yaml 을 읽어 로봇(=지게차) 목록을 만든다.
  2. "데이터 소스"에서 각 로봇의 최신 상태(위치·배터리·작업·상태)를 가져온다.
       - MockFleetSource : ROS 없이 가짜 데이터(랜덤 진화) → GUI 단독 실행용
       - (예정) RosFleetSource : rclpy 로 /tbN/odom·battery·nav2 상태 구독 (P1+)
  3. refresh() 로 소스를 한 번 폴링 → GUI 가 로봇 리스트를 읽어 그린다.

설계 원칙 (plc_study 와 동일):
  - 제어/수집(refresh)과 화면(그리기)을 분리 → 여러 브라우저가 붙어도 안전.
  - 소스를 인터페이스로 추상화 → mock ↔ ros 를 config 한 줄로 교체.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

import yaml


# ─────────────────────────────────────────────────────────────────────
# 로봇(지게차) 한 대의 상태 모델
#   TurtleBot 을 AGV 로 본 최소 필드. 실제 ROS 소스가 이 필드를 채운다.
# ─────────────────────────────────────────────────────────────────────
@dataclass
class RobotState:
    id: str                 # tb1 등 (ROS 네임스페이스와 일치)
    name: str               # 화면 표시명
    online: bool = True     # 통신 살아있나
    state: str = "idle"     # idle / driving / charging / loading / unloading / error
    battery: float = 100.0  # 0~100 %
    task: str = "-"         # 현재 작업 설명 (예: "PICK-A→DROP-B")
    x: float = 0.0          # 맵 좌표 (odom/amcl pose)
    y: float = 0.0
    yaw: float = 0.0        # 방향 (rad)
    tx: float | None = None # 목표 좌표(mock 이동용). None = 목표 없음
    ty: float | None = None


# ─────────────────────────────────────────────────────────────────────
# 작업(Task): "픽업 스테이션 → 드롭 스테이션" 배송 1건
#   운영자가 GUI 에서 만들면 pending 으로 큐에 쌓이고, 배차기가 idle 로봇에 할당.
# ─────────────────────────────────────────────────────────────────────
@dataclass
class Task:
    id: int
    pickup: str               # 픽업 스테이션 이름
    drop: str                 # 드롭 스테이션 이름
    state: str = "pending"    # pending(대기) / running(수행중) / done(완료)
    robot: str | None = None  # 배차된 로봇 id


# 상태 → 색. GUI_설계.md 의 색 규칙과 공유(대시보드·맵뷰 공통).
STATE_COLORS = {
    "idle":      "#9aa7b0",  # 회색 : 대기
    "driving":   "#2e86de",  # 파랑 : 주행중
    "charging":  "#27ae60",  # 초록 : 충전
    "loading":   "#f39c12",  # 주황 : 적재
    "unloading": "#f39c12",  # 주황 : 하역
    "error":     "#e74c3c",  # 빨강 : 에러
}


# ─────────────────────────────────────────────────────────────────────
# 데이터 소스 (mock): poll() 이 로봇 리스트의 상태를 '살아있는 것처럼' 갱신
#   ⚠ 실제 배차/nav2 로직 아님 — 화면 골격 확인용 가짜 데이터.
# ─────────────────────────────────────────────────────────────────────
class MockFleetSource:
    def __init__(self, robots: list[RobotState]):
        self.robots = robots

    def poll(self) -> None:
        for r in self.robots:
            # 배터리는 매 틱 조금씩 소모
            r.battery = max(0.0, r.battery - random.uniform(0.0, 0.3))

            if r.battery < 20 and r.state != "charging":
                # 저전력 → 충전 복귀
                r.state, r.task = "charging", "저전력→충전복귀"
            elif r.state == "charging":
                # 충전중이면 배터리 회복, 다 차면 대기로
                r.battery = min(100.0, r.battery + 1.0)
                if r.battery > 95:
                    r.state, r.task = "idle", "-"
            elif r.state == "driving":
                # 주행중: 목표(tx,ty)가 있으면 그쪽으로 한 스텝씩, 없으면 랜덤 표류.
                #   (idle→driving 전환은 mock 이 아니라 send_goal/배차기가 한다)
                if r.tx is not None and r.ty is not None:
                    dx, dy = r.tx - r.x, r.ty - r.y
                    dist = math.hypot(dx, dy)
                    if dist < 0.15:                       # 도착
                        r.x, r.y = r.tx, r.ty
                        r.state, r.task, r.tx, r.ty = "idle", "-", None, None
                    else:
                        step = min(0.2, dist)             # 한 틱 이동량
                        r.x += step * dx / dist
                        r.y += step * dy / dist
                        r.yaw = math.atan2(dy, dx)        # 진행 방향으로 회전
                else:
                    r.x += random.uniform(-0.1, 0.2)
                    r.y += random.uniform(-0.1, 0.2)
                    if random.random() < 0.08:
                        r.state, r.task = "idle", "-"


# (예정) RosFleetSource — rclpy 노드로 실제 ROS2 상태 구독.
#   /tbN/odom(pose) · /tbN/battery_state · nav2 액션 결과 등을 받아
#   RobotState 필드를 채운다. P1+ 에서 브릿지(rclpy 직접 vs rosbridge) 결정 후 구현.
#   class RosFleetSource:
#       def __init__(self, robots): ...   # rclpy 노드·구독 세팅
#       def poll(self): ...               # 최신 메시지 → RobotState 반영
#   # TODO(P1)


# ─────────────────────────────────────────────────────────────────────
# Fleet 전체 상태: config 로드 + 소스 보유 + refresh/summary 제공
# ─────────────────────────────────────────────────────────────────────
class FleetState:
    def __init__(self, cfg_path: str):
        # 1) 설정 로드
        with open(cfg_path, encoding="utf-8") as f:
            self.cfg = yaml.safe_load(f)

        self.poll_interval = float(self.cfg.get("poll_interval_sec", 0.5))

        # 2) config 의 robots 목록 → RobotState 리스트 (배터리 랜덤 초기값)
        self.robots: list[RobotState] = [
            RobotState(id=r["id"], name=r.get("name", r["id"]),
                       battery=random.uniform(60, 100))
            for r in self.cfg.get("robots", [])
        ]
        self.stations = self.cfg.get("stations", [])
        self.source_name = self.cfg.get("source", "mock")

        # 3) 소스 선택
        if self.source_name == "ros":
            # rclpy 는 여기서만 lazy import (mock 실행은 rclpy 없이도 되게).
            #   ⚠ ros 는 ROS2 환경(집 머신)에서만 동작 — 이 개발머신엔 rclpy 없음.
            from gui.ros_source import RosFleetSource
            self.source = RosFleetSource(self.robots)
        else:
            self.source = MockFleetSource(self.robots)

        # 작업 큐 (운영자가 GUI 에서 추가)
        self.tasks: list[Task] = []
        self._task_seq = 0

    # ── 작업 생성 / 배차 ─────────────────────────────────────────────
    def add_task(self, pickup: str, drop: str) -> None:
        """운영자가 새 배송 작업을 큐에 추가(pending)."""
        self._task_seq += 1
        self.tasks.append(Task(id=self._task_seq, pickup=pickup, drop=drop))

    def send_goal(self, robot_id: str, x: float, y: float, yaw: float = 0.0) -> None:
        """로봇 N 을 (x,y) 로 보낸다 = 마스터 모델 "1번 로봇 A로 가라".
        - ros 소스면 실제 nav2 목표 전송(RosFleetSource.send_goal)
        - mock 이면 화면 상태만 driving 으로 (실제 이동은 안 함)
        (P3+ 에서 '로봇별 목적지 지정' UI 가 이 함수를 호출한다.)
        """
        r = next((rr for rr in self.robots if rr.id == robot_id), None)
        if r is None:
            return
        r.state, r.task = "driving", f"→({x:.1f},{y:.1f})"
        r.tx, r.ty = x, y                          # mock 이동 목표(ros 는 nav2 가 실이동)
        if hasattr(self.source, "send_goal"):      # ros 소스만 실제 전송
            self.source.send_goal(robot_id, x, y, yaw)

    def send_to_station(self, robot_id: str, station_name: str) -> None:
        """로봇을 '스테이션 이름'으로 보낸다(UI 편의). 이름→좌표 찾아 send_goal."""
        st = next((s for s in self.stations if s["name"] == station_name), None)
        if st is not None:
            self.send_goal(robot_id, float(st["x"]), float(st["y"]))

    def dispatch(self) -> None:
        """대기(pending) 작업을 idle·배터리충분 로봇에 배차.
        지금은 가장 단순 규칙: '첫 번째 여유 로봇'. (P3+ 에서 근접·배터리·혼잡 최적화)
        """
        for t in self.tasks:
            if t.state != "pending":
                continue
            robot = next((r for r in self.robots
                          if r.state == "idle" and r.battery > 20), None)
            if robot is None:
                break                       # 여유 로봇 없음 → 다음 틱에 다시
            t.state, t.robot = "running", robot.id
            robot.state, robot.task = "driving", f"{t.pickup}→{t.drop}"

    def _complete_tasks(self) -> None:
        """running 작업의 로봇이 idle 로 돌아오면(=목적지 도착) 작업 done 처리."""
        for t in self.tasks:
            if t.state == "running":
                r = next((r for r in self.robots if r.id == t.robot), None)
                if r is not None and r.state == "idle":
                    t.state = "done"

    def refresh(self) -> None:
        """한 사이클(GUI 타이머가 호출):
        1) 소스에서 로봇 상태 갱신 → 2) 대기작업 배차 → 3) 완료작업 정리.
        """
        self.source.poll()       # 배터리·주행 진행 등
        self.dispatch()          # pending → 로봇 할당
        self._complete_tasks()   # 도착한 로봇의 작업 done

    @property
    def summary(self) -> dict:
        """상단 요약용 집계."""
        return {
            "total":    len(self.robots),
            "online":   sum(1 for r in self.robots if r.online),
            "driving":  sum(1 for r in self.robots if r.state == "driving"),
            "charging": sum(1 for r in self.robots if r.state == "charging"),
            "error":    sum(1 for r in self.robots if r.state == "error"),
        }
