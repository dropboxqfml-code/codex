# Image Duplicate Finder v0.1.1 보안 점검

> 이 문서는 v0.1.1 점검 기록입니다. v0.2.0의 추가 분석 캐시와 A/B 안전 경계는
> [두 폴더 비교 보안·검증 문서](cross-folder-compare.md)를 함께 확인하세요.

점검일: 2026-10-17. 기준 버전은 v0.1.0 (`e5e1f4b`), 수정 버전은 v0.1.1입니다.
사용자 사진 대신 자동 생성한 시험 이미지만 사용했습니다.

## 1. 외부 통신과 명령 실행

`src`, 패키징 진입점, 빌드 스크립트, CI 설정을 검토했습니다. 앱에 HTTP 업로드,
업데이트 조회, AI API, 원격 이미지 분석, 텔레메트리 엔드포인트는 발견되지 않았습니다.
이 결과는 모든 네이티브 라이브러리와 운영체제가 통신하지 않는다는 보증이 아닙니다.

| 경로 | 확인 결과 / 수정 |
| --- | --- |
| 앱의 requests/httpx/urllib HTTP/socket 호출 | 직접 호출 없음. Python 감사 훅으로 인터넷 소켓·DNS·외부 프로세스 호출을 추가 차단 |
| 네트워크 공유·매핑 드라이브 | 기존에는 입력 제한 없음. UNC/장치 경로·원격/불명 드라이브를 파일 조회 전에 거부 |
| 링크·클라우드 파일 | 경로 조상부터 검사. 링크·junction·reparse/recall/offline 속성과 알려진 OneDrive 루트 거부 |
| Linux 원격 마운트 | mountinfo를 먼저 검사해 로컬로 확인되지 않는 FS 접근 거부 |
| 기본 폴더 선택 | Windows Shell·클라우드 provider가 개입할 수 있어 직접 로컬 디렉터리만 나열하는 Qt 선택기로 교체 |
| Pillow EPS | 기존 전체 형식 검색에서 Ghostscript를 실행할 수 있었음. PNG/JPEG/BMP/WebP/GIF/TIFF 허용 목록으로 제한 |
| Pillow ImageShow | 앱에서 사용하지 않음. 배포물에서 외부 표시기·EPS/PDF/WMF 플러그인 제외 |
| Pillow JPEG/GIF의 선택적 외부 helper | 일반 load 경로가 아닌 명시적 helper 기능에 subprocess가 존재. 앱은 호출하지 않으며 Python 실행 가드로 차단 |
| NumPy DataSource / SciPy datasets | URL 입력 시 다운로드하는 별도 API가 존재. 앱은 배열 연산만 사용. SciPy datasets는 배포 제외, NumPy URL 다운로드는 클라이언트 제외·런타임 가드로 차단 |
| Qt generic TUIO 입력 플러그인 | PyInstaller 기본 GUI 훅이 불필요한 qtuiotouchplugin.dll과 Qt6Network.dll을 수집함을 발견. GUI 훅을 최소 플랫폼 플러그인으로 제한하고 통신 DLL 검사는 유지 |
| Qt 환경 설정 | VNC/WebGL·원격 X11 화면 거부, generic 입력·외부 플러그인 경로 override 제거, 앱의 로컬 Qt 플러그인 경로로 고정 |
| Send2Trash OS 버전 조회 | platform.version의 불필요한 로컬 hostname 조회가 엄격한 감사 가드에 걸림. 외부 전송이 확인된 건은 아님. 가드는 유지하고 Windows 커널 버전 API를 사용하는 어댑터로 대체 |
| NumPy의 로컬 시스템 조회 | numpy.testing의 platform.machine이 인수 없는 gethostname을 호출함을 스택으로 확인. 로컬 컴퓨터 이름 조회는 별도 카운트로 관찰하고 값은 보관하지 않음. 주소 해석 getaddrinfo/gethostbyname 및 인터넷 소켓은 계속 차단 |
| 상태·오류 문구 | 경로에 포함된 HTML이 해석되지 않도록 PlainText로 고정 |
| 빌드·감사 도구 | PyInstaller·Git·pip-audit를 고정된 인수 목록으로 실행. 앱 기능과 분리되며 앱에 배포하지 않음 |
| GitHub Actions | 설치·의존성 감사·Artifact 업로드에 인터넷 사용. 분석 대상은 시험용 생성 이미지뿐이며 사용자 폴더를 검색하지 않음 |

