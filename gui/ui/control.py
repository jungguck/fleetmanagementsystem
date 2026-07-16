"""FMS 관제 — 로봇별 목적지 제어 패널
═══════════════════════════════════════════════════════════════════════
[목적] 마스터 모델 그대로: 운영자가 '로봇마다 목적지를 직접 지정'.
       예) 1번→A, 2번→B, 3번→C, 4번→D.
       버튼을 누르면 state.send_to_station() → (ros면 nav2 목표, mock이면 그쪽 이동).
       ※ teleop(조이스틱 운전) 아님 — '목적지 명령' 이라 "수동 안 함"과도 일치.

[자동배차(tasks.py)와 차이]
  - control_panel(여기): 운영자가 '로봇도, 목적지도' 직접 고름 (마스터 모델).
  - tasks.create_form: A→B 작업만 만들면 시스템이 로봇을 고름(자동배차, 대안).

[⚠ 폼은 자동갱신 밖]
  select(목적지)를 가진 입력 위젯이라, 매 0.5초 다시 그려지면 선택값이 리셋됨.
  → main.py 에서 '한 번만' 렌더(refresh 밖). tasks.create_form 과 동일 원칙.
═══════════════════════════════════════════════════════════════════════
"""
from nicegui import ui

from gui.state import FleetState


def control_panel(state: FleetState) -> None:
    """로봇마다 [이름] [목적지 select] [이동] — 페이지에서 한 번만 렌더."""
    names = [s["name"] for s in state.stations]   # 목적지 선택지(스테이션)

    with ui.card().classes("w-full"):
        ui.label("🎯 로봇 목적지 지정 (운영자 직접)").classes("text-base font-bold")
        ui.label("각 로봇을 스테이션으로 보냅니다 (예: 1번→A). nav2 목표 전송.").classes(
            "text-xs").style("color:#9aa7b0")

        for r in state.robots:
            with ui.row().classes("items-center gap-2"):
                ui.label(r.name).classes("w-16 font-bold")
                dest = ui.select(names, value=names[0] if names else None).props("dense")
                # 버튼 클릭 → 선택 목적지로 이 로봇 전송.
                #   루프 클로저 함정 회피: rid·d 를 기본인자로 '지금 값' 캡처.
                #   d.value 는 클릭 시점의 select 값을 읽는다.
                ui.button(
                    "이동",
                    on_click=lambda rid=r.id, d=dest: (
                        state.send_to_station(rid, d.value),
                        ui.notify(f"{rid} → {d.value}", type="positive", position="top"),
                    ),
                ).props("dense color=primary")
