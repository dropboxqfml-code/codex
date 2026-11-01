# Sabi3 초기화·드라이버 규약 검토 — 2026-11-01

## 현재까지 실제 확인한 범위

사용자가 전달한 `samsung-files-20261101T112523`에서 새 import 함수 분석 기능의 실제 Windows 결과를 확인했습니다. Sabi3 x64/x86 모두 CreateFileW와 DeviceIoControl 참조가 있으며 wsabi는 COM 초기화·객체 생성 참조가 있습니다. 이 사실로 어느 export가 어떤 인수·장치 경로·IOCTL을 사용하는지는 알 수 없습니다. 두 EXE의 함수 표시는 한도가 있어 전체 부재 판정에 사용하지 않습니다.

공개 C# 래퍼는 `InitBIOSInterface → CheckSamsung → 모델 조회` 순서를 보여주지만 DLL 내부 구현을 포함하지 않습니다. 추가로 GitHub 공개 README·이슈·커밋 메타데이터에서 초기화 함수, SABI.sys, CreateFile, DeviceIoControl, IOCTL 조합으로 14건의 제한된 검색을 수행했습니다. 현재 DLL 버전/해시와 연결된 초기화·드라이버 계약을 확보하지 못했습니다. 이는 전체 웹이나 모든 소스에 규약이 없다는 결론이 아닙니다.

검색에서 다시 확인한 [공개 이슈 1](https://github.com/akastormseeker/samsung-hotkeys/issues/1)은 다른 모델 NP700Z5C-S01UB의 키보드 백라이트와 드라이버 설치 경험이며 필요한 장치 경로·버퍼 규약을 제공하지 않습니다. [공개 래퍼](https://github.com/akastormseeker/samsung-hotkeys/blob/0d3947eea0003dd8e9372c36925c0fd0a8fd28d3/SamsungHotkeys/Controls/SamsungBIOSInterface.cs)는 여전히 참조 계약이며 현재 DLL의 내부 동작 검증은 아닙니다.

현재 첨부 저장 공간에 있는 이전 분석 ZIP 네 개의 파일명 목록도 확인했으나 Sabi3.dll은 없었습니다. 현재 정보 TXT는 함수 이름·해시·참조를 담고 있으며 기계어 함수 본문은 포함하지 않습니다. 사용자의 로컬 C 드라이브를 클라우드에서 직접 열 수 없습니다.

## 이번에 구현한 응답 해석

`Sabi3ReplyDecoder`는 공개 예제의 4바이트 응답을 해석하는 순수 함수입니다. DLL 로드·초기화·드라이버·OEM 메서드를 호출하지 않습니다.

| 입력 | 해석 |
| --- | --- |
| API 반환 코드가 0이 아님 | API 오류, 버퍼의 과거 값은 사용하지 않음 |
| 응답 없음 또는 길이가 4바이트가 아님 | 응답 형식 불일치 |
| 첫 바이트 0 | 공개 참조 계약상 보호 비활성 |
| 첫 바이트 1 | 공개 참조 계약상 보호 활성 |
| 첫 바이트 0xFF | 미지원. OFF와 구분 |
| 기타 값 | 알 수 없음. OFF로 대체하지 않음 |

반환 객체는 실제 하드웨어 관측 여부와 쓰기 허용을 항상 false로 두고 충전 상한 퍼센트는 null로 둡니다. 이 결과를 실제 모드나 80% 상한으로 연결하지 않았습니다. 실제 DLL 응답 계약이 검증되면 검증된 호출자와 연결할 수 있도록 준비한 코드입니다.

## 다음 정적 분석에 필요한 정확한 대상

| 항목 | 식별값 |
| --- | --- |
| 파일명 | Sabi3.dll |
| 구조 / 버전 | x64 / 3.2.0.0 |
| 크기 | 28,976바이트 |
| 파일 설명 | SABI3 Library For Windows7 (x64) |
| SHA-256 | 09a9714f0e11734872d60f2966edf8590ca721f0c05b2ca852a0bf20d6c006ae |

필요한 자료는 이 파일 하나의 ZIP입니다. Settings 전체, x86 Sabi3, 다른 wsabi, 반복 진단 TXT는 현재 분석의 선행 자료가 아닙니다. 제공받으면 해시·구조를 먼저 맞춘 뒤 DLL을 실행하지 않고 DllMain, InitBIOSInterface, CheckSamsung, CallBIOSInterface 계열의 코드와 호출 대상을 정적으로 검토합니다. 원본 파일이나 기계어 덤프는 GitHub 소스·배포물에 포함하지 않습니다.

분석할 질문은 장치 핸들 대상, 접근 권한, 초기화·종료의 서비스/설정 변경 여부, IOCTL 및 버퍼 방향, 조회와 변경의 구분입니다. 확인 전에는 함수 이름을 근거로 실제 초기화나 충전 제어를 수행하지 않습니다. 이번 단계에서 새 실행용 ZIP을 만들거나 동일 메타데이터 수집을 반복 요청하지 않습니다.
