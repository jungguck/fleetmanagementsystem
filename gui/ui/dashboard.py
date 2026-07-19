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


def _chip(label: str, value, color: str) -> None:
    """요약용 상태 칩(알약). 색으로 종류를 구분해 한눈에 스캔되게."""
    with ui.element("div").style(
            f"display:flex;gap:6px;align-items:center;padding:2px 10px;"
            f"border-radius:999px;background:{color}1a;border:1px solid {color}55"):
        ui.label(label).classes("text-xs").style(f"color:{color}")
        ui.label(str(value)).classes("text-sm font-bold").style(
            f"color:{color};font-variant-numeric:tabular-nums")


def summary_bar(state: FleetState) -> None:
    """상단 요약 바 — 텍스트 한 줄 대신 색 칩으로(한눈에 파악)."""
    s = state.summary
    with ui.row().classes("items-center gap-2 w-full flex-wrap"):
        ui.label("🐢 Fleet").classes("text-base font-bold")
        _chip("가동", f"{s['online']}/{s['total']}", "#2e86de")
        _chip("주행", s["driving"], "#27ae60")
        _chip("양보", s["waiting"], "#e67e22")
        _chip("수동", s["manual"], "#8e44ad")
        _chip("충전", s["charging"], "#16a085")
        _chip("에러", s["error"], "#e74c3c")
        ui.space()
        ui.label(f"백엔드: {state.source_name}").classes("text-xs").style("color:#9aa7b0")


def robot_cards(state: FleetState) -> None:
    """로봇 상태 카드 그리드. snapshot() 사본으로 같은 순간을 그린다(경합 방지)."""
    with ui.row().classes("w-full flex-wrap gap-3"):
        for r in state.snapshot():
            robot_card(r)
