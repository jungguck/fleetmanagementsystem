# 관제 GUI 설계 (FMS TurtleBot Fleet)

> 마스터, 이 문서는 `README.md` §4 GUI 관제 요구(맵뷰·작업지시·상태카드·수동 override·알람)를 **ASCII 목업 + 패널별 상세**로 구체화한 것입니다.
> 스택은 **NiceGUI 웹**(README §8 결정: 재사용). `~/plc_study_for_me/app/ui/{dashboard.py, components.py}`의 `robot_card`·`camera_grid`·refreshable 패턴을 **재사용/치환**하는 방법을 명시합니다.

---

## 1. 전체 레이아웃 (ASCII 목업)

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  FMS 관제   [시뮬 ● 연결]   Fleet: 가동 3/4   작업 대기2 진행3 완료12   🕐 12:41:07   │  ← 헤더
│                                             [＋작업생성] [수동모드] [🟥 E-STOP]        │
├──────────────────────────────────────────────┬────────────────────────────────────┤
│  🗺 맵뷰 (map 프레임, 라이브 pose)              │  로봇 상태카드 리스트                │
│                                              │ ┌────────────────────────────────┐ │
│   ┌P──────────────────────────────────┐     │ │ tb1        [🟦 주행]   🔋78%    │ │
│   │  ▣CHG1        ●tb1→────▶ ▣DROP_B  │     │ │ 상태 MOVING  작업 #201 GOTO_DROP│ │
│   │       ●tb2                        │     │ │ 위치 (4.2, 1.8)  경로 ▓▓▓░ 62%  │ │
│   │   ▣PICK_A   ⚠(장애물)   ●tb3(대기) │     │ │ [목표전송][정지][teleop][상세]  │ │
│   │        ▣IDLE1                     │     │ ├────────────────────────────────┤ │
│   │  ← zone 점유: 교차로#3 (tb1 예약)  │     │ │ tb2        [🟩 충전]   🔋41%↑   │ │
│   └───────────────────────────────────┘     │ │ 상태 CHARGING 작업 —            │ │
│   범례: ●로봇 ▣스테이션 ─경로 ⚠장애물        │ ├────────────────────────────────┤ │
│         [맵 클릭 → 선택 로봇 목표전송]         │ │ tb3        [⬜ 대기]   🔋90%    │ │
│                                              │ ├────────────────────────────────┤ │
│                                              │ │ tb4        [🟥 에러] 연결 끊김  │ │
│                                              │ └────────────────────────────────┘ │
├──────────────────────────────────────────────┴────────────────────────────────────┤
│  작업 패널                                    │  알람 / 이벤트 로그                  │
│  큐: #204(HIGH) #205 | 진행: #201 #202 #203  │ 12:40 tb4 통신두절 → 재배차          │
│  [PICKUP▾][DROP▾][우선순위▾][＋추가]          │ 12:39 교차로#3 tb2 대기(예약)        │
│  #201 tb1 A→B  ▓▓▓░ GOTO_DROP  [취소][우선] │ 12:38 tb1 장애물 감지 PAUSE→재개     │
└───────────────────────────────────────────────────────────────────────────────────┘
```

**그리드 구조** (dashboard.py의 `display:grid;grid-template-columns` 패턴 재사용):
- 상단 헤더(고정 높이) / 본문 2컬럼(`좌 맵뷰 : 우 카드리스트` ≈ `2.4fr : 2fr`, 기존 대시보드 비율 차용) / 하단 2컬럼(작업패널 : 알람).

---

## 2. 패널별 상세

### 2.1 헤더 (상단 바)
- **표시요소**: 시스템명, 연결/모드(시뮬·실기), Fleet 요약(가동 N/M — 기존 `snap.active_count/total_count` 대응), 작업 요약(대기/진행/완료), 시각.
- **상호작용**:
  - `[＋작업생성]` → 작업생성 모달(2.4 폼).
  - `[수동모드]` → 전역 수동 override 토글(선택 로봇 teleop 활성).
  - `[🟥 E-STOP]` → 즉시 fleet broadcast 정지(시나리오8). 눌리면 화면 전체 빨강 배너 + 2단계 RESET.
- **재사용**: `plc_study` topbar 개념. E-STOP은 `~/robot_api`의 `/api/fleet/emergency_stop`(병렬·partial-failure) 백엔드에 연결.

### 2.2 맵뷰 (좌측, 라이브 pose)
- **표시요소**:
  - 배경: SLAM 저장맵(pgm) 이미지 위 오버레이.
  - 로봇 pose `●`(색=상태, 4.1 규칙), heading 화살표, 로봇ID 라벨.
  - 계획 경로 폴리라인(nav2 `plan` 구독, 로봇별 색).
  - 스테이션 `▣`(PICK/DROP/CHG/IDLE, 타입별 아이콘/색).
  - 장애물 `⚠`(costmap 동적 장애물), zone 점유 하이라이트(교통관제, 시나리오3).
- **좌표 변환**: `map`(m) → 픽셀 = 맵 yaml의 `resolution`·`origin` 사용. (world m ↔ 이미지 px 변환 유틸 필요, 확인 필요.)
- **렌더 방식**(택1, 확인 필요):
  - (a) NiceGUI `ui.interactive_image` 위에 SVG/마커 오버레이 — 클릭좌표→목표 변환 용이(권장).
  - (b) canvas 직접 그리기.
- **상호작용**: **맵 클릭 → 현재 선택된 로봇에게 목표전송**(클릭 px→map 좌표 역변환 → nav_client goal). 우클릭/드래그로 heading 지정(확인 필요).
- **재사용/치환**: 기존 `components.camera_grid`(카메라 타일 격자)를 **맵뷰 위젯으로 치환**. `_cam_tile`의 "라이브/오프 뱃지·오버레이 라벨" 패턴을 로봇 pose 마커 오버레이 방식으로 재활용(같은 absolute overlay 기법).

### 2.3 로봇 상태카드 리스트 (우측)
- **표시요소**(카드 1장 = 로봇 1대):
  - 헤더: 로봇ID + **상태 알약**(color=상태) + 배터리 🔋%(바).
  - 줄: State / Task(작업ID·단계) / 위치(x,y) / 경로 진행률 / 연결·Health.
  - 고장 시: 끊김 테두리·배경(붉은색) + fault 배지.
  - 버튼: `[목표전송][정지][teleop][상세]`.
- **상호작용**:
  - 카드 클릭 → 맵뷰에서 해당 로봇 선택(맵 클릭 목표전송 대상).
  - `[정지]` → 개별 로봇 정지(cmd_vel=0/nav cancel).
  - `[teleop]` → 수동 override 패널(2.5).
- **재사용/치환**: `components.robot_card(r, pneu=…)`를 **거의 그대로 개조**:
  - 기존 `rows` 리스트 구조(항목명/값/danger) 유지 → 항목을 `상태·작업·위치·배터리·연결`로 교체.
  - 상태 알약 `step_label/step_color`(status_map.py) → **FMS 상태맵**(`state_label/state_color`)으로 치환.
  - 끊김 테두리/배경(`border`/`bg` 붉은색) 로직 그대로 → 로봇 통신두절(시나리오7) 표시에 재사용.
  - `pneu` 줄 자리 → **배터리/충전 줄**로 재활용.
  - fault 배지(`fault_display`) → 로봇 에러/충돌회피 배지로 재활용.
- **갱신**: `@ui.refreshable` + `state.py` refresh 루프(주기 폴링→FleetSnapshot→`dashboard_body.refresh()`) 패턴 그대로(README §7-4 브릿지가 pose/battery/state 공급).

### 2.4 작업 패널 (하단 좌)
- **표시요소**: 큐(대기, 우선순위 표시) / 진행(로봇·단계·진행바) / 완료 카운트. 작업행: `#id 로봇 A→B [진행바] 단계 [취소][우선]`.
- **상호작용**:
  - **작업생성 폼**: `PICKUP▾ DROP▾ 우선순위▾ [＋추가]`(드롭다운=스테이션 목록, config/stations.yaml).
  - 행 `[취소]`(작업 취소·재배차), `[우선]`(우선순위 상향 → 재배차, 시나리오6).
