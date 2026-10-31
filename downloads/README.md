# ATIV Battery Guard — Samsung Settings 앱 분석판

[새 실행용 ZIP 다운로드 페이지](ATIVBatteryGuard-SETTINGS-ANALYSIS.zip) · [현재 소스 ZIP](ATIVBatteryGuard-SOURCE.zip)

ZIP 페이지의 **Download raw file** 버튼으로 받을 수 있습니다.

1. 기존 프로그램을 닫고 새 실행용 ZIP을 새 폴더에 모두 압축 해제합니다.
2. `ATIVBatteryGuard.exe`를 실행합니다.
3. 아래쪽 **Settings 분석 파일 만들기**를 누릅니다.
4. EXE/DLL 복사본 포함 안내를 읽고 만들려면 **예**를 선택합니다.
5. 완료되면 **파일 위치 열기**를 누르고 가장 최근의 `samsung-analysis-*.zip`을 채팅에 첨부합니다.

위치나 파일을 확인하지 못해 점검 보고서만 포함된 ZIP이 만들어져도 그 ZIP을 전달하세요. 실제 충전 제한은 여전히 미지원입니다. 충전 명령을 추측해 호출하지 않습니다. 기존 WMI 정의 진단판은 사용자 노트북에서 창 실행, 62% 배터리 표시 및 정확한 삼성 클래스 정의 조회가 확인됐습니다.

이번 변경은 실제 Samsung Settings 앱의 EXE/DLL을 전용 설치 폴더에서 제한적으로 복사하는 기능입니다. 사용자 확인 전에는 추가 탐색·복사를 시작하지 않으며, 원본 파일 실행·설정 변경·자동 업로드는 없습니다. 설정·로그·개인 문서·드라이버는 복사하지 않습니다. 관리자 권한이나 코딩 도구는 필요하지 않습니다.

새 WPF 빌드는 경고·오류 0개, portable 회귀 테스트는 105개 통과·실패 0개·건너뜀 0개입니다. 새 Settings 파일 수집 기능의 실제 Windows 동작은 아직 미검증입니다. [변경 소스](../ATIVBatteryGuard)와 소스 ZIP도 이 브랜치에 보관합니다. 삼성 바이너리와 사용자 업로드 자료는 이 배포에 포함하지 않습니다. main과 클라우드 환경 구성은 변경하지 않았습니다.

| ZIP | SHA-256 |
|---|---|
| Settings 앱 분석판 | `ca8dbd05951cb646b5bc7cd687adda97617e01b448f32c3738426d8f710c1ed2` |
| 현재 소스 | `37fbe2ba47a00ba386a16ccde37ab7c45c16dbff7753fb14c2a0ae28518e8aa4` |

이전 `ATIVBatteryGuard-WMI-SCHEMA.zip`은 과거 진단판입니다. 이번 작업에는 위의 새 Settings 앱 분석판을 사용하세요.
