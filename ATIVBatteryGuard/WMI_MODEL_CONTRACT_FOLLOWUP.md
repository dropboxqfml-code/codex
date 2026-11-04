# WMI 모델별 명령 계약 추가 조사 — 2026-11-04

## 이번 사용자 확인

사용자가 RESULT-REVIEW 일반 앱을 일반 권한으로 실행했고 현재 배터리 상태가 정상 표시된다고 확인했습니다. 이는 해당 빌드의 시작·배터리 표시 확인입니다. 과거 결과 붙여넣기·오류 처리까지 실기 확인된 것으로 확대하지 않습니다. 파일 재제출이나 새 노트북 시험을 요청하지 않습니다.

승인된1회 조회에서 이미 WMI 응답과 ValidFrame·후보FF를 확인했습니다. 이번에는 추가 호출 없이 남은 병목인 **현재 모델·BIOS의 Windows WMI 배터리 명령 의미**를 조사했습니다.

## 입력과 프로토콜 가정 대조

| 확인 대상 | 정적 근거 | 수정 판단 |
| --- | --- | --- |
| 조회 입력 첫 바이트0x80 | Linux v6.12도 배터리 조회 전에 구조체를0으로 지우고 첫 바이트0x80을 명시 | FF만을 근거로 입력을0으로 바꾸지 않음 |
| 후보0x65와 main0x5843 | 같은 소스의 SABI3 명령표에 있음 | 숫자 혼동의 명백한 오류는 찾지 못했으나 현재 WMI 모델 계약을 증명하지는 않음 |
| SABI2 표의 BLE0xFFFF | 해당 공개 표에서 명령 미제공을 나타냄 | 응답 첫 바이트FF와 별개이며 다른 버전 명령을 추측하지 않음 |
| WmiAcpiVersion.version=16 | 노트북에서 읽은 해석되지 않은 UInt32 | SABI2/3 또는 프로토콜1.0으로 변환하지 않음 |
| Sabi3 caller11 / WMI payload16 | 제공 파일의 저장된 정적 분석상 다른 ABI | 차이만으로 요청 길이·패딩 오류를 단정하거나 한쪽 디코더를 재사용하지 않음 |

