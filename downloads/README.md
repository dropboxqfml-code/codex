# ATIV Battery Guard — 삼성 WMI 정의 진단판

[실행용 ZIP 다운로드 페이지](ATIVBatteryGuard-WMI-SCHEMA.zip) · [복원 소스 ZIP](ATIVBatteryGuard-SOURCE.zip)

ZIP 파일 페이지의 **Download raw file** 버튼으로 다운로드할 수 있습니다. 실행용 ZIP을 새 폴더에 모두 압축 해제하고 `ATIVBatteryGuard.exe`를 실행하세요. 코딩 도구나 관리자 권한은 필요하지 않습니다.

1. ‘읽기 전용 진단’에서 **진단 파일 만들기**를 누릅니다.
2. 완료되면 **진단 파일 위치 열기**를 누릅니다.
3. 가장 최근의 `diagnostics-*.txt` 파일을 채팅에 첨부합니다.

이번에는 삼성 분석 ZIP을 다시 만들 필요가 없습니다. 실제 충전 제한은 아직 미지원입니다. 배터리 0%는 Windows가 보고하는 실제 값으로 유지합니다. 새 기능은 정확한 삼성 WMI 클래스의 정의만 읽으며 DLL이나 OEM 메서드를 호출하지 않습니다.

실제 .NET Framework 4.8 x64 WPF 빌드는 경고·오류 0개, 새 portable 회귀 테스트는 78개 통과·실패 0개·건너뜀 0개입니다. 새 빌드의 Windows GUI와 실제 노트북 WMI 조회는 아직 미검증입니다.

이 브랜치에는 복원한 수정 가능한 [앱 소스](../ATIVBatteryGuard)와 소스 ZIP도 보관합니다. 이전 원본 주석/테스트의 완전 복구가 아니라 자체 배포본에서 C#을 복원하고 XAML·프로젝트·테스트를 재구성한 코드입니다. OEM 바이너리나 사용자 업로드 자료는 포함하지 않습니다. main 및 클라우드 환경 구성은 변경하지 않았습니다.

| ZIP | SHA-256 |
|---|---|
| 실행용 | `80b97773081de48197574d82a413f67b8fc76a2e8a4bbabe7cf2d400dee53e3b` |
| 소스 | `71acfb5c8a4da178afa9bf51be9b4c4009d37700f060621cedceeadeaa6cd6ff` |
