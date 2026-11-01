# 공개 충전 제어 규약 검토 — 2026-11-01

## 이번 단계의 결론

공개 Windows 프로젝트와 Linux 원본에서 배터리 수명 연장 기능의 명령 후보를 찾았습니다. 이전의 ‘충전 명령 자체를 찾지 못한 상태’에서, **명령 후보는 있으나 현재 ATIV의 Windows WMI 전송 규약과 모델 적합성이 확인되지 않은 상태**로 조사 범위가 좁혀졌습니다.

실제 제어를 추가하지 않았습니다. 삼성 DLL 추출·실행, 드라이버 설치, 외부 코드 실행, Linux 코드 포팅도 하지 않았습니다. 아래 숫자는 조사 식별자이며 사용자가 장치에 실행할 명령이 아닙니다.

| 경로 | 실제로 확인한 공개 근거 | 현재 제품에 적용할 수 없는 이유 |
| --- | --- | --- |
| Windows 표준 배터리 요청 | 사용자 진단에서 `0x80000000`, 표준 충전·방전 요청 지원 표시 없음 | 현재 드라이버가 해당 요청 지원을 표시하지 않음. 80% 상한 API로 볼 근거도 없음 |
| 구형 Windows SABI3 도구 | 공개 C#의 Battery Life Extender 조회·변경 메서드 | `Sabi3.dll` 호출에 의존. 현재 WMI 패킷 형식과 ATIV 모델 적합성을 설명하지 않음 |
| 구형 Linux SABI3 | 공개 커널의 같은 기능 조회·변경 구현 | BIOS 메모리·포트 I/O 전송이며 Windows WMI 규약이 아님 |
| Galaxy Book SCAI | 공개 ACPI 드라이버에 실제 퍼센트 상한 조회·설정 구현 | 적용 ACPI ID와 Windows 접근 방법을 현재 ATIV에서 확인하지 못함 |

## 1. 구형 Windows 공개 프로젝트

검토 대상은 `akastormseeker/samsung-hotkeys`의 고정 커밋 `0d3947eea0003dd8e9372c36925c0fd0a8fd28d3`입니다.

