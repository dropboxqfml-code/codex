# 개인 노트북에서 SmartScreen 경고가 나타날 때

2026-11-26 한국 시간. 사용자는 Windows 10 / 940X3G에서 Microsoft Defender SmartScreen이 경고한다고 확인했고, 현재 배포 범위를 본인 노트북 한 대로 정했습니다. 현재 RC3는 미서명이며 이 안내로 코드 서명이나 앱 평판을 확보한 것은 아닙니다.

## 현재 파일을 확인하고 실행하기

1. 이 프로젝트에서 전달받은 RC3 원본 ZIP인지 확인합니다. 다른 곳에서 받은 파일은 같은 이름만으로 판단하지 않습니다. 파일 해시는 PowerShell의 다음 명령으로 확인할 수 있습니다. `<ZIP 전체 경로>`를 실제 압축 파일 경로로 바꿉니다.

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath '<ZIP 전체 경로>'
```

현재 일반 프로그램 ZIP의 기준값:

```text
ATIVBatteryGuard-0.3.0-rc.3-WIN10-X64.zip
9af9dd9758b75a2e6449548be4a12ece42548d7b888c77698ffd64195e7096c5
```

이 값은 ZIP 전체의 해시입니다. EXE 단독이나 추가 검사 ZIP과 비교하지 않습니다. 대소문자는 무관하며 일치하지 않으면 이 기준으로 실행을 허용하지 않습니다. 해시 일치는 전달한 배포물과 같은 바이트임을 확인하며 악성 코드 부재를 보증하는 검사는 아닙니다.

2. ZIP 전체를 새 폴더에 풀고 `ATIVBatteryGuard.exe`를 실행합니다. DLL/config를 함께 두며 일반 사용에는 검사 CMD가 필요 없습니다.
3. SmartScreen 경고에서 **추가 정보**를 누릅니다. 표시된 앱 이름이 실행하려던 EXE인지 확인하고, 위 파일을 신뢰하기로 결정한 경우 **실행** 버튼으로 해당 실행을 허용합니다. 현재 미서명이므로 게시자가 ‘알 수 없는 게시자’로 남는 것이 예상됩니다.
4. 실행 버튼이 없거나 별도의 관리자/조직 정책 차단이 보이면 이 절차로 해결할 수 없습니다. 창 제목·문구와 버튼 유무로 원인을 확인해야 합니다.

이는 사용자가 해당 파일의 실행을 허용하는 절차입니다. SmartScreen 전체를 끄거나 Defender 예외·정책 변경을 적용하지 않습니다. 파일 속성의 차단 해제나 `Unblock-File`을 자동으로 실행하는 도구도 추가하지 않습니다. 파일을 확인하기 전에 자동으로 승인하는 기능은 없습니다.

다음 실행에는 이미 압축을 푼 같은 폴더의 EXE/바로가기를 사용합니다. 매번 ZIP을 다시 풀 필요는 없습니다. 새 버전이나 새로 받은 파일에서는 경고가 다시 나타날 수 있으며 한 번 허용했다고 향후 모든 실행이 허용되는 것은 아닙니다. 검사를 위해 받았던 CMD/IME 도구를 다시 실행할 필요는 없습니다.

## 장기 배포를 위한 선택 사항

개인 사용을 위해 유료 인증서를 먼저 구매할 필요는 없습니다. 외부 배포 시에는 검증된 배포자 서명과 같은 게시자 신원을 계속 사용하는 방법을 검토합니다. Microsoft 안내상 OV/EV 서명도 새 파일의 평판 경고를 즉시 없애지는 않습니다. EV를 구매하면 바로 사라진다는 안내는 적용하지 않습니다. 소비자 SmartScreen 평판 경고를 없애기 위해 파일을 제출하는 일반 심사 경로도 제공되지 않습니다.

Store의 MSIX 배포는 별도 경로이며 현재 ZIP을 단순히 올리는 작업은 아닙니다. 이 프로그램은 수동 충전 제어에서 별도 helper의 `runas`를 사용하므로 패키징/권한/Store 적합성 검토가 필요합니다. 현재 앱의 기능을 임의로 제거하거나 MSIX로 바꾸지 않았습니다.

무료 공개 소프트웨어 서명 지원은 공개 저장소·OSI 라이선스 등 자격과 심사가 필요합니다. 현재 저장소에서 LICENSE/COPYING을 찾지 못했으며 사용자는 공개 배포를 선택하지 않았으므로 라이선스 변경이나 신청은 하지 않습니다. Artifact Signing은 공식 제품 빠른 시작 문서상 한국 조직의 Public Trust를 지원하지만 개인 개발자는 미국/캐나다로 제한됩니다. 한국 거주 개인에게 사용 가능하다고 단정하지 않습니다.

## 근거와 확인 범위

- [Microsoft: SmartScreen 앱 평판](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation)
- [Microsoft: 코드 서명 선택](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)
- [Artifact Signing: 실제 가입 요건](https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart) — 서명 선택 개요 페이지보다 조직 지원 국가 목록이 넓으므로 서비스 가입 요건을 우선 확인합니다.
- [SignPath Foundation 조건](https://signpath.org/terms.html)
- [MSIX 데스크톱 앱 준비](https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-prepare)

이번 작업은 개인 사용 절차/현재 상태의 기록입니다. 사용자의 실제 PC에서 실행 허용이나 경고 해소를 확인한 결과는 아직 없습니다. 앱 소스·배포 ZIP·검사 코드는 변경하지 않았고 새 빌드/기능 테스트도 실행하지 않았습니다. 실제 서명·비용 발생·서비스 가입·외부 파일 제출은 없습니다.
