# 개발 환경과 재개 명령

기준: 0.3.1 / 2026-11-26 한국 시간. 이 문서는 기존에 성공한 환경과 복구 방법을 기록합니다. 이번 문서 정리에서 새 환경 설치·제품 재빌드·기능 검사를 수행하지 않았습니다.

## Windows 개발 PC — 권장

- Windows 10 x64 대상, Visual Studio 2022의 .NET 데스크톱 개발 워크로드.
- .NET Framework 4.8 개발자 팩/대상 팩.
- .NET 8 SDK. 검증된 SDK는 8.0.428입니다. SDK를 바꾸면 빌드 바이트가 달라질 수 있습니다.
- 패키징 작업에만 Python과 pefile/dnfile 필요. 일반 사용자는 개발 도구가 필요 없습니다.

GitHub 브랜치를 받은 후 `ATIVBatteryGuard` 폴더에서 실행합니다.

```powershell
dotnet --info
dotnet restore src/ATIVBatteryGuard.App/ATIVBatteryGuard.App.csproj --configfile NuGet.Config
dotnet restore tests/ATIVBatteryGuard.PortableTests.csproj --configfile tests/NuGet.Config
dotnet build src/ATIVBatteryGuard.App/ATIVBatteryGuard.App.csproj -c Release --no-restore
dotnet run --project tests/ATIVBatteryGuard.PortableTests.csproj -c Release --no-restore -- --report reports/portable-maintenance.json
```

매번 새 보고서 이름/폴더를 사용해 원본을 보존합니다. GUI/플랫폼에 영향을 주는 수정일 때만 Windows에서 `ATIVBatteryGuard.exe --self-test "새 결과 JSON의 전체 경로"` 또는 해당 버전에 맞는 ValidationCheck를 실행합니다. 기존0.3.1의 현장 확인을 반복할 필요는 없습니다.

앱 결과는 `src/ATIVBatteryGuard.App/bin/Release/net48`입니다. EXE와 Core.dll/WmiInterop.dll/helper EXE 및 두 config를 함께 다룹니다. 앱은 일반 권한으로 시작하며 사용자가 제어 작업을 선택한 경우만 별도 helper에 관리자 확인을 요청합니다.

## 현재 클라우드 작업공간이 남아 있을 때

먼저 디렉터리가 실제로 있는지 확인합니다. 경로가 없으면 아래 새 환경 절차를 사용합니다.

```bash
source /workspace/work/ativ-setup/env.sh
dotnet --version
```

기존 SDK는 `/workspace/tools/dotnet`, NuGet 캐시는 `/workspace/tools/nuget`, 패키징 Python은 `/workspace/tools/ativ-packaging/bin/python`입니다. 이 설치/캐시/셸 파일은 GitHub 배포물이 아니므로 새 환경에 있다고 가정하지 않습니다.

## 새 Linux 클라우드 환경

Linux는 portable 회귀와 net48 WPF 교차 빌드용입니다. 실제 Windows/WPF 실행·IME·Defender·하드웨어 작동을 대신하지 않습니다. 명령 실행을 먼저 확인하고 상태가 starting인 환경은 준비될 때까지 기다립니다.

1. Linux x64용 .NET SDK 8.0.428을 사용자 쓰기 가능 경로에 설치합니다. 공식 릴리스 메타데이터는 `https://dotnetcli.blob.core.windows.net/dotnet/release-metadata/8.0/releases.json`입니다. 다운로드 원본과 SHA512를 검증합니다.
2. 같은 버전의 공식 Windows x64 SDK ZIP에서 `sdk/8.0.428/Sdks/Microsoft.NET.Sdk.WindowsDesktop/` 하위만 Linux 설치의 같은 경로에 복사합니다. Windows SDK 전체를 덮어써 Linux dotnet host를 바꾸지 않습니다. 기존 환경의 해당48파일은 아래 공식 Windows SDK ZIP과 모두 동일했고 SDK targets를 임의 수정하지 않았습니다.
3. `DOTNET_ROOT`, `PATH`, `DOTNET_CLI_HOME`, `NUGET_PACKAGES`를 해당 설치/캐시 경로에 맞춥니다. 시스템 HOME을 다른 용도로 덮어쓰지 않습니다. 네트워크가 필요한 복원/다운로드 권한은 그 환경의 정책을 따릅니다.
4. root `NuGet.Config`로 앱과 확인 도구를 복원합니다. Linux의 net48 참조는 프로젝트가 지정한 `Microsoft.NETFramework.ReferenceAssemblies.net48` 1.0.3을 사용합니다. portable 테스트에는 외부 NuGet 소스가 필요 없으며 `tests/NuGet.Config`를 사용합니다.

