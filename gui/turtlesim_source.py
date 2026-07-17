"""FMS 관제 — turtlesim 백엔드 (실제 ROS 2)
═══════════════════════════════════════════════════════════════════════
[정체] ROS 2 의 가장 기본 예제인 **turtlesim** 거북이 N 마리를 이 FMS 의 로봇으로 쓴다.
       (TurtleBot3/Gazebo/nav2 아님 — turtlesim_node 하나면 끝.)

[구조]
  turtlesim_node  ←── /turtleN/cmd_vel (Twist)  ── 이 노드(FmsNode)  ── FleetState ── 웹 GUI
                  ──→ /turtleN/pose  (Pose)  ──→

[하는 일]
  1. 시작 시 기본 거북이(turtle1)를 /kill → config 의 로봇들을 /spawn 으로 원하는 위치에 생성.
  2. /turtleN/pose 구독 → RobotState.x/y/yaw 갱신 (화면 맵뷰가 이걸 그린다).
  3. 20Hz 제어루프 → 경로(A* 웨이포인트) 를 따라가도록 /turtleN/cmd_vel 발행.
     turtlesim 거북이는 diff-drive(전진 linear.x + 회전 angular.z) 라 nav2 없이
     '제자리 회전 → 전진' 단순 제어기로 충분하다.
  4. 배터리는 turtlesim 에 없는 개념 → FMS 관제(충전복귀) 를 위해 가상으로 증감시킨다.

[스레드]
  ROS 실행기(executor)는 별도 스레드에서 돈다. 제어루프도 그 스레드에서 20Hz 로 돈다.
  웹 GUI 스레드(send_goal 등)와 같은 RobotState 를 만지므로 FLEET_LOCK 으로 보호한다.
  (GUI 타이머는 0.5s — 화면 갱신용. 제어는 그보다 훨씬 빨라야 부드럽다 → 분리.)
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import atexit
import math
import threading
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from turtlesim.msg import Pose
from turtlesim.srv import Kill, SetPen, Spawn

from gui import traffic
from gui.models import FLEET_LOCK, TRAIL_MAX, RobotState

# ── 제어기 상수 ────────────────────────────────────────────────────────
CTRL_HZ = 20.0        # 제어루프 주파수
MAX_LIN = 2.0         # 최대 전진 속도 [turtlesim 단위/s]
MAX_ANG = 4.0         # 최대 회전 속도 [rad/s]
K_LIN, K_ANG = 1.5, 4.0   # P 제어 게인
ANG_TOL = 0.12        # 이 각도[rad] 이상 틀어지면 제자리 회전부터
ARRIVE_TOL = 0.15     # 웨이포인트 도달 판정 거리
POSE_TIMEOUT = 2.0    # 이 시간[s] 동안 pose 없으면 offline 판정
TRAIL_STEP = 0.05     # 궤적에 점을 하나 더 찍는 최소 이동거리

# 배터리(가상) — turtlesim 엔 없는 개념이라 여기서 만들어 준다. 단위: %/초
DRAIN_DRIVE, DRAIN_IDLE, CHARGE_RATE = 0.5, 0.04, 4.0


def _norm(a: float) -> float:
    """각도를 -π~π 로 정규화 (목표각 - 현재각 오차 계산용)."""
    return math.atan2(math.sin(a), math.cos(a))


class _FmsNode(Node):
    """cmd_vel 발행 / pose 구독을 담당하는 rclpy 노드."""

    def __init__(self, robots: list[RobotState]):
        super().__init__("fms_gui")
        self.robots = robots
        self.pubs: dict[str, object] = {}
        self.last_pose: dict[str, float] = {}

    def create_io(self) -> None:
        """토픽 입출력 개설. ⚠ 반드시 거북이 kill/spawn '이후'에 호출할 것.
        (먼저 구독하면, spawn 전에 서비스 응답을 기다리며 spin 하는 동안
         '기존' 거북이의 pose 콜백이 RobotState.x/y 를 덮어써 버린다.)"""
        for r in self.robots:
            self.pubs[r.id] = self.create_publisher(Twist, f"/{r.id}/cmd_vel", 10)
            # 기본인자로 r 캡처 — 루프 클로저 함정 회피.
            self.create_subscription(
                Pose, f"/{r.id}/pose", lambda m, rr=r: self._on_pose(m, rr), 10)

    def _on_pose(self, msg: Pose, r: RobotState) -> None:
        """turtlesim 이 알려주는 실제 위치 → RobotState 반영(맵뷰가 그림)."""
        r.x, r.y, r.yaw = msg.x, msg.y, msg.theta
        r.online = True
        self.last_pose[r.id] = time.monotonic()

        # 궤적 기록 = turtlesim '펜' 의 웹 재현.
        #   pose 는 62Hz 로 오므로 전부 쌓으면 낭비 → TRAIL_STEP 이상 움직였을 때만.
        if not r.trail or math.dist(r.trail[-1], (msg.x, msg.y)) > TRAIL_STEP:
            r.trail.append((msg.x, msg.y))
            if len(r.trail) > TRAIL_MAX:
                del r.trail[:-TRAIL_MAX]


class TurtlesimSource:
    """FleetState 가 쓰는 백엔드. Sim2DSource 와 같은 인터페이스(poll)."""

    def __init__(self, robots: list[RobotState], cfg: dict):
        self.robots = robots
        # 교통관제: 이 거리 안에 두 로봇이 들어오면 우선순위 낮은 쪽이 선다.
        self.safe_dist = float(cfg.get("safe_dist", 1.0))

        # spawn 할 자리를 '지금' 스냅샷해 둔다 — 아래 서비스 호출 도중 pose 콜백이
        # 돌아 r.x/r.y 가 바뀌더라도, config 에 적은 초기 위치로 생성되게.
        spawn_poses = [(r.id, float(r.x), float(r.y), float(r.yaw)) for r in robots]

        if not rclpy.ok():
            rclpy.init()
        self.node = _FmsNode(robots)

        # ── 초기화: 기본 turtle1 제거 → config 로봇들을 원하는 자리에 spawn ──
        #   (spawn/kill 은 서비스 호출. 실행기 스레드를 띄우기 '전에' 동기로 처리.)
        self._setup_turtles(spawn_poses)

        # ── 거북이가 다 생긴 뒤에 토픽 개설(순서 중요 — create_io 주석 참고) ──
        self.node.create_io()

        # ── 실행기 스레드 시작 (pose 콜백 + 제어루프가 여기서 돈다) ──
        self._closed = False
        # 어떤 경로로 프로세스가 끝나든 정리되게(웹앱은 app.on_shutdown 이 부르지만,
        # 스크립트/테스트처럼 그냥 끝나는 경우 rclpy 를 안 닫아 exit 때 core dump 가 난다).
        atexit.register(self.shutdown)
        self._last_tick = time.monotonic()
        self.node.create_timer(1.0 / CTRL_HZ, self._control)
        self._exec = SingleThreadedExecutor()
        self._exec.add_node(self.node)
        self._thread = threading.Thread(target=self._exec.spin, daemon=True)
        self._thread.start()

    # ── 거북이 생성 ─────────────────────────────────────────────────
    def _call(self, client, req, what: str):
        """서비스 1회 동기 호출 (실행기 스레드 시작 전에만 사용)."""
        if not client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError(
                f"turtlesim 서비스({what})가 없습니다. 먼저 turtlesim_node 를 실행하세요:\n"
                f"  source /opt/ros/jazzy/setup.bash && ros2 run turtlesim turtlesim_node")
        fut = client.call_async(req)
        rclpy.spin_until_future_complete(self.node, fut, timeout_sec=5.0)
        return fut.result()

    def _setup_turtles(self, poses: list[tuple[str, float, float, float]]) -> None:
        n = self.node

        # 1) turtlesim 이 자동으로 띄우는 기본 turtle1 을 지운다(위치를 우리가 정하려고).
        #    이미 없으면 kill 이 실패하는데 무시해도 된다(우리가 원하는 상태 = 없음).
        kill = n.create_client(Kill, "/kill")
        self._call(kill, Kill.Request(name="turtle1"), "kill")

        # 2) config 의 로봇들을 초기 위치에 생성.
        #    이름이 이미 있으면 turtlesim 이 빈 이름을 돌려준다 → 경고만 남기고 진행
        #    (기존 거북이를 그대로 쓰게 된다. 위치만 config 와 다를 수 있음).
        spawn = n.create_client(Spawn, "/spawn")
        for rid, x, y, theta in poses:
            if rid != "turtle1":
                self._call(kill, Kill.Request(name=rid), "kill")   # 재실행 대비 정리
            res = self._call(spawn, Spawn.Request(x=x, y=y, theta=theta, name=rid), "spawn")
            if res is None or not res.name:
                n.get_logger().warn(f"'{rid}' spawn 실패 — 같은 이름이 이미 있습니다.")

        # 3) 궤적 펜 색 — 로봇마다 다르게(누가 누군지 구분).
        #    웹 맵뷰의 궤적도 같은 r.pen 색으로 그린다 → 두 화면의 색이 항상 일치.
        for r in self.robots:
            cr, cg, cb = r.pen
            self._call(n.create_client(SetPen, f"/{r.id}/set_pen"),
                       SetPen.Request(r=cr, g=cg, b=cb, width=2, off=0), "set_pen")

    # ── 20Hz 제어루프 (ROS 실행기 스레드) ───────────────────────────
    def _control(self) -> None:
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now

        with FLEET_LOCK:
            # 교통관제: 지금 양보해야 하는 로봇들(충돌 위험). 매 틱 새로 판단한다
            #   — 위험이 풀리면 자동으로 집합에서 빠져 로봇이 알아서 재개한다.
            yield_ids = traffic.yielders(self.robots, self.safe_dist)

            for r in self.robots:
                # 통신 감시: pose 가 끊기면 offline.
                #   last==0 은 '아직 첫 pose 를 못 받은 기동 직후' → offline 이지만 에러 아님.
                last = self.node.last_pose.get(r.id, 0.0)
                was_online = r.online
                r.online = (now - last) < POSE_TIMEOUT if last else False

                # 살아있다가 끊긴 경우에만 에러 처리(기동 직후는 제외).
                #   유령 경로를 그대로 두면 맵에 죽은 로봇의 계획경로가 계속 그려지고,
                #   그 로봇의 작업이 running 에 박힌다(→ state._advance_tasks 가 재배차).
                #   복구는 운영자가 ■(정지)를 눌러 idle 로 되돌리는 것.
                if was_online and not r.online:
                    r.state, r.path, r.manual, r.task = "error", [], None, "통신두절"

                self._drive_one(r, dt, now, r.id in yield_ids)

    def _drive_one(self, r: RobotState, dt: float, now: float,
                   must_yield: bool = False) -> None:
        tw = Twist()

        # ① 수동(teleop): 버튼으로 내린 명령이 유효한 동안 그대로 발행.
        #    수동은 교통관제보다 우선 — 운영자가 직접 잡은 조종간을 관제가 막지 않는다.
        if r.manual and now < r.manual_until:
            tw.linear.x, tw.angular.z = r.manual
            r.battery = max(0.0, r.battery - DRAIN_DRIVE * dt)
        elif r.manual:                       # 수동 명령 만료 → 정지·대기 복귀
            r.manual, r.state, r.task = None, "idle", "-"

        # ② 충전중: 제자리에서 배터리 회복.
        elif r.state == "charging":
            r.battery = min(100.0, r.battery + CHARGE_RATE * dt)
            if r.battery >= 99.5:
                r.state, r.task = "idle", "-"

        # ③ 교통관제 양보: 정지(cmd_vel=0) 하되 **경로는 그대로 들고 있는다**.
        #    → 위험이 풀리면 다음 틱에 아래 ④ 로 떨어져 가던 길을 그대로 이어간다.
        elif must_yield and r.state in ("driving", "waiting") and r.path:
            r.state = "waiting"
            r.battery = max(0.0, r.battery - DRAIN_IDLE * dt)

        # ④ 주행중: A* 웨이포인트를 따라간다.
        elif r.state in ("driving", "waiting") and r.path:
            r.state = "driving"              # 양보 해제 → 재개
            wx, wy = r.path[0]
            dx, dy = wx - r.x, wy - r.y
            dist = math.hypot(dx, dy)

            if dist < ARRIVE_TOL:                 # 이 웨이포인트 도달
                r.path.pop(0)
                if not r.path:                    # 경로 끝 = 최종 도착
                    if r.goal_kind == "charge":
                        r.state, r.task = "charging", "충전중"
                    else:
                        r.state, r.task = "idle", "-"
                    r.goal_kind = ""
            else:
                err = _norm(math.atan2(dy, dx) - r.yaw)   # 목표방향과의 각도차
                tw.angular.z = max(-MAX_ANG, min(MAX_ANG, K_ANG * err))
                # 많이 틀어졌으면 제자리 회전부터(엉뚱한 방향으로 전진 방지).
                if abs(err) < ANG_TOL:
                    tw.linear.x = max(0.0, min(MAX_LIN, K_LIN * dist))
                r.battery = max(0.0, r.battery - DRAIN_DRIVE * dt)

        # ⑤ 그 외(대기): 정지 + 자연 방전.
        else:
            r.battery = max(0.0, r.battery - DRAIN_IDLE * dt)

        self.node.pubs[r.id].publish(tw)

    # ── FleetState 인터페이스 ───────────────────────────────────────
    def poll(self) -> None:
        """sim2d 와 인터페이스를 맞추기 위한 자리. 실제 갱신은 20Hz 제어루프가 한다."""

    def shutdown(self) -> None:
        """웹앱 종료 시 정리. 순서 중요:
        실행기를 먼저 멈추고 스레드가 실제로 빠져나온 걸 확인한 뒤 노드를 파괴해야 한다
        (spin 중인 스레드를 두고 destroy_node 하면 C++ 쪽에서 terminate → core dump).

        두 번 불려도 안전해야 한다 — app.on_shutdown 과 atexit 둘 다 부를 수 있다."""
        if self._closed:
            return
        self._closed = True

        for r in self.robots:                      # 마지막으로 정지 명령
            with FLEET_LOCK:
                r.manual, r.path = None, []
        self._exec.shutdown()
        self._thread.join(timeout=3.0)
        self.node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
