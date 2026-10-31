# ATIV Battery Guard — Windows 배터리 읽기 전용 조회판

[현재 실행용 ZIP](ATIVBatteryGuard-WINDOWS-BATTERY-QUERY.zip) · [현재 소스](ATIVBatteryGuard-SOURCE.zip) · [구조·출처·검증 기록](../ATIVBatteryGuard/WINDOWS_BATTERY_QUERY.md)

삼성 DLL을 추출하지 않고 Microsoft의 표준 배터리 조회로 Windows 드라이버의 BatteryCharge/BatteryDischarge 요청 지원 비트를 읽습니다. 이 지원 표시는 80% 상한 설정이나 충전 제한 성공의 증거가 아닙니다. 실제 제어는 계속 미지원입니다.

새 버전을 사용할 경우 기존 앱을 닫고 ZIP을 새 폴더에 모두 압축 해제한 뒤 ATIVBatteryGuard.exe를 실행합니다. 기존 **진단 파일 만들기**로 생성한 diagnostics TXT의 **Windows 표준 배터리 드라이버의 요청 지원 여부** 섹션에서 결과를 확인할 수 있습니다. 삼성 실행 파일이나 DLL을 보낼 필요가 없습니다.

GENERIC_READ, QUERY_TAG(대기 0), QUERY_INFORMATION(BatteryInformation)만 사용합니다. SET 요청이나 OEM 메서드는 호출하지 않습니다. 자체 보조 프로세스에 10초 제한을 적용하고 최대 8개 인터페이스만 확인합니다. 장치 경로·태그·시리얼번호·고유 ID는 결과에 포함하지 않습니다. 보조 조회는 상세 진단 버튼을 선택했을 때만 실행합니다.

회귀 테스트 130개 통과·실패 0개·건너뜀 0개, WPF 빌드 경고·오류 0개입니다. 실행 파일의 x64/net48/BAML/일반 권한 manifest와 OEM 수집 타입 부재·새 조회 타입 포함을 확인했습니다. 새 기능의 실제 Windows 장치 조회는 아직 미검증입니다. 코드 검토와 Linux 테스트가 하드웨어 동작 검증을 대신하지 않습니다.

배포에는 자체 앱·소스·연구 요약만 들어 있으며 삼성 원본 파일·사용자 업로드·외부 문서 원본은 포함하지 않습니다. main과 게시된 환경은 변경하지 않았습니다.

| ZIP | SHA-256 |
|---|---|
| 실행용 | `4a814e66062d2c32c98cbb6e75af20c66fb8edc48723420f1a59bf91ab244f87` |
| 소스 | `20003da93f843a854c866c8130ba81fc52f37809a9ecb96e9968be572ec507d7` |

이전 ZIP은 과거 기록입니다. 현재 사용할 파일은 위 Windows 배터리 조회판입니다.
