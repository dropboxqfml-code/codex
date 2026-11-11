# 실장비 commissioning 기록지

첨부된 6517A-900-01 Rev. D 원문을 반영한 current 측정 경로를 제공합니다. 문서 체크나 JSON의 과거 승인값만으로 현재 연결의 출력을 승인하지 않습니다. 아래 절차는 자격 있는 담당자가 승인된 enclosure와 독립적인 하드웨어 보호·차단·방전 수단 아래 수행해야 하며, 실제 시험은 아직 수행하지 않았습니다. Native resistance 실장비 경로는 측정 전류 보호를 검증하지 못해 비활성 상태입니다.

| 항목 | 기록 |
|---|---|
| 날짜·담당자·승인 문서 | 미기입 |
| Model / serial / firmware | 미확인 |
| USB-GPIB 모델 / driver / VISA library | 미확인 |
| Resource / timeout / EOI / read·write terminator | 미확인 |
| Fixture ID / revision / 케이블 정격 | 미확인 |
| 시료 / 기준저항 ID·교정·전압 정격 | 미확인 |
| Warm-up 실제 전원 투입 / 교정 이력 | 미확인 |
| 외부 차단·방전·전압 확인 장치 | 미제공 |

1. 실제 배선과 enclosure를 [안전 문서](wiring_and_safety.md)에 따라 검토합니다. 장비 6517A, USB-GPIB, SCPI language를 확인합니다. NI MAX 등 다른 제어 프로그램을 닫고 단일 session 소유권을 확보합니다.
2. 출력 OFF 상태에서 IDN, 설정 readback, error queue 원문을 수집합니다. 공식 매뉴얼 Figure 3-19 형식·단위·status·RNUM·VSO를 보유 firmware의 실제 transcript와 비교합니다. trigger 세 layer 경로와 one-shot READ freshness를 확인합니다.
3. OUTPUT OFF 상태에서 interlock 케이블 설치를 물리적으로 확인하고 lid-open=0 / lid-closed=1 전이를 기록합니다. query=1 단독은 합격이 아닙니다. 실제 차단 동작·정격·배선은 담당자가 별도로 검증합니다. 이 절차에 고전압 자동 인가 시험은 포함되지 않습니다.
4. 승인된 기준저항으로 허용된 낮은 전압부터 시험합니다. 예시 `[0, 1, 2, 5, 10] V`도 정격 승인이 선행되어야 합니다. 장비 전면과 PC의 값·단위·부호·시간·측정 기능을 비교합니다.
5. Manual V-Source, voltage limit·range, METER CONNECT, current autorange/fixed range, NPLC·filter·REL, Zero Check/Correct, 출력 상태 readback을 각각 확인합니다. Auto V-Source가 40/400 V를 임의 선택하는 상태가 아닌지 확인합니다.
6. 정상 중지·software trip·소프트웨어 오류·통신 실패에 대해 실제 출력 상태와 독립적인 물리 차단을 검증합니다. 통신 단절 시험은 담당자의 별도 계획 아래 제한된 조건에서 수행합니다. 고전압 상태 USB 분리를 초보자에게 권하는 시험이 아닙니다.
7. 동일 fixture blank와 정격 기준저항으로 누설·전압 의존성·settling·range 전환을 평가합니다. blank 값을 일괄 subtraction하지 않습니다.
8. capacitive/흡수·polarization 시료는 충전·방전·전압 회복 프로토콜을 별도로 검증합니다. OFF 후 잔류 전압과 실제 방전은 독립 측정·기록합니다.
9. 각 결과와 transcript를 보존하고 승인 후 단계적으로 범위를 확대합니다. 장비가 ±1000 V 범위를 가진다는 이유로 모든 주변 기기가 정격을 충족한다고 가정하지 않습니다.

프로그램에서는 같은 연결의 OUTPUT OFF 상태에서 사용자가 fixture lid를 실제로 열고 `0`을 확인한 뒤 닫고 `1`을 확인합니다. 두 관찰은 fixture ID·승인자에 연결되고 재연결에 재사용되지 않습니다. ARM은 이 관찰·정격·실험 승인을 검증하고 설정만 고정합니다. 별도의 START 전에는 출력 ON 명령을 보내지 않습니다.

연결·fixture가 달라지면 설치·lid 전이 확인을 다시 수행합니다. 통신 오류 후 재연결은 측정을 재개하지 않으며, 사용자 재검토·ARM·START가 다시 필요합니다.

## 프로그램에 남길 승인 기록

설정에는 `rating_approval`, `current_trip_A`, `sample_limit_V`, `fixture_limit_V`, `cable_limit_V`, `resistive_limit_enabled`와 `commissioning.fixture_id`·`approved_by`가 필요합니다. `installation_confirmed`, `lid_open_zero`, `lid_closed_one`은 담당자가 완료한 독립 commissioning 기록에 근거해야 합니다. 단순히 true로 바꿔 물리적 검증을 대신하지 않습니다. Resistive-limit ON/OFF 정책은 실제 승인된 하드웨어 구성에 따라 정하며, 내부 저항값을 20 MΩ 또는 1 MΩ로 가정해 보호·보정을 계산하지 않습니다.

이 정적 기록과 별도로 프로그램은 현재 연결의 OUTPUT OFF 상태에서 `0` → `1`을 직접 관찰해야 합니다. GUI에는 ‘인터록 열림 확인’·‘인터록 닫힘 확인’ 버튼이 있고, `cli measure --config 승인파일.json`은 `OPEN`·`CLOSED` 입력 뒤 각 조회를 수행합니다. ARM 이후 마지막 `START` 입력/버튼 전에는 ON하지 않습니다. 연결을 끊었다가 다시 연결하면 과거 관찰을 재사용하지 않습니다.

현재 연결에서 0 → 1 전이를 관찰해도 **이후 케이블이 계속 연결돼 있다는 증명은 아닙니다**. 3-137에 따라 케이블을 나중에 분리해도 `SYST:INT?`가 1을 반환할 수 있어 소프트웨어가 모든 분리 사건을 검출할 수 없습니다. 승인된 fixture의 케이블 고정·접근 관리와 독립적인 하드웨어 보호가 필요하며, 현재 연결 관찰을 하드웨어 인증이나 연속 감시 보증으로 해석하지 않습니다.
