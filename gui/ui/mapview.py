"""FMS 관제 — 맵뷰 (웹에 그리는 turtlesim 화면 + 관제 오버레이)
═══════════════════════════════════════════════════════════════════════
[목적]
  turtlesim 창을 '웹에서' 보고, 그 위에 관제 정보를 겹쳐 본다.
  turtlesim 창 없이 브라우저만 열어도 되게 하는 게 목표(원격 관제).

[turtlesim 창 vs 이 화면]
  turtlesim 창 : 파란 배경 + 거북이 + 펜 궤적. 그게 전부(순수 시뮬 화면).
  이 맵뷰      : 똑같이 그리고 + 관제가 아는 것을 겹친다 —
                 · A* 계획 경로(점선)  ← 어디로 갈 계획인지
                 · 스테이션(픽업/드롭/충전) 마커
                 · 가상벽(진입금지 구역)   ← turtlesim 엔 없는 개념
                 · 상태색 링(대기/주행/수동/충전)
  → 같은 좌표계(0~11.09)를 쓰므로 두 화면의 거북이 위치는 항상 일치한다.

[어떻게 같은 그림이 되나]
  거북이 위치는 /turtleN/pose 실측값, 궤적은 그 pose 를 쌓은 것(RobotState.trail),
  궤적 색은 turtlesim 의 펜 색(set_pen)과 같은 r.pen 을 쓴다 → 색·자취가 일치.

[핵심 개념 — 좌표 변환]
  pose·벽은 '월드 좌표(0~11.09)'다. 화면은 '픽셀'이다. 그래서 변환이 필요:
     px = (x - xmin) / (xmax - xmin) * 화면폭
  화면 y축은 아래로 +, 월드 y축은 위로 + 라서 y 는 뒤집는다.
  월드 범위(window)는 config.world 에서 오고 state.world 로 전달된다(맵뷰·플래너 공유).

[왜 SVG]
  좌표 도형(원·선·사각)을 가볍게 그리고 매 틱 통째로 다시 그리기 쉽다.
  도형 수백 개뿐이라 '전체 재생성'이 부분 업데이트보다 단순·충분.
═══════════════════════════════════════════════════════════════════════
"""
import math

from nicegui import ui

from gui import traffic
from gui.models import STATE_COLORS, TURTLESIM_BG, RobotState, rgb_hex
from gui.state import FleetState

# 화면 크기(px). turtlesim 창처럼 정사각(월드가 11.09 x 11.09 정사각이므로).
_W, _H = 520, 520

# 클릭 좌표를 받기 위한 '빈 배경'(520x520). interactive_image 의 좌표계를 이 크기로 고정한다.
#   (실제 그림은 content SVG 가 다 그린다. 이 소스는 좌표 기준용 투명 SVG 일 뿐.)
#   %3C=< %3E=> %2F=/ %22=" %3D== %20=공백 (data URI 라 URL 인코딩)
_BLANK_SRC = ('data:image/svg+xml;charset=utf-8,'
              '%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22'
              '%20width%3D%22520%22%20height%3D%22520%22%2F%3E')

# 스테이션 종류별 색
_STATION_COLOR = {"pickup": "#f39c12", "drop": "#8e44ad", "charge": "#27ae60"}


