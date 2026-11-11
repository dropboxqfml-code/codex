# 6517A SCPI 원문 근거와 실행 범위

사용자가 제공한 `6517A_900_01C.pdf` 원문을 대조했습니다. 이전 개발 단계의 웹 다운로드는 프록시 CONNECT 403으로 실패했지만, 이번 첨부 PDF로 원문 접근이 해결됐습니다. 아래 명령은 다른 모델에서 가져오지 않았습니다.

- 문서: **Model 6517A Electrometer User's Manual**.
- 내부 표기: **6517A-900-01 Rev. D**, Fourth Printing, **May 2003**. 파일명의 `01C`와 내부 revision을 구분합니다.
- PDF: **343 pages**, 4,314,952 bytes.
- SHA-256: `3c02f1e97a0fd101cbc77a09aae87b1d0ce43e45b9bc46d433e671e8dea78adb`.
- 입력 파일: 사용자 첨부 `6517A_900_01C.pdf`; 이번 작업의 로컬 경로는 `/workspace/attachments/a5a29c4a-7165-4410-9495-b9af191b68cd/6517A_900_01C.pdf`.
- 아래 쪽수는 **PDF 뷰어 번호가 아닌 인쇄 쪽수**입니다.

원문 확인은 실제 장비/firmware/USB-GPIB 시험이 아닙니다. 현재 연결의 출력 OFF·인터록 전이 및 물리적 정격·실험 승인을 검증한 `FVMI_CURRENT` 경로만 실장비 START 승인을 받을 수 있습니다. Native resistance 실장비 출력은 측정 전류 기반 trip을 검증하지 못해 차단합니다. JSON 승인값이나 원문의 존재만으로 START하지 않습니다.

## 사용하는 명령

`W`는 상태 변경, `Q`는 조회입니다. `W/Q`는 쓰기와 같은 경로의 `?` 조회를 각각 사용합니다. 예상 응답은 원문이 정의한 종류이며 실제 장비의 철자/표현은 readback 검증 대상으로 처리합니다. `확인/미시험`은 **원문 확인 / 실장비 시험** 상태입니다. 아래 명령은 출력 OFF와 구성 검증을 포함한 driver 경로에 한정되며 write-capable console은 제공하지 않습니다.

