#!/usr/bin/env bash
# FMS — ROS 2 스택 설치 (OS에 맞는 distro 자동감지)
# 사용:  bash setup/install.sh    (sudo 비번 한 번 입력)
set -e

DISTRO="${ROS_DISTRO:-}"
if [ -z "$DISTRO" ]; then
  UB=$(lsb_release -rs 2>/dev/null)
  case "$UB" in
    22.04) DISTRO=humble ;;
    24.04) DISTRO=jazzy ;;
    *) echo "지원 OS 아님 (Ubuntu $UB). ROS_DISTRO 를 직접 지정 후 재실행하세요."; exit 1 ;;
  esac
fi
echo "[FMS] Ubuntu $(lsb_release -rs 2>/dev/null) → ROS 2 '$DISTRO' 로 설치합니다."

PKGS="
ros-$DISTRO-turtlebot3
ros-$DISTRO-turtlebot3-simulations
ros-$DISTRO-turtlebot3-gazebo
ros-$DISTRO-navigation2
ros-$DISTRO-nav2-bringup
ros-$DISTRO-slam-toolbox
ros-$DISTRO-ros-gz
"

sudo apt update
sudo apt install -y $PKGS

echo ""
echo "[FMS] 설치 완료. 다음:"
echo "   source setup/env.sh"
echo "   (시뮬 실행은 TurtleBot3 공식 Jazzy bringup 확인 후 — 이 스크립트는 설치만 함)"