정상 앱 진입점과 배포 진입점은 제3자 GUI/분석 모듈을 사용하기 전에 Python 런타임 가드를
설치합니다. DNS·인터넷 소켓, subprocess, shell/open/startfile을 차단하며 별도 해제 스위치는
제공하지 않습니다. **Python 감사 훅은 C/C++·ctypes·COM을 격리하는 OS 샌드박스가 아닙니다.**
`gethostname()`은 외부 주소를 받지 않는 로컬 조회입니다. 이를 DNS 해석으로 오분류했던 진단을
수정했으며, 커널 인터넷 소켓 거부 상태에서도 로컬 조회가 동작하는 별도 대조를 추가했습니다.
이 구분은 외부 송신 검사 해제가 아니며 Windows 네이티브 패킷 캡처를 대체하지 않습니다.

## 2. 라이브러리와 알려진 취약점

PyPI 취약점 서비스에 pip-audit 2.10.1로 정확히 고정된 이름·버전을 조회했습니다.
Windows 전용 조건부 의존성도 Linux에서 조회하도록 마커를 제거하되 의존성 설치·실행은
하지 않았습니다. `--no-deps --disable-pip`은 조회용이며 설치 무결성 검사를 우회하지 않습니다.
실제 설치는 `uv.lock`의 아티팩트 체크섬을 사용합니다.

| 검사 대상 | 결과 |
| --- | --- |
| 수정 전 런타임 13개 버전 | 조회된 알려진 취약점 0, 누락 0 |
| 수정 후 런타임·개발·빌드·감사 도구 51개 버전 | 조회된 알려진 취약점 0, 누락 0 |
| 수정 후 런타임 | 9개: PySide6-Essentials 6.12.0, shiboken6 6.12.0, Pillow 12.3.0, ImageHash 4.3.2, NumPy 2.5.4, SciPy 1.18.1, PyWavelets 1.10.0, Send2Trash 2.1.0, pywin32 312 |
| Windows 내장 SQLite 별도 조회 | 기존 빌드의 3.49.1은 CVE-2025-6965 영향 범위에 해당. managed CPython 3.12 런타임으로 교체하고 앱·빌드에서 SQLite 3.50.2 미만을 거부 |

