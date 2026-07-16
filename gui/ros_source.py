"""FMS 관제 — ROS 2 소스 (rclpy 브릿지)   [P1+ 골격 · 이 개발머신선 실행 불가]
═══════════════════════════════════════════════════════════════════════
[목적] mock 을 '실제 ROS2 로봇'으로 교체하는 다리.
  - 읽기(구독): /tbN/odom(위치) · /tbN/battery_state(배터리) → RobotState 채움
  - 쓰기(명령): send_goal(robot, x, y) → /tbN/navigate_to_pose (nav2 액션)
        ★ 마스터 모델 "1번 로봇 A로 가라" 가 실제로 나가는 지점이 여기다.

[왜 별도 파일인가]
  rclpy 는 ROS2 환경에서만 import 된다(이 개발머신엔 없음).
  그래서 최상단에서 import 하지 않고, FleetState 가 source: ros 일 때만
  이 모듈을 lazy import 한다(mock 실행은 rclpy 없이도 되게).

[⚠ 확인 필요 — 설치·실기 후 검증]
  - 네임스페이스 규칙: /tb1 /tb2 … 로 topic·action 이 remap 되는지 (bringup 설정).
  - 토픽/타입: odom=nav_msgs/Odometry, battery=sensor_msgs/BatteryState 가정 — 실기 확인.
  - nav2 액션명: nav2_msgs/action/NavigateToPose, action 경로 '/tbN/navigate_to_pose' 가정.
  - 이 머신엔 rclpy·nav2 없음 → 집에서 빌드·실행·검증.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import math

# ── ROS2 의존 (source: ros 일 때만 이 모듈이 import 됨) ──
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient

from nav_msgs.msg import Odometry
from sensor_msgs.msg import BatteryState
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose

from gui.state import RobotState


def _yaw_from_quat(q) -> float:
    """쿼터니언 → yaw(rad). (odom orientation 에서 방향 뽑기)"""
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                      1.0 - 2.0 * (q.y * q.y + q.z * q.z))


class RosFleetSource:
    """로봇 N대의 상태를 ROS2 로 구독하고, nav2 목표를 보내는 소스."""

    def __init__(self, robots: list[RobotState]):
        self.robots = robots
        rclpy.init()
        self.node = Node("fms_gui")

        # 로봇별 구독·액션클라이언트 (네임스페이스 /tbN)
        self._subs = []
        self._goal_clients: dict[str, ActionClient] = {}
        for r in robots:
            ns = f"/{r.id}"   # 예: /tb1  ⚠ bringup 의 remap 규칙과 일치해야 함
            # 위치(odom) 구독 — 콜백에서 해당 RobotState 갱신
            self._subs.append(self.node.create_subscription(
                Odometry, f"{ns}/odom",
                lambda msg, rr=r: self._on_odom(rr, msg), 10))
            # 배터리 구독
            self._subs.append(self.node.create_subscription(
                BatteryState, f"{ns}/battery_state",
                lambda msg, rr=r: self._on_battery(rr, msg), 10))
            # nav2 목표 액션 클라이언트
            self._goal_clients[r.id] = ActionClient(
                self.node, NavigateToPose, f"{ns}/navigate_to_pose")

    # ── 구독 콜백: 메시지 → RobotState 반영 ──
    def _on_odom(self, r: RobotState, msg: Odometry) -> None:
        p = msg.pose.pose
        r.x, r.y = p.position.x, p.position.y
        r.yaw = _yaw_from_quat(p.orientation)
        r.online = True

    def _on_battery(self, r: RobotState, msg: BatteryState) -> None:
        # percentage 는 0~1 (없으면 무시) — 실기 값 확인 필요
        if msg.percentage is not None:
            r.battery = float(msg.percentage) * 100.0

    # ── poll(): mock 의 poll 과 같은 인터페이스. 콜백 처리(spin_once). ──
    def poll(self) -> None:
        rclpy.spin_once(self.node, timeout_sec=0.0)   # 대기 없이 쌓인 콜백만 처리

    # ── send_goal(): "로봇 N → (x,y) 로 가라" = nav2 목표 전송 ──
    def send_goal(self, robot_id: str, x: float, y: float, yaw: float = 0.0) -> None:
        client = self._goal_clients.get(robot_id)
        if client is None:
            return
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = "map"          # ⚠ 맵 프레임명 확인 필요
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)
        client.wait_for_server(timeout_sec=2.0)
        client.send_goal_async(goal)               # 비동기 전송(결과는 P3+ 에서 추적)

    def shutdown(self) -> None:
        self.node.destroy_node()
        rclpy.shutdown()
