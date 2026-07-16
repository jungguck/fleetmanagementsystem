# FMS System — AGV Fleet Management (TurtleBot)

> TurtleBot 여러 대를 **지게차(AGV/AMR)** 로 보고, GUI 관제시스템에서 "어디로 가서 무엇을 옮겨라"를 지시·조율하는 **Fleet Management System(FMS)**.
> **현재 상태: 계획 단계(개념·아키텍처 확정, 미구현).**

- **타깃**: ROS 2 **Humble** (⚠ 개발 머신은 Jazzy/Ubuntu 24.04 → **Docker Humble** 또는 별도 22.04 머신 필요)
- **문서 성격**: 프로젝트 착수 전 개념·아키텍처·로드맵·난제 정리

---

## 1. 개념 매핑 (지게차 ↔ TurtleBot)

| 지게차/AGV 개념 | FMS 구현 요소 | TurtleBot 대응 |
|---|---|---|
| 자율주행 | **nav2** (경로계획·장애물회피) | diff-drive 베이스 |
| 위치 인식 | AMCL/SLAM + **공유 맵** | LiDAR + odom |
| 적재/하역 | 작업 상태머신(load/unload) | ⚠ 포크 없음 → 상태 플래그 / AR마커 / 간이 메커니즘 |
| 관제 지시·감시 | Fleet Manager + GUI 관제 | — |
| 충전 | 자동 충전복귀 | 배터리 상태 |

## 2. 시스템 아키텍처 (4계층)

```
┌─────────────────────────────────────────────┐
│  GUI 관제 (HMI): 맵뷰·작업지시·상태카드·수동override·알람  │
├─────────────────────────────────────────────┤
│  Fleet Manager(두뇌): 맵·작업큐·배차·[교통관제]·상태집계   │
├─────────────────────────────────────────────┤
│  통신: ROS2 DDS(로봇간, 네임스페이스) + 웹 브릿지(관제↔GUI) │
├─────────────────────────────────────────────┤
│  로봇: nav2·AMCL·base control·상태리포트·적재상태 (TurtleBot N)│
└─────────────────────────────────────────────┘
```

1. **로봇 계층** — nav2(주행)·AMCL(위치)·base control·상태 리포트(pose/battery/task/state)·적재 상태.
2. **통신 계층** — 로봇 간 ROS2 DDS(로봇별 네임스페이스 `/tb1 /tb2 …`), 관제↔GUI 브릿지.
3. **Fleet Manager** — 맵/스테이션(픽업·드롭·충전·대기) · 작업큐 · 배차 · **교통관제(최난제)** · fleet 상태 집계.
4. **GUI 관제** — 맵뷰(실시간 위치)·작업 생성/지시·로봇 상태카드·수동 teleop override·알람.

## 3. 제어 흐름 (어디로 / 무엇을)

```
작업생성("픽업A 자재 → 드롭B")
   → 배차(가장 가깝고 한가한 로봇 tbN 선택)
   → tbN: A로 nav2 주행 → 적재(load) → B로 주행 → 하역(unload) → 충전/대기 복귀
   ↑ 그동안 Traffic Manager가 경로 예약·우선순위로 충돌/교착 방지
```

## 4. 로드맵 (단계별)

| 단계 | 내용 | 완료 기준 |
|---|---|---|
| **P0 환경** | Humble + TurtleBot3 + nav2 + Gazebo (Docker) | 시뮬 1대 뜸 |
| **P1 단일** | SLAM 맵 → nav2 목표이동 → GUI 1대 상태+목표전송 | 클릭→로봇 그 지점 도착 |
| **P2 다중** | 네임스페이스 N대 동시 nav2 → GUI 다중카드+맵 N위치 | 2~3대 동시 주행 |
| **P3 작업/배차** | 작업큐 + 배차로직(근접/한가) | 작업 넣으면 로봇 자동 선택·수행 |
| **P4 교통관제** | 충돌/교착 회피 (예약 또는 Open-RMF) | 교차로에서 안 부딪힘 |
| **P5 적재/충전** | 픽업·드롭 상태머신 + 자동충전복귀 | 왕복 사이클 무인 반복 |

