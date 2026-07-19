"""FMS 관제 — 중앙 상태 (Fleet State) = 관제 두뇌
═══════════════════════════════════════════════════════════════════════
[이 프로젝트가 뭔가]
  ROS 2 의 가장 기본 예제인 **turtlesim** 거북이 4 마리를 '지게차(AGV)' 로 보고,
  웹 화면에서 조작·관제하는 Fleet Management System.
  (TurtleBot3 / Gazebo / nav2 는 쓰지 않는다 — turtlesim_node 하나면 충분.)

[역할 분담]
  - turtlesim_source.py : 로봇 몸 (cmd_vel 발행 / pose 구독 / 20Hz 제어루프)
  - state.py (여기)     : 관제 두뇌 (경로계획 호출·배차·작업 FSM·충전복귀·집계)
  - ui/*                : 화면 (맵뷰·상태카드·조작 패널·작업큐)

[백엔드 2종 — config 의 source 한 줄로 교체]
  - turtlesim : 실제 ROS 2 turtlesim (메인). turtlesim_node 가 떠 있어야 함.
  - sim2d     : ROS 없이 도는 2D 운동학 시뮬(폴백). ROS 안 깔린 데서 UI 만 볼 때.

[설계 원칙]
  제어/수집과 화면 그리기를 분리 → 여러 브라우저가 붙어도 안전.
  로봇 상태는 ROS 스레드와 GUI 스레드가 같이 만지므로 FLEET_LOCK 으로 보호.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import replace

import yaml

from gui import traffic
from gui.models import (FLEET_LOCK, LOW_BATT, PEN_COLORS, TRAIL_MAX, RobotState,
                        Task)
from gui.planner import GridPlanner

# teleop 버튼 한 번에 얼마나 오래 움직이나 [s] (이 시간 뒤 자동 정지).
TELEOP_HOLD = 1.0

# '스테이션에 도착했다'고 인정할 거리. 제어루프의 도착판정(ARRIVE_TOL=0.15)보다 넉넉하게
# 잡아, 마지막 웨이포인트에서 조금 못 미쳐 멈춘 경우도 도착으로 본다.
ARRIVE_EPS = 0.4


# ─────────────────────────────────────────────────────────────────────
# 폴백 백엔드: 2D 운동학 시뮬 (ROS 없이 UI 를 돌려볼 때)
#   poll() 한 번 = 한 틱: 로봇을 웨이포인트로 등속 이동 + 배터리 증감.
#   turtlesim 백엔드와 인터페이스(poll/shutdown)만 같으면 된다.
# ─────────────────────────────────────────────────────────────────────
class Sim2DSource:
    LIN_SPEED = 0.35    # 단위/tick : 한 틱(poll_interval)당 이동 거리
    DRAIN_DRIVE = 0.25  # 주행 중 배터리 소모 /틱
    DRAIN_IDLE = 0.02   # 대기 중 자연 방전 /틱
    CHARGE_RATE = 2.0   # 충전 회복 /틱

    def __init__(self, robots: list[RobotState], cfg: dict | None = None):
        self.robots = robots
        self.safe_dist = float((cfg or {}).get("safe_dist", 1.0))
        for r in robots:
            r.online = True          # 가상 로봇이라 항상 연결됨

    def poll(self) -> None:
        with FLEET_LOCK:                                  # 로봇 상태를 실제로 바꾸므로
            self._poll_locked()

    def _poll_locked(self) -> None:
        now = time.monotonic()
        # turtlesim 백엔드와 같은 교통관제 규칙을 쓴다(두 백엔드 동작을 일치시킨다).
        yield_ids = traffic.yielders(self.robots, self.safe_dist)
        for r in self.robots:
            self._trail(r)                                # 궤적 기록(웹 맵뷰의 펜)
            if r.manual and now < r.manual_until:        # 수동 조작(teleop)
                lin, ang = r.manual
                r.yaw += ang * 0.5
                r.x += lin * 0.5 * math.cos(r.yaw)
                r.y += lin * 0.5 * math.sin(r.yaw)
                r.battery = max(0.0, r.battery - self.DRAIN_DRIVE)
                continue
            if r.manual:                                  # 명령 만료 → 정지
                r.manual, r.state, r.task = None, "idle", "-"
                continue

            if r.state == "charging":
                r.battery = min(100.0, r.battery + self.CHARGE_RATE)
                if r.battery >= 99.5:
                    r.state, r.task = "idle", "-"
                continue

            # 교통관제 양보: 서되 경로는 유지 → 위험이 풀리면 그대로 재개.
            if r.id in yield_ids and r.state in ("driving", "waiting") and r.path:
                r.state = "waiting"
                r.battery = max(0.0, r.battery - self.DRAIN_IDLE)
                continue

            if r.state in ("driving", "waiting") and r.path:
                r.state = "driving"                      # 양보 해제 → 재개
                wx, wy = r.path[0]                       # 다음 웨이포인트
                dx, dy = wx - r.x, wy - r.y
                dist = math.hypot(dx, dy)
                r.yaw = math.atan2(dy, dx)               # 진행 방향으로 회전
                if dist <= self.LIN_SPEED:               # 이 웨이포인트 도달
                    r.x, r.y = wx, wy
                    r.path.pop(0)
                    if not r.path:                       # 경로 끝 = 최종 도착
                        if r.goal_kind == "charge":
                            r.state, r.task = "charging", "충전중"
                        else:
                            r.state, r.task = "idle", "-"
                        r.goal_kind = ""
                else:                                    # 한 스텝 전진
                    r.x += self.LIN_SPEED * dx / dist
                    r.y += self.LIN_SPEED * dy / dist
                    r.battery = max(0.0, r.battery - self.DRAIN_DRIVE)
            else:
                r.battery = max(0.0, r.battery - self.DRAIN_IDLE)

    @staticmethod
    def _trail(r: RobotState) -> None:
        if not r.trail or math.dist(r.trail[-1], (r.x, r.y)) > 0.05:
            r.trail.append((r.x, r.y))
            if len(r.trail) > TRAIL_MAX:
                del r.trail[:-TRAIL_MAX]

    def shutdown(self) -> None:
        pass


# ─────────────────────────────────────────────────────────────────────
# Fleet 전체 상태: config 로드 + 백엔드 보유 + 배차/충전/작업 오케스트레이션
# ─────────────────────────────────────────────────────────────────────
class FleetState:
    def __init__(self, cfg_path: str):
        # 1) 설정 로드
        with open(cfg_path, encoding="utf-8") as f:
            self.cfg = yaml.safe_load(f)

        self.poll_interval = float(self.cfg.get("poll_interval_sec", 0.5))
        self.source_name = self.cfg.get("source", "turtlesim")

        # 2) config 의 robots → RobotState (초기 위치·배터리 반영)
        #    id 는 곧 turtlesim 이름 = 토픽 네임스페이스(/turtle1/cmd_vel).
        #    pen = 궤적 색. 웹 맵뷰와 turtlesim 창(set_pen)이 같은 색을 쓰게 여기서 배정.
        self.robots: list[RobotState] = [
            RobotState(
                id=r["id"], name=r.get("name", r["id"]),
                pen=PEN_COLORS[i % len(PEN_COLORS)],
                prio=i,                      # 교통관제 우선순위 = config 순서(앞선 로봇이 우선)
                x=float(r.get("x", 0.0)), y=float(r.get("y", 0.0)),
                yaw=float(r.get("theta", 0.0)),
                battery=float(r.get("battery", random.uniform(55, 100))),
            )
            for i, r in enumerate(self.cfg.get("robots", []))
        ]
        # 맵 클릭 이동 명령의 '대상 로봇'. 조작 패널의 토글로 바꾼다(기본=첫 로봇).
        self.selected_id: str | None = self.robots[0].id if self.robots else None
        self.stations = self.cfg.get("stations", [])

        # 맵: 월드 범위 + 벽(가상 진입금지 구역). 맵뷰·플래너가 공유(단일 정의처).
        w = self.cfg.get("world", {})
        self.world = (float(w.get("xmin", 0.0)), float(w.get("ymin", 0.0)),
                      float(w.get("xmax", 11.09)), float(w.get("ymax", 11.09)))
        self.walls = self.cfg.get("walls", [])
        self.planner = GridPlanner(self.world, self.walls)

        # 교통관제: 두 로봇이 이 거리 안에 들어오면 우선순위 낮은 쪽이 양보(traffic.py).
        self.safe_dist = float(self.cfg.get("safe_dist", 1.0))

        # 3) 백엔드 선택 — turtlesim(실 ROS) / sim2d(폴백).
        #    turtlesim 은 rclpy 가 필요해서 '고를 때만' import 한다
        #    (ROS 안 깔린 환경에서도 sim2d 로 UI 가 뜨게).
        #
        # [관찰 2026-07-19] '시각화' 목적만 보면 turtlesim 창은 사실 없어도 된다.
        #   웹 맵뷰(ui/mapview.py)가 이미 로봇 위치·궤적·A* 경로·스테이션·벽을 다 그리므로,
        #   sim2d 만으로 관제 로직과 화면 시연이 전부 가능하다(이번 윈도우 실행이 그 증거).
        #   turtlesim 이 의미 있는 경우는 딱 두 가지:
        #     (a) 실제 ROS 2 토픽(/turtleN/cmd_vel, /pose) 연동이 제대로 되는지 검증할 때,
        #     (b) 별도 turtlesim 창의 실시간 렌더가 따로 필요할 때.
        #   그 외 '관제 두뇌'를 만들고 보여주는 목적에는 sim2d 로 충분하다.
        if self.source_name == "turtlesim":
            from gui.turtlesim_source import TurtlesimSource
            self.source = TurtlesimSource(self.robots, self.cfg)
        else:
            self.source = Sim2DSource(self.robots, self.cfg)

        # 작업 큐 (운영자가 GUI 에서 추가)
        self.tasks: list[Task] = []
        self._task_seq = 0

        # E-STOP 래치. True 인 동안 자동(배차·충전복귀)·수동(이동·teleop) 명령을 전부 막는다.
        #   reset() 으로만 풀린다. UI 버튼이 bind_visibility_from 으로 이 값을 본다.
        self.estopped = False

    # ── 이동 명령 ────────────────────────────────────────────────────
    def send_goal(self, robot_id: str, x: float, y: float,
                  kind: str = "", label: str | None = None) -> bool:
        """로봇 N 을 (x,y) 로 보낸다. kind=도착 시 처리(charge면 충전).
        A* 로 경로를 만들어 path 에 넣으면, 백엔드 제어루프가 알아서 따라간다.
        반환: 보냈으면 True / 못 감(E-STOP·경로없음)이면 False."""
        r = self._robot(robot_id)
        if r is None or self.estopped:
            return False

        # ⚠ A* 는 락 '밖'에서 계산한다.
        #   락을 쥔 채로 수십 ms 짜리 경로계획을 돌리면, 같은 락을 20Hz 로 잡는
        #   제어루프가 그동안 멈춰서 로봇이 뚝뚝 끊긴다. 계산은 밖, 대입만 안에서.
        path = self.planner.plan((r.x, r.y), (x, y))
        if not path:
            return False                                     # 도달 불가 → 목표 거부

        with FLEET_LOCK:
            r.manual = None                                  # 수동 명령 취소
            r.state = "driving"
            r.goal_kind = kind
            r.path = path
            r.task = label or f"→({x:.1f},{y:.1f})"
        return True

    def send_to_station(self, robot_id: str, station_name: str) -> bool:
        """로봇을 '스테이션 이름'으로 보낸다(UI 편의). 이름→좌표·종류 찾아 send_goal."""
        st = self._station(station_name)
        if st is None:
            return False
        return self.send_goal(robot_id, float(st["x"]), float(st["y"]),
                              kind=st.get("kind", ""), label=f"→{station_name}")

    def _station(self, name: str) -> dict | None:
        return next((s for s in self.stations if s["name"] == name), None)

    def teleop(self, robot_id: str, lin: float, ang: float) -> bool:
        """수동 조작(teleop): 전진 lin / 회전 ang 을 TELEOP_HOLD 초 동안 발행.
        자동 목표(path)는 취소된다 — 운영자 수동 override 가 우선."""
        if self.estopped:
            return False
        with FLEET_LOCK:
            r = self._robot(robot_id)
            if r is None:
                return False
            r.path, r.goal_kind = [], ""
            r.state, r.task = "manual", "수동조작"
            r.manual = (lin, ang)
            r.manual_until = time.monotonic() + TELEOP_HOLD
        return True

    def stop(self, robot_id: str) -> None:
        """정지: 목표·수동명령 모두 취소하고 대기 상태로."""
        with FLEET_LOCK:
            r = self._robot(robot_id)
            if r is None:
                return
            r.path, r.goal_kind, r.manual = [], "", None
            r.state, r.task = "idle", "-"

    def stop_all(self) -> None:
        """E-STOP: 전 로봇 정지 + 대기중/수행중 작업 취소 + **래치**.

        ⚠ 래치(estopped)가 핵심이다. 이게 없으면 '정지시켰는데 0.5초 뒤 알아서
          다시 출발'한다 — 저전력 로봇을 _auto_charge() 가 충전소로 보내고,
          남은 작업을 dispatch() 가 배차해 버리기 때문. 그건 E-STOP 이 아니다.
          해제(reset)를 부를 때까지 자동·수동 명령을 전부 막는다.
        """
        with FLEET_LOCK:
            self.estopped = True
            for r in self.robots:
                self.stop(r.id)
            for t in self.tasks:
                if t.state != "done":
                    t.state, t.robot, t.phase = "cancelled", None, ""

    def reset(self) -> None:
        """E-STOP 해제. 운영자가 명시적으로 눌러야만 다시 움직인다."""
        with FLEET_LOCK:
            self.estopped = False

    def clear_trails(self) -> None:
        """전 로봇의 궤적(발자취) 지우기 — turtlesim 의 /clear 에 해당하는 화면 청소."""
        with FLEET_LOCK:
            for r in self.robots:
                r.trail.clear()

    def add_task(self, pickup: str, drop: str) -> None:
        """운영자가 새 배송 작업을 큐에 추가(pending)."""
        with FLEET_LOCK:
            self._task_seq += 1
            self.tasks.append(Task(id=self._task_seq, pickup=pickup, drop=drop))

    def _robot(self, robot_id: str) -> RobotState | None:
        return next((r for r in self.robots if r.id == robot_id), None)

    # ── 관제 로직 (refresh 가 순서대로 호출) ───────────────────────────
    def _at_station(self, r: RobotState, station_name: str) -> bool:
        """로봇이 그 스테이션에 '실제로 서 있나'."""
        st = self._station(station_name)
        if st is None:
            return False
        return math.hypot(r.x - float(st["x"]), r.y - float(st["y"])) < ARRIVE_EPS

    def _requeue(self, t: Task, r: RobotState | None) -> None:
        """작업을 큐로 되돌린다(배차 취소) → 다음 dispatch() 가 다른 로봇에게 준다."""
        with FLEET_LOCK:
            t.state, t.robot, t.phase = "pending", None, ""
            if r is not None:
                r.task = "-"

    def _advance_tasks(self) -> None:
        """수행중(running) 작업 오케스트레이션: 픽업 도착 → 드롭 이동 → 완료.

        ⚠ 'idle 이면 도착' 이 아니다.
          정지(■)·teleop·통신두절로도 idle 이 된다. 그걸 도착으로 믿으면,
          운영자가 주행 중에 ■ 한 번 누른 것만으로 "픽업 완료 → 드롭으로 출발",
          한 번 더 누르면 "작업 완료" 가 된다(거북이는 어디에도 간 적이 없는데).
          → 목표 스테이션 근처에 실제로 서 있을 때만 다음 단계로 넘긴다.
        """
        for t in self.tasks:
            if t.state != "running":
                continue
            r = self._robot(t.robot or "")

            # 배차된 로봇이 사라졌거나 통신두절/에러 → 작업을 큐로 돌려 다른 로봇이 잇게.
            #   (이게 없으면 그 작업은 영원히 running 에 박혀 아무도 안 건드린다.)
            if r is None or not r.online or r.state == "error":
                self._requeue(t, r)
                continue

            if r.state != "idle":
                continue                      # 아직 주행 중(또는 수동/충전) — 대기

            target = t.pickup if t.phase == "to_pickup" else t.drop
            if not self._at_station(r, target):
                self._requeue(t, r)           # 도착 전에 멈춤(정지/수동) → 재배차
                continue

            if t.phase == "to_pickup":        # 픽업 도착 → 드롭으로
                if self.send_to_station(t.robot, t.drop):
                    t.phase = "to_drop"
                    r.task = f"{t.pickup}→{t.drop} (적재)"
            elif t.phase == "to_drop":        # 드롭 도착 → 완료
                t.state, r.task = "done", "-"

    def _auto_charge(self) -> None:
        """저전력 유휴 로봇을 자동으로 충전소로 복귀시킨다."""
        if self.estopped:
            return                             # E-STOP 중엔 아무도 움직이지 않는다
        charge = next((s for s in self.stations if s.get("kind") == "charge"), None)
        if charge is None:
            return
        for r in self.robots:
            if r.state == "idle" and r.battery < LOW_BATT:
                self.send_goal(r.id, float(charge["x"]), float(charge["y"]),
                               kind="charge", label="저전력→충전복귀")

    def dispatch(self) -> None:
        """대기(pending) 작업을 유휴·배터리충분 로봇에 배차 → 픽업으로 출발.
        규칙: 픽업 스테이션에서 '가장 가까운' 여유 로봇."""
        if self.estopped:
            return                             # E-STOP 중엔 배차하지 않는다
        for t in self.tasks:
            if t.state != "pending":
                continue
            st = self._station(t.pickup)
            free = [r for r in self.robots
                    if r.state == "idle" and r.online and r.battery > LOW_BATT]
            if not free:
                break                          # 여유 로봇 없음 → 다음 틱에 다시
            robot = (min(free, key=lambda r: math.hypot(r.x - float(st["x"]),
                                                        r.y - float(st["y"])))
                     if st else free[0])
            # 경로가 안 나오면(도달 불가) 배차하지 않는다 — pending 유지 → 다음 틱 재시도.
            if not self.send_to_station(robot.id, t.pickup):
                continue
            t.state, t.robot, t.phase = "running", robot.id, "to_pickup"
            robot.task = f"{t.pickup}→{t.drop} (픽업)"

    def refresh(self) -> None:
        """한 사이클(GUI 타이머가 호출):
        1) 백엔드 갱신 → 2) 진행중 작업 단계 진행 → 3) 저전력 충전복귀 → 4) 대기작업 배차.
        (순서 중요: 도착한 작업 로봇을 먼저 다음 단계로 보낸 뒤 충전/배차 판단.)
        turtlesim 백엔드에선 poll() 이 비어 있다 — 실제 이동은 20Hz 제어루프가 한다.

        ⚠ 여기서 FLEET_LOCK 을 통째로 잡지 않는다.
          아래 단계들은 A*(수십 ms)를 부를 수 있는데, 그동안 락을 쥐고 있으면
          20Hz 제어루프가 멈춰 로봇이 끊긴다. 각 메서드가 '바꿀 때만' 짧게 잡는다.
        """
        self.source.poll()
        self._advance_tasks()
        self._auto_charge()
        self.dispatch()

    def snapshot(self) -> list[RobotState]:
        """화면용 읽기 전용 사본.

        ⚠ 이게 왜 필요한가: ROS 스레드가 20Hz 로 path.pop(0)/trail.append() 를 한다.
          화면(GUI 스레드)이 그걸 그대로 읽으면, `if r.path` 를 통과한 직후 제어루프가
          마지막 웨이포인트를 pop 해버려 `r.path[-1]` 이 IndexError 로 터진다
          (로봇이 목표에 도착할 때마다 열리는 창). 락 안에서 통째로 복사해 그린다.
        """
        with FLEET_LOCK:
            return [replace(r, path=list(r.path), trail=list(r.trail))
                    for r in self.robots]

    def shutdown(self) -> None:
        self.source.shutdown()

    @property
    def summary(self) -> dict:
        """상단 요약용 집계."""
        return {
            "total":    len(self.robots),
            "online":   sum(1 for r in self.robots if r.online),
            "driving":  sum(1 for r in self.robots if r.state == "driving"),
            "waiting":  sum(1 for r in self.robots if r.state == "waiting"),
            "manual":   sum(1 for r in self.robots if r.state == "manual"),
            "charging": sum(1 for r in self.robots if r.state == "charging"),
            "error":    sum(1 for r in self.robots if r.state == "error"),
        }
