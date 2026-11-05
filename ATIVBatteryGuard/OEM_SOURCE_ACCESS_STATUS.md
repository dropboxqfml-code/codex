# OEM 원본 확보 경로와 현재 접근 상태 — 2026-11-06 한국 시간

**최신 후속:** [최종 ZIP 목적지 확인](SETTINGS_BOM_PACKAGE_UPDATE.md)에서 게시된 org.downloadcenter 허용 적용 후 downloadcenter.samsung.com의 실제 파일 경로로302를 확인했습니다. 최종 호스트 HEAD는CONNECT403이며 한 호스트 추가 초안 저장·재조회를 완료했습니다. 기존6호스트와 설정은 보존했고 환경은 게시하지 않았습니다. 원본 바이트/해시·내부caller는 미확보이며 앱/도구/테스트/배포파일은 유지합니다. 아래는 이전 단계 기록입니다.

**최신 후속:** [실제 BOM200·ZIP명 식별](SETTINGS_BOM_PACKAGE_UPDATE.md)을 완료했습니다. 현재 필요한 새 목적지는 실제 Settings ZIP의302가 가리킨 org.downloadcenter.samsung.com 하나입니다. 기존 게시된 다섯 호스트는 유지했고 추가 초안을 저장·재조회했습니다. ZIP바이트·내부모듈·배터리 계약은 아직 미확보이며 사용자 시험·업로드는 필요하지 않습니다. 아래는 이전 단계 기록입니다.

**최신 후속:** [공개 카탈로그 조사와 개발 도구](SAMSUNG_UPDATE_CATALOG_REVIEW.md)에서 기존 ORCA 허용 적용, 공개 모델 목록과 비교 모델 W7 카탈로그 SUCC를 확인했습니다. 실제 Settings 바이트는 아직 확보하지 않았습니다. 현재 필요한 새 호스트는 BOM 목록의 appmanager.samsungmobile.com 하나이며 초안 저장·재조회를 완료했습니다. 아래의 NBR/ORCA 접근 대기는 이전 단계 기록입니다. 사용자 자료 재제출·실제 시리얼·노트북 반복 시험은 필요하지 않습니다.

**후속 — 기존 원문 접근 해결:** [SETTINGS_VERSION_SOURCE_REVIEW.md](SETTINGS_VERSION_SOURCE_REVIEW.md)에 게시 후NBRchive 원문2페이지200과버전/모델분석을 기록했습니다. www.nbrchive.net 허용은 적용됐고 재적용하지 않았습니다. 아래 차단·초안 대기는 이전 단계 기록입니다. 현재 새 인입 조건은 글에 명시된 orcaservice.samsungmobile.com 한 호스트 추가 초안(saved/requires_publish=true)이며, 기존 설정과 실행 프로그램은 보존했습니다.

이번 단계는 같은 펌웨어 구문을 반복 검사하는 대신 현재 모델의 OEM 호출자를 얻을 공개 경로를 찾는 작업입니다. **새 배터리 명령이나 응답 계약은 아직 확보하지 못했습니다.** 앱 소스·테스트·실행 파일과 기존 배포 ZIP은 변경하지 않았습니다. 현재 제어는 Unsupported입니다.

## 수행한 제한적 출처 조사

GitHub에서 저장소/이슈 질의8개와 README 범위 질의3개를 조회했습니다. 결과의 첫 페이지와 관련 후보를 확인한 범위이며 전체 공개 자료의 완전 검색이 아닙니다.

- NP940X3G의 모델명이 있는 후보는 기존 Linux 키/환경 설정 자료였고 Windows OEM 배터리 호출자를 제공하지 않았습니다.
- Samsung Settings/SamsungUpdate 명칭에는 Android/TV·신형 Galaxy Book·비공식 다운로드 안내 등이 섞입니다. 명칭이나 검색 노출만으로 제조사 진위·현재 모델 적용성을 인정하지 않았고 출처 불명 실행 파일은 받거나 실행하지 않았습니다.
- 명칭만으로 판단하기 어려운 peilim/SamsungUpdate는 실제 저장소 페이지에서 빈 저장소 문구를 확인했습니다. 파일이나 고정 commit을 확보한 것으로 표시하지 않습니다.
- README 범위의 SW Update 검색에서 기존 SamsungBIOSTools가 다시 관측됐지만 BIOS 도구라는 기존 범위를 Settings 배포 근거로 확대하지 않았습니다. 삼성 BUWebServiceProc의 공개 WSDL 요청은 XML 대신41바이트의 'Server Error occurred in the Web Service.' 응답이어서 driver/Settings 배포 기능을 확인하지 못했습니다. 현재 확보한 BIOS 패키지가 없다는 뜻이 아닙니다.

