# FMS System — turtlesim Fleet 관제

> ROS 2 의 가장 기본 예제인 **turtlesim** 거북이 4마리를 **지게차(AGV)** 로 보고,
> **웹 브라우저에서 조작·관제**하는 Fleet Management System.
>
> **현재 상태: 동작함.** 웹에서 목적지 지정(A* 자동주행)·수동 teleop·작업 배차·충전복귀까지.

- **타깃**: ROS 2 Jazzy (Ubuntu 24.04) + `turtlesim` + NiceGUI 웹.
- **문서**: [개발노트](docs/개발노트.md)(왜 이렇게 만들었나·어디서 물렸나) ·
  [환경](docs/환경.md) · [시나리오](docs/시나리오.md) · [GUI 설계](docs/GUI_설계.md) ·
  [구현 로드맵](docs/구현_프롬프트.md)
- **TurtleBot3 / Gazebo / nav2 는 쓰지 않는다.** turtlesim_node 하나면 끝 —
  FMS 의 핵심 가치는 3D 물리가 아니라 **관제 두뇌**(배차·작업 FSM·경로계획·충전·안전)에 있고,
  그 로직은 turtlesim 의 2D 평면 위에서 전부 만들고 검증할 수 있다.

---

## 1. 실행

터미널 2개가 필요하다.

```bash
# 터미널 1 — 시뮬레이터
source /opt/ros/jazzy/setup.bash
ros2 run turtlesim turtlesim_node

# 터미널 2 — 관제 웹
cd ~/fleetmanagementsystem
./run.sh                      # → http://localhost:8090
```

`run.sh` 가 알아서 한다: ROS 환경 source → **python3.12 venv** 생성(최초 1회) → 웹앱 실행.

> **왜 python3.12 venv 인가**: 이 머신의 기본 python 은 3.13 인데 Jazzy 의 `rclpy` 는
> 3.12 용으로 빌드돼 있다(3.13 으로 import 하면 `_rclpy_pybind11` .so 없음 에러).
> → `python3.12 -m venv --system-site-packages` 로 만들어야 rclpy 가 붙는다.

**ROS 없이 UI 만 보고 싶다면** `gui/config.yaml` 의 `source: sim2d` 로 바꾸면
turtlesim 없이 2D 시뮬로 똑같은 화면이 돈다.

---

## 2. 웹 화면

```
┌─ 🎯 로봇 조작 ───────────────────── [궤적 지우기] [🟥 E-STOP] ┐
│  TB-1  [PICK-A ▾] [이동]      ▲ ◀ ▶ ▼ ■                     │
│  TB-2  [DROP-B ▾] [이동]      ▲ ◀ ▶ ▼ ■                     │  ← 목적지 지정 + 수동 teleop
│  …                                                          │
├─ ➕ 작업 생성 : [픽업 ▾] → [드롭 ▾] [추가] ──────────────────┤  ← 자동배차(대안)
├──────────────────────────┬──────────────────────────────────┤
│  🗺 turtlesim 화면(웹)     │  로봇 상태카드                    │
│   파란 배경 + 🐢거북이     │  TB-1 [주행] 🔋78% 📍(4.2,1.8)   │
│   + 펜 궤적(실선)          │  TB-2 [충전] 🔋41%               │
│   + A* 계획경로(점선)      │  …                               │
│   + 스테이션 ▣ / 가상벽    │                                  │
├──────────────────────────┴──────────────────────────────────┤
│  📋 작업 큐 : #1 PICK-A→DROP-B  running [turtle3]            │
└─────────────────────────────────────────────────────────────┘
```

**맵뷰 = 웹에 그린 turtlesim 창 + 관제 오버레이.**
turtlesim 창은 거북이와 펜 궤적만 안다. 웹 맵뷰는 같은 좌표계(0~11.09) 위에
**turtlesim 창이 모르는 것**(A* 계획경로·스테이션·가상벽·상태색)을 겹쳐 그린다.
→ turtlesim 창을 안 봐도 브라우저만으로 관제된다(원격 관제).

조작 방식 2가지:
| 방식 | 누가 고르나 | 어떻게 |
|---|---|---|
| **목적지 지정** | 운영자가 로봇도 목적지도 | [이동] → A* 경로 생성 → 거북이가 자동 주행 |
| **수동 teleop** | 운영자가 직접 운전 | ▲◀▶▼ → `/turtleN/cmd_vel` 직발행 (1초씩, 자동정지) |
| **자동 배차** | 시스템이 로봇을 고름 | 작업(A→B) 생성 → 가장 가까운 유휴 로봇에 배차 |

