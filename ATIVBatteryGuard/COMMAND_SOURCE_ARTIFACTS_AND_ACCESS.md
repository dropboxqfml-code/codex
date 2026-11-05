# 배터리 명령 원본 후보·접근 조건 — 2026-11-05 한국 시간

## 이번에 구체화한 두 원본 후보

일반화된0x65/0x66/FF 설명 이미지는 적용하지 않습니다. [동일 모델·BIOS의 공개 ACPI 분석](P05ACJ_BATTERY_COMMAND_EVIDENCE.md)에 이어, 배터리 호출자와 관련 펌웨어 처리 근거를 얻을 원본 후보를 고정했습니다. 아래는 패키지 위치와 메타데이터의 확인이며 아직 패키지 본문의 명령 계약을 분석한 결과가 아닙니다.

| 후보 | 고정 출처 | 실제 확보 상태 |
| --- | --- | --- |
| P05ACJ 업데이트 패키지 | tavinus/SamsungBIOSTools의 ACJ 플랫폼 매핑·수집 로그 | 정확한 파일명·출처 유래 경로를 확인했습니다. EXE 바이트·내부 펌웨어·서명·모델 목록은 미확보입니다. |
| 구형 Battery Life Extender1.0.0.11 | Elc3r/drivers_NP-RV520의 고정 Git LFS pointer | 133바이트 포인터를 확보했습니다. 포인터가 가리키는 ZIP 바이트는 미확보입니다. 다른 모델의 비교 자료입니다. |

### P05ACJ 위치의 출처와 한계

고정 커밋은 `tavinus/SamsungBIOSTools@f920045b7c9bb05fdd3d3a12d1175c80c908afd3`입니다.

