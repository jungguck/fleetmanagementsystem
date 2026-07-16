"""FMS 관제 — 작업(Task) 패널
═══════════════════════════════════════════════════════════════════════
[목적]
  운영자가 "픽업 A → 드롭 B" 배송 작업을 만들고, 큐/배차 현황을 본다.

[⚠ 중요 공부 포인트 — 폼은 '자동갱신 영역 밖'에 둬야 한다]
  대시보드는 매 0.5초 dash.refresh() 로 통째로 다시 그린다.
  만약 '작업 생성 폼(select·버튼)'을 그 안에 두면, 매 0.5초마다 폼이
  다시 그려져서 운영자가 고르던 select 값이 리셋된다(사용 불가).
  → 그래서:
     - create_form() = 페이지에서 '한 번만' 렌더 (main.py, refresh 밖)
     - task_queue()  = refresh 영역(dashboard_body) 안 (읽기 전용이라 매번 다시 그려도 OK)
  (plc_study 에서 reject_panel 폼을 refreshable 밖에 둔 것과 같은 이유.)
═══════════════════════════════════════════════════════════════════════
"""
from nicegui import ui

from gui.state import FleetState

# 작업 상태 색
_TASK_STATE_COLOR = {"pending": "#9aa7b0", "running": "#2e86de", "done": "#27ae60"}


def create_form(state: FleetState) -> None:
    """작업 생성 폼 — 페이지에서 '한 번만' 렌더(자동갱신 영역 밖)."""
    names = [s["name"] for s in state.stations]   # 스테이션 이름(픽업/드롭 선택지)

    with ui.card().classes("w-full"):
        ui.label("➕ 작업 생성").classes("text-base font-bold")
        with ui.row().classes("items-center gap-2"):
            pickup = ui.select(names, label="픽업",
                               value=names[0] if names else None)
            ui.label("→")
            drop = ui.select(names, label="드롭",
                             value=names[1] if len(names) > 1 else None)

            def _add() -> None:
                # 픽업/드롭이 서로 다를 때만 큐에 추가
                if pickup.value and drop.value and pickup.value != drop.value:
                    state.add_task(pickup.value, drop.value)
                    ui.notify(f"작업 추가: {pickup.value} → {drop.value}",
                              type="positive", position="top")
                else:
                    ui.notify("픽업/드롭을 서로 다르게 고르세요", type="warning")

            ui.button("추가", on_click=_add).props("color=primary")


def task_queue(state: FleetState) -> None:
    """작업 큐 현황 — refresh 영역(dashboard_body) 안. 읽기 전용이라 매 틱 재생성 OK."""
    with ui.card().classes("w-full"):
        pend = sum(1 for t in state.tasks if t.state == "pending")
        run = sum(1 for t in state.tasks if t.state == "running")
        done = sum(1 for t in state.tasks if t.state == "done")
        ui.label(f"📋 작업 큐  —  대기 {pend} · 수행 {run} · 완료 {done}").classes(
            "text-base font-bold")

        # 최근 작업부터 최대 8개 표시
        for t in list(reversed(state.tasks))[:8]:
            c = _TASK_STATE_COLOR.get(t.state, "#9aa7b0")
            with ui.row().classes("items-center gap-2 text-sm"):
                ui.label(f"#{t.id}").classes("font-mono")
                ui.label(f"{t.pickup} → {t.drop}")
                ui.label(t.state).style(f"color:{c};font-weight:600")
                ui.label(f"[{t.robot or '-'}]").classes("text-xs")   # 배차 로봇
        if not state.tasks:
            ui.label("작업 없음 — 위 폼에서 생성").classes("text-xs").style("color:#9aa7b0")