[공식 CNA CVE-2025-6965 기록](https://github.com/CVEProject/cvelistV5/blob/main/cves/2025/6xxx/CVE-2025-6965.json)은
SQLite 3.50.2 미만의 aggregate 항목 처리에 메모리 손상 가능성을 명시합니다. 앱은 고정 SQL과
바인딩 매개변수를 사용하고 사용자 SQL을 받지 않지만, 영향 버전을 그대로 배포하지 않습니다.
Windows 런타임 설치·다운로드는 개발/CI 단계에만 수행하며 앱에 자동 설치·업데이트 코드를
넣지 않습니다. SQLite가 기준 미만이면 DB를 열기 전에 중단합니다. 새 번들의 실제 SQLite 버전은
`frozen-smoke.json`의 `native_versions`에서 확인해야 합니다.

`reports/dependency-audit.json`와 `audit-requirements.txt`를 CI 증거로 보관합니다. 이 조회는
현재 공개된 Python 패키지 권고에 한정됩니다. 미공개 취약점, OS·드라이버, Qt/C++ 및 Pillow에
내장된 libjpeg/libtiff/libwebp/zlib, CPython·SQLite의 모든 CPE 권고를 포괄하지 않습니다.
실제로 로드한 네이티브 버전은 `frozen-smoke.json`의 `native_versions`에 기록하며, 이 버전들의
별도 바이너리 SBOM/CVE 매칭과 퍼징은 **미검증**입니다.

| 라이브러리 | 사용 / 남는 위험 |
| --- | --- |
| PySide6-Essentials | 로컬 Widgets·PNG 썸네일 표시. 네이티브 Qt·Windows 입력/글꼴/provider의 동작은 별도 관찰 필요 |
| Pillow | 허용한 로컬 이미지 디코딩. 외부 helper 경로 차단, 이미지 폭탄 보호 유지. 악성 이미지의 네이티브 파서 위험은 남음 |
| ImageHash·NumPy·SciPy·PyWavelets | 로컬 수치 계산. 사용한 분석 흐름에 자동 업데이트/텔레메트리 호출 발견 없음. 라이브러리 전체 기능이 무통신이라는 뜻은 아님 |
| SQLite | 사용자별 최소 선택 기록. 앱 SQL은 상수 및 바인딩 매개변수 사용, trusted_schema OFF·defensive 설정 |
| Send2Trash·pywin32 | 운영체제 휴지통. Windows modern IFileOperation만 사용, legacy 대체 없음. OS Shell/보안 서비스 동작은 Python 훅 밖 |

## 3. 배포물과 불필요한 기능

PySide6 메타 패키지를 PySide6-Essentials로 교체하여 Addons/Pdf/WebEngine을 런타임 의존성에서
제거했습니다. PyInstaller는 Qt Network/WebEngine/WebSockets/QML, requests/httpx/urllib3 등
사용하지 않는 클라이언트, pip/pip-audit/pytest 및 외부 디코더를 제외합니다.
NumPy 2의 f2py는 SciPy의 호환성 import가 요구하므로 통째로 제거하지 않습니다. 컴파일 helper의
존재가 자동 실행을 의미하지 않으며 앱의 분석 흐름은 해당 API를 호출하지 않습니다.
Qt 통신 DLL이 실제 수집되면 빌드가 실패하도록 검사합니다. 모듈·네이티브 파일 목록은
`reports/bundle-inventory.json`에 남깁니다. 소스의 제외 설정만으로 배포물이 검증됐다고
주장하지 않으며, 해당 커밋의 Windows 빌드·번들 검사가 통과해야 합니다.

일반 배포 앱에는 자동 업데이트나 버전 확인 요청이 없습니다. 보안 업데이트는 개발자가 의존성을
갱신·감사·재빌드한 뒤 사용자가 새 Artifact를 다운로드하는 방식입니다.

## 4. 이미지·파일 정보의 저장

| 정보 | 위치 / 수명 |
| --- | --- |
| 원본 이미지 | 사용자가 선택한 로컬 폴더. 읽기만 수행하며 휴지통 이동은 확인 후 수행 |
| 파일명·경로·크기·해상도·SHA-256·픽셀 해시·pHash·썸네일 | 검색 작업과 GUI 메모리. 일반 사용 중 별도 파일·로그·원격 보고서에 저장하지 않음 |
| 선택 DB | Qt AppLocalDataLocation의 `reviews.sqlite3`. Windows 기본은 `%LOCALAPPDATA%\ImageDuplicateFinder\Image Duplicate Finder` |
| DB 내용 | `review_id`(키 기반 HMAC 식별자), `decision`(keep/delete) 두 필드. 평문 경로·원본 해시·시간·썸네일 없음. 보류는 행을 지움 |
| HMAC 키 | 같은 폴더의 `reviews.sqlite3.key`, 무작위 32바이트. DB와 함께 백업 필요 |
| 삭제 파일 | 운영체제 휴지통. 원래 경로 등 OS 복원 메타데이터는 Windows가 보관 |
| CI 진단 | 자동 생성한 시험 이미지·스크린샷·패키지 목록·테스트 기록만 Artifact에 업로드. 실제 사진을 CI/저장소에 넣지 말 것 |

HMAC는 최소화·가명화이며 DB 암호화가 아닙니다. 키와 DB를 읽을 수 있는 로컬 계정/악성코드는
후보 경로·이미지의 존재를 대조할 수 있습니다. POSIX 파일 권한은 0600으로 설정하고 Windows는
사용자 AppData의 상속 ACL을 사용합니다. Windows ACL 자체의 독립 검증은 수행하지 않았습니다.

v0.1.0 DB는 선택을 보존하며 변환하고 secure_delete 및 VACUUM으로 기존 필드를 정리합니다.
동시에 다른 인스턴스가 DB를 열고 있으면 변환을 중단하므로 종료 후 다시 시도해야 합니다.
선택 기록 지우기는 기본 ‘아니요’ 확인 후 DB만 정리합니다. SSD·스냅샷·기존 백업의 물리적 삭제나
RAM·페이지 파일·GPU 버퍼·OS crash dump의 삭제까지 보증하지 않습니다.

## 5. 수정 및 테스트

| 점검 | 수정 전 / 후 |
| --- | --- |
| 회귀 테스트 | 수정 전 37 passed. 수정 후 결과는 CI JUnit에 플랫폼별 통과·실패·제외로 구분해 기록 |
| 평문 DB | 이전 fixture에서 경로·SHA 바이트 존재 확인 → 변환 후 DB/부속 파일에 해당 바이트 없음, 선택 복원 통과 |
| EPS | 외부 delegate 사용 가능 → 잘못된 `.png` 확장자를 붙인 EPS도 해석·delegate 호출 없이 거부 |
| 파일 이동 | GUI 기본 ‘아니요’ 유지, backend는 confirmed=True 없으면 거부. 보관·변경 파일·실패 시 영구 삭제 방지 회귀 검사 |
| 진단 출력 | 진단 모드가 기존 JSON/PNG를 덮어쓰지 못하도록 신규 로컬 경로만 허용 |
| Linux 오프라인 | libseccomp로 네이티브 IPv4/IPv6 socket 생성 EPERM 강제, Qt offscreen 검색·판별·SQLite·확인 취소/동의·실제 시험 사본 휴지통 이동 통과 |
| Python 동작 관찰 | 정상 오프라인 흐름의 차단된 네트워크·프로세스 시도 각각 0. 별도 양성 대조에서는 DNS/소켓/HTTP·프로세스 호출 차단 확인 |
| strace | 초기 Python 실행 외 추가 exec 없음. 인터넷 소켓은 의도한 IPv4/IPv6 차단 대조 2회뿐, Internet connect/send 없음 |

Linux network namespace 생성은 이 환경의 읽기 전용 uid_map 때문에 불가했습니다. 대신 커널
seccomp 필터의 실제 native socket 거부를 확인했습니다. 이는 앱에 방화벽 규칙을 설치하는 기능이
아니며, 검증 도구/회귀 CI에만 적용합니다. 추적 증거는 `offline-probe.json`,
`offline-functional.json`, `offline-syscalls.log`에 남습니다. Unix IPC 및 다른 프로세스가 대신
수행하는 OS 작업은 이 인터넷 소켓 통제의 범위 밖입니다.

재현 명령(Linux, libseccomp·strace 필요):

```bash
uv sync --locked --group security
.venv/bin/python scripts/audit_dependencies.py
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
QT_QPA_PLATFORM=offscreen strace -f -e trace=network,process -o reports/offline-syscalls.log .venv/bin/python scripts/offline_probe.py
.venv/bin/python scripts/check_network_trace.py reports/offline-syscalls.log
```

## 6. 추가로 필요한 동적 검증과 운영 조건

**이 검사는 개인 이미지 유출 위험이 0이라는 인증이 아닙니다.** 정상 입력의 시험 시나리오를
검사했으며 모든 악성 이미지·시스템 구성을 검증하지 않았습니다.

Windows 최종 exe의 WFP/ETW·Wireshark/Procmon으로 프로세스와 자식·OS broker의 TCP/UDP/DNS,
UNC/SMB·WebDAV, 클라우드 placeholder의 읽기와 이미지/DB 파일 I/O를 관찰해야 합니다.
런타임 가드의 Python 시도 0은 네이티브 트래픽 0의 증거가 아닙니다. 이 Windows 패킷/시스템 호출
캡처, 완전 망분리 PC 검증, Windows ACL 검증은 **미실행**입니다.

검증 PC에서 실행 파일별 Windows 방화벽 outbound 차단을 적용하고, 브라우저·개발 도구를 종료한
뒤 시작/폴더 선택/검색/취소/선택 복원/휴지통 이동/유휴/종료 전체를 관찰하세요. 네트워크 어댑터를
차단한 별도 VM에서도 반복하고, 패킷 캡처의 정상 수집 여부는 별도 양성 대조로 확인해야 합니다.
로컬 바이너리·네이티브 디코더는 최신 보안 업데이트와 추가 SBOM/CVE 점검이 필요합니다.

알 수 없는 Dropbox/Google Drive 등 동기화 도구, 기업 DLP·EDR·백신 샘플 제출, OS crash 보고,
프로필·휴지통 백업은 앱 밖에서 파일/메타데이터를 전송할 수 있습니다. 모든 동기화 폴더를
자동 식별할 수 없으므로 업무 이미지는 동기화되지 않는 로컬 폴더에 두고 해당 환경의 정책도
검토하세요. 앱의 로컬 경로 검증은 악의적인 동시 경로 교체와 운영체제 자체를 격리하지 못합니다.