고정 원문은 [Linux v6.12 명령표](https://github.com/torvalds/linux/blob/v6.12/drivers/platform/x86/samsung-laptop.c#L152)와 [조회 입력](https://github.com/torvalds/linux/blob/v6.12/drivers/platform/x86/samsung-laptop.c#L700)입니다. SHA-256은 이전 대조와 같은 `42593bb4c71de22756a3d051ba79d8ad0ba3964e652872d627c2384e0d791063`입니다. 이는 직접 SABI 구현의 정적 근거이며 Windows에 포팅하거나 실행하지 않았습니다.

공개 hotkeys도 같은 후보와 입력을 사용하지만 Sabi3.dll에 의존합니다. 해당 DLL의 공개 예제4바이트 버퍼는 제공 x64 DLL의11바이트 접근과 맞지 않는다는 기존 분석을 유지합니다. 이번에 원본 삼성 DLL/기계어 덤프를 현재 첨부·임시 파일 범위에서 다시 찾지는 못했으므로 새로운 기계어 검증을 했다고 주장하지 않습니다. 동일 DLL 재제출도 요구하지 않습니다.

## 모델별 공개 ACPI 자료 조사

이전 README/인덱스 확인보다 범위를 넓혀 [linuxhw/ACPI](https://github.com/linuxhw/ACPI/tree/d6d30c6ef6f45506567f25a302c64f009d8f5f4e)의 실제 Git 트리 메타데이터를 읽었습니다. 조사 기준 커밋은 `d6d30c6ef6f45506567f25a302c64f009d8f5f4e`입니다.

blob 없는 shallow clone과 `git ls-tree -r`을 사용했고 pack은 약132KiB였습니다. 삼성 디렉터리에서 960QHA, 300E4, 300V3, 305U1, 355V4, 530U3, Q310, RF510 계열 경로는 관측했지만 `940X3G`, `930X3G`, `940X`, `930X`에 해당하는 경로를 찾지 못했습니다. 정확한 모델이 없어 다른 모델의 AML을 가져와 대입하지 않았고 테이블 본문이나 AML도 실행하지 않았습니다.

확보한 객체는 commit1개·tree1,183개·blob0개이고 전체1,449개 경로 중 Samsung Electronics 경로는12개였습니다. 별도 검토와 실제 트리 재대조로 확인했습니다. 재현 가능한 조회는 다음과 같습니다. 임시 경로만 사용하며 제품 실행 절차가 아닙니다.

```text
git clone --filter=blob:none --no-checkout --depth=1 https://github.com/linuxhw/ACPI.git <temporary-directory>
git -C <temporary-directory> ls-tree -r --name-only d6d30c6ef6f45506567f25a302c64f009d8f5f4e
```

이는 해당 커밋·경로명 검색 범위의 결과입니다. 다른 공개 자료의 부재, 장치/기능 부재나 Windows WMI 미지원을 증명하지 않습니다. GitHub의 제한된 모델명 검색도 현재 계약을 확정할 추가 근거를 제공하지 못했습니다.

신형 Galaxy Book의 SCAI 배터리 기능은 적용 ACPI ID·메서드와 전송 경로가 다른 별도 구현입니다. 현재 ATIV에 대한 동일성 근거 없이 해당 명령·퍼센트 값을 채택하지 않습니다.

[고정 Galaxy Book 소스](https://github.com/torvalds/linux/blob/e5f0a698b34ed76002dc5cff3804a61c80233a7a/drivers/platform/x86/samsung-galaxybook.c#L403)의 배터리 기능은 CSFI의 별도 selector를 사용하며 [적용 ID](https://github.com/torvalds/linux/blob/e5f0a698b34ed76002dc5cff3804a61c80233a7a/drivers/platform/x86/samsung-galaxybook.c#L1405)는 SAM0426–SAM0430입니다. 현재 사용자 기록에는 이 ID의 근거가 없습니다. 파일 SHA-256은 `c5b713cc76520ac37b354b8a6bf1634dc42e5be1e3ca30d0d01d1ebfd401e7e5`입니다.

## 구현 판단과 남은 조건

이번 조사에서 요청 바이트를 고치거나 실제 충전 어댑터를 활성화할 근거는 확보하지 못했습니다. 남은 것은 프레임 형식이나 일반 권한 배터리 표시가 아니라, **940X3G/930X3G·P05ACJ의 Windows WMI에서 후보 명령/selector와 응답FF를 어떻게 정의하는지**입니다.

이를 입증할 모델별 규약이나 대응되는 정적 구현이 필요합니다. 다른 모델 자료·일반 메서드 존재·ACK·과거bool 래퍼만으로 빈 부분을 채우지 않습니다. 별도 근거 없이 입력 보정, 다른 명령 탐색, 추가 OEM 호출이나0x66 쓰기를 구현하지 않습니다.

현재 일반 앱은 그대로 사용합니다. 기존 요청·디코더·예약·제어 정책과 실행 코드는 변경하지 않았고 새 EXE도 만들지 않았습니다. 반복 진단 UI나 의미 없는 추가 추상화를 만들지 않고 조사 결과를 기록했습니다. 실제 충전 제어는 계속 Unsupported이며 기존 예약 표식을 유지합니다.

이번 변경은 문서와 조사 기록뿐입니다. 342개 테스트·Python19개·빌드 경고/오류0개는 직전 코드의 검증 기록이며 이번에 재실행한 것으로 보고하지 않습니다. 하드웨어·삼성 DLL·드라이버·서비스·펌웨어는 실행/변경하지 않았습니다.
