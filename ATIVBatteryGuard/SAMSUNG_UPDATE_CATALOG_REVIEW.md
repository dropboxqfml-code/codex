# 공개 모델 카탈로그 조회와 서비스 응답 구분 — 2026-11-06 한국 시간

**후속 완료:** [실제 BOM·Settings 파일명과 최종 목적지 확인](SETTINGS_BOM_PACKAGE_UPDATE.md)에서 게시된 appmanager 허용 적용과 XML2개200을 확인했습니다. Easy Settings2.0.0.89의 정확 ZIP명은 BASW-83876A21.ZIP입니다. 이어 org.downloadcenter 허용은 적용됐고 실제302가 최종 downloadcenter.samsung.com을 가리켜 그 한 호스트 추가 초안을 저장했습니다. 아래 BOM 접근 대기는 이전 기록입니다. ZIP바이트·내부모듈·배터리 계약은 아직 미확보입니다.

**사용자 시리얼 없이 삼성 공개 모델 검색과 비교 모델의 소프트웨어 카탈로그 조회에 성공했습니다.** 아직 Settings 원본 파일이나 현재 ATIV의 배터리 명령 계약을 확보한 것은 아닙니다. 개발용 오프라인 응답 검사기를 추가했으며 Windows 프로그램과 실제 충전 제어는 기존 상태를 유지합니다.

## 새로 확인한 공개 경로

게시된 환경의 `orcaservice.samsungmobile.com` 허용은 current/enforced 상태입니다. [이전 원문](SETTINGS_VERSION_SOURCE_REVIEW.md)에 나온 `http://orcaservice.samsungmobile.com/SWUpdate.aspx`의 정상 HEAD 요청은 HTTP302로 다음 파일을 가리켰습니다.

- 호스트: `org.downloadcenter.samsung.com`
- 파일명: `SamsungUpdate_2.2.9.50_2.ZIP`
- 용도: Samsung Update 도구의 배포 파일. Settings 2.2나 배터리 호출자 파일로 동일시하지 않습니다.

리다이렉트 대상의 HTTPS CONNECT는403이었고 파일 바이트·서명·내부 코드는 확보하지 않았습니다. 이 도구를 실행하는 대신 다음의 고정 공개 프로토콜 기록을 정적으로 읽었습니다.

