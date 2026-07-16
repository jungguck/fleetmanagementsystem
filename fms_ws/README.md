# fms_ws — FMS ROS 2 워크스페이스

> ⚠ 이 골격은 **설치·실행 없이 코드만** 만든 상태입니다. 실제 실행·검증은 집 머신에서.

## 집에서 실행 순서
1. **설치**: `bash ../setup/install.sh`  (OS 자동감지 → ros-<distro>-turtlebot3·nav2·gazebo·slam·ros-gz)
2. **env**: `source ../setup/env.sh`  (TURTLEBOT3_MODEL=waffle_pi 등)
3. **빌드**: `cd fms_ws && colcon build && source install/setup.bash`
4. **(P0-3) 시뮬 1대**: `ros2 launch fms_bringup sim_single.launch.py`
5. **(P0-4) nav2**: `ros2 launch fms_bringup nav2_single.launch.py map:=<pgm/yaml>`

## ⚠ 확인 필요 (설치 후 검증)
- `launch/sim_single.launch.py`·`nav2_single.launch.py` 안의 **upstream launch 파일명**(gz sim·nav2 버전별 상이)은 설치 후 `ros2 launch <pkg> <TAB>` 로 확인 후 `TODO(확인필요)` 부분 교체.
- Gazebo: Jazzy는 gz sim(Harmonic) + ros_gz. Classic 아님.

## 패키지 구성
| 패키지 | 역할 | 상태 |
|---|---|---|
| `fms_bringup` | 시뮬·nav2 bringup launch (P0) | 골격(확인필요 TODO) |
| `fms_fleet` (예정) | 배차·교통관제 (P3~P4) | 미착수 |
| `fms_gui` (예정) | 관제 웹 GUI (plc_study_for_me 재사용, P1~) | 미착수 |
