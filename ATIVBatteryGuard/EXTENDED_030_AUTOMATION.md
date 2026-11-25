# 0.3.0 RC2 추가 자동 검증 도구 v2

사용자가 남은 실사용 검증의 자동화를 요청해 별도 Windows WPF 검사 도구를 작성했습니다. 프로그램 자체는 사용자 Windows 자동 검사가 통과한 RC2/e710446을 유지합니다. 이번 작업은 새 정식 프로그램 버전이 아닙니다.

[추가 검사 ZIP](../downloads/ATIVBatteryGuard-0.3.0-rc.2-EXTENDED-CHECKS-v2.zip) · [실행 순서](EXTENDED_030_USER_STEPS.txt) · [구현](validation/ATIVBatteryGuard.ExtendedCheck/Runner.cs) · [클라우드 검사 기록](reports/extended-030-v2-validation.json)

## 자동화한 항목

| 항목 | 구현한 검사 |
| --- | --- |
| 한글 문자열·줄바꿈 | 실제 RC2 TextBox에 확정 문자열을 설정 → PropertyChanged 바인딩 → 저장 버튼의 연결 명령 → 실제 저장소 → 닫기/재열기. 실제 IME 조합은 아님 |
| 창 X 취소 | 실제 MainWindow에 제품과 같은 TryPrepareToClose 종료 가드를 검사 호스트에서 연결. 실제 저장 확인 MessageBox의 취소를 선택해 창/초안 유지 확인 |
| A/B 닫기 취소 | 실제 버튼에 연결된 명령과 저장 확인 대화상자를 거쳐 두 초안 유지/저장 후 닫기 확인 |
| 두 창 충돌 | 독립 MainViewModel/저장소 어댑터와 실제 MainWindow 두 개를 같은 프로세스에 구성. 앞선 저장 보호, 뒤의 초안·B 유지, 닫기 차단, 실제 .ativrecord 백업, 다시 읽기 취소/허용 확인 |
| 잠금 실패·재시도 | 실제 FileShare.None 메모 잠금으로 저장 실패/닫기 차단·기존 내용 보존 후 해제 재시도 |
| 반복 사용 | A/B 열기·TextBox 수정·저장·닫기, 파일/잠금의 배타적 재열기, 남은 임시 파일 확인 |
| 시간·응답 관찰 | 빠른 30회 또는 20분 반복. 완료 횟수/시간, 메모리·핸들 수, Dispatcher 왕복 지연 기록. 반복 사이 30초 초과 공백은 정지/절전 가능성 때문에 미통과 |

독립 Application 검사 호스트가 제품의 MainWindow/어셈블리를 사용하고, 원본 App.xaml의 모든 스타일을 구조가 같은 별도 ResourceDictionary로 컴파일해 불러옵니다. WPF가 거부하는 다른 어셈블리 App 파생 클래스의 InitializeComponent 호출을 제거했습니다. 제품의 일반 시작 코드를 호출하지 않습니다. 실제 서비스/배터리/WMI 어댑터 대신 합성 배터리와 임시 경로를 주입합니다. 일반 앱의 실제 시작·폴링 경로를 실행한 검사는 아닙니다. 버튼은 실제 연결된 ICommand를 동기 실행하므로 바인딩·명령을 확인하며 물리적 포인터 적중은 새로 검사하지 않습니다.

저장 확인에는 제품 LocalUserInteraction의 실제 MessageBox를 사용합니다. 현재 검사 UI 스레드의 #32770 창 중 정확한 소유 창이 같은 것만 찾고 그 안의 Yes/No/Cancel 버튼을 선택합니다. 다른 앱 창을 열거하거나 전역 키보드/마우스 이벤트를 보내지 않습니다. 자동 선택 실패는 별도 누적 표시로 남겨 취소의 정상 결과로 오인하지 않습니다.

## 결과와 중단 처리