- **재사용/치환**: `components.error_list`의 "시간·주체·종류·상세 한 줄" 나열 패턴을 **작업 리스트 행**으로 재활용. 진행바는 신규(간단 div width%).

### 2.5 알람/이벤트 로그 (하단 우) + 수동 teleop override
- **알람**: 시간·로봇·이벤트(고장/장애물/예약대기/충전복귀/E-STOP). 심각도 색(경고/에러).
  - **재사용**: `error_list` 그대로(빨강 category·회색 detail 패턴). `safety_banner`의 안전 배너 개념 → 하단 상시 안전상태 띠로 재활용 가능.
- **수동 teleop override 패널**(카드 `[teleop]` 또는 헤더 수동모드 시 노출):
```
  ┌ 수동 조작: tb1 ────────────────┐
  │        [ ▲ ]        속도 [====o ] │
  │   [ ◀ ] [ ■ ] [ ▶ ]  회전 [==o  ] │
  │        [ ▼ ]        [자율모드 복귀] │
  └────────────────────────────────┘
```
  - **동작**: 방향/슬라이더 → `/tbN/cmd_vel`(Twist) 발행. 수동 중 nav2 goal 일시중단.
  - **재사용**: `~/mobile_robot_proto_type-main/.../hardware_test.py`의 cmd_vel Twist 발행·방향버튼+속도슬라이더·/odom 실측 표시 패턴을 **웹 위젯으로 이식**(백엔드 rclpy publisher 경유).

