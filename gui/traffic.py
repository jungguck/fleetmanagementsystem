"""FMS 관제 — 교통관제 (충돌 감지 + 양보)
═══════════════════════════════════════════════════════════════════════
[목적] 거북이끼리 부딪히지 않게 한다. 실제 AMR/AGV 관제의 최난제.
       "두 대가 같은 교차로로 동시에 들어오면 누가 서고 누가 가나?"

[규칙 — 단순하지만 교착이 없다]
  1. 움직이는 두 로봇의 거리가 safe_dist 안으로 들어오면 = 충돌 위험.
  2. **우선순위가 낮은 쪽이 선다**(양보). 우선순위 = config 에 적힌 순서(prio).
  3. 단, 양보 대상이 상대를 향해 '다가가는 중' 일 때만 세운다.
     이미 멀어지는 중이면 세울 이유가 없다(세우면 오히려 길을 막는다).
  4. 위험이 풀리면 멈춰 있던 로봇이 알아서 재개한다(경로는 그대로 들고 있다).

[왜 교착(deadlock)이 안 생기나 — 이게 핵심]
  우선순위가 **전순서(total order)** 라서 'A는 B를 기다리고 B는 A를 기다리는' 상황이
  구조적으로 불가능하다. 두 로봇 중 항상 정확히 한 쪽만 양보한다.
  (구역 예약 방식은 훨씬 유연하지만 교착 감지·해소를 따로 만들어야 한다.
   여기선 '교착이 생길 수 없는 규칙'을 골라서 그 문제를 아예 없앴다.)

[한계 — 정직하게]
  · 서 있는(idle) 로봇은 장애물로 치지 않는다. 치면 그 앞의 로봇이 영원히 못 간다
    (비켜줄 방법이 없으므로). 실제로 피해 가려면 동적 장애물 회피(재계획)가 필요 — 미구현.
  · turtlesim 은 거북이끼리 물리 충돌이 없다. 양보를 안 하면 그냥 겹쳐 지나간다.
    즉 이 모듈은 '충돌 방지'라기보다 **'관제가 교통을 정리한다'** 를 보여주는 것이다.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import math

from gui.models import RobotState

# 양보 판정에 쓰는 상태들: 실제로 길 위에 있는 로봇만 서로를 신경 쓴다.
_ON_ROAD = ("driving", "waiting")


def _approaching(r: RobotState, other: RobotState) -> bool:
    """r 이 other 쪽으로 다가가는 중인가.

    r 의 진행방향 단위벡터 (cos yaw, sin yaw) 와 'r→other' 벡터의 내적 > 0 이면
    상대가 내 앞쪽에 있다는 뜻 = 다가가는 중.
    """
    return (math.cos(r.yaw) * (other.x - r.x) +
            math.sin(r.yaw) * (other.y - r.y)) > 0


def yielders(robots: list[RobotState], safe_dist: float) -> set[str]:
    """지금 양보(정지)해야 하는 로봇 id 집합. 20Hz 제어루프가 매 틱 호출한다.

    로봇이 몇 대뿐이라 전쌍(O(N²)) 비교로 충분하다(4대 = 6쌍).
    """
    out: set[str] = set()
    active = [r for r in robots if r.state in _ON_ROAD and r.online]

    for i, a in enumerate(active):
        for b in active[i + 1:]:
            if math.hypot(a.x - b.x, a.y - b.y) >= safe_dist:
                continue                      # 충분히 멀다 — 신경 안 씀
            # 우선순위 낮은 쪽(prio 큰 쪽)이 양보. 동률이면 id 로 결정(결정론적).
            if (a.prio, a.id) < (b.prio, b.id):
                lo, hi = a, b                 # lo = 우선, hi = 양보
            else:
                lo, hi = b, a
            if _approaching(hi, lo):
                out.add(hi.id)
    return out


def headon_yielders(robots: list[RobotState], safe_dist: float,
                    react_dist: float | None = None) -> dict[str, tuple[float, float]]:
    """정면대향(head-on)으로 양보하는 로봇 → {yielder_id: (상대 x, 상대 y)}.

    yielders() 는 '서라'만 시키는데, 정면대향(둘이 서로 마주 보고 다가옴)에선 양보 로봇이
    서 봤자 상대 경로 위에 그대로 서 있어 상대가 못 지나간다(개발노트 §6 한계).
    → 이 경우는 '서지 말고 상대를 피해 우회(재계획)'해야 한다. 그 대상을 골라낸다.

    판정: safe_dist(기본 2배 react_dist 로 좀 더 일찍)안 + **둘 다 서로에게 다가가는 중**
      이면 정면대향. (한쪽만 다가가는 교차/추월은 기존 yielders 의 단순 정지로 충분.)
    반환 dict 의 값 = 우선순위 높은(안 서는) 상대 로봇의 현재 위치 → 재계획 시 임시 장애물.
    """
    react = react_dist if react_dist is not None else safe_dist * 3.0
    out: dict[str, tuple[float, float]] = {}
    active = [r for r in robots if r.state in _ON_ROAD and r.online]
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            if math.hypot(a.x - b.x, a.y - b.y) >= react:
                continue
            lo, hi = (a, b) if (a.prio, a.id) < (b.prio, b.id) else (b, a)  # hi=양보(우회)
            if _approaching(hi, lo) and _approaching(lo, hi):   # 둘 다 다가감 = 정면대향
                out[hi.id] = (lo.x, lo.y)
    return out


def conflicts(robots: list[RobotState], safe_dist: float) -> list[tuple[str, str]]:
    """safe_dist 안에 들어온 로봇 쌍 (맵뷰에 경고선으로 그리기 위함)."""
    out: list[tuple[str, str]] = []
    active = [r for r in robots if r.state in _ON_ROAD and r.online]
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            if math.hypot(a.x - b.x, a.y - b.y) < safe_dist:
                out.append((a.id, b.id))
    return out