기존 환경에 사용한 공식 SDK 원본:

```text
Linux x64:
https://builds.dotnet.microsoft.com/dotnet/Sdk/8.0.428/dotnet-sdk-8.0.428-linux-x64.tar.gz
SHA512:
33212bb99a2bf003973d41106c7e8fe94208a12958ff601d4a476be379403c85a7dc9183a6ec64dfb44ded7102965be09f35add1758e68e9251bae7891d7b7bf

Windows x64 SDK ZIP (WindowsDesktop SDK 하위만 사용):
https://builds.dotnet.microsoft.com/dotnet/Sdk/8.0.428/dotnet-sdk-8.0.428-win-x64.zip
SHA512:
cce1dc5cfb2c5b73ddd9d3658f6009deb85be3a58dbec44a6dfe3910bb32b044ad2fc6bb28c77aded70c73270a204d207fe790dcb82ffca6c7b42c1335b51c21
```

프로젝트 루트에서의 복원/빌드 예:

```bash
dotnet restore tests/ATIVBatteryGuard.PortableTests.csproj --configfile tests/NuGet.Config
dotnet restore src/ATIVBatteryGuard.App/ATIVBatteryGuard.App.csproj --configfile NuGet.Config
dotnet restore validation/ATIVBatteryGuard.ValidationCheck/ATIVBatteryGuard.ValidationCheck.csproj --configfile NuGet.Config
dotnet build tests/ATIVBatteryGuard.PortableTests.csproj -c Release --no-restore -p:UseSharedCompilation=false -m:1
dotnet tests/bin/Release/net8.0/ATIVBatteryGuard.PortableTests.dll --report reports/portable-maintenance.json
DOTNET_ReadyToRun=0 dotnet build src/ATIVBatteryGuard.App/ATIVBatteryGuard.App.csproj -c Release --no-restore -p:UseSharedCompilation=false -m:1
dotnet build validation/ATIVBatteryGuard.ValidationCheck/ATIVBatteryGuard.ValidationCheck.csproj -c Release --no-restore -p:UseSharedCompilation=false -m:1
```

`DOTNET_ReadyToRun=0`은 Windows SDK에서 가져온 WPF 빌드 작업을 Linux에서 로드할 때 사용한 기존 대응입니다. WPF 교차 빌드에 사용하는 설정이며 Windows GUI를 Linux에서 실행할 수 있게 하는 설정은 아닙니다.

## Python 패키징 개발 환경

기존에 검증한 환경은 Python 3.12.14, pefile 2024.8.26, dnfile 0.18.0입니다. 개발 때만 필요한 의존성입니다.

```bash
python3 -m venv /workspace/tools/ativ-packaging
/workspace/tools/ativ-packaging/bin/python -m pip install -r docs/maintenance/packaging-requirements.txt
```

소스를 수정했을 때 관련 배포 검사를 실행하는 예:

```bash
/workspace/tools/ativ-packaging/bin/python -m unittest discover -s scripts -p 'test_*release*.py' -v
```

현재0.3.1에서는27개였습니다. 제품 portable 회귀는1275개입니다. 개수만 합격 조건으로 삼지 말고 실패/skip과 관련 새 사례를 확인합니다. 고정 버전의 패키지 검사는 해당 소스와 과거ZIP에 의존합니다. 미래의 변경이 의도대로 고정 조건에 거부되면 이유를 조사하고 새 버전에 맞는 검증을 준비합니다.

## 기록과 배포

- 새 실행 결과는 별도 이름으로 저장하고 필요한 JSON/로그만 Git에 추가합니다. `reports/`는 ignore 대상이므로 명시적인 추가가 필요합니다.
- 현재0.3.1 합격 기록은 [파일 색인](FILE_INDEX.md)을 참조합니다. 문서만 갱신하면 ZIP/해시와 프로그램 동일성을 확인하고 제품 빌드/하드웨어 시험을 반복하지 않습니다.
- 개인용 배포와 향후 서명 배포를 구분합니다. 기존 스크립트의 소스/서명/Defender 조건을 지워 새 버전을 통과시키지 않습니다.
