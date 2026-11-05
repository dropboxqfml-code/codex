# Settings 비교 원본 식별과 BOM 검사 — 2026-11-06 한국 시간

**실제 삼성 BOM 두 개에서 Easy Settings for Win7 2.0.0.89와 정확한 파일명 `BASW-83876A21.ZIP`을 확인했습니다.** 포럼의 버전 단서를 공개 배포 목록에 연결했습니다. ZIP 자체는 아직 확보하지 못해 내부 Win8 Settings·배터리 호출자·현재 ATIV 적용성은 미확정입니다.

## 게시 후 접근과 관측 원본

새 환경에서 명령 실행, runtime current/running, 네트워크 enforced와 `appmanager.samsungmobile.com` 허용을 확인했습니다. 기존 설정을 다시 적용하지 않고 [직전 카탈로그](SAMSUNG_UPDATE_CATALOG_REVIEW.md)의 실제 FURL 두 개를 정상 요청으로 읽었습니다. 두 응답은 HTTP200이며 원본과 접근 기록은 저장소 밖 비공개 캐시에만 보존했습니다.

| 원본 | 바이트 | SHA-256 | 직접 Item / 전체 XML 노드 / 깊이 |
| --- | ---: | --- | --- |
| BOM0 | 426,679 | `ac93fcf335218ad1a5b34cb57a92b58a2fb9e67be3d415683c229bac79848f46` | 40 / 7,126 / 6 |
| BOM1 | 488,124 | `116e0e2d84bd44d2d4024bd10c17f281b78717e61a03e6e3fad094c55d6509dc` | 45 / 8,271 / 6 |

둘 다 `MaxList` 아래 직접 `Head`와 `Item`을 갖습니다. Header의 모델은930X5J이며 OS는 각각W7PR64와DONCR입니다. DONCR의 의미는 이번 응답만으로 확정하지 않습니다. 둘 다 `Test=Yes`를 포함하지만 이는 배포 메타데이터의 값이며 프로그램 시험 통과나 사용자 노트북 검증을 뜻하지 않습니다.

930X5J는 현재940X3G/930X3G와 다른 비교 모델입니다. 공개 모델 검색에서 받은 코드만 사용했으며 사용자 시리얼·DMI·장치 고유 식별자를 수집하거나 전송하지 않았습니다. 원본 BOM 주소·식별자·설치 경로·명령 인수는 보고서와 배포 ZIP에 넣지 않습니다.

## 정확한 비교 패키지와 남은 구분

| 필드 | 양쪽 목록의 관측 |
| --- | --- |
| DisplayName | Easy Settings for Win7 2.0.0.89 |
| Version / VerifyAttribute | 2.0.0.89 |
| CheckType | FileVer |
| 직접 FURL | ORCA의 FileDownloader.aspx, FILENAME=`BASW-83876A21.ZIP` |
| InstallFile | Inst.exe |
| InstallOrgFileSize / InstallFileSize | 131,598,830 / 126,414,820 |

두 Settings 항목은 전체 XML 내용까지 같고 같은 다운로드 위치를 가리킵니다. 이를 독립적인 바이너리 두 개의 증거로 세지 않습니다. FileVer/VerifyAttribute는 버전 검사 메타데이터이며 원본 ZIP의 SHA-256이나 제조사 서명 검증이 아닙니다. 두 크기 필드도 실제 수신 ZIP 길이로 단정하지 않습니다.

SubItemInfo에는 Settings.exe 이름에 관한 메타데이터가 있지만, 이 목록을 읽는 것만으로 실제 파일 바이트나 내부 Win8 모듈을 확보한 것은 아닙니다. 외부 Win7용 Easy Settings와 포럼이 언급한 내부 Win8용 Settings를 분리한 채, ZIP을 읽은 뒤 아키텍처·버전·파일 해시와 실제 구성을 확인해야 합니다. Inst.exe와 설치 인수는 실행하지 않습니다.

항목40/45개 중 비어 있지 않은 직접 FURL은25/30개입니다. 각 목록에는 FURL 필드 자체가 없는 항목15개와 빈 Version17개도 있습니다. 원본 위치 없는 메타데이터를 파싱 오류나 목록 전체의 부재로 처리하지 않습니다. 목록에 Settings가 있다는 사실은 현재 ATIV의 충전 보호 지원이나 명령 계약을 입증하지 않습니다.

## 실제 ZIP 인입과 환경 초안

ORCA의 실제 파일 링크는 HTTP302로 `org.downloadcenter.samsung.com`의 ContentsFile.aspx를 가리켰으며, 목적지 VPath의 파일명도 `BASW-83876A21.ZIP`입니다. 초기 GET은 허용 목록 밖 리다이렉트에서 중단했고, 같은 원본의 HEAD로 목적지를 기록했습니다. 목적지 HTTPS HEAD는 프록시 CONNECT403이었습니다. ZIP 바이트·길이·해시·서명은 아직 미확보이며 원 서버의 파일 삭제로 해석하지 않습니다.

실제 Settings ZIP 목적지를 근거로 **`org.downloadcenter.samsung.com` 한 호스트만 추가한 초안**을 저장·재조회했습니다(status=saved/requires_publish=true, revision2). 기존에 게시된 다섯 호스트·프리셋·설치/시작 스크립트·저장소·변수/비밀 요구사항은 보존했습니다. 환경은 게시하지 않았고 초안 저장만으로 접근이 허용됐다고 주장하지 않습니다. 프록시·TLS 검증을 유지하며 중계·대체 Host·임의 URL 추측은 사용하지 않습니다.