---

## 3. 구조

```
turtlesim_node ──/turtleN/pose──→ turtlesim_source (rclpy, 20Hz 제어루프)
               ←─/turtleN/cmd_vel─┘        │
                                           ↓
                                   state.FleetState  (관제 두뇌)
                                     · planner: A* 경로계획
                                     · dispatch: 배차
                                     · 작업 FSM / 충전복귀 / E-STOP
                                           ↓
                                   NiceGUI 웹 (맵뷰·카드·조작·작업큐)
```

| 파일 | 역할 |
|---|---|
| `gui/config.yaml` | **로봇·스테이션·벽·백엔드 설정** — 대수 조정은 여기서만(코드 무관) |
| `gui/models.py` | 공용 데이터 모델(RobotState·Task·색·락) — 순환 import 방지용 최하위 |
| `gui/turtlesim_source.py` | ROS 백엔드: spawn / pose 구독 / cmd_vel 20Hz 제어 |
| `gui/state.py` | 관제 두뇌: 배차·작업 FSM·충전복귀 + `sim2d` 폴백 백엔드 |
| `gui/planner.py` | 격자 A* 경로계획 (nav2 의 경로계획 역할을 대신) |
| `gui/traffic.py` | 교통관제: 충돌 감지 + 우선순위 양보 (교착이 생길 수 없는 규칙) |
| `gui/ui/mapview.py` | 웹에 그리는 turtlesim 화면 + 관제 오버레이 |
| `gui/ui/dashboard.py` | 상단 요약 + 로봇 상태카드 |
| `gui/ui/control.py` | 목적지 지정 + 수동 teleop + E-STOP |
| `gui/ui/tasks.py` | 작업 생성 폼 + 작업 큐 |
| `run.sh` | ROS source + python3.12 venv + 실행 |

**스레드 2개**가 같은 `RobotState` 를 만진다 → `models.FLEET_LOCK` 으로 보호:
- ROS 실행기 스레드: 20Hz 제어루프 (path/state/battery 갱신)
- 웹 GUI 스레드: 버튼 클릭(send_goal/teleop) + 0.5초 관제틱/화면 갱신

이 구조에서 **꼭 지켜야 하는 3가지** (전부 실제로 물렸던 것들):
1. **A\* 는 락 밖에서 계산한다.** 락을 쥔 채 경로계획을 돌리면 20Hz 제어루프가 멈춰 로봇이 끊긴다.
2. **화면은 `state.snapshot()` 사본으로 그린다.** 살아있는 `path` 를 읽으면 제어루프가
   `pop(0)` 하는 순간과 겹쳐 `IndexError` 가 난다(로봇이 도착할 때마다 열리는 창).
3. **관제틱은 `app.timer`(앱 1개), 화면갱신은 `ui.timer`(페이지별).**
   관제를 `ui.timer` 로 두면 브라우저 0개일 때 배차가 멈추고, 2개일 때 2배속으로 돈다.

## 4. 대수 조정

`gui/config.yaml` 의 `robots:` 에 항목만 추가/삭제 → **코드 수정 없이** 몇 마리든.
`id` 가 곧 turtlesim 이름이자 토픽 네임스페이스(`/turtle5/cmd_vel`).

## 5. 개념 매핑 (지게차 ↔ turtlesim)

| 지게차/AGV 개념 | 이 프로젝트 구현 | 비고 |
|---|---|---|
| 자율주행 | A* 경로계획 + 20Hz 추종 제어 | nav2 대신 `planner.py` |
| 위치 인식 | `/turtleN/pose` (정확한 실측) | SLAM/AMCL 불필요 |
| 장애물 회피 | config 의 `walls` = **가상 진입금지 구역** | turtlesim 엔 실제 장애물이 없다 |
| 적재/하역 | 작업 상태머신(to_pickup → to_drop) | 포크 없음 → 상태 플래그 |
| 배터리/충전 | **가상 배터리** + 저전력 자동 충전복귀 | turtlesim 엔 배터리 개념이 없다 |
| 관제 지시·감시 | FleetState + NiceGUI 웹 | — |

## 6. 남은 것

- **정면대향 우회**: 교통관제가 교차 상황은 풀지만(한 대가 양보), 1폭 통로에서 정면으로
  마주치면 선 로봇을 그대로 통과한다 — 우회 재계획이나 일방통행 규칙 필요(`docs/구현_프롬프트.md` P4-2).
- 맵 클릭 → 목표 전송 (지금은 스테이션 선택만).
- 알람/이벤트 로그, 작업 우선순위·개별 취소, 속도 슬라이더.