| 명령 (코드의 SCPI 단축 표기) | W/Q·상태 변경 | 예상 응답·검사 | 인쇄 절·쪽 | 원문/실장비 |
|---|---|---|---|---|
| `*IDN?` | Q·없음 | 제조사,MODEL 6517A,serial,firmware; 정확한 모델 검사 | 3.11.4, 3-30 | 확인/미시험 |
| `*OPC?` | Q·완료 대기 | ASCII `1`; idle에서 사용, 응답 전 다음 query 없음 | 3.11.6, 3-32 | 확인/미시험 |
| `:SYST:ERR?` | Q·오류큐 소비 | 오류 코드/문자열, 없으면 `0`; 원문 보존·유한 drain | 3.22.4, 3-129 | 확인/미시험 |
| `:OUTP1 OFF`, `:OUTP1 ON`, `:OUTP1?` | W/Q·출력 relay | `0`/`1`; ON은 one-use START 승인 후만 | 3.17, 3-80; Table 3-8, 3-45; 2-50 | 확인/미시험 |
| `:INIT:CONT OFF`, `:INIT:CONT?` | W/Q·continuous 시작 여부 | `0`; one-shot 유지 | 3.24.1, 3-142 | 확인/미시험 |
| `:ABOR` | W·trigger 중단 | 응답 없음; OFF와 별도 조치 | 3.24.2, 3-142 | 확인/미시험 |
| `:TSEQ:ABOR` | W·내장 test sequence 중단 | 응답 없음; takeover/보호 중지 시 사용 | 3.25.1, 3-148 | 확인/미시험 |
| `:ROUT:SCAN:LSEL NONE`, `?` | W/Q·scan 사용 | `NONE`; 기존 scan 동작 해제 | 3.18.4, 3-83 | 확인/미시험 |
| `:TRAC:FEED:CONT NEV`, `?` | W/Q·buffer 수집 | `NEV`; host 수집과 기존 buffer 동작 분리 | 3.23.4, 3-140 | 확인/미시험 |
| `:SYST:HLC ON`, `?` | W/Q·A/D noise-spike limit | `1`; out-of-limit 검출 사용, source compliance와 별도 | 3.22.13, 3-134 | 확인/미시험 |
| `:SOUR:VOLT <V>`, `:SOUR:VOLT?` | W/Q·source 설정값 | 수치 V; 요청·양자화·조회값 비교 | 3.20.2, 3-106~107 | 확인/미시험 |
| `:SOUR:VOLT:RANG <100/1000>`, `?` | W/Q·source 범위 | 100/1000 V 범위 | 3.20.2, 3-107 | 확인/미시험 |
| `:SOUR:VOLT:LIM <V>`, `?` | W/Q·절대 전압 상한 | 수치 V, ±상한 적용 | 3.20.2, 3-107 | 확인/미시험 |
| `:SOUR:VOLT:LIM:STAT ON`, `?` | W/Q·상한 사용 | `1`; 현재 amplitude가 상한보다 높으면 충돌 | 3.20.2, 3-108 | 확인/미시험 |
| `:SOUR:VOLT:MCON ON`, `?` | W/Q·LO 내부 연결 | `1`; 승인된 저측 FVMI | 3.20.2, 3-108 | 확인/미시험 |
| `:SOUR:CURR:RLIM:STAT <ON/OFF>`, `?` | W/Q·저항성 current limit | `0`/`1`; 저항값은 보정 상수로 사용 안 함 | 3.20.2, 3-108 | 확인/미시험 |
| `:SOUR:CURR:LIM:STAT?` | Q·없음 | `0`=limit 미도달, `1`=도달 | 3.20.2, 3-108 | 확인/미시험 |
| `:SYST:INT?` | Q·없음 | `0`/`1`; `1`은 케이블 미연결에서도 가능 | 3.22.16, 3-137 | 확인/미시험 |
| `:SENS:FUNC 'CURR'/'RES'`, `?` | W/Q·측정 기능 | current/resistance 기능명; 따옴표·DC 표기 검사 | 3.19.2, 3-85 | 확인/미시험 |
| `:SENS:CURR:RANG:AUTO <ON/OFF>`, `?` | W/Q·전류 autorange | `0`/`1`; Auto V-Source와 독립 | 3.19.6, 3-90~92; Table 3-10, 3-48 | 확인/미시험 |
| `:SENS:CURR:RANG <A>`, `?` | W/Q·전류 범위 | 수치 A; 장비 선택 range readback 검사 | 3.19.6, 3-90~92 | 확인/미시험 |
| `:SENS:CURR:NPLC <n>`, `?`; `:AUTO OFF`, `?` | W/Q·적분·자동 선택 | 0.01~10 NPLC; AUTO=`0` | 3.19.5, 3-89 | 확인/미시험 |
| `:SENS:RES:VSC MAN`, `?` | W/Q·저항 V-source 제어 | `MAN`; AUTO는 40/400 V를 선택하므로 사용 안 함 | 3.19.16, 3-102 | 확인/미시험 |
| `:SENS:RES:MSEL NORM`, `?` | W/Q·저항법 | `NORM`; normal resistance | 3.19.17, 3-103 | 확인/미시험 |
| `:SENS:RES:MAN:CRANG:AUTO <ON/OFF>`, `?`; `:CRANG <A>`, `?` | W/Q·Manual ohms 전류 범위 | A 단위, Auto V-Source ohm range와 구분 | 3.19.6, 3-92~95; Table 3-10, 3-49 | 확인/미시험 |
| `:SENS:RES:NPLC <n>`, `?`; `:AUTO OFF`, `?` | W/Q·저항 적분 | 수치 NPLC; 실장비 native 출력은 차단 | 3.19.5, 3-89 | 확인/미시험 |
| `:SENS:CURR/RES:AVER:STAT OFF`, `?` | W/Q·평균 filter | `0`; 각 기능의 설정·조회 | 3.19.10, 3-99 | 확인/미시험 |
| `:SENS:CURR/RES:MED:STAT OFF`, `?` | W/Q·median filter | `0`; 각 기능의 설정·조회 | 3.19.11, 3-100 | 확인/미시험 |
| `:SENS:CURR/RES:REF:STAT OFF`, `?` | W/Q·REL/reference | `0`; 각 기능의 reference 사용 해제 | 3.19.7, 3-95~96 | 확인/미시험 |
| `:SENS:RES:IREF OFF`, `?` | W/Q·저항의 amps reference | `0`; raw current reference와 별도 | 3.19.8, 3-97 | 확인/미시험 |
| `:CALC:STAT OFF`, `?`; `:CALC2:STAT OFF`, `?` | W/Q·계산 | `0`; CALC1 math와 CALC2 buffer 계산 해제 | 3.13.1~2, 3-63/3-65 | 확인/미시험 |
| `:CALC3:LIM1:STAT OFF`, `?`; `:CALC3:LIM2:STAT OFF`, `?` | W/Q·장비 limit test | `0`; software trip·source limit와 구분 | 3.13.3, 3-68 | 확인/미시험 |
| `:SYST:ZCH ON/OFF`, `?` | W/Q·Zero Check | `0`/`1`; 정상 수집 전 OFF 확인 | 3.22.12, 3-133 | 확인/미시험 |
| `:SYST:ZCOR:ACQ` | W·내부 영점 획득 | 응답 없음; 출력 OFF·ZCH ON일 때만 | 3.22.12, 3-134 | 확인/미시험 |
| `:SYST:ZCOR ON`, `?` | W/Q·Zero Correct | `1`; 획득 후 ZCH OFF → ZCOR ON 순서 | 3.22.12, 3-133~134 | 확인/미시험 |
| `:FORM:DATA ASC`, `?` | W/Q·데이터 형식 | `ASC`; 선택 형식 검사 | 3.16, 3-75 | 확인/미시험 |
| `:FORM:ELEM READ,STAT,UNIT,RNUM,VSO`, `?` | W/Q·포함 요소 | 같은 요소 집합; 응답 순서는 Figure 3-19 고정 | 3.16, 3-76~78 | 확인/미시험 |
| `:ARM:SOUR IMM`, `?`; `:ARM:COUN 1`, `?` | W/Q·arm layer 1 | `IMM`, `1`; **delay 항목 없음** | 3.24.4~6, 3-143~144 | 확인/미시험 |
| `:ARM:LAY2:SOUR IMM`, `?`; `:COUN 1`, `?`; `:DEL 0`, `?` | W/Q·scan layer | `IMM`, `1`, `0` | 3.24.4~6, 3-143~144 | 확인/미시험 |
| `:TRIG:SOUR IMM`, `?`; `:COUN 1`, `?`; `:DEL 0`, `?` | W/Q·measure layer | `IMM`, `1`, `0` | 3.24.4~6, 3-143~144 | 확인/미시험 |
| `:READ?` | Q·새 conversion | ABOR → INIT → FETCH; 아래 ASCII 형식 | 3.12, 3-38~39 | 확인/미시험 |