사용자가 환경 설정에서 추가 호스트를 검토·저장하고 환경을 게시하면 다음 순서로 재개합니다.

1. 현재 runtime과 새 호스트 허용 적용을 확인하고 기록된 실제 목적지를 정상 요청으로 읽습니다. 메타데이터 크기를 정답으로 가정하지 않고 수신 길이·SHA-256·컨테이너를 확인합니다.
2. 비공개 캐시에서만 ZIP과 내부 컨테이너를 정적으로 읽고 외부 Win7/내부 Win8 모듈, 관련 EXE/DLL의 아키텍처·버전·해시를 고정합니다. 삼성 코드를 로드/설치/실행하지 않습니다.
3. 배터리 UI에서 실제 getter/setter, 모델/OS/펌웨어 가드, 선택된 전송 DLL·ABI·입력·응답 분기·실패 fallback을 추적합니다. 지원 검사 전에 쓰기가 실행되는 시작 경로도 조사합니다.
4. 적용 가능한 호출자 계약을 기존 P05ACJ 처리자·등록·공통 실패 경로와 대조합니다. 비교 모델이나 메뉴 문자열만으로 보호 상태 디코더·충전 제어를 추가하지 않습니다.

## 구현한 오프라인 BOM 검사

[개발용 응답 검사기](scripts/inspect_samsung_update_response.py)에 stdin 전용 `--kind bom`을 추가했습니다. 네트워크 요청이나 경로 입력을 추가하지 않았습니다.

```text
python3 scripts/inspect_samsung_update_response.py --kind bom --http-status 200 < saved-bom.xml
```

`MaxList`·직접 Head·Item과 Model/OS/DisplayName/Version/FURL의 지원 구조를 확인하고 항목 수, 비어 있지 않은 직접 다운로드 위치 수, 정확한 비교 DisplayName/Version에 맞는 후보 수만 보고합니다. 전체 BOM 스키마를 검증하거나 설치 조건을 해석하지 않습니다. 후보 수는 문자열 메타데이터 일치이며 파일 확보·모델 지원·충전 가능성 검증이 아닙니다. missing/empty FURL은 위치 없는 항목으로 허용하고 중복 core 필드·복잡한 값·잘못된 위치는 전체 실패로 처리합니다. 실제 레이블에 포함된 XML 줄바꿈·탭은 허용하며 URL 내부의 공백·제어 문자는 계속 거부합니다.

새 BOM 전용 상한은 **노드16,384·깊이16·Item256개**입니다. 입력2MiB/stdin cap+1, DTD/entity 거부, 원문·식별자·URL·설치 인수·예외 비노출, 실패 시 부분 수치 폐기를 유지합니다. 기존 SOAP/JSON의 노드8192·깊이32·항목2048 상한은 유지합니다. 실제 BOM1의8271노드를 지원하려고 기존 검사 범위를 확대하지 않았습니다.

새 보고 필드는 `bomDownloadLocatorCount`, `comparisonSettingsCandidateCount`이며 전체 BOM 검사가 성공한 뒤에만 채웁니다. 진위·현재 장치/모델·원본 파일 무결성·배터리 계약·기능 부재 추론·하드웨어 읽기/호출/쓰기·네트워크·OEM 실행 플래그는 모두false입니다. 메타데이터의 설치 경로·명령·조건을 평가하지 않으며 locator를 따라가지 않습니다.

## 검증과 사용자 프로그램

새 BOM 테스트11개를 포함한 **전체 Python85개가 통과**했습니다. 두 BOM의 전체 항목40/45·위치25/30·후보1/1·해시를 대조했고 기존 SOAP/JSON 실제 응답8개를 포함해 총10개 응답의 분류·수치를 확인했습니다. BOM1을 기존 SOAP 종류로 넣으면 기존8192노드 상한으로 거부되는 것도 확인했습니다. 원문 값·URL·모델명은 검사 결과에 포함되지 않고 모든 권한 플래그는false입니다.

합성 검증은 missing/empty·레이블 줄바꿈/URL 내부 줄바꿈 구분·정확 후보 조건·core 중복/잘린 입력/후반 오류·노드/깊이/Item 경계·stdin cap+1·오류 원문 비노출·기존 범위 유지를 포함합니다. 독립 읽기 전용 코드/자료 검토와 차이·문자 검사도 완료했습니다. 재현 명령은 `python3 -m unittest discover -s scripts -p 'test_*.py' -v`입니다.

테스트 fixture에는 합성 XML만 사용하고 실제 BOM·Settings 원본·HTML은 저장소와 배포물에서 제외합니다. C# 소스와 Windows EXE는 변경하지 않았으므로 C#435개는 직전 검증 기록이며 이번 빌드/테스트 실행 수치로 제시하지 않습니다.

[새 개발 소스 ZIP](../downloads/ATIVBatteryGuard-SETTINGS-BOM-SOURCE.zip) · [체크섬](../downloads/ATIVBatteryGuard-SETTINGS-BOM-SHA256SUMS.txt)은 개발 검토용입니다. 기존 실행 프로그램을 그대로 사용하고 소스 ZIP을 실행 폴더에 함께 풀 필요가 없습니다. 기존 ZIP은 보존합니다.

실제 충전 제어는 **Unsupported**입니다. 배터리 현재 상태 표시는 유지합니다. 추가 노트북 시험·관리자 비교·TXT/DLL/EXE 재제출·Samsung Update 실행/Export·시리얼 제공·OEM 재호출·실험 예약 표식 삭제는 필요하지 않습니다. 하드웨어 안전 경계를 유지합니다.
