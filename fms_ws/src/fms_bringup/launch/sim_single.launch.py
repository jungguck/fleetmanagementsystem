"""P0-3: TurtleBot3 1대를 Gazebo(gz sim)에 스폰.

⚠ 확인 필요 (설치 후 검증):
  - Jazzy(gz sim) turtlebot3_gazebo 의 정확한 launch 파일명.
    설치 후:  ros2 launch turtlebot3_gazebo <TAB>   로 확인.
    (Humble/Classic 표준은 turtlebot3_world.launch.py — Jazzy는 gz 기반이라 다를 수 있음)
  - TURTLEBOT3_MODEL env 필요 (setup/env.sh: waffle_pi).
실행 예:  ros2 launch fms_bringup sim_single.launch.py    (또는 파일 경로 직접)
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description():
    tb3_gazebo = get_package_share_directory('turtlebot3_gazebo')

    # TODO(확인필요): 설치 후 실제 launch 파일명으로 교체.
    world_launch = os.path.join(tb3_gazebo, 'launch', 'turtlebot3_world.launch.py')

    return LaunchDescription([
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(world_launch),
        ),
    ])