---

## 3. 색 / 상태 규칙 (시나리오.md와 공유)

| State | 색상 코드(제안) | 카드 알약 | 맵 마커 |
|---|---|---|---|
| MOVING(주행) | `#2980b9` 파랑 | 🟦 | 파랑 ● + 경로선 |
| IDLE(대기) | `#95a5a6` 회색 | ⬜ | 회색 ● |
| LOADING/UNLOADING(적재/하역) | `#f39c12` 노랑 | 🟨 | 노랑 ● (스테이션 위) |
| CHARGING(충전) | `#27ae60` 초록 | 🟩 | 초록 ● (CHG 위) |
| PAUSED(일시정지) | `#e67e22` 주황 | 🟧 | 주황 ● |
| ERROR/ESTOP(에러/비상) | `#e74c3c` 빨강 | 🟥 | 빨강 ● + 끊김 테두리 |

- 배터리: ≥50 초록 / 30~50 노랑 / <30 빨강(임계값 시나리오4, 확인 필요).
- 연결 끊김: 카드 테두리·배경 붉은색(기존 `robot_card` 로직 재사용).
- **theme.py 재사용**: 기존 `SUCCESS/DANGER` 등 색상수 정의를 FMS 상태색으로 확장.

---

## 4. 데이터 흐름 (GUI ↔ 백엔드)

```
[NiceGUI 화면]  ──클릭/폼──▶  [백엔드 명령 API]  ──▶  [rclpy 브릿지]  ──▶  /tbN goal·cmd_vel·estop
      ▲                                                     │
      └──── @ui.refreshable ◀── FleetSnapshot ◀── state.refresh 폴링 ◀── /tbN pose·battery·state
```
- 상태 소스: 브릿지가 `/tbN/{amcl_pose|odom, battery_state, ...}` 구독 → FleetSnapshot 캐시.
- 명령: 목표전송(nav_client)·정지·teleop(cmd_vel)·E-STOP(broadcast).
- 갱신주기: 기존 대시보드 refresh 주기(~0.3s 관측, state.py 주석) 참고, 맵 pose는 더 빠르게(확인 필요).

## 5. 파일 매핑 (재사용 → FMS)

| 기존(plc_study/robot_api/proto) | FMS 대응 | 개조 정도 |
|---|---|---|
| `ui/dashboard.py` (레이아웃·`_panel`·refreshable) | `ui/dashboard.py` | 레이아웃 재구성(맵/카드/작업/알람) |
| `ui/components.py:robot_card` | 로봇 상태카드 | rows·상태맵·배터리로 치환 |
| `ui/components.py:camera_grid/_cam_tile` | 맵뷰 오버레이 | 오버레이 기법 재사용, 내용 교체 |
| `ui/components.py:error_list` | 작업리스트·알람 | 거의 그대로 |
| `ui/components.py:safety_banner` | 안전상태 띠 | 개념 재사용 |
| `status_map.py:step_*` | `state_*` | 상태 코드·색 재정의 |
| `state.py` refresh/snapshot | FleetSnapshot 루프 | 폴링→ROS 브릿지로 소스 교체 |
| `robot_api:/emergency_stop` | E-STOP 백엔드 | 병렬·partial-failure 그대로 |
| `proto:hardware_test cmd_vel` | teleop 위젯 | tkinter→웹 이식 |
