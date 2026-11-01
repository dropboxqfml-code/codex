# ATIV Battery Guard — 삼성 파일 정보 확인판

[현재 실행용 ZIP](ATIVBatteryGuard-SAMSUNG-FILE-INFO.zip) · [현재 자체 소스](ATIVBatteryGuard-SOURCE.zip) · [기능과 검증 한계](../ATIVBatteryGuard/SAMSUNG_FILE_INSPECTION.md)

기존 앱을 닫고 새 ZIP을 새 폴더에 모두 압축 해제한 뒤 ATIVBatteryGuard.exe를 실행합니다. 창 아래쪽 **삼성 파일 정보 확인 → 삼성 파일 정보 만들기**를 누르고 **정보 파일 위치 열기**에서 새 `samsung-files-*.txt`를 확인합니다. 후속 분석에는 이 TXT를 사용하며 삼성 DLL·EXE나 폴더 전체는 전송할 필요가 없습니다.

Program Files (x86)의 Samsung\Setting 및 Samsung\Settings와 제한된 하위 폴더에서 Sabi3.dll, wsabi.dll, BatteryToast.exe, PowerAudit.exe만 확인합니다. 버전·PE 구조·오프라인 내장 서명·SHA-256·정적 DLL 참조·내보낸 함수 이름을 읽습니다. 원본 파일을 복사·로드·실행하거나 초기화·제어 함수를 호출하지 않습니다.

서명은 WinVerifyTrust의 로컬 캐시만 사용합니다. 온라인 폐기 확인과 카탈로그 서명은 별도 미확인입니다. 관리 코드의 실제 비트 수, 지연·동적 로드와 P/Invoke·어셈블리 참조·프로세스 간 통신을 모두 분석한 결과는 아닙니다. 정보·함수 이름·서명 성공은 실제 충전 제어의 지원 근거가 아닙니다.

새 기능은 버튼을 선택했을 때만 자체 보조 모드로 실행합니다. 10초 제한과 종료 요청 후 1초 대기, 단일 프로세스 슬롯, 최대 512 KiB의 엄격한 결과 형식을 적용합니다. 전체 설치 경로·사용자 이름·시리얼번호·예외 원문은 결과에 포함하지 않습니다. 자동 전송하지 않습니다.

이번 변경에서 테스트 **158개 통과·실패 0개·건너뜀 0개**, 실제 WPF/XAML x64 net48 빌드 경고·오류 0개를 확인했습니다. 실행 파일의 일반 권한 manifest, BAML, 새 검사 타입 포함과 기존 수집기·벤더 DLL 호출 부재도 정적으로 검사했습니다. **새 파일 정보 기능의 Windows 실기 실행은 아직 미검증입니다.** 실제 80%/100% 충전 제어는 계속 미지원입니다.

| ZIP | SHA-256 |
| --- | --- |
| 실행용 | `ba3cd178efab6d73e564171594c3fcaa76e6c23c1969799744307c6954f92e3c` |
| 소스 | `4227fe7950acb78936cdb819feee11ecbe6353f002509e50a1a5a6527d089be4` |

배포에는 자체 앱·소스·연구 요약만 포함합니다. 삼성 원본 파일·사용자 업로드·외부 문서 원본은 포함하지 않습니다. main과 환경 게시 상태는 변경하지 않았습니다. 이전 ZIP은 과거 기록입니다.
