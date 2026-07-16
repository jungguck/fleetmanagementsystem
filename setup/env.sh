# FMS 환경변수 — 사용:  source setup/env.sh
# (설치만 하는 이 단계에선 실행 안 함. 시뮬은 마스터가 별도 실행.)

export ROS_DISTRO="${ROS_DISTRO:-jazzy}"       # 22.04면 humble, 24.04면 jazzy
export TURTLEBOT3_MODEL="${TURTLEBOT3_MODEL:-waffle_pi}"   # burger / waffle / waffle_pi(lidar+cam 권장)
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"    # fleet 공용 도메인(팀 협의값)

# ROS 2 underlay
if [ -f "/opt/ros/${ROS_DISTRO}/setup.bash" ]; then
  source "/opt/ros/${ROS_DISTRO}/setup.bash"
fi
# (워크스페이스 빌드 후) overlay: source install/setup.bash

echo "[FMS] ROS_DISTRO=${ROS_DISTRO}  TURTLEBOT3_MODEL=${TURTLEBOT3_MODEL}  ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
