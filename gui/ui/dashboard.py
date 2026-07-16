"""FMS 관제 — 대시보드 화면 위젯
═══════════════════════════════════════════════════════════════════════
plc_study_for_me/app/ui/{dashboard,components}.py 의 robot_card·요약 패턴 차용.
여기선 TurtleBot(AGV) 상태 카드로 치환한다.
  - robot_card()    : 로봇 1대 카드 (상태등·작업·배터리·위치)
  - dashboard_body(): 상단 요약 + 로봇 카드 그리드
═══════════════════════════════════════════════════════════════════════
"""
from nicegui import ui

from gui.state import STATE_COLORS, FleetState, RobotState
from gui.ui import mapview   # 좌측 맵뷰(로봇 위치·스테이션)


def robot_card(r: RobotState) -> None:
    """로봇(지게차) 1대 카드."""
    color = STATE_COLORS.get(r.state, "#9aa7b0")   # 상태 색 (없으면 회색)

    with ui.card().classes("w-64"):
        # ── 헤더: 이름 + 상태 표시등(색 점) ──
        with ui.row().classes("items-center justify-between w-full"):
            ui.label(r.name).classes("text-lg font-bold")
            ui.element("div").style(
                f"width:12px;height:12px;border-radius:50%;background:{color}")

        # ── 상태 / 작업 ──
        ui.label(f"상태: {r.state}").style(f"color:{color};font-weight:600")
        ui.label(f"작업: {r.task}").classes("text-sm")

        # ── 배터리 바 (20% 미만은 빨강 경고색) ──
        ui.linear_progress(r.battery / 100, show_value=False).props(
            f"color={'red' if r.battery < 20 else 'green'}")

        # ── 배터리 % + 맵 위치 ──
        ui.label(f"🔋 {r.battery:.0f}%   📍({r.x:.1f}, {r.y:.1f})").classes("text-xs")

        # ── 오프라인이면 경고 ──
        if not r.online:
            ui.label("⚠ OFFLINE").classes("text-xs").style("color:#e74c3c")


def dashboard_body(state: FleetState) -> None:
    """대시보드 본문: 상단 요약 줄 + 로봇 카드 그리드."""
    s = state.summary

    # ── 상단 요약 ──
    ui.label(
        f"🚜 Fleet 관제  —  가동 {s['online']}/{s['total']}  ·  "
        f"주행 {s['driving']}  ·  충전 {s['charging']}  ·  에러 {s['error']}  ·  "
        f"소스: {state.source_name}"
    ).classes("text-lg font-bold mb-2")

    # ── 본문: 왼쪽 맵뷰 + 오른쪽 로봇 카드 (GUI_설계.md 배치) ──
    with ui.row().classes("w-full gap-4 items-start"):
        # 왼쪽: 맵뷰 (로봇 위치·스테이션을 2D 평면에)
        mapview.map_view(state)
        # 오른쪽: 로봇 카드 그리드 (대수만큼 순회 — plc_study for r in snap.robots 패턴)
        with ui.column().classes("flex-1"):
            with ui.row().classes("flex-wrap gap-3"):
                for r in state.robots:
                    robot_card(r)