- [플랫폼 매핑31행](https://github.com/tavinus/SamsungBIOSTools/blob/f920045b7c9bb05fdd3d3a12d1175c80c908afd3/SamsungPlatformCorrelation_20210422.txt#L31)에 `ACJ > ITEM_20140901_21421_WIN_P05ACJ.exe`가 있습니다. 이 **목록 파일**의 SHA-256은 `93cf2e71b40dacc14394a13cabc274b4935e569a47fa1807bb46822dbfe7cc6b`입니다.
- [수집 로그65행](https://github.com/tavinus/SamsungBIOSTools/blob/f920045b7c9bb05fdd3d3a12d1175c80c908afd3/lists/data/HIDPermutedBIOSFetcher.log#L65)과 [ItemList1060행](https://github.com/tavinus/SamsungBIOSTools/blob/f920045b7c9bb05fdd3d3a12d1175c80c908afd3/ItemList.txt#L1060)에도 같은 이름이 있습니다. 같은 저장소·수집 계통이므로 독립된 제조사 확인3건으로 세지 않습니다.
- [수집 스크립트30행 이후](https://github.com/tavinus/SamsungBIOSTools/blob/f920045b7c9bb05fdd3d3a12d1175c80c908afd3/lists/scripts/latestBiosFetcher.sh#L30)는 Samsung GetContents의 FilePathName을 읽는 구조입니다. [README190행](https://github.com/tavinus/SamsungBIOSTools/blob/f920045b7c9bb05fdd3d3a12d1175c80c908afd3/README.md#L190)은 목록 수집일을2021-04-22로 설명합니다. 외부 스크립트는 실행하지 않았습니다.

출처에서 구성되는 공식 호스트 위치는 다음입니다. 설치·플래시를 위한 사용자 실행 지시가 아니며, 확보 후 **바이트 정적 분석만** 하기 위한 위치입니다.

```text
https://sbuservice.samsungmobile.com/upload/BIOSUpdateItem/ITEM_20140901_21421_WIN_P05ACJ.exe
```

실제 HTTPS HEAD는 프록시의 CONNECT403으로 끝났습니다. 삼성 서버가 파일 존재·부재나 접근 권한에 대해 응답한 것으로 해석하지 않습니다. 원 출처의 HTTP 경로와 현재 HTTPS의 실제 제공 여부도 미확인입니다. 파일명·날짜·ACJ 매핑은 현재 사용자 장치용 이미지, 동일한 내부 빌드, 서명 유효성·안전성을 증명하지 않습니다. 목록 파일 해시를 EXE/펌웨어 해시로 사용하지 않습니다.

별도 공개 LPCK 파서 소스도 정적 포맷 참고로 찾았지만 P05ACJ가 그 형식인지는 확인하지 못했습니다. 설치 프로그램을 실행해 임시 파일을 얻거나 펌웨어를 갱신하는 공개 안내는 따르지 않습니다.

### 구형 배터리 호출자 비교 자료

고정 커밋은 `Elc3r/drivers_NP-RV520@c20c758117b1410a5e486a7042fc004ac589287f`입니다. [Windows7 패키지 경로](https://github.com/Elc3r/drivers_NP-RV520/blob/c20c758117b1410a5e486a7042fc004ac589287f/W7/32bit_64bit/Battery_Life_Extender_1.0.0.11.ZIP)와 WindowsXP 동명 버전 경로는 같은 LFS 객체를 가리킵니다.

| 구분 | 확인한 값 |
| --- | --- |
| 실제 받은 포인터 길이 / SHA-256 | 133바이트 / 3c4db3c03893d20ac2f0a26c6d665d7316f8ecb4a20cff6cc81d5de450a4d95d |
| 포인터가 선언한 ZIP 길이 | 13,728,500바이트 |
| 포인터가 선언한 객체 SHA-256 | 5e3be33df74283d00542777320519c3f5d5fb6a01bdcbd664d7d9e33ce2511fc |

ZIP 자체를 다운로드·해시 검증한 것이 아닙니다. Git LFS batch는403, 정상 다운로드 경로는 media.githubusercontent.com 대상 연결에서 프록시403으로 중단됐습니다. URL/Host 재작성·중계·다른 프록시로 우회하지 않았습니다.

저장소 설명과 경로는 NP-RV520·Windows7/XP 문맥입니다. 원본을 확보하더라도 현재 ATIV/P05ACJ에 대한 적용성이 자동으로 생기지 않습니다. 내부 배터리 조회/설정 호출 지점·전송·입력 준비·응답 분기·모듈 버전/해시를 정적으로 대조할 자료일 뿐입니다. 공개 LFS 객체와 일치해도 제조사 진위·서명·현재 모델 적합성을 증명하지 않습니다.

## 개발용 원본 인입 검증

`scripts/inspect_command_research_artifact.py`는 원본 확보 후 사용할 **개발용 오프라인 검사기**입니다. 사용자 노트북 진단·설치 도구나 실제 제어 어댑터가 아닙니다.

- LFS 포인터와 원본 바이트를 구분합니다. 포인터의 OID가 같다는 이유로 ZIP을 검증했다고 표시하지 않습니다.
- 구형 BLE는 고정 길이·객체 해시와 제한된 ZIP 구조/CRC를 검사합니다. 이 결과는 공개 원본의 무결성 범위입니다.
- P05ACJ는 아직 원본 해시가 없어 PE 구조 관측까지만 보고할 수 있습니다. 펌웨어·제조사 진위·현재 모델 또는 배터리 명령 계약을 검증한 것으로 표시하지 않습니다.
- 입력 크기·ZIP 항목/해제량·PE 구조 경계를 제한하고 고정 상태·수·내용 해시만 출력합니다. 입력 경로·원문 이름·원문 예외는 보고하지 않습니다. 다운로드·외부 프로세스·라이브러리 로드·파일 추출·코드 실행 기능은 없습니다.

### 검사 결과

Python 전체41개(기존 배포 검사27개와 신규 인입 검사14개)를 실행해 모두 통과했습니다. 포인터/잘못된 길이·해시, 위조된 ZIP 개수·길이·CRC·descriptor·경로·링크·겹침, 해제량/읽기 상한, 정상 deflate 경계, PE 경계와 입력 경로/예외 비노출을 검사합니다. 독립 읽기 전용 검토에서 발견한 ZIP 경계 문제를 수정했고 추가 차단 문제는 발견하지 못했습니다.

실제로 받은133바이트 파일에 대한 결과는 `GitLfsPointerOnly`, `pointerMatchesExpected=true`, `sourcePayloadIntegrityVerified=false`입니다. 선언된 객체와 같은 포인터라는 관측이며 ZIP 바이트 검증이나 OEM/모델/명령 지원 검증이 아닙니다. 기록은 reports/command-artifact-pointer-review.json 및 command-artifact-python-tests.log에 있습니다. 실제 원본은 여전히 미확보입니다.

## 네트워크 검토 초안과 다음 작업

현재 차단 호스트만 좁게 추가한 초안을 저장했고 재조회로 확인했습니다.

| 추가 호스트 | 필요한 작업 |
| --- | --- |
| sbuservice.samsungmobile.com | P05ACJ 공식 메타데이터/패키지에 정상 접근해 바이트를 정적으로 확보 |
| media.githubusercontent.com | 고정 공개 Git LFS ZIP을 정상 경로로 확보하고 선언된 길이·SHA-256 대조 |

결과는 `status=saved`, `requires_publish=true`입니다. 기존 custom 목록을 먼저 읽었고 package manager/GitHub 프리셋·저장소·설치/시작 스크립트·변수/자격 요구사항은 바꾸지 않았습니다. 초안 저장은 실행 환경 적용이나 환경 게시가 아닙니다. 환경은 에이전트가 게시하지 않았으며 현재 두 원본 접근은 해결되지 않았습니다.

환경 설정에서 이 변경이 검토·저장·게시된 뒤에는 해당 요청을 다시 확인하고, 성공한 원본만 인입 검사 → 실행 없는 내부 자료 추출/정적 분석 → 모델/전송/명령/응답 근거 대조 순서로 진행합니다. 준비된 위치가 존재하지 않거나 원본이 다르면 그 결과를 기록하며 다른 펌웨어로 대신하지 않습니다.

앱·요청·디코더·기존 ZIP·예약/제어 정책은 유지합니다. 검증되지 않은 FF 설명을 적용하거나 원본 재제출·반복 진단·추가 OEM 실험·드라이버/서비스/보안 변경·펌웨어 실행/쓰기를 요구하지 않습니다. 실제 충전 제어는 Unsupported입니다.
