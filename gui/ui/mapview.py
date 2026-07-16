"""FMS 관제 — 맵뷰 (2D 평면도)
═══════════════════════════════════════════════════════════════════════
[목적]
  로봇(지게차)들이 지금 맵 어디에 있는지 + 스테이션(픽업/드롭/충전) 위치를
  한눈에 보는 화면. plc_study 엔 없던 신규 — '이동 로봇 fleet'의 핵심 화면이다.

[핵심 개념 — 좌표 변환]
  로봇 pose 는 '월드 좌표(미터)'다 (nav2/odom 기준, 예: x=3.2m, y=1.5m).
  화면은 '픽셀'이다. 그래서 월드(m) → 화면(px) 변환이 필요하다:
     px = (x - xmin) / (xmax - xmin) * 화면폭
  그리고 화면 y축은 아래로 +, 월드 y축은 위로 + 라서 y 는 뒤집는다.

[왜 SVG 인가]
  좌표 기반 도형(원·선·사각)을 가볍게 그리고, 매 틱 통째로 다시 그리기 쉽다.
  외부 지도 타일(Leaflet 등) 불필요 — 창고 평면도엔 이게 단순·적합.

[지금은 골격]
  - 배경은 빈 사각(맵 테두리)만. 실제 SLAM 맵(pgm) 오버레이는 P1+ TODO.
  - _WORLD 범위는 예시값 → 실제 맵 bounds 로 확인 필요.
═══════════════════════════════════════════════════════════════════════
"""
import math

from nicegui import ui

from gui.state import STATE_COLORS, FleetState

# 화면 크기(px)
_W, _H = 520, 400
# 맵이 커버하는 월드 범위 (xmin, ymin, xmax, ymax) [m]  ⚠ 확인필요: 실제 맵 기준
_WORLD = (-1.0, -1.0, 6.0, 5.0)

# 스테이션 종류별 색
_STATION_COLOR = {"pickup": "#f39c12", "drop": "#8e44ad", "charge": "#27ae60"}


def _to_screen(x: float, y: float) -> tuple[float, float]:
    """월드 좌표(m) → 화면 픽셀. y축은 화면(아래로 +)에 맞춰 뒤집는다."""
    xmin, ymin, xmax, ymax = _WORLD
    px = (x - xmin) / (xmax - xmin) * _W
    py = _H - (y - ymin) / (ymax - ymin) * _H   # y 뒤집기
    return px, py


def map_view(state: FleetState) -> None:
    """로봇 위치 + 스테이션을 SVG 로 그린다(매 refresh 마다 재생성)."""
    parts: list[str] = []

    # ── 배경: 맵 영역 테두리 (P1+ 에 실 맵 이미지로 교체) ──
    parts.append(
        f'<rect x="0" y="0" width="{_W}" height="{_H}" fill="#f4f6f8" stroke="#dde3ea"/>')

    # ── 스테이션 마커 (사각 + 이름) ──
    for st in state.stations:
        sx, sy = _to_screen(st["x"], st["y"])
        c = _STATION_COLOR.get(st.get("kind"), "#7f8c8d")
        parts.append(
            f'<rect x="{sx-7:.1f}" y="{sy-7:.1f}" width="14" height="14" rx="3" fill="{c}"/>')
        parts.append(
            f'<text x="{sx+10:.1f}" y="{sy+4:.1f}" font-size="11" fill="#2c3e50">{st["name"]}</text>')

    # ── 로봇: 상태색 원 + 방향선(yaw) + 이름 ──
    for r in state.robots:
        rx, ry = _to_screen(r.x, r.y)
        color = STATE_COLORS.get(r.state, "#9aa7b0")
        # 방향선: yaw 방향으로 짧은 선. 화면 y가 뒤집혔으니 sin 부호도 반전(-yaw).
        hx = rx + 14 * math.cos(-r.yaw)
        hy = ry + 14 * math.sin(-r.yaw)
        parts.append(
            f'<line x1="{rx:.1f}" y1="{ry:.1f}" x2="{hx:.1f}" y2="{hy:.1f}" '
            f'stroke="{color}" stroke-width="2"/>')
        parts.append(
            f'<circle cx="{rx:.1f}" cy="{ry:.1f}" r="9" fill="{color}" '
            f'stroke="#fff" stroke-width="2"/>')
        parts.append(
            f'<text x="{rx+11:.1f}" y="{ry-8:.1f}" font-size="11" font-weight="bold" '
            f'fill="#2c3e50">{r.name}</text>')

    ui.html(f'<svg width="{_W}" height="{_H}">{"".join(parts)}</svg>')
