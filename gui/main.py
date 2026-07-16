"""FMS 관제 — 진입점 (NiceGUI 웹앱)
═══════════════════════════════════════════════════════════════════════
plc_study_for_me/app/main.py 패턴 차용:
  - @ui.page 로 페이지 정의
  - ui.timer(poll_interval) 로 주기적 갱신 ('수집'과 '화면 그리기'를 한 틱에서)
지금은 mock 소스라 ROS 없이 단독 실행된다.

실행:
  pip install -r requirements.txt
  cd ~/FMSsystem_agv           # 리포 루트 (gui 가 패키지로 import 되게)
  python -m gui.main           # → http://localhost:8090
═══════════════════════════════════════════════════════════════════════
"""
import os

from nicegui import ui

from gui.state import FleetState
from gui.ui import dashboard

# config.yaml 경로 (이 파일과 같은 폴더)
CFG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

# 전역 Fleet 상태 — 모든 브라우저 클라이언트가 공유(지금은 mock 데이터).
state = FleetState(CFG_PATH)


@ui.page("/")
def index() -> None:
    """관제 대시보드 페이지."""
    ui.label("FMS — TurtleBot Fleet 관제").classes("text-2xl font-bold m-2")

    # 이 영역만 주기적으로 다시 그린다(refreshable) → 전체 페이지 리로드 없음.
    @ui.refreshable
    def dash() -> None:
        dashboard.dashboard_body(state)

    dash()

    # 타이머: 매 poll_interval 마다 (1) 소스 갱신 → (2) 화면 refresh.
    #   plc_study 처럼 '수집(state.refresh)'과 '그리기(dash.refresh)'를 순서대로.
    ui.timer(state.poll_interval, lambda: (state.refresh(), dash.refresh()))


if __name__ in {"__main__", "__mp_main__"}:
    # 포트 8090 — 8080(plc_study)·8081(llama-server) 과 충돌 회피.
    # show=False : 자동 브라우저 안 띄움(집에서 직접 접속).
    ui.run(title="FMS Fleet 관제", port=8090, reload=False, show=False)