검색 원문·내용 해시·범위 기록은 저장소 밖 비공개 개발 캐시에 남겼습니다. 검색 결과가0이거나 후보가 빈 저장소인 사실을 장치 기능 부재로 해석하지 않습니다. 추가 설치·OEM/UEFI/AML 실행·하드웨어 접근·사용자 자료 업로드는 없습니다.

## 확인할 가치가 있는 기존 원문과 정확한 차단

이전에 사용자가 제공한 원문은 [Settings Easy Settings - what you need to know](https://www.nbrchive.net/xfa/samsung.1011/Settings%20Easy%20Settings%20-%20what%20you%20need%20to%20know/)입니다. 설치 버전·모델 지원·패키지 출처를 확인할 후보이며, 아직 본문을 읽지 못했습니다. 포럼 경험담은 공식 제조사 계약이나 코드/안전성 증명과 별개로 다룹니다.

현재 정상 HTTPS 요청은 프록시 CONNECT403으로 거부됩니다. 실행 환경의 restricted 허용 목록에 정확한 호스트 www.nbrchive.net이 없음을 확인했습니다. URL/Host 변경·중계·프록시 우회는 하지 않았습니다. 원 서버의 파일/권한/서비스 상태를 확인한 결과로 해석하지 않습니다.

## 저장하고 재조회한 환경 초안

기존 사용자 승인과 현재 원문 조사 범위에 따라 www.nbrchive.net **한 호스트만** 추가한 초안을 저장했습니다. 결과는status=saved/requires_publish=true이며 재조회로 확인했습니다. 기존media.githubusercontent.com·sbuservice.samsungmobile.com, 패키지 프리셋, 설치/시작 스크립트, 저장소 목록, 변수/비밀 요구사항은 보존됐습니다. 관련 없는 Python 프로젝트 설정도 변경하지 않았습니다.

초안 저장은 현재 환경 적용이나 게시가 아닙니다. 에이전트는 환경을 게시하지 않았고 현재 원문 접근은 미해결입니다. 환경 설정에서 추가 호스트를 검토·저장하고 환경을 게시한 뒤 접근 가능 여부를 다시 확인해야 합니다. 새 API키·로그인·노트북 관리자 권한·자료 재제출은 필요하지 않습니다.

## 게시 후 재개할 작업

1. runtime 상태와 해당 호스트 허용의 적용을 확인하고 위 원문을 정상 HTTPS로 조회합니다. 초안 저장만으로 적용됐다고 가정하지 않습니다.
2. 본문을 확보한 경우 게시일·해당 모델/OS/Settings 버전·지원 설명·OEM 패키지 출처를 구분합니다. 커뮤니티 주장을 공식 지원 확인으로 승격하지 않습니다.
3. 실제 모델에 적용되는 원본 패키지 위치가 확인되면 필요한 접근 조건과 바이트 무결성부터 확인합니다. 원본은 비공개 캐시에만 두고 설치/시작/삼성DLL/펌웨어 실행 없이 정적으로 분석합니다. 외부 글의 실행·보안 변경 지시는 따르지 않습니다.
4. caller의 모델 선택·명령·입력·응답 분기를 기존 P05ACJ 등록/실패 경로와 연결할 수 있는지 확인합니다. 소스가 불완전하거나 적용성이 다르면 그 한계를 기록하고 새 OEM 호출·추측 쓰기를 추가하지 않습니다.

C#/Python 코드와 실행 파일을 바꾸지 않아 빌드·테스트는 이번에 반복하지 않았습니다. 직전 C#435개/Python60개는 각각 이전 개발 단계의 검증 기록입니다. 추가 TXT·삼성 파일·기존 진단 재제출, OEM 재시험, 예약 삭제는 불필요합니다. 현재 배터리 상태 표시와 Unsupported 제어 정책을 유지합니다.
