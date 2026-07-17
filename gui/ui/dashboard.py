"""FMS 관제 — 대시보드 화면 위젯
═══════════════════════════════════════════════════════════════════════
plc_study_for_me/app/ui/{dashboard,components}.py 의 robot_card·요약 패턴 차용.
여기선 turtlesim 거북이(AGV) 상태 카드로 치환한다.
  - robot_card()    : 로봇 1대 카드 (상태등·작업·배터리·위치)
  - dashboard_body(): 상단 요약 + 로봇 카드 그리드
═══════════════════════════════════════════════════════════════════════
"""
from nicegui import ui

from gui.models import LOW_BATT, STATE_COLORS, STATE_LABELS, RobotState
from gui.state import FleetState
from gui.ui import mapview   # 좌측 맵뷰(로봇 위치·스테이션)
from gui.ui import tasks     # 하단 작업 큐


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
        ui.label(f"상태: {STATE_LABELS.get(r.state, r.state)}").style(
            f"color:{color};font-weight:600")
        ui.label(f"작업: {r.task}").classes("text-sm")

        # ── 배터리 바 (임계치 미만은 빨강 경고색 → 자동 충전복귀 대상) ──
        ui.linear_progress(r.battery / 100, show_value=False).props(
            f"color={'red' if r.battery < LOW_BATT else 'green'}")

        # ── 배터리 % + 맵 위치 (turtlesim /pose 실측값) ──
        ui.label(f"🔋 {r.battery:.0f}%   📍({r.x:.1f}, {r.y:.1f})").classes("text-xs")

        # ── /pose 가 안 들어오면 경고(거북이가 죽었거나 turtlesim 종료) ──
        if not r.online:
            ui.label("⚠ OFFLINE — /pose 없음").classes("text-xs").style("color:#e74c3c")


def dashboard_body(state: FleetState) -> None:
    """대시보드 본문: 상단 요약 줄 + 로봇 카드 그리드.

    로봇 상태는 snapshot() 사본으로 한 번만 떠서 맵뷰·카드가 **같은 순간**을 그린다
    (매번 살아있는 값을 읽으면 맵과 카드가 서로 다른 틱을 보여줄 수 있고,
     ROS 스레드와 경합해 터진다 — FleetState.snapshot() 주석 참고).
    """
    robots = state.snapshot()
    s = state.summary

    # ── 상단 요약 ──
    ui.label(
        f"🐢 Fleet 관제  —  가동 {s['online']}/{s['total']}  ·  "
        f"주행 {s['driving']}  ·  ⚠양보대기 {s['waiting']}  ·  수동 {s['manual']}  ·  "
        f"충전 {s['charging']}  ·  에러 {s['error']}  ·  백엔드: {state.source_name}"
    ).classes("text-lg font-bold mb-2")

    # ── 본문: 왼쪽 맵뷰 + 오른쪽 로봇 카드 (GUI_설계.md 배치) ──
    with ui.row().classes("w-full gap-4 items-start"):
        # 왼쪽: 웹에 그린 turtlesim 화면(거북이·궤적) + 관제 오버레이(경로·스테이션·벽)
        with ui.column().classes("gap-1"):
            mapview.map_view(state, robots)
            ui.label("🐢거북이(색=펜) · 실선=지나온 궤적 · 점선=A* 계획경로 · "
                     "▣스테이션 · 흐린사각=가상벽(진입금지) · "
                     "🔴빨간점선=충돌위험 · 🟠주황원=양보대기(안전거리)").classes(
                "text-xs").style("color:#9aa7b0; max-width:520px")
        # 오른쪽: 로봇 카드 그리드 (대수만큼 순회 — plc_study for r in snap.robots 패턴)
        with ui.column().classes("flex-1"):
            with ui.row().classes("flex-wrap gap-3"):
                for r in robots:
                    robot_card(r)

    # ── 하단: 작업 큐 현황 (생성 폼은 페이지에서 별도 렌더 — tasks.py 공부포인트 참고) ──
    tasks.task_queue(state)
