# ATIV Battery Guard — Sabi3 연동 준비 및 함수 참조 분석판

[현재 실행용 ZIP](ATIVBatteryGuard-SABI3-PREPARATION.zip) · [현재 자체 소스](ATIVBatteryGuard-SOURCE.zip) · [실제 관측과 구현 범위](../ATIVBatteryGuard/SABI3_COMPATIBILITY_REVIEW.md)

사용자 TXT에서 Sabi3 3.2.0.0 x64/x86과 예상 함수 이름을 확인했습니다. 현재 버전은 파일별 DLL 이름뿐 아니라 실제 정적 import 함수의 이름 또는 ordinal을 읽고 x64 후보를 해시로 구분합니다. 초기화·장치·동적 로드 관련 함수 이름의 참조를 따로 표시하며 실제 호출로 해석하지 않습니다.

기존 앱을 닫고 새 ZIP을 새 폴더에 모두 압축 해제한 뒤 ATIVBatteryGuard.exe를 실행합니다. 아래쪽 **삼성 파일 정보 만들기**를 누르고 **정보 파일 위치 열기**에서 새 `samsung-files-*.txt`를 확인합니다. 추가 분석 결과로 사용할 파일은 이 TXT이며 삼성 DLL·EXE를 옮기거나 전달할 필요는 없습니다.

삼성 DLL 로드·초기화·OEM 조회·충전 제어는 실행하지 않습니다. 함수 이름 일치는 ABI나 해당 모델의 실제 설정 조회 성공을 뜻하지 않습니다. 실제 80%/100% 충전 제어는 계속 미지원입니다.

이번 변경의 공유 소스 테스트173개 통과·실패0개·건너뜀0개, 실제 x64 net48 WPF/XAML 빌드 경고·오류0개입니다. 별도 Python 배포 검증 테스트6개도 통과했습니다. 이전 식별 기능의 실기 결과는 확인했으나 새 함수 참조 분석과 준비 판정의 Windows 실행은 아직 미검증입니다. 원본 사용자 TXT·삼성 바이너리·외부 문서 원본은 배포에 포함하지 않습니다.

| ZIP | SHA-256 |
| --- | --- |
| 실행용 | `2c9bd2d5bd73a54b2cbab189072d26b2656673eda917fa420e39e67acd11d325` |
| 소스 | `b2fca188e8858048a038aadb85f7154777efb9d424e652a8e10cb2772c46e409` |

사용자 요청에 따라 DLL 식별 결과를 바탕으로 개발을 재개했습니다. 개발 미리보기의 서명 여부는 BUILD-INFO에 실제값으로 기록하며 명시적인 Windows 배포 검증 도구도 보관합니다. main과 환경 게시 상태는 변경하지 않았습니다.