`CURR/RES`는 표를 줄이기 위한 표기이며 slash를 실제 command에 보내지 않습니다. `?`만 적힌 칸은 해당 행의 전체 경로에 붙입니다. 코드에서 활성화하지 않은 고급 기능의 명령은 사용하지 않습니다.

## 원문 대조로 바로잡은 점

- Arm layer 1은 delay를 사용하지 않습니다(3-143). 예전 provisional profile의 `:ARM:LAY1:DEL`을 제거했습니다. Layer 1은 `:ARM:SOUR`·`:ARM:COUN`, layer 2와 trigger만 `:DEL`을 사용합니다.
- 전류·저항 기능의 `REF:STAT`와 ohms `IREF`를 명시적으로 해제합니다. CALC를 끄는 것만으로 REL이 꺼지는 것은 아닙니다.
- Source current-limit 명령은 상세 명령 설명 3-108의 **`:SOUR:CURR:...` root 경로**를 사용합니다. Table 3-11의 시각적 들여쓰기만 보고 `:SOUR:VOLT:CURR:...`를 만들지 않습니다. 임의 nA/µA programmable compliance 쓰기는 없습니다.
- Zero correction acquire 방식은 출력 OFF에서 ZCH ON → ACQ → ZCH OFF → ZCOR ON입니다(3-133~134). Autorange 구성 시 최소 전류 range에서 먼저 zero correction을 획득한 뒤 autorange를 적용하고, 고정 range면 그 range에서 획득합니다. 2-60은 uprange에서 zero가 유지되고 downrange에는 다시 zero해야 한다고 설명합니다. 획득 range·시각을 기록하며 이 절차가 모든 range에서 정격 정확도를 인증한다는 뜻은 아닙니다. 정격의 “properly zeroed” 조건은 2.13.4의 별도 절차와 실제 시료 조건도 검토해야 합니다.
- `READ?`는 ABOR/INIT/FETCH를 수행합니다. 세 layer의 source/count와 실제 존재하는 delay를 명시해 one-shot을 구성합니다. `FETCH?`만 반복하면 old reading이 재반환될 수 있으므로 정상 수집에 사용하지 않습니다. `CONF`/`MEAS`를 매 sample 호출하지 않습니다.
- `*OPC?`는 continuous operation에서 무조건적인 안전 동기화 수단이 아닙니다. 3-32는 continuous initiation 뒤 *OPC?가 장비를 대기 상태에 묶을 수 있다고 설명합니다. 본 구성의 idle·continuous OFF 조건에서만 완료 응답을 검증합니다.