## 5. 기존 프레임워크 먼저 (밑바닥 발명 금지)

- **Open-RMF** (Open Robotics Middleware Framework): ROS 2 표준 오픈소스 **fleet 관제** — 다중로봇 **교통관제·작업 dispatch·이종 fleet 통합·web 대시보드** 제공, TurtleBot 데모 존재.
- **핵심 결정**: 교통관제·배차를 **직접 커스텀**(학습용, 매우 어려움) vs **Open-RMF 채택/확장**(빠르고 견고). → 최난제(P4)를 이미 푼 걸 쓰는 게 합리적.

## 6. 재사용 자산 (같은 워크스테이션 내)

| 필요 요소 | 재사용 자산 | 경로 |
|---|---|---|
| 웹 관제 대시보드 골격(다중로봇 카드·폴링·push) | plc_study_for_me NiceGUI | `~/plc_study_for_me/app/{main.py, ui/dashboard.py, ui/components.py, state.py}` |
| 로봇 목록 설정화(YAML) | config robots 리스트 | `~/plc_study_for_me/config.yaml`, `app/config.py` |
| 멀티로봇 병렬 명령/폴링 | dispatch(gather)/_fetch_bounded | `~/plc_study_for_me/app/{plc_control.py, state.py}` |
| Fleet 레지스트리 + 병렬 비상정지 | RobotManager.units, `/api/fleet/emergency_stop` | `~/robot_api/api/{robot_manager.py, server.py}` |
| TurtleBot 직접 제어(cmd_vel teleop) 예시 | tkinter+rclpy GUI | `~/mobile_robot_proto_type-main/src/gui_py/gui_py/hardware_test.py` |
| ROS↔웹 브릿지 | **없음 — 신규 도입 필요** | (미설치) |

→ 관제 레이어는 거의 재활용, **TurtleBot↔관제 연결만 신규.**

## 7. 핵심 난제 (뭐가 문제인가)

1. **다중로봇 교통관제 (최난)** — 좁은 통로·교차로 충돌/교착. 해법: 차선/구역 예약·우선순위·데드락 감지 또는 Open-RMF.
2. **로컬라이제이션·맵 일관성** — 전 로봇 같은 맵 좌표계, 드리프트·재로컬.
3. **작업 배차/스케줄링** — 거리·배터리·혼잡 최적화(단순 근접부터).
4. **ROS↔GUI 브릿지 확장성** — N대 상태 실시간 웹 관제, DDS/네임스페이스.
5. **적재 개념 매핑** — 포크 없는 TurtleBot의 "적재/하역" 표현·검증.
6. **배터리/충전 관리** — 방전 방지·자동 충전복귀.
7. **안전** — E-STOP·사람/장애물 감지·속도제한·비상정지 전파.
8. **환경 미스매치** — Humble↔Jazzy → Docker Humble.
9. **시뮬↔실기 갭** — Gazebo↔실 TurtleBot(센서 노이즈·지연).

## 8. 결정 포인트 (착수 전 좁힐 것)

- Open-RMF 채택 vs 커스텀
- 시뮬(Gazebo) vs 실 TurtleBot, 대수
- 제어 깊이: teleop 관제 ↔ 완전 자율(nav2+배차+교통)
- GUI 스택: NiceGUI 웹(재사용) vs RViz/rqt/Foxglove
- ROS↔웹 브릿지: rclpy 노드 직접 vs rosbridge/foxglove
- Humble 실행환경: Docker vs 22.04 머신

## 9. 검증 방식 (착수 시)

단계별 e2e 실측: P1에서 **"GUI 클릭 → Gazebo TurtleBot이 목표점 도착"** 확인 후 다음 단계. 각 단계는 앞 단계 회귀(단일→다중→배차→교통) 유지.
