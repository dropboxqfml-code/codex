# 추가 자동 검사 v2 — 시작 구조 수정과 진단

2026-11-25 한국 시간. 사용자는 바탕화면에 ZIP을 풀고 v1 빠른 검사/20분 검사를 모두 실행했지만 시작 실패 안내만 나왔다고 보고했습니다. 두 모드의 실제 검사 통과 근거는 없습니다. 당시 도구는 시작 예외를 하나의 문구로 처리해 JSON이 없으므로 사용자 PC의 정확한 예외나 실패 단계를 단정할 수 없습니다. 바탕화면 압축 해제가 잘못됐다고 판단하지 않습니다.

## 코드에서 찾은 문제

v1은 다른 어셈블리에 정의한 ExtendedApplication이 제품 App을 상속한 뒤 제품의 InitializeComponent를 호출했습니다. WPF의 Application.LoadComponent(object, Uri)는 BAML 리소스의 어셈블리와 실제 객체 타입의 어셈블리가 다르면 거부합니다. [WPF Application 소스](https://github.com/dotnet/wpf/blob/main/src/Microsoft.DotNet.Wpf/src/PresentationFramework/System/Windows/Application.cs)의 `bamlStream.Assembly != component.GetType().Assembly` 조건을 확인했습니다. 이는 v1 시작 코드의 구조적 결함이며 새 진단 전까지 사용자 PC에서 바로 이 예외가 발생했다고 확정하지는 않습니다.

v2는 System.Windows.Application을 직접 상속하는 독립 호스트를 사용합니다. 제품의 MainWindow/ViewModel/저장소 어셈블리는 그대로 참조하고, 원본 App.xaml의 모든 리소스를 구조가 같은 ProductResources.xaml ResourceDictionary로 별도 컴파일해 단일 Uri 오버로드로 불러옵니다. 제품 App의 InitializeComponent/일반 시작·실제 서비스는 호출하지 않습니다. 리소스 동일성을 회귀 검사와 패키징 양쪽에서 확인합니다.

## 시작 진단

WPF/제품 타입을 사용하는 시작 메서드는 NoInlining으로 분리하고 그 전에 BCL만 사용하는 StartupJournal을 생성합니다. 새 startup JSON에 단계·고정 오류 코드·고정 예외 분류·숫자 HResult만 남깁니다. 예외 메시지/스택/인수/개인 경로/메모/장치 식별값은 저장하지 않습니다. 실패 기록은 완료 호출로 덮어쓰지 않습니다. 시작이 완료되어도 본 검사 종료 코드와 본 JSON을 확인해야 하며 최종 출시는 false입니다.

폴더 쓰기 실패나 CLR이 Main 진입 전에 실패한 경우에는 JSON이 없을 수 있습니다. 가능한 시작 실패는 콘솔에도 단계/고정 코드를 표시합니다. 파일·플랫폼·매니페스트 검사를 완화하거나 예외를 통과로 바꾸지 않았습니다.

## 검증과 다음 확인

원본 스타일 동일성·한글/공백 경로의 초기 JSON 생성·예외 중첩 분류와 개인정보 제외·실패/이전 실행 보존·고정 단계 거부 회귀5개를 추가했습니다. 전체1263통과·실패/skip0, portable 및 실제 XAML/BAML을 포함한 별도 net48 WPF 빌드는 경고/오류0입니다. 제품207소스·6파일과 기존 RC2/v1 ZIP은 보존합니다.

v2의 실제 Windows 시작과 검사 실행은 이 Linux에서 확인하지 않았습니다. 사용자에게 [v2 ZIP](../downloads/ATIVBatteryGuard-0.3.0-rc.2-EXTENDED-CHECKS-v2.zip)을 새 폴더에 풀고 빠른추가검사.cmd만 먼저 실행하도록 안내합니다. 실패하면 startup JSON, 실행됐다면 startup과 extended JSON을 받습니다. 시작 실패 중에는 20분 검사를 반복하지 않습니다. 기존 프로그램 GUI/충전 시험은 반복하지 않습니다.

[새 검증 기록](reports/extended-030-v2-validation.json) · [실행 순서](EXTENDED_030_USER_STEPS.txt)