## ASCII parser와 fixture의 출처

Figure 3-19(3-76)는 reading/status/unit이 붙은 token을 보여줍니다. 선택한 다섯 요소는 다음 세 필드로 반환됩니다.

```text
+1.00000000E-11NADC,+00001rdg#,+0010.000Vsrc
```

이 예는 **매뉴얼 도식에서 구성한 합성 fixture**이며 실장비 transcript가 아닙니다. 정확한 unit suffix는 current `ADC`, resistance `OHM`, reading number **`rdg#`**입니다. 예전 simulator의 `RDNG#` suffix는 원문과 달라 수정했습니다. 전체 FORMAT 요소를 어떤 순서로 나열해도 wire 순서는 reading → timestamp → reading number → channel → external temperature → humidity → V-source 순서입니다. 이 driver는 timestamp·channel·온습도 요소를 선택하지 않으며 선택 밖 형식은 조용히 추정하지 않습니다.

Status는 `N` 정상, `Z` zero check, `O` overflow, `U` underflow, `R` reference/REL, `L` out-of-limit입니다. `R`은 저항 단위가 아닙니다. 3-77의 sentinel은 overflow/out-of-limit `+9.9E37`, zero check `+9.91E37`, underflow `0.00E00`입니다. 해당 상태/sentinel을 유효 측정이나 평균으로 쓰지 않고 원문·flag를 보존합니다.

3-137의 interlock 응답은 계속 연결돼 있음을 보증하지 않습니다. 초기 0 → 1 관찰 뒤에도 케이블을 분리하면 query=1이 가능하므로, 이 query만으로 모든 이후 cable-disconnect를 검출할 수 없습니다. 현재 연결 관찰은 설치 확인을 보조하며 물리적 안전 기능의 연속성 인증이 아닙니다.

RNUM counter는 전원 투입 또는 `:SYST:RNUM:RES` 후 0부터 시작합니다(3-77, 3-133). 이 프로그램은 host READ 순서에서 중복/역행 counter를 fresh sample로 받아들이지 않습니다. 불연속은 내부 conversion/reset 가능성과 구분하여 기록하며 누락 데이터의 증명으로 단정하지 않습니다. Buffer/pre-trigger의 별도 counter·음수 reading 번호는 이 host profile 대상이 아닙니다.

3-78의 VSO는 source 출력에 관한 보고값이며 standby에서는 0 V로 보고됩니다. `:SOUR:VOLT?` 설정값이나 VSO를 독립 DUT 전압 측정으로 표시하지 않습니다. Source limit 상태가 켜지면 설정 전압 기반 V/I는 무효이며 중단합니다. Status query와 reading은 원자적 snapshot이 아닙니다.

## 원문 자체의 불일치와 실제 장비에서 남은 확인

2-49는 resistive-limit **20 MΩ**, 3-108은 **1 MΩ**를 기재합니다. 또 2-46/2-49는 범위별 source current limit를 100 V에서 10 mA, 1000 V에서 1 mA로 설명하지만 3-108의 query 설명은 1 mA만 언급합니다. 어느 저항값도 보정 상수·안전 보증치로 채택하지 않았으며 실제 revision·제조사 확인이 필요합니다.

매뉴얼에서 확인한 명령이어도 firmware별 readback·ASCII 표현·trigger freshness, adapter EOI/terminator·timeout/lock, zero correction와 range 유효성, 실제 인터록·출력 차단·방전은 아직 실장비에서 시험하지 않았습니다. [Commissioning 기록지](commissioning_checklist.md)에 단계별 결과와 실제 transcript를 보존해야 합니다. OFF 확인은 방전 확인이 아닙니다.
