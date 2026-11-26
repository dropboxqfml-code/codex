# 0.3.0 최종 파일 검사와 검토용 패키징

현재 작업의 개인용 0.3.0은 [별도 배포 기록](RELEASE_030_PERSONAL.md)을 따릅니다. 아래는 향후 **서명된 배포**를 위한 경로로 유지하며 개인 사용의 선행 조건이 아닙니다. 제품은 버전 상수만 0.3.0으로 변경됐지만 실제 서명·서명된 파일의 GUI/보안 검사는 여전히 없습니다. 아래 준비 당시 RC3 설명은 이력입니다.

2026-11-26 한국 시간. 현재 앱은 **0.3.0-rc.3**이며 변경하지 않았습니다. [RC3 Windows 닫기 통과](FIELD_IME_CLOSE_030_RC3_RESULT.md)를 보존합니다. 서명 인증서/서비스는 없으며 실제 서명·새 Windows 검사·최종 ZIP 작성/공개는 수행하지 않았습니다. [실행 경고](WINDOWS_STARTUP_WARNINGS.md)는 미해결입니다.

## 준비한 코드

- `Test-WindowsRelease.ps1 -RequireTimestamp -RunGuiSelfTest`: 고정 6파일/PE 4개 동일 유효 게시자·타임스탬프, Defender 보호/정의/검사·탐지·파일 전후 해시를 확인하고 같은 폴더의 EXE에 고정 `--self-test` 인수를 전달합니다. 별도 helper는 실행하지 않습니다. 120초 이내 종료 0/GUI 통과/바인딩 오류 0/하드웨어 쓰기 false를 요구하며 GUI JSON 해시·시각·동일 6파일 해시를 수집합니다. 시간 초과 시 프로세스를 강제 종료하지 않고 증거 생성을 실패시킵니다. GUI 검사는 실제 수동 입력/IME나 물리적 클릭을 대신하지 않습니다.
- `final_release_030.py`: 정확한 최종 버전 0.3.0, 24시간 이내 Windows 보안/GUI 근거, 동일 서명 파일 6개의 해시와 원본 GUI JSON 해시를 연결합니다. 중복 키·비유한 수·과대 JSON·잘못된 타입을 거부합니다. RC3의 207소스는 정확한 버전 상수 변경만 허용합니다. 그 외 소스 변경은 새 검증이 필요합니다.
- `package_final_030.py`: 위 조건과 전체 회귀 1272개 이상 통과, 기존 RC3 ZIP 지문 및 닫기 통과 근거, 실제 PE/버전/권한/기존 안전 조건을 모두 요구합니다. 최종 서명 경로는 서명 존재와 Windows 유효성 근거를 함께 확인합니다. 기존 미서명 RC 경로는 그대로입니다. 통과 뒤에만 9항목 ZIP을 작성하고 CRC/내부 바이트를 확인하며 기존 파일을 덮어쓰지 않습니다.

생성 대상은 `ATIVBatteryGuard-0.3.0-WIN10-X64-SIGNED-REVIEW.zip`입니다. `signed-review-prepared`, `finalReleaseApproved=false`, `publicationPerformed=false`로 남습니다. JSON 근거는 실수로 검증되지 않은 파일을 묶는 일을 막기 위한 것이며 위조 보고서에 대한 독립 인증이 아닙니다.

## 인증서가 준비된 후 개발자 순서

1. RC3 근거와 원본 ZIP을 보존합니다. 최종 소스는 ApplicationRelease.cs의 Version 상수만 0.3.0으로 바꿉니다. 현재 작업에서는 이 변경을 하지 않습니다. 다른 기능 수정은 검증 범위를 다시 정합니다.
2. 별도 폴더에 Windows x64/net48 전체 프로그램을 빌드하고 실제 회귀 결과 JSON을 보존합니다. 최종 소스 지문은 아래 코드로 얻습니다. 현재 RC3에서는 의도적으로 실패합니다.

```python
# ATIVBatteryGuard 폴더, 패키징 도구의 Python 환경에서 실행
import sys, zipfile
from pathlib import Path
sys.path.insert(0, 'scripts')
from final_release_030 import read_json_bytes, verify_source_identity
from package_manual_control_beta import source_closure
root = Path.cwd()
with zipfile.ZipFile(root.parent / 'downloads/ATIVBatteryGuard-0.3.0-rc.3-WIN10-X64.zip') as z:
    candidate = read_json_bytes(z.read('BUILD-INFO.json'))
sources = dict(source_closure(root, root/'src/ATIVBatteryGuard.App/ATIVBatteryGuard.App.csproj'))
sources.update(source_closure(root, root/'src/ATIVBatteryGuard.ManualProtectionHelper/ATIVBatteryGuard.ManualProtectionHelper.csproj'))
print(verify_source_identity(sources, candidate))
```

3. 정당한 코드 서명 환경에서 EXE/DLL 4개에 SHA-256 서명과 인증기관이 안내한 타임스탬프를 적용합니다. 키/비밀번호를 저장소나 공유 로그에 넣지 않습니다. 실제 비용/발급/외부 전송은 별도 준비가 필요합니다.
4. Windows에서 해당 서명 폴더에 수집기를 실행합니다. 아래 경로와 지문은 실제 값으로 바꿉니다. 보호 기능·실행 정책을 바꾸지 않으며 필요한 실행 권한이 없으면 중단하고 미완료로 남깁니다.

```powershell
.\scripts\Test-WindowsRelease.ps1 -BuildDirectory 'C:\release\signed' -SourceFingerprint '<최종 소스 SHA256>' -ReportPath 'C:\release\evidence\windows.json' -RequireTimestamp -RunGuiSelfTest
```

5. 반환된 `guiReportFile`의 원본 JSON과 Windows 보고서를 함께 보존하고 24시간 안에 검토 ZIP을 작성합니다.

```text
python scripts/package_final_030.py --build-directory <서명된6파일폴더> --test-report <전체회귀결과.json> --windows-report <windows.json> --gui-report <final-gui-식별자.json> --output <새검토폴더>
```

6. 검토 ZIP의 게시자/해시/구성과 실제 Windows 실행 경고 상태를 확인합니다. 패키징 성공을 자동 출시 승인이나 경고 해소로 표시하지 않습니다. 일반 사용자는 EXE로 실행하고 검사 CMD는 제공하지 않습니다.

## 이번 검증 범위

Python 새 11개 + 기존 13개 = **24개 통과**. 가상 서명/백신/GUI 근거에 대한 판정 검사와 실제 RC3 미서명 PE 검사/최종 묶음 생성 거부를 포함합니다. 현재 RC3는 최종 버전 조건에서 거부되고 출력 폴더/ZIP이 생성되지 않음을 확인했습니다. 소스 지문도 기존 207파일과 같습니다. 제품 회귀 1272개/네 빌드 통과는 이전 RC3 기록이며 이번에 다시 실행하지 않았습니다. PowerShell·서명·타임스탬프·Defender·최종 Windows GUI는 이 Linux에서 실행하지 않았습니다.
