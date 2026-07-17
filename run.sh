#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# FMS 관제 GUI 실행
#
# 왜 이 스크립트가 필요한가:
#   시스템 기본 python 은 3.13 인데 ROS 2 Jazzy 의 rclpy 는 3.12 용으로 빌드돼 있다
#   (3.13 으로 import 하면 _rclpy_pybind11 .so 없음 에러).
#   → python3.12 venv(--system-site-packages)를 만들고, ROS 를 source 한 상태로 실행.
#
# 사용:
#   터미널 1)  source /opt/ros/jazzy/setup.bash && ros2 run turtlesim turtlesim_node
#   터미널 2)  ./run.sh          → http://localhost:8090
# ═══════════════════════════════════════════════════════════════════
set -e
cd "$(dirname "$0")"          # 리포 루트 (gui 가 패키지로 import 되게)

# 1) ROS 2 환경 (rclpy·turtlesim 인터페이스가 PYTHONPATH 에 올라온다)
ROS_SETUP="/opt/ros/${ROS_DISTRO:-jazzy}/setup.bash"
if [ ! -f "$ROS_SETUP" ]; then
  echo "[FMS] ROS 2 를 찾을 수 없습니다: $ROS_SETUP"
  echo "      ROS 없이 UI 만 보려면 gui/config.yaml 의 source 를 sim2d 로 바꾸세요."
  exit 1
fi
# shellcheck disable=SC1090
source "$ROS_SETUP"

# 2) python3.12 venv (없으면 생성). --system-site-packages → ROS 파이썬 패키지 접근.
#    ⚠ 설치는 '폴더 존재' 로 건너뛰지 않는다. venv 만 만들어지고 pip 이 실패하면
#      (네트워크 등) 다음부터 폴더가 있다고 설치를 건너뛰어 ModuleNotFoundError 로만
#      죽는다 — 원인도 안 보인 채로. 설치는 매번 확인(이미 깔렸으면 즉시 끝난다).
VENV=".venv"
if [ ! -d "$VENV" ]; then
  echo "[FMS] python3.12 venv 생성 중…"
  python3.12 -m venv --system-site-packages "$VENV"
fi
if ! "$VENV/bin/pip" install -q -r gui/requirements.txt; then
  echo "[FMS] ⚠ 의존성 설치 실패. 네트워크 확인 후 다시 실행하세요."
  echo "      계속 실패하면 venv 를 지우고 재생성:  rm -rf $VENV && ./run.sh"
  exit 1
fi

# 3) 포트가 비었나 확인.
#    이전에 켠 앱이 안 죽고 남아 있으면 새로 켜도 'address already in use' 로 죽는데,
#    브라우저엔 '옛날 서버' 가 그대로 뜨기 때문에 "안 켜진다/안 바뀐다" 로 보인다.
PORT=8090
OLD_PID="$(ss -tlnp 2>/dev/null | grep ":$PORT " | grep -oP '(?<=pid=)\d+' | head -1)"
if [ -n "$OLD_PID" ]; then
  echo "[FMS] ⚠ 포트 $PORT 를 이미 쓰는 프로세스가 있습니다 (PID $OLD_PID)."
  echo "      이전에 켠 FMS 가 안 죽고 남은 것일 수 있습니다. 정리하려면:"
  echo "         kill $OLD_PID     # 그 뒤 ./run.sh 다시"
  exit 1
fi

# 4) turtlesim 이 떠 있나 확인(안 떠 있으면 spawn 서비스를 5초 기다리다 에러남).
if ! ros2 node list 2>/dev/null | grep -q turtlesim; then
  echo "[FMS] ⚠ turtlesim_node 가 안 보입니다. 다른 터미널에서 먼저 실행하세요:"
  echo "         source $ROS_SETUP && ros2 run turtlesim turtlesim_node"
  echo "      (ROS 없이 UI 만 볼 거면 gui/config.yaml 의 source 를 sim2d 로)"
fi

echo "[FMS] http://localhost:$PORT"
exec "$VENV/bin/python" -m gui.main
