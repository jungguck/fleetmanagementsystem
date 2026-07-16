"""P0-4 / P1: nav2 단독 기동 (저장 맵 + amcl + planner/controller).

⚠ 확인 필요 (설치 후 검증):
  - nav2_bringup 의 launch 파일명 (bringup_launch.py 표준이나 버전별 상이 가능).
  - map: P1-1에서 slam_toolbox 로 생성·저장한 pgm/yaml 경로.
  - use_sim_time: 시뮬이면 true.
실행 예:  ros2 launch fms_bringup nav2_single.launch.py map:=/path/to/warehouse.yaml
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    nav2_bringup = get_package_share_directory('nav2_bringup')

    # TODO(확인필요): 설치 후 실제 launch 파일명 확인 (bringup_launch.py / navigation_launch.py 등).
    bringup = os.path.join(nav2_bringup, 'launch', 'bringup_launch.py')

    return LaunchDescription([
        DeclareLaunchArgument('map', description='pgm/yaml 맵 경로 (P1-1 SLAM 저장맵)'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(bringup),
            launch_arguments={
                'map': LaunchConfiguration('map'),
                'use_sim_time': LaunchConfiguration('use_sim_time'),
            }.items(),
        ),
    ])