| 출처 | 고정 버전과 범위 |
| --- | --- |
| [qt-kaneko/su-downloader README](https://github.com/qt-kaneko/su-downloader/blob/94f425236760721adcf50ecb0d355eb22c952500/README.md) | commit `94f425236760721adcf50ecb0d355eb22c952500`; README SHA-256 `62e6378dca64b62e2c033984bea53e1a54a9ae0b10794675ef0198f5f1e4b536`. 공개 모델명 → 공개 ModelCode → 구형 카탈로그 요청을 설명하는 제3자 자료 |
| [suddenBook/samsung-galaxy-book-updates](https://github.com/suddenBook/samsung-galaxy-book-updates/tree/e46a5afa5830f8c852ad3ea9bf722eb209ff8a46) | commit `e46a5afa5830f8c852ad3ea9bf722eb209ff8a46`; 검토 Python SHA-256 `82af758aecd610ba59e24860522f955f497ebbe3a7540cc42f2b81a389afda89`. 실제 장치 시리얼을 보내는 현대 클라이언트여서 실행하지 않음 |

첫 출처의 SOAP endpoint는 `https://orcaservice.samsungmobile.com:10443/downloadcenter.asmx`, namespace는 `http://orcaservice.samsungmobile.com/`입니다. 공개 모델명을 넣는 `GetModelListBykeyword`, `GetSupportedOSList`, `GetModelCode`를 사용했습니다. 공개 검색에서 서버가 반환한 ModelCode만 후속 `api/ORCAHDMInfo`의 `SN` 필드에 넣었습니다. **필드명이 SN이어도 이번 값의 출처는 공개 모델 조회이며 사용자의 실제 시리얼·DMI·WMI·UUID가 아닙니다.** 그 값이나 원본 응답의 식별자·URL은 보고서와 ZIP에 넣지 않습니다.

카탈로그 요청은 구형 문서의 `XMLVERSION=3.0`, `CLIENTVERSION=3.0.108.0`, 빈 REGION/LANG/ETC, `TESTMODE=NONE` 형식을 유지했습니다. 현대 클라이언트의 실제 시리얼 조회, API 버전과 OS 조건을 섞지 않았으며 해당 클라이언트나 Samsung Update를 실행하지 않았습니다. 이 서버 메타데이터 요청은 노트북의 OEM/WMI 메서드 실행과 별개입니다.

## 실제 응답과 해석 범위

아래 요청은 모두 HTTP200을 받았지만 서비스 성공 여부는 달랐습니다.

| 요청 | 서비스 결과 | 확정할 수 있는 내용 |
| --- | --- | --- |
| 모델 검색 `NP940X3G` | SOAP ResultCode0, 고유 파생 모델116개 | 공개 목록에 `NP940X3G-K03FR` 포함. 현재 사용자 장치의 판매 접미사를 알아낸 결과는 아님 |
| 위 목록의 `NP940X3G-K03FR` 모델 코드 조회 | ResultCode0, 공개 코드1개 | 익명 공개 모델 식별 경로 동작 |
| 전체 모델명 및 기본 `NP940X3G`의 지원 OS 조회 | ResultCode404 | 이번 조건에서 OS 목록을 얻지 못함. 두 응답은 바이트가 같아 독립적인 부재 근거 두 건으로 세지 않음 |
| 위 공개 코드, OS W8 카탈로그 | JSON ResultFAIL / FailCode404 | HDM/PATCH/ADDSW null. 응답의 OS·CLIENTVERSION도 null이므로 요청 조건이 서버에서 수락·반영됐다고 주장하지 않음 |
| 모델 검색 `NP930X5J` | ResultCode0, 고유 파생 모델36개 | 원문 비교 후보 `NP930X5J-S02US` 포함. 전체 접미사를 keyword로 넣은 별도 검색은404였음 |
| 위 비교 모델의 코드 조회 및 OS W7 카탈로그 | 코드 조회0; JSON ResultSUCC | HDM.ITEM 메타데이터2개. 응답 OS W7·CLIENTVERSION3.0.108.0 확인 |

비교 카탈로그의 두 항목은 ID/HASHCODE/FURL을 가진 **목록 XML의 위치 정보**입니다. 실제 FURL 호스트는 `appmanager.samsungmobile.com`, 확장자는 XML입니다. 아직 XML을 읽지 못했으므로 Settings2.0.0.89의 포함 여부·버전·직접 ZIP 주소·파일 바이트·SHA-256은 미확정입니다. 항목의 HASHCODE를 원본 파일의 암호학적 무결성 검증으로 간주하지 않습니다.

`NP930X5J-S02US`는 비교용 모델이며 현재940X3G/930X3G와 다릅니다. 공개 카탈로그의 존재는 해당 모델에서 현재 충전이 제어된다는 증거가 아닙니다. 반대로 현재 계열의 이번404는 카탈로그 전체 삭제, 장치 미지원, 배터리 보호 기능 부재, 과거FF의 원인이나 충전 제한 불가능을 뜻하지 않습니다. 요청 OS는 당시 배포 원문과 구형 프로토콜 기록을 근거로 정했고 OS·클라이언트 버전의 무차별 대입이나 실제 시리얼 경로 전환은 하지 않았습니다.

원본 응답과 인입 조건은 저장소 밖 비공개 캐시에 보존했습니다. 재현 시 응답 내용이 바뀔 수 있으므로 관측 바이트를 다음처럼 구분합니다. SHA-256은 로컬에서 받은 바이트를 식별하며 제조사 서명·현재 모델 적용성을 보증하지 않습니다.

| 관측 응답 | 바이트 | SHA-256 |
| --- | ---: | --- |
| NP940X3G 모델 검색 | 5,524 | `5ded21cea2a453b763384c2c89c1e580d9065cf20a23925f8be3e466b7dd628b` |
| NP940X3G OS404 | 491 | `84e0b17518ee9a5b32cc4054767b4f60fce2f4fecc700bd4003d46a577e7cd5b` |
| NP940X3G 공개 코드 조회 | 492 | `8682efebb30fea8521f12ad3c8b0f26e2c4151002366fddbcbb19f974a48d81c` |
| 위 코드 W8 카탈로그 FAIL404 | 280 | `0751e20724c896875a035b4a1c2991ffd0b7f6617ed247bb94206451e6c91fa1` |
| NP930X5J 모델 검색 | 2,084 | `7282ecdc5b7021a40fb2a4ceae63e18ee067f2b69d56569281dd67e3c42dc565` |
| NP930X5J-S02US 공개 코드 조회 | 492 | `b6e932ee5b229a9fd58049cd5f27d31584e156051a176e7cb271bf6ff3e0829c` |
| 위 비교 코드 W7 카탈로그 SUCC | 555 | `071bc22523b9493ff591b7151c2b988576eaa46ef312b2fe982b8791122ad683` |

## 구현

개발용 [inspect_samsung_update_response.py](scripts/inspect_samsung_update_response.py)는 저장된 응답을 stdin으로만 읽습니다. 네트워크·파일 경로 인자·장치 정보 수집·OEM 실행은 없습니다. 개발자가 실제 HTTP 상태를 `--http-status`로 전달하며 도구 자체가 네트워크 상태나 출처 진위를 확인한 것으로 표시하지 않습니다.

```text
python3 scripts/inspect_samsung_update_response.py --kind catalog --http-status 200 < saved-response.json
```

사용자 노트북에서 이 명령을 실행하거나 응답 파일을 제출할 필요는 없습니다. `models`, `os`, `model-code`, `catalog` 종류별 예상 응답만 처리하며 경로·원문 값·ModelCode/SN·URL·예외 원문을 출력하지 않습니다. 출력은 고정 상태, HTTP/서비스 코드, 바이트 수·해시, 항목 수와 모두 false인 진위·현재 모델·배터리 계약·하드웨어 권한 표식입니다.

| 상태 | 뜻 |
| --- | --- |
| TransportRejected | 호출자가 전달한 HTTP 상태가200이 아님. 서비스 파싱하지 않음 |
| ServiceRejected / SoapFault | HTTP200이어도 해당 작업의 서비스 코드가 실패하거나 SOAP Fault |
| Completed / CompletedEmpty | 예상 구조와 서비스 성공을 확인했고 항목이 존재하거나 명시적으로 비어 있음. 기능 존재·부재 판정은 아님 |
| NoPrimaryCatalog | JSON SUCC이지만 HDM null. 명시적 ITEM 빈 목록과 구분 |
| InvalidResponse / LimitExceeded | 파싱·형식·모호함 오류 또는 상한 초과. 부분 성공 수치를 남기지 않음 |

SOAP namespace·Envelope/Body·작업별 Response/Result·ResultInfo의 단일성을 확인하고 ResultCode0만 성공으로 처리합니다. JSON은 중복 키를 거부하고 ResultFAIL에 남아 있는 목록을 세지 않습니다. SUCC의 HDM.ITEM은 예상 단일 객체/목록과 FURL 구조를 확인합니다. ID/HASHCODE의 형식·암호학적 검증은 수행하지 않습니다. 원본 FURL을 따라가거나 HASHCODE를 파일 서명으로 승격하지 않습니다.

입력 상한2MiB, 깊이32, 노드8192, 항목2048입니다. stdin은 cap+1로 읽고 초과 입력은 해시하지 않습니다. JSON은 바이트·깊이를 먼저 확인한 뒤 파싱 결과의 노드를 세므로 노드 수에 해당하는 할당 전에 차단했다고 주장하지 않습니다. DTD/entity를 거부하며 잘린 입력·중복 XML/JSON·과도한 깊이·실패 응답의 잔여 항목을 전체 실패로 처리합니다. 입력이 유효해도 배터리 제어 권한을 만들지 않습니다. 테스트는 원본 서버 응답을 포함하지 않는 합성 fixture만 사용합니다.

## 현재 접근 초안과 다음 작업

실제 카탈로그에 포함된 BOM 주소의 정상 HEAD는403이었고 현재 restricted 목록에는 `appmanager.samsungmobile.com`이 없습니다. 정확한 차단 응답과 정책 상태를 비공개로 기록했습니다. 이 응답만으로 원 서버의 목록 삭제나 권한 상태를 확정하지 않습니다.

**`appmanager.samsungmobile.com` 한 호스트만 추가하는 초안**을 저장·재조회했습니다(status=saved/requires_publish=true, revision3). 기존에 게시된 네 호스트, 프리셋, 설치/시작 스크립트, 저장소, 변수·비밀 요구사항은 보존했습니다. 이번 단계 초반에 bootstrapper용으로 잠시 추가했던 미게시 `org.downloadcenter.samsung.com`은 원본 목록 직접 경로가 확인돼 초안에서 제외했습니다. 기존 게시 설정을 제거한 작업이 아닙니다. 환경은 게시하지 않았고 초안 저장을 현재 접근 허용으로 보고하지 않습니다.

1. 사용자가 환경 설정에서 추가 호스트를 검토·저장하고 환경을 게시한 뒤 적용 상태와 해당 XML 두 개의 정상 접근을 확인합니다.
2. XML의 길이/해시/구조를 확인하고 Easy Settings/Settings의 정확한 버전·파일명·OS·모델 연결을 기록합니다. 비교 버전이 목록에 실제로 있는지부터 확인하며 추측 URL을 만들지 않습니다.
3. 적용할 원본이 확인되면 비공개 캐시에서만 컨테이너·모델 선택·배터리 caller·응답 분기를 정적으로 조사합니다. OEM 원본의 설치·DLL 로드·실행은 하지 않습니다.
4. 현재 모델 caller → 전송 → P05ACJ 처리자 → 응답 의미를 연결할 근거가 생긴 부분만 순수 명세에 반영합니다. 비교 모델 정보만으로 제어 어댑터나 새 OEM 요청을 추가하지 않습니다.

## 검증과 사용자 프로그램

새 응답 검사기14개를 포함한 **전체 Python74개 테스트가 통과**했습니다. 서비스 성공/거부·SOAP Fault·명시적 빈 목록/null·중복/모호함·잘린 입력·byte/depth/node/record 상한·오류 원문 비노출·stdin cap+1을 검증했습니다. 독립 읽기 전용 코드 리뷰에서도 중요한 결함은 발견되지 않았습니다.

재현 명령: `python3 -m unittest discover -s scripts -p 'test_*.py' -v`.

실제 저장 응답8개를 검사기에 넣어 모델116/36개·공개 코드 각1개·OS404 두 응답·W8 FAIL404·W7 SUCC2를 원문 비노출로 대조했습니다. OS404 두 응답은 동일 바이트이므로 별개의 부재 근거가 아닙니다. 원본 응답·OEM 바이너리·HTML은 소스 ZIP에서 제외합니다. C# 소스와 Windows EXE는 변경하지 않았으므로 이번에 C# 빌드·435개 테스트를 다시 수행한 것으로 보고하지 않습니다. 435개는 직전 C# 검증 기록입니다.

새 개발 소스는 [소스 ZIP](../downloads/ATIVBatteryGuard-UPDATE-CATALOG-SOURCE.zip)과 [체크섬](../downloads/ATIVBatteryGuard-UPDATE-CATALOG-SHA256SUMS.txt)으로 제공합니다. 이 ZIP은 Windows 실행 프로그램 교체판이 아니며 기존 프로그램과 함께 풀 필요가 없습니다. 기존 CALLER-CONTRACT-REVIEW 프로그램과 다운로드 파일은 보존합니다.

현재 배터리 상태 표시는 유지되고 실제 충전 제어는 **Unsupported**입니다. 새 노트북 실행·관리자 비교·TXT/DLL/EXE 재제출·Samsung Update 실행/Export·시리얼 제공·완료된 OEM 실험 반복은 필요하지 않습니다. 일회 예약 표식과 모든 하드웨어 안전 경계를 유지합니다.
