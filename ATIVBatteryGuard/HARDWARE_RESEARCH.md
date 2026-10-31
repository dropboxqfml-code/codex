# 하드웨어 조사

## 확인된 사실

사용자가 제공한 화면·진단과 로컬 정적 분석에서 확인한 범위입니다.

- 모델: `940X3G/930X3G`, BIOS: `P05ACJ.128.140819.dg`.
- Windows 10 Home `10.0.19045`, OS와 앱 프로세스는 x64.
- 사용자 노트북의 실제 배터리 상태는 Windows와 앱에서 모두 0%이며, 사용자가 정상 반영임을 확인했습니다. 수치 보정 대상이 아닙니다.
- Samsung Settings 2.2.0이 설치되어 있지만 충전 제한 메뉴가 없다고 사용자가 확인했습니다.
- `SamsungSystemConfiguration` 서비스가 실행 중인 것으로 보고되었습니다. 서비스 실행은 충전 제한 지원 증거가 아닙니다.
- 업로드된 `SamsungConfigurationMonitor.exe`는 같은 폴더의 `wsabi.dll`을 정적으로 참조합니다. 확인된 호출 문맥은 팬·정숙 모드입니다. 이 문맥의 `0x80`을 배터리 80% 명령으로 해석하지 않습니다.
- 최신 업로드 ZIP에서 `wsabi.dll` 수집에 성공했습니다. 파일은 22,920바이트이며 SHA-256은 `564b640d62db2a4e4b56c6331e0e526bad2ac1fcf438a41a9e5241551f457b6e`입니다.
- 해당 DLL은 x86 네이티브 WMI/COM SABI 중계 DLL입니다. export는 `InitBIOSInterface`, `UninitBIOSInterface`, `CallBIOSInterface`, `GetBiosVersion`, `GetBiosMode`입니다.
- 정적 코드에서 `ROOT\WMI`, `WmiAcpiVersion`, `WmiAcpiMethod`, `DataBuffer`, `Bytes`, `inData`, `outData`, `CallSabiFunction` 참조를 확인했습니다.
- `CallBIOSInterface`에는 실제 WMI 메서드 실행 경로가 있으므로 읽기 전용 진단 함수로 취급할 수 없습니다. `GetBiosMode`가 조회하는 것은 SMBIOS 정보이며 배터리 보호 모드로 볼 근거가 없습니다.
- 이 분석에서는 OEM 파일을 실행·로드하거나 DLL 함수를 호출하지 않았습니다. 전자서명 신뢰 검증과 Windows 동작 검증도 수행하지 않았습니다.

## 가정

이전에 Samsung/SABI라는 이름만 검색한 진단은 `WmiAcpi*` 클래스를 놓쳤을 가능성이 있습니다. DLL에 정확한 클래스 이름이 있으므로 그 **정의만** 확인하는 진단을 추가하는 것이 다음 조사에 도움이 됩니다.

이 가정은 사용자 노트북에 해당 클래스가 현재 등록되어 있다거나, 그 클래스가 충전 제한 기능을 제공한다는 뜻이 아닙니다. 범용 중계 DLL에서 충전 문자열을 찾지 못한 사실도 충전 기능이 없다는 확정 증거는 아닙니다.

## 아직 검증되지 않은 항목

- 사용자 노트북에 위 WMI 클래스가 실제 존재하는지, 조회 권한과 클래스·메서드 정의가 무엇인지
- `CallSabiFunction` 입력 바이트의 의미와 모델·BIOS별 지원·안전 범위
- 실제 충전 상한 80%/100% 명령과 현재 설정을 읽는 방법
- Windows에서 쓸 수 있는 공식·검증된 OEM 제어 인터페이스
- 앱 종료·재부팅·전원 차단 뒤 펌웨어 설정 유지 여부
- 삼성 DLL의 공식 ABI와 전자서명 신뢰

클래스나 메서드가 발견되어도 실제 제어 지원으로 표시하지 않습니다. 하드웨어 상태는 계속 미지원으로 유지합니다.

## 다음 검증

`ROOT\WMI`의 `WmiAcpiVersion`, `WmiAcpiMethod`, `DataBuffer`를 대상으로 클래스·속성·메서드·파라미터 정의만 로컬 진단에 기록합니다. 메서드 호출, 인스턴스 값 수집, OEM DLL 로드, 드라이버 설치는 이 단계에 포함하지 않습니다.

실제 커널·펌웨어 제어 코드는 별도의 명시적 사용자 승인과 모델 적합성·안전성 근거가 확보된 뒤에만 추가할 수 있습니다.