- [공개 C# 원본](https://github.com/akastormseeker/samsung-hotkeys/blob/0d3947eea0003dd8e9372c36925c0fd0a8fd28d3/SamsungHotkeys/Controls/SamsungBIOSInterface.cs): `GetBLEEnabled`와 `SetBLEEnabled`가 있고, 기능 번호는 각각 `0x65`와 `0x66`입니다. 입력의 `0x80`/`0x81`은 기능 제어 인코딩입니다. `0x80`을 80%라는 수치로 해석하지 않습니다.
- 같은 원본의 실제 전송 함수는 `DllImport("Sabi3.dll")`입니다. 독립 WMI 구현이나 `CallSabiFunction`의 입력 바이트 구조를 제시하지 않습니다.
- [README](https://github.com/akastormseeker/samsung-hotkeys/blob/0d3947eea0003dd8e9372c36925c0fd0a8fd28d3/README.md)는 EasySettings에서 얻는 삼성 DLL과 BIOS 인터페이스 드라이버를 전제로 합니다. 사용자가 지정한 DLL 추출 없는 개발 조건에 맞지 않습니다. 설치 우회 방법은 따르지 않습니다.
- README의 Windows 10 업데이트 호환성 설명은 작성자의 경험담입니다. 현재 사용자의 모델·BIOS·Settings 2.2에서 배터리 메뉴가 사라진 원인으로 확정할 수 없습니다.
- [이슈 1](https://github.com/akastormseeker/samsung-hotkeys/issues/1)의 사용자 시험은 NP700Z5C-S01UB의 키보드 백라이트입니다. ATIV 배터리 충전 제한의 시험 근거로 사용하지 않습니다.
- [이슈 4](https://github.com/akastormseeker/samsung-hotkeys/issues/4)는 명령 번호의 출처를 묻는 질문입니다. 읽은 내용에서 공식 규약의 답변은 확인하지 못했습니다.

따라서 이 자료는 구형 Windows용 충전 기능 래퍼가 공개돼 있다는 근거입니다. 삼성 DLL 없이 이 노트북을 제어할 수 있다는 증거는 아닙니다. 해당 소스를 제품에 복사하지 않았습니다.

## 2. 구형 Linux SABI와의 비교

검토 대상은 Linux v6.1, 커밋 `830b3c68c1fb1e9176028d02ef86f3cf76aa2476`의 [samsung-laptop.c](https://github.com/torvalds/linux/blob/830b3c68c1fb1e9176028d02ef86f3cf76aa2476/drivers/platform/x86/samsung-laptop.c)입니다.

- 188–189행과 251–252행: SABI 버전별 명령이 다릅니다. SABI2에서는 해당 기능이 미제공 표시이고 SABI3에는 조회·변경 번호 `0x65`/`0x66`이 있습니다.
- 701–733행: 기능 상태의 조회와 변경이 분리돼 있으며 상태 응답을 검사합니다. Windows 래퍼와 번호·제어 바이트가 일치합니다. 이 일치를 현재 모델의 독립적인 실기 검증으로 확대하지 않습니다.
- 384–448행: 전송은 BIOS 메모리와 포트 I/O입니다. 현재 진단에서 찾은 `WmiAcpiMethod.CallSabiFunction`의 전송 계약이 아닙니다.
- 1494–1551행: 일반 삼성 DMI 조건과 일부 다른 모델 조건이 있습니다. 940X3G/930X3G의 명시적인 검증 기록은 이 부분에서 찾지 못했습니다. 명시 부재만으로 미지원이라고 판정하지 않습니다.
- 1562–1563행: EFI 부팅이면 초기화를 거부합니다. 이를 피하기 위한 부팅 설정 변경은 제안하지 않습니다.

공개 명령 번호만 골라 C# WMI 입력에 넣는 작업은 하지 않습니다. 조회라는 이름의 함수도 전송·초기화 동작이 확인되기 전에는 안전한 읽기로 취급할 수 없습니다.

## 3. Galaxy Book의 퍼센트 상한 규약

검토 대상은 Linux v6.17, 커밋 `e5f0a698b34ed76002dc5cff3804a61c80233a7a`의 [samsung-galaxybook.c](https://github.com/torvalds/linux/blob/e5f0a698b34ed76002dc5cff3804a61c80233a7a/drivers/platform/x86/samsung-galaxybook.c)와 [커널 공식 설명 문서](https://github.com/torvalds/linux/blob/e5f0a698b34ed76002dc5cff3804a61c80233a7a/Documentation/admin-guide/laptops/samsung-galaxybook.rst)입니다. 삼성의 Windows 공식 API 문서는 아닙니다.

- 소스 399–490행에 실제 퍼센트 상한의 조회·설정과 무제한 값 변환이 있습니다. 무제한 설정은 내부 값 `0`과 사용자 표시 `100`으로 변환합니다.
- 문서는 해당 계열에서 Windows Samsung Settings와 호환할 값으로 50/60/70/80/90/100을 설명하며, 모델마다 기능 지원이 다를 수 있다고 명시합니다.
- 소스 1405–1411행의 적용 ACPI ID는 `SAM0426`, `SAM0427`, `SAM0428`, `SAM0429`, `SAM0430`입니다. 현재 사용자 진단에는 이 ID의 관측이 없으므로 존재·부재를 판단할 수 없습니다.
- 드라이버는 SCAI ACPI의 배터리 요청에 `CSFI`, 초기화에 `SDLS`, 성능 모드에 `CSXI`를 사용합니다. 다른 공개 SABI 구현과 일부 구조·식별자가 닮더라도 현재 Windows WMI와 같은 전송이라고 판단하지 않습니다.

따라서 공개적으로 문서화된 삼성 퍼센트 상한 규약이 전혀 없다고 말할 수는 없습니다. 그러나 이 규약을 현재 ATIV의 Windows 제어 경로로 채택할 근거도 아직 없습니다.

## 현재 남은 검증 조건

다음 구현의 선행 조건은 새로운 잔량 진단이 아니라 아래 연결 고리입니다.

1. 명령 후보가 940X3G/930X3G 및 BIOS P05ACJ.128.140819.dg에 적용된다는 근거
2. 삼성 DLL 없이 Windows에서 호출할 수 있는 전송 방법과 정확한 입력·출력 바이트 계약
3. 초기화의 부작용, 오류·미지원 응답, 실제 설정 조회의 의미
4. 기능 ON/OFF가 현재 모델에서 뜻하는 실제 상한과 설정 유지 조건

이 중 현재 확보된 것은 공개 소스상의 명령 후보와 다른 전송 방식의 설명입니다. 조건을 충족하기 전에는 실행 가능한 OEM 호출 코드나 시험 도구를 배포하지 않습니다. 기존 앱은 배터리 상태와 로컬 선택값을 표시하고 실제 제어는 Unsupported로 유지합니다. 같은 진단이나 삼성 파일의 추가 업로드는 요청하지 않습니다.

## 조사 범위와 검증

허용된 GitHub 저장소·README·공개 이슈와 커널 원본을 정적으로 읽었습니다. 삼성 공식 사이트와 사용자가 제공한 NBRchive 원문은 현재 활성 네트워크 정책에서 접근되지 않아 읽지 못했습니다. GitHub 검색은 전체 웹 조사나 해당 모델의 공식 지원 확인을 대신하지 않습니다.

외부 소스와 사용자 진단 원본은 저장소·배포물에 포함하지 않습니다. 이번 변경은 조사 문서이며 앱 소스·실행 파일은 바꾸지 않았습니다. 이전 앱의 138개 테스트·성공한 빌드는 이전 버전의 검증 기록으로 유지하며, 이번 조사 때문에 다시 실행했다고 보고하지 않습니다.