`extended-results/startup-*.json`을 BCL 시작 단계부터 만들고 플랫폼/경로/매니페스트/파일 확인/버전/호스트/리소스/Dispatcher 단계와 고정 오류 코드·예외 분류/HResult를 기록합니다. 예외 메시지/스택/개인 경로/인수는 남기지 않습니다. 시작 완료는 본 검사 통과를 의미하지 않습니다. 본 검사의 `extended-results/extended-*.json`에 새 실행별 파일을 만들고 원자적 교체로 중간 상태와 최종 결과를 저장합니다. 중간 `running-not-passed`, 사용자 중단 `stopped-not-passed`, 파일/시나리오/바인딩/정리 실패 `not-passed`는 통과가 아닙니다. 최종 성공은 `automated-checks-passed-ime-and-release-pending`입니다. 결과 저장 실패도 성공 종료 코드를 반환하지 않습니다. 강제 종료에서는 완료된 보고서가 없을 수 있습니다.

검사 전후 6파일 해시와 후보 버전을 확인하며 기존 결과 파일·개인 데이터·기존 RC2 ZIP은 덮어쓰지 않습니다. 새 임시 폴더의 예제만 사용하고 종료 때 정리합니다. 창 X나 Ctrl+C는 다음 처리 지점에서 중단하며, 다른 프로그램/helper를 종료하지 않습니다. 실제 충전 제어·OEM/배터리 조회·자동 전송·Defender·서명·정책 변경은 없습니다.

## 자동화하지 않은 범위

- 실제 한글 입력기의 조합 시작/진행/완료와 OS 입력 서비스. `ImeCompositionEngineTested=false`로 기록합니다. 확정 문자열 주입을 이 검사의 대체 근거로 쓰지 않습니다.
- 실제 파일 선택/저장 대화상자, 물리적 마우스 적중, 독립 프로세스 사이의 동시 실행 경쟁. 각각 자동화하지 않았음을 기록하고 기존 사용자 근거와 구분합니다.
- 메모리 누수 부재나 모든 장기 안정성의 증명. 강제 GC로 수치를 낮추지 않고 샘플을 보존하며 `MemoryVerdict`는 관찰값임을 표시합니다.
- 보안 검사·코드 서명·최종 0.3.0 승인. 해당 필드는 false입니다.

## 개발 환경 검증

기존 정책 회귀3개와 새 리소스 동일성/시작 진단 회귀5개를 포함해 portable 전체1263통과·실패/skip0입니다. 명시적 quick/soak 인수만 허용하고, 완료 횟수/20분/유한 시간·30초 공백 조건·중단/부분 결과/파일/시나리오/바인딩/정리 실패 판정을 검사했습니다. Portable과 별도 net48 WPF 검사 도구 빌드는 경고/오류0입니다. 제품 207소스 지문과 RC2 배포 6파일 일치를 검사하고 새 ZIP의 CRC·내부 SHA·18항목을 확인했습니다.

실제 Windows에서 이 새 도구의 대화상자/화면/20분 검사를 실행하지는 않았습니다. 기존 RC2 자체의 Windows GUI 통과 근거와 새 도구의 컴파일/정책 회귀를 분리합니다. 새 실행 결과를 받기 전까지 새 자동 검증의 현장 통과를 주장하지 않습니다.

빌드 시 이미 일치하는 RC2 앱/Core net48 출력이 필요합니다. 새 도구는 해당 어셈블리를 참조하고 패키징에서 원래 RC2 바이트와 대조합니다.

```bash
DOTNET_ReadyToRun=0 dotnet build validation/ATIVBatteryGuard.ExtendedCheck/ATIVBatteryGuard.ExtendedCheck.csproj -c Release
dotnet run --project tests/ATIVBatteryGuard.PortableTests.csproj -c Release -- --report /tmp/extended-tests.json
python scripts/package_extended_030.py --candidate-zip ../downloads/ATIVBatteryGuard-0.3.0-rc.2-WIN10-X64.zip --test-report /tmp/extended-tests.json --output /tmp/extended-package
```

사용자는 v1의 두 모드가 시작 안내 오류로 실행되지 않았다고 보고했습니다. 기존 v1 자료는 보존하고 [시작 구조 수정과 진단](EXTENDED_030_STARTUP_FIX.md)을 추가했습니다. 다음은 사용자 Windows에서 v2 빠른 검사 결과를 받는 것입니다. 시작이 안 되면 20분 검사를 반복하지 않습니다. 이미 통과한 기존 검증시작.cmd와 충전 시험은 반복하지 않습니다. 이후 실제 IME 조합 확인과 서명 배포 준비를 이어갑니다.
