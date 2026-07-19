"""FMS 관제 — 로봇 조작 패널 (목적지 지정 + 수동 teleop)
═══════════════════════════════════════════════════════════════════════
[목적] 운영자가 거북이 4마리를 웹에서 직접 조작한다. 두 가지 방식:
  ① 목적지 지정 (자동주행) : 스테이션 고르고 [이동] → A* 경로 → 거북이가 알아서 감.
     예) 1번→PICK-A, 2번→DROP-B … (마스터 모델: 로봇도 목적지도 운영자가 고름)
  ② 수동 teleop            : ▲◀▶▼ 버튼 → /turtleN/cmd_vel 직발행.
     누르면 TELEOP_HOLD(1초) 동안 움직이고 자동 정지(연타로 계속 이동).
     수동을 쓰면 자동 목표(path)는 취소된다 — 수동 override 가 우선.

[자동배차(tasks.py)와 차이]
  - control_panel(여기): 운영자가 '로봇도, 목적지도' 직접 고름.
  - tasks.create_form  : A→B 작업만 만들면 시스템이 로봇을 고름(자동배차).

[⚠ 폼은 자동갱신 밖]
  select(목적지)를 가진 입력 위젯이라, 매 0.5초 다시 그려지면 선택값이 리셋됨.
  → main.py 에서 '한 번만' 렌더(refresh 밖). tasks.create_form 과 동일 원칙.
═══════════════════════════════════════════════════════════════════════
"""
from nicegui import ui

from gui.state import FleetState

# teleop 속도 — turtlesim 기준 (linear.x [단위/s], angular.z [rad/s])
_LIN, _ANG = 2.0, 1.5


def control_panel(state: FleetState) -> None:
    """로봇마다 [이름] [목적지▾] [이동] [▲◀▶▼] [정지] — 페이지에서 한 번만 렌더."""
    names = [s["name"] for s in state.stations]   # 목적지 선택지(스테이션)

    with ui.card().classes("w-full"):
        with ui.row().classes("items-center justify-between w-full"):
            ui.label("🎯 로봇 조작 (목적지 지정 · 수동 teleop)").classes("text-base font-bold")
            with ui.row().classes("items-center gap-2"):
                # 궤적 청소 — turtlesim 의 /clear 처럼 화면의 펜 자취를 지운다.
                ui.button("궤적 지우기", on_click=state.clear_trails).props("dense flat")
                # 해제(RESET): E-STOP 래치를 푼다. 걸려 있을 때만 보인다.
                #   bind_visibility_from = state.estopped 를 계속 지켜보다 자동 표시/숨김.
                ui.button("🔓 해제(RESET)", on_click=lambda: (
                    state.reset(),
                    ui.notify("E-STOP 해제 — 조작 가능", type="positive", position="top"),
                )).props("dense color=amber").bind_visibility_from(state, "estopped")
                # E-STOP: 전 로봇 즉시 정지 + 작업 취소 + 래치(해제 전까지 아무것도 안 움직임).
                ui.button("🟥 E-STOP", on_click=lambda: (
                    state.stop_all(),
                    ui.notify("E-STOP — 전 로봇 정지, 작업 취소. [해제] 눌러야 재개",
                              type="negative", position="top"),
                )).props("dense color=red")

        ui.label("목적지 [이동]=자동주행(A* 경로) · ▲◀▶▼=수동(cmd_vel 직발행, 1초씩)").classes(
            "text-xs").style("color:#9aa7b0")
        # (맵 클릭 대상 로봇 선택기는 맵 바로 위로 옮김 — main.py index() 참고)

        for r in state.robots:
            with ui.row().classes("items-center gap-2"):
                ui.label(r.name).classes("w-14 font-bold")

                # ── ① 목적지 지정(자동주행) ──
                dest = ui.select(names, value=names[0] if names else None).props("dense")
                # 루프 클로저 함정 회피: rid·d 를 기본인자로 '지금 값' 캡처.
                #   d.value 는 클릭 시점의 select 값을 읽는다.
                ui.button("이동", on_click=lambda rid=r.id, d=dest: _go(state, rid, d)
                          ).props("dense color=primary")

                # ── ② 수동 teleop — (전진, 회전) 조합을 그대로 cmd_vel 로 ──
                ui.space()
                for icon, lin, ang in (("▲", _LIN, 0.0), ("◀", 0.0, _ANG),
                                       ("▶", 0.0, -_ANG), ("▼", -_LIN, 0.0)):
                    ui.button(icon, on_click=lambda rid=r.id, l=lin, a=ang:
                              _teleop(state, rid, l, a)).props("dense flat color=teal")
                # 정지는 E-STOP 중에도 허용(정지는 언제나 안전한 명령).
                ui.button("■", on_click=lambda rid=r.id: state.stop(rid)).props(
                    "dense flat color=grey")


def _go(state: FleetState, rid: str, dest) -> None:
    """[이동] 클릭. 실패하면 '왜' 안 갔는지 알려준다(조용히 무시하면 고장으로 보인다)."""
    if state.estopped:
        ui.notify("E-STOP 상태입니다 — [해제] 후 조작하세요", type="warning", position="top")
    elif state.send_to_station(rid, dest.value):
        ui.notify(f"{rid} → {dest.value}", type="positive", position="top")
    else:
        ui.notify(f"{dest.value} 로 가는 경로가 없습니다 (벽에 막힘)",
                  type="negative", position="top")


def _teleop(state: FleetState, rid: str, lin: float, ang: float) -> None:
    if not state.teleop(rid, lin, ang):
        ui.notify("E-STOP 상태입니다 — [해제] 후 조작하세요", type="warning", position="top")
