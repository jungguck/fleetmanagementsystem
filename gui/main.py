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
from gui.ui import control, dashboard, mapview, tasks

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
    """관제 대시보드 페이지 — 한 화면(스크롤 최소): 왼쪽 맵(고정) + 오른쪽 탭."""
    # 화면 높이를 꽉 채우고 페이지 자체 스크롤을 없앤다(정보를 한 화면에).
    ui.query(".nicegui-content").classes("h-screen w-full p-2 gap-2 flex flex-col")

    ui.label("FMS — turtlesim Fleet 관제").classes("text-lg font-bold")

    # ── 상단 요약 바(가벼움 → refreshable) ──
    @ui.refreshable
    def summary() -> None:
        dashboard.summary_bar(state)
    summary()

    # ── 본문: 왼쪽 맵(고정) + 오른쪽 탭(로봇/조작/작업) ──
    with ui.row().classes("w-full flex-1 gap-3 items-stretch min-h-0"):
        # 왼쪽 맵: '한 번만' 생성(고정) → 이후 render_map 이 내용만 갱신(깜빡임 없음).
        with ui.column().classes("gap-1"):
            # 맵 클릭 대상 로봇 선택 — 맵 바로 위에 항상 노출(탭 이동 없이 전환).
            #   여기서 고른 로봇이 맵 클릭 지점으로 이동한다(맵에 흰 점선 링으로 표시).
            #   index() 는 한 번만 실행 → 이 토글은 재생성 안 됨 → 선택값 유지.
            with ui.row().classes("items-center gap-2"):
                ui.label("🖱 클릭 대상:").classes("text-sm font-bold")
                ui.toggle({r.id: r.name for r in state.robots}, value=state.selected_id,
                          on_change=lambda e: setattr(state, "selected_id", e.value)
                          ).props("dense")
            map_img = mapview.create_map(state)
            ui.label("🐢거북이 · 실선=궤적 · 점선=A*경로 · ▣스테이션 · "
                     "흐린사각=가상벽 · 🔴충돌위험 · 🟠양보").classes(
                "text-xs").style("color:#9aa7b0; max-width:520px")

        # 오른쪽: 탭으로 정보 분리 → 세로 스크롤 최소화.
        with ui.column().classes("flex-1 min-w-0"):
            with ui.tabs().classes("w-full") as tabs:
                ui.tab("로봇")
                ui.tab("조작")
                ui.tab("작업")
            with ui.tab_panels(tabs, value="로봇").classes(
                    "w-full flex-1 min-h-0").style("overflow:auto"):
                with ui.tab_panel("로봇"):        # 로봇 상태 카드
                    @ui.refreshable
                    def cards() -> None:
                        dashboard.robot_cards(state)
                    cards()
                with ui.tab_panel("조작"):        # 조작 패널 — 한 번만(폼/토글 리셋 방지)
                    control.control_panel(state)
                with ui.tab_panel("작업"):        # 작업 생성(한 번만) + 큐(갱신)
                    tasks.create_form(state)
                    @ui.refreshable
                    def queue() -> None:
                        tasks.task_queue(state)
                    queue()

    # ── 화면 갱신 틱: 맵은 '내용만' 교체, 나머지는 refresh ──
    #   관제 로직(배차·충전)은 위 app.timer(state.refresh) 담당. 여기선 그리기만.
    def tick() -> None:
        mapview.render_map(state, map_img)   # 요소 재생성 X → 깜빡임 없음
        summary.refresh()
        cards.refresh()
        queue.refresh()
    ui.timer(state.poll_interval, tick)


if __name__ in {"__main__", "__mp_main__"}:
    # 포트 8090 — 8080(plc_study)·8081(llama-server) 과 충돌 회피.
    # reload=False : 리로더가 뜨면 ROS 노드가 두 번 뜬다(거북이 중복 spawn) → 끔.
    # show=False   : 자동 브라우저 안 띄움(원격 접속).
    ui.run(title="FMS turtlesim 관제", port=8090, reload=False, show=False)
