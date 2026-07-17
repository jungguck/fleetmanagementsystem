"""FMS 관제 — 진입점 (NiceGUI 웹앱)
═══════════════════════════════════════════════════════════════════════
ROS 2 turtlesim 거북이 4마리를 웹에서 조작·관제한다.

구조:
  turtlesim_node ──/turtleN/pose──→ turtlesim_source(rclpy, 20Hz 제어)
                 ←─/turtleN/cmd_vel─┘        │
                                             ↓
                                     state.FleetState (배차·작업·충전)
                                             ↓
                                   NiceGUI 웹 (맵뷰·카드·조작·작업큐)

plc_study_for_me/app/main.py 패턴 차용:
  - @ui.page 로 페이지 정의
  - ui.timer(poll_interval) 로 주기적 갱신 (수집 → 화면 그리기)

실행 (터미널 2개):
  1) source /opt/ros/jazzy/setup.bash && ros2 run turtlesim turtlesim_node
  2) ./run.sh                  # → http://localhost:8090
═══════════════════════════════════════════════════════════════════════
"""
import os

from nicegui import app, ui

from gui.state import FleetState
from gui.ui import control, dashboard, tasks

# config.yaml 경로 (이 파일과 같은 폴더)
CFG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

# 전역 Fleet 상태 — 모든 브라우저 클라이언트가 공유.
#   여기서 turtlesim 에 접속하고 거북이 4마리를 spawn 한다(백엔드=turtlesim 일 때).
state = FleetState(CFG_PATH)

# 웹앱 종료 시 ROS 노드/실행기 정리.
app.on_shutdown(state.shutdown)

# ── 관제 두뇌 틱: '앱 전체에 하나' (app.timer) ──────────────────────────
# ⚠ 이걸 @ui.page 안의 ui.timer 로 두면 안 된다. 페이지 함수는 '브라우저마다' 실행되므로
#   관제 로직(배차·작업FSM·충전복귀)이 접속자 수만큼 돈다:
#     · 브라우저 0개 → refresh 가 아예 안 돎 → 작업이 배차되지 않는다(관제 정지)
#     · 브라우저 2개 → 배차·배터리 계산이 2배속
#   화면 그리기(dash.refresh)만 페이지별이면 된다.
app.timer(state.poll_interval, state.refresh)


@ui.page("/")
def index() -> None:
    """관제 대시보드 페이지."""
    ui.label("FMS — turtlesim Fleet 관제").classes("text-2xl font-bold m-2")

    # 로봇 조작(목적지 지정 + 수동 teleop) — 한 번만 렌더(자동갱신 밖).
    control.control_panel(state)

    # (대안) 자동배차 작업 생성 폼 — A→B 만들면 시스템이 로봇을 고름.
    #   폼이라 역시 '한 번만' 렌더(자동갱신 영역 밖. tasks.py 상단 공부포인트 참고).
    tasks.create_form(state)

    # 아래 영역만 주기적으로 다시 그린다(refreshable) → 전체 페이지 리로드 없음.
    @ui.refreshable
    def dash() -> None:
        dashboard.dashboard_body(state)

    dash()

    # 이 타이머는 '이 브라우저의 화면만' 다시 그린다(관제 로직은 위 app.timer 가 담당).
    #   ※ 로봇 제어(cmd_vel)는 둘 다 아니고 ROS 스레드가 20Hz 로 돌린다.
    ui.timer(state.poll_interval, dash.refresh)


if __name__ in {"__main__", "__mp_main__"}:
    # 포트 8090 — 8080(plc_study)·8081(llama-server) 과 충돌 회피.
    # reload=False : 리로더가 뜨면 ROS 노드가 두 번 뜬다(거북이 중복 spawn) → 끔.
    # show=False   : 자동 브라우저 안 띄움(원격 접속).
    ui.run(title="FMS turtlesim 관제", port=8090, reload=False, show=False)
