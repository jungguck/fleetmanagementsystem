"""FMS 관제 — 2D 격자 경로계획 (A*)
═══════════════════════════════════════════════════════════════════════
[목적] 거북이를 목표까지 '직선'이 아니라 '벽을 피해' 보내기 위한 최소 내비게이션.
       nav2 없이 turtlesim 평면(0~11.09) 위에서 nav2 의 경로계획 역할을 대신한다.
       ⚠ turtlesim 엔 실제 장애물이 없다 → 여기서 피하는 벽은 config 의 '가상 진입금지 구역'.
         (실물이 없어도, 관제가 경로로 피해가게 만드는 것 = nav2 costmap 의 역할)

[동작]
  1. 월드를 res(단위/셀) 격자로 나눠 점유맵(blocked)을 만든다.
  2. 벽(사각형)에 겹치는 셀 = 막힘. 로봇 반경만큼 inflate(팽창)해 벽에 붙지 않게.
  3. A* (8방향) 로 시작셀→목표셀 최단경로 → 월드 좌표 웨이포인트 리스트 반환.
  4. 일직선 구간은 합쳐(zigzag 제거) 자연스러운 경로로.

[왜 격자 A*]
  창고형 평면 + 소수 장애물엔 격자 A* 가 단순·충분·빠르다(11x11 을 0.2 격자 = 약 3천 셀,
  즉시 계산). 결과 웨이포인트는 RobotState.path 에 들어가고, 백엔드 제어루프가 추종한다.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import heapq
import math

# 8방향 이웃 (dcol, drow, 이동비용)
_NEI = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
        (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142)]


class GridPlanner:
    def __init__(self, world: tuple[float, float, float, float],
                 walls: list[dict], res: float = 0.2, inflate: int = 1):
        self.xmin, self.ymin, self.xmax, self.ymax = world
        self.res = res
        self.ncols = max(1, int(math.ceil((self.xmax - self.xmin) / res)))
        self.nrows = max(1, int(math.ceil((self.ymax - self.ymin) / res)))

        # 1) 벽 사각형 → 막힌 셀
        raw = [[False] * self.ncols for _ in range(self.nrows)]
        for w in walls:
            self._mark_rect(raw, float(w["x"]), float(w["y"]),
                            float(w["w"]), float(w["h"]))

        # 2) inflate: 막힌 셀 주변 inflate칸도 막음(로봇 반경 여유 → 벽에 안 붙음)
        self.blocked = [[False] * self.ncols for _ in range(self.nrows)]
        for r in range(self.nrows):
            for c in range(self.ncols):
                if raw[r][c]:
                    for dr in range(-inflate, inflate + 1):
                        for dc in range(-inflate, inflate + 1):
                            rr, cc = r + dr, c + dc
                            if 0 <= rr < self.nrows and 0 <= cc < self.ncols:
                                self.blocked[rr][cc] = True

    # ── 월드 사각형을 격자에 막힘으로 표시 ──
    def _mark_rect(self, grid, x, y, w, h) -> None:
        c0, r0 = self._cell(x, y)
        c1, r1 = self._cell(x + w, y + h)
        for r in range(min(r0, r1), max(r0, r1) + 1):
            for c in range(min(c0, c1), max(c0, c1) + 1):
                if 0 <= r < self.nrows and 0 <= c < self.ncols:
                    grid[r][c] = True

    # ── 좌표 ↔ 셀 ──
    def _cell(self, x: float, y: float) -> tuple[int, int]:
        c = int((x - self.xmin) / self.res)
        r = int((y - self.ymin) / self.res)
        return (min(max(c, 0), self.ncols - 1), min(max(r, 0), self.nrows - 1))

    def _center(self, c: int, r: int) -> tuple[float, float]:
        return (self.xmin + (c + 0.5) * self.res, self.ymin + (r + 0.5) * self.res)

    def _free(self, c: int, r: int) -> bool:
        return 0 <= c < self.ncols and 0 <= r < self.nrows and not self.blocked[r][c]

    def _nearest_free(self, c: int, r: int) -> tuple[int, int]:
        """막힌 셀이면 가장 가까운 빈 셀로 스냅(스테이션이 벽 옆이어도 안전)."""
        if self._free(c, r):
            return (c, r)
        for rad in range(1, max(self.ncols, self.nrows)):
            for dr in range(-rad, rad + 1):
                for dc in range(-rad, rad + 1):
                    if max(abs(dr), abs(dc)) != rad:   # 링(테두리)만 검사
                        continue
                    if self._free(c + dc, r + dr):
                        return (c + dc, r + dr)
        return (c, r)

    # ── A* : (x,y) 시작 → (x,y) 목표 → 월드 웨이포인트 리스트 ──
    def plan(self, start: tuple[float, float],
             goal: tuple[float, float],
             avoid: list[tuple[float, float]] | None = None,
             avoid_radius: float = 0.55
             ) -> list[tuple[float, float]]:
        """경로 웨이포인트. **경로가 없으면 빈 리스트** — 호출자가 목표를 거부해야 한다.
        (예전엔 직선 폴백을 돌려줬는데, 그러면 '벽을 뚫고 가는 경로'를 정상 경로인 척
         내주게 된다. 못 가면 못 간다고 말하는 게 맞다.)

        avoid: 임시 동적 장애물(다른 로봇 등)의 월드 좌표 [(x,y),…]. 그 주변 셀을 이 호출
          동안만 막아 '피해가는' 경로를 만든다(정적 self.blocked 는 안 건드림 → 다음 호출엔 무효).
          정면대향(head-on) 교통관제 우회에 쓴다.
        """
        # 동적 장애물 → 이 호출에서만 막을 셀 집합(정적 벽과 별개, self.blocked 불변).
        dyn: set[tuple[int, int]] = set()
        if avoid:
            rad = max(2, int(round(avoid_radius / self.res)))   # 로봇 회피 반경(셀)
            for (ax, ay) in avoid:
                ac, ar = self._cell(ax, ay)
                for dr in range(-rad, rad + 1):
                    for dc in range(-rad, rad + 1):
                        if dc * dc + dr * dr <= rad * rad:  # 원형으로 막기
                            dyn.add((ac + dc, ar + dr))

        def free(c: int, r: int) -> bool:                  # 정적 벽 + 동적 장애물 둘 다 통과 가능해야 free
            return self._free(c, r) and (c, r) not in dyn

        s = self._nearest_free(*self._cell(*start))
        g = self._nearest_free(*self._cell(*goal))
        # 목표가 벽 안이면 _nearest_free 가 바깥으로 스냅한다 → 마지막에 '진짜 목표'를
        # 덧붙이면 결국 벽으로 직진하게 되므로, 그 경우엔 스냅된 지점까지만 간다.
        goal_free = self._free(*self._cell(*goal))
        if s == g:
            return [goal] if goal_free else [self._center(*g)]

        openq: list = [(0.0, s)]
        came: dict = {}
        gscore = {s: 0.0}
        gc, gr = g
        while openq:
            _, cur = heapq.heappop(openq)
            if cur == g:
                break
            cc, cr = cur
            for dc, dr, cost in _NEI:
                nc, nr = cc + dc, cr + dr
                if not free(nc, nr):
                    continue
                # 대각선이 벽 모서리를 자르지 않게: 양옆 셀 하나라도 막히면 금지
                if dc != 0 and dr != 0 and (not free(cc + dc, cr) or
                                            not free(cc, cr + dr)):
                    continue
                ng = gscore[cur] + cost
                nxt = (nc, nr)
                if ng < gscore.get(nxt, math.inf):
                    gscore[nxt] = ng
                    came[nxt] = cur
                    h = math.hypot(nc - gc, nr - gr)   # 유클리드 휴리스틱
                    heapq.heappush(openq, (ng + h, nxt))

        if g not in came:
            return []                        # 도달 불가 — 벽으로 완전히 갇힌 목표

        # 셀 경로 복원 → 월드 좌표
        #   came[칸] 은 '그 칸의 직전 칸'(뒤를 가리키는 화살표)만 저장한다.
        #   확실히 아는 건 '목표(g)에 닿았다'는 것뿐이라, g 부터 came 를 계속 따라가
        #   시작(s)까지 되짚는다. 그래서 목록은 [목표 … 시작] 순(거꾸로)으로 만들어진다.
        #   ('다음 칸'은 목표에 닿기 전엔 알 수 없어서 앞으로는 못 쌓는다.)
        cells = [g]
        while cells[-1] != s:
            cells.append(came[cells[-1]])
        # 로봇은 시작→목표로 가야 하므로 뒤집어 [시작 … 목표] 순으로 바꾼다.
        cells.reverse()
        pts = [self._center(c, r) for (c, r) in cells]
        pts = self._simplify(pts)
        if goal_free:
            pts.append(goal)                 # 마지막은 실제 목표(스테이션 정중앙)
        return pts

    # ── 일직선 구간 합치기(zigzag 제거) ──
    @staticmethod
    def _simplify(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(pts) <= 2:
            return pts
        out = [pts[0]]
        for i in range(1, len(pts) - 1):
            ax, ay = out[-1]
            bx, by = pts[i]
            cx, cy = pts[i + 1]
            # (a→b) 와 (b→c) 방향이 같으면 b 생략(외적 ≈ 0)
            cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
            if abs(cross) > 1e-6:
                out.append(pts[i])
        out.append(pts[-1])
        return out