def _build_svg(state: FleetState, robots: list[RobotState]) -> str:
    """맵 SVG '문자열'만 만든다(요소 생성 X). create_map/render_map 이 이걸 쓴다.

    robots 는 `FleetState.snapshot()` 이 준 **사본**이어야 한다(살아있는 RobotState 금지).
    ROS 스레드가 20Hz 로 path/trail 을 바꾸는 중에 그리면 터진다 — snapshot() 주석 참고.
    """
    xmin, ymin, xmax, ymax = state.world

    def to_screen(x: float, y: float) -> tuple[float, float]:
        px = (x - xmin) / (xmax - xmin) * _W
        py = _H - (y - ymin) / (ymax - ymin) * _H     # y 뒤집기
        return px, py

    def scale(v: float, axis: str) -> float:
        """길이(월드) → 픽셀 길이(폭·높이 각각의 배율)."""
        return v / (xmax - xmin) * _W if axis == "x" else v / (ymax - ymin) * _H

    parts: list[str] = []

    # ── ① 배경: turtlesim 창과 같은 파란 캔버스 ──
    parts.append(f'<rect x="0" y="0" width="{_W}" height="{_H}" fill="{TURTLESIM_BG}"/>')

    # ── ② 가상벽(진입금지 구역): 반투명 — turtlesim 엔 없고 관제만 아는 것이라 흐리게 ──
    for wl in state.walls:
        wx, wy = float(wl["x"]), float(wl["y"])
        ww, wh = float(wl["w"]), float(wl["h"])
        sx, sy = to_screen(wx, wy + wh)               # 좌상단 = 월드 (x, y+h)
        parts.append(
            f'<rect x="{sx:.1f}" y="{sy:.1f}" width="{scale(ww,"x"):.1f}" '
            f'height="{scale(wh,"y"):.1f}" fill="#ffffff" fill-opacity="0.22" '
            f'stroke="#ffffff" stroke-opacity="0.5" stroke-dasharray="4 3" rx="2"/>')

    # ── ③ 펜 궤적: turtlesim 이 창에 그리는 그 자취를 웹에서 재현 ──
    for r in robots:
        trail = list(r.trail)                          # ROS 스레드가 append 중 → 스냅샷
        if len(trail) < 2:
            continue
        poly = " ".join(f"{x:.1f},{y:.1f}" for (x, y) in
                        (to_screen(tx, ty) for (tx, ty) in trail))
        parts.append(
            f'<polyline points="{poly}" fill="none" stroke="{rgb_hex(r.pen)}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')

    # ── ④ 스테이션 마커 (사각 + 이름) — 관제 오버레이 ──
    for st in state.stations:
        sx, sy = to_screen(st["x"], st["y"])
        c = _STATION_COLOR.get(st.get("kind"), "#7f8c8d")
        parts.append(
            f'<rect x="{sx-7:.1f}" y="{sy-7:.1f}" width="14" height="14" rx="3" '
            f'fill="{c}" stroke="#fff" stroke-width="1.5"/>')
        # 이름은 마커 '아래'에 — 거북이 이름표(마커 위)와 자리를 나눠 겹치지 않게.
        parts.append(
            f'<text x="{sx:.1f}" y="{sy+20:.1f}" font-size="11" font-weight="bold" '
            f'fill="#fff" text-anchor="middle">{st["name"]}</text>')

    # ── ⑤ A* 계획 경로(남은 웨이포인트): 상태색 점선 — turtlesim 창엔 없는 정보 ──
    for r in robots:
        if not r.path:
            continue
        color = STATE_COLORS.get(r.state, "#9aa7b0")
        pts = [to_screen(r.x, r.y)] + [to_screen(px, py) for (px, py) in r.path]
        poly = " ".join(f"{x:.1f},{y:.1f}" for (x, y) in pts)
        parts.append(
            f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-dasharray="5 4" opacity="0.9"/>')
        # 목표 지점 표식
        gx, gy = to_screen(*r.path[-1])
        parts.append(f'<circle cx="{gx:.1f}" cy="{gy:.1f}" r="4" fill="none" '
                     f'stroke="{color}" stroke-width="2"/>')

    # ── ⑥ 교통관제: 충돌 위험 쌍을 빨간 선으로 + 양보 중인 로봇에 안전거리 원 ──
    #    "관제가 지금 무엇을 보고 세웠는지"가 보여야 한다(안 보이면 그냥 멈춘 걸로 오해).
    pos = {r.id: r for r in robots}
    for a_id, b_id in traffic.conflicts(robots, state.safe_dist):
        ax, ay = to_screen(pos[a_id].x, pos[a_id].y)
        bx, by = to_screen(pos[b_id].x, pos[b_id].y)
        parts.append(
            f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" '
            f'stroke="#e74c3c" stroke-width="2" stroke-dasharray="3 3" opacity="0.9"/>')
    for r in robots:
        if r.state != "waiting":
            continue
        cx, cy = to_screen(r.x, r.y)
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{scale(state.safe_dist,"x"):.1f}" '
            f'fill="#e67e22" fill-opacity="0.12" stroke="#e67e22" '
            f'stroke-dasharray="3 3" stroke-width="1.5"/>')

    # ── ⑦ 거북이 (+ '맵 클릭 명령 대상' 로봇 하이라이트) ──
    for r in robots:
        px, py = to_screen(r.x, r.y)
        if r.id == state.selected_id:                 # 클릭 명령 대상 → 흰 점선 링으로 표시
            parts.append(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="18" fill="none" '
                f'stroke="#ffffff" stroke-width="2" stroke-dasharray="3 3" opacity="0.9"/>')
        parts.append(_turtle_svg(r, px, py))

    return "".join(parts)


