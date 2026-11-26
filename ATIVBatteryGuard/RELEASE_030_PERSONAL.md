# ATIV Battery Guard 0.3.0 개인용 배포 준비

2026-11-26 한국 시간. 대상은 Windows 10 x64 / 940X3G / .NET Framework 4.8입니다. 사용자는 본인 노트북에서만 사용하며 미서명 안내를 프로그램 화면에 추가하지 않고 텍스트 파일에 간단히 적도록 요청했습니다.

## 변경 범위

제품 207소스는 검증된 RC3와 비교해 ApplicationRelease.cs의 버전 상수 `0.3.0-rc.3` → `0.3.0`만 다릅니다. 파일 버전은 0.3.0.0입니다. 화면 구성·도움말·충전 제어·설정·기록/메모 형식은 유지합니다. 서명 안내 배너/팝업을 제품에 추가하지 않았습니다.

일반 프로그램 ZIP은 기존 6파일과 `먼저 읽어주세요.txt`, `BUILD-INFO.json`, `SHA256SUMS.txt`의 9항목입니다. 미서명과 SmartScreen 안내는 텍스트 파일에 간단히 적었습니다. 일반 ZIP에는 CMD/PowerShell/검사 EXE가 없습니다.

- [일반 프로그램 ZIP](../downloads/ATIVBatteryGuard-0.3.0-WIN10-X64.zip)
- [마지막 화면 확인 ZIP](../downloads/ATIVBatteryGuard-0.3.0-FINAL-CHECK.zip)
- [화면 확인 순서](FINAL_030_PERSONAL_CHECK_USER_STEPS.txt)
- [빌드·회귀·패키지 근거](reports/release-030-personal-validation.json)

## 배포 검증

개인용 패키징은 기존 서명 배포 경로와 별도입니다. RC3 원본 ZIP 지문과 현장 닫기 통과 근거, 최종 소스가 버전만 변경됐음, 제품 회귀 전체 통과, net48/x64·일반 권한·기존 안전 조건, app/helper의 공유 파일 일치를 요구합니다. 현재 미서명 PE만 허용하며 ZIP CRC/정확한 허용 목록/내부 바이트를 검사합니다. 기존 파일을 덮어쓰지 않습니다. 기존 서명 배포 조건을 완화하거나 미서명 파일을 서명된 것으로 표시하지 않습니다.

회귀 테스트 두 곳의 버전 기대값/불일치 예제도 갱신했습니다. 초기 전체 검사에서 불일치 예제가 새 최종 버전과 같아 1개 실패했으며, 불일치 조건을 `현재 버전 + -mismatch`로 바꿔 거부 검사 의도를 유지했습니다. 이 테스트 수정은 제품 소스 범위에 포함되지 않습니다. 별도 검사 EXE의 버전 메타데이터도 0.3.0으로 맞췄습니다.

## 마지막 Windows 확인

FINAL-CHECK 묶음의 제품 6파일은 일반 프로그램 ZIP과 완전히 같습니다. 새 폴더에 풀고 `ATIVBatteryGuard.ValidationCheck.exe`를 실행하면 파일 전후 해시·최종 EXE 버전·GUI 자동 검사/바인딩을 확인하고 `validation-results`에 JSON을 저장합니다. 검사 CMD는 포함하지 않습니다. 기존 검사 도구의 절차는 그대로 사용하며 충전 제어·helper 실행·관리자 요청·보안 설정 변경·자동 전송은 없습니다. 기본 배터리/WMI 읽기는 기존 GUI self-test 범위입니다.

이미 통과한 RC3 한글 조합 닫기/이전 저장·빠른/20분·충전 시험은 인계하며 다시 요청하지 않습니다. 도구의 수동 검사 대기 문구는 이번 실행의 범위이지 기존 통과 결과의 취소가 아닙니다. 새 Windows GUI 확인이 끝나기 전에는 `personalReleaseApproved=false`, `windowsFinalFileGuiPassed=false`, `final030ReleaseApproved=false`입니다. 미서명 상태와 앱 평판은 GUI 통과 여부와 구분합니다.

현재 Linux에서는 최종 Windows GUI·SmartScreen 직접 허용·Defender·서명을 실행하지 않았습니다. 다음은 이 최종 파일의 `validation-*.json`, `gui-*.json` 결과를 확인하는 것입니다. 공개 배포/유료 서명/Store 전환을 수행하지 않습니다.
