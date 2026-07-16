# fms_gui — 관제 웹 대시보드 (골격)

`plc_study_for_me` 의 NiceGUI 대시보드 패턴을 재사용. **현재 mock 소스라 ROS 없이 단독 실행** 가능(집에서 바로 확인).

## 실행 (집에서)
```bash
pip install -r requirements.txt
cd ~/FMSsystem_agv          # 리포 루트에서 (gui 가 패키지로 import 되도록)
python -m gui.main          # → http://localhost:8090
```

## 구성
| 파일 | 역할 |
|---|---|
| `config.yaml` | 로봇(현재 4대)·스테이션·소스(mock/ros) 설정 — **대수는 여기서만 조정** |
| `state.py` | `FleetState` + `RobotState` + `MockFleetSource` (ros 소스는 P1+ TODO) |
| `ui/dashboard.py` | 로봇 카드·요약 (plc_study `robot_card` 패턴 차용) |
| `main.py` | NiceGUI 페이지 + refresh 타이머 (port 8090) |

## 대수 조정
`config.yaml` 의 `robots:` 목록에 항목만 추가/삭제 → **코드 수정 없이** 몇 대든.
(예: 8대면 tb5~tb8 추가.)

## 지금 상태 / TODO
- ✅ 로봇 카드(상태·배터리·작업·위치) + 상단 요약 + mock 진화 데이터
- ⬜ (P1+) **ros 소스**: rclpy 로 `/tbN` pose·battery·nav2 상태 구독 → mock 대체
- ⬜ (P1+) **맵뷰**: 로봇 위치·경로·스테이션 표시
- ⬜ (P3+) **작업 생성/배차 패널**, 수동 teleop override, E-STOP