def create_map(state: FleetState):
    """맵을 '한 번만' 만든다(고정 요소). 반환한 img 를 render_map 으로 갱신한다.

    ⚠ 깜빡임 방지 핵심: 예전엔 매 0.5초 dash.refresh 가 이 요소를 통째로 재생성해서
    <img> 가 매번 새로 로드 → 깜빡였다. 이제 요소는 그대로 두고 render_map 이
    content(SVG 문자열)만 교체한다 → 재생성 없음 → 깜빡임 없음.

    클릭: ui.interactive_image 는 클릭 시 e.image_x/image_y(이미지 좌표 0~520)를 준다.
    _on_map_click 에서 월드 좌표(0~11.09)로 역변환해 send_goal 한다.
    """
    return ui.interactive_image(
        _BLANK_SRC, content=_build_svg(state, state.snapshot()), size=(_W, _H),
        on_mouse=lambda e: _on_map_click(state, e),
        events=["mousedown"], cross=True,
        sanitize=False,          # content 는 서버가 만든 신뢰된 SVG → 정제로 도형 안 깎이게
    ).style("border-radius:6px; cursor:crosshair")


def render_map(state: FleetState, img) -> None:
    """매 틱 호출: 요소는 그대로, SVG 내용만 교체(재생성 X → 깜빡임 없음)."""
    img.set_content(_build_svg(state, state.snapshot()))


def _on_map_click(state: FleetState, e) -> None:
    """맵 클릭 → 클릭 지점(월드 좌표)으로 '명령 대상 로봇'을 A* 주행시킨다.
    실패하면 '왜' 안 갔는지 알린다(조용히 무시하면 고장으로 보인다)."""
    xmin, ymin, xmax, ymax = state.world
    # 역변환: 픽셀(0~520) → 월드(0~11.09). 화면 y 는 뒤집혀 있으니 (H - image_y).
    wx = xmin + (e.image_x / _W) * (xmax - xmin)
    wy = ymin + ((_H - e.image_y) / _H) * (ymax - ymin)
    rid = state.selected_id
    if not rid:
        ui.notify("먼저 조작 패널에서 '맵 클릭 대상' 로봇을 고르세요",
                  type="warning", position="top")
        return
    if state.send_goal(rid, wx, wy, label=f"→맵({wx:.1f},{wy:.1f})"):
        ui.notify(f"{rid} → ({wx:.1f}, {wy:.1f})", type="positive", position="top")
    elif state.estopped:
        ui.notify("E-STOP 상태입니다 — [해제] 후 조작하세요", type="warning", position="top")
    else:
        ui.notify("그 지점으로 가는 경로가 없습니다 (벽/도달 불가)",
                  type="negative", position="top")


def _turtle_svg(r: RobotState, px: float, py: float) -> str:
    """거북이 한 마리 (등껍질·머리·발 + 상태색 링 + 이름).

    회전: 월드 yaw 는 반시계(+), 화면 y 는 뒤집혀 있으니 그리기 각도는 -yaw.
    SVG rotate 는 도(degree) 단위 & 시계방향(+) 이라 -yaw[rad] → degree 변환.
    """
    deg = -math.degrees(r.yaw)
    body = rgb_hex(r.pen)                              # 펜 색 = 그 거북이 색
    ring = STATE_COLORS.get(r.state, "#9aa7b0")        # 상태색 링(대기/주행/수동/충전)
    dim = "" if r.online else ' opacity="0.35"'        # 통신 끊기면 흐리게

    return (
        f'<g transform="translate({px:.1f},{py:.1f}) rotate({deg:.1f})"{dim}>'
        # 상태색 링 — 이 거북이가 지금 무슨 상태인지 한눈에
        f'<circle r="13" fill="none" stroke="{ring}" stroke-width="2.5"/>'
        # 발 4개
        f'<circle cx="-5" cy="-7" r="3" fill="{body}"/>'
        f'<circle cx="-5" cy="7" r="3" fill="{body}"/>'
        f'<circle cx="5" cy="-7" r="3" fill="{body}"/>'
        f'<circle cx="5" cy="7" r="3" fill="{body}"/>'
        # 등껍질
        f'<circle r="8" fill="{body}" stroke="#ffffff" stroke-width="1.5"/>'
        f'<circle r="3.5" fill="#ffffff" fill-opacity="0.35"/>'
        # 머리 (진행 방향 = +x 쪽)
        f'<circle cx="10" cy="0" r="3.5" fill="{body}" stroke="#fff" stroke-width="1"/>'
        f'</g>'
        # 이름표: 회전 밖(항상 수평) · 거북이 '위'(스테이션 이름은 아래라 안 겹침).
        #   배경 알약을 깔아 궤적/벽 위에서도 읽히게 — 글자 외곽선(paint-order)은
        #   렌더러에 따라 무시돼 글자가 뭉개지므로 쓰지 않는다.
        f'<rect x="{px-15:.1f}" y="{py-27:.1f}" width="30" height="14" rx="7" '
        f'fill="#000000" fill-opacity="0.45"/>'
        f'<text x="{px:.1f}" y="{py-17:.1f}" font-size="10" font-weight="bold" '
        f'fill="#ffffff" text-anchor="middle">{r.name}</text>'
    )
