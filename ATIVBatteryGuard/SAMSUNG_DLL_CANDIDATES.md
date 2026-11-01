# 삼성 배터리 제어 관련 DLL 조사 목록

2026-11-01 기준입니다. 사용자가 전달한 참고 경로는 `C:\Program Files (x86)\Samsung\Setting`입니다. 경로의 `Setting` 표기를 그대로 기록합니다. 이 경로는 사용자 노트북의 로컬 폴더이며 클라우드 작업 환경에서 직접 열람한 폴더가 아닙니다. 아래는 실제 폴더 전체 목록이 아니라 공개 소스와 기존 조사에 근거한 확인 후보입니다.

## 우선 확인할 정확한 파일명

| 우선순위 | 파일명 | 확인한 역할과 근거 | 현재 노트북에서의 확인 범위 |
| --- | --- | --- | --- |
| 1 | `Sabi3.dll` | 공개 Windows C# 구현이 Battery Life Extender의 설정 조회·변경에 실제 참조하는 삼성 BIOS 인터페이스 DLL | 사용자가 해당 파일이 있다고 보고함. 파일 버전·함수·비트 수·모델 호환성은 아직 확인하지 않음 |
| 2 | `wsabi.dll` | 이전 자료의 정적 분석에서 확인한 삼성 WMI/COM 펌웨어 중계 DLL. 배터리 제어와 연결되는지는 별도 조사 대상 | 이전 서비스 자료에서 존재를 확인했으나 현재 `Setting` 폴더에 있는지는 미확인. 확인된 호출 문맥은 팬·정숙 모드 |

배터리 기능을 직접 가리키는 공개 근거는 현재 `Sabi3.dll`에 있습니다. `wsabi.dll`은 배터리 전용 DLL로 확정하지 않습니다. 두 파일이 서로 대체 가능하거나 같은 호출 규약을 가진다고 가정하지 않습니다.

## 추가 후보를 찾을 검색 패턴

파일 탐색기에서 아래 패턴으로 이름을 찾아볼 수 있습니다. 이 항목들은 실제 파일명을 확인한 목록이 아니라 검색 조건입니다. 일치한 파일도 배터리 상한 제어용이라고 바로 판단할 수는 없습니다.

| 검색 패턴 | 이름으로 찾는 범위 |
| --- | --- |
| `*sabi*.dll` | SABI 계열 이름 |
| `*battery*.dll` | 배터리 관련 이름 |
| `*power*.dll` | 전원 관련 이름. 일반 절전 기능도 포함될 수 있음 |
| `*charge*.dll` | 충전 관련 이름. USB 충전 기능도 포함될 수 있음 |

후보가 보이면 이후 식별에 필요한 정보는 정확한 파일명, 상대 폴더 위치, 파일 버전, 제품명·설명, 32/64비트 구조입니다. 이번 단계에서는 정보 제출이나 파일 업로드를 요청하지 않습니다.

## 배터리 제어 DLL로 오해하지 않을 항목

- `SABI.dll`: 공개 프로젝트의 초기화 오류 문구에는 나오지만 실제 `DllImport`는 `Sabi3.dll`을 가리킵니다. 오류 문구만으로 별도 제어 DLL의 존재나 역할을 확정하지 않습니다.
- `Sabi2.dll`, `BatteryLifeExtender.dll`: 이번에 읽은 자료와 제한된 GitHub README 검색에서는 근거를 확보하지 못했습니다. 그럴듯한 이름이라는 이유로 실제 설치 파일명으로 제시하지 않습니다. 검색 결과가 없다는 사실만으로 파일이 어디에도 없다고 단정하지 않습니다.
- `SABI.sys`: 구형 공개 도구의 README에 나오는 커널 드라이버입니다. DLL이 아니며 현재 Settings 버전의 필수 의존성이라고 확정하지 않습니다.
- `ModuleKeyboardBacklit.dll`: 다른 모델인 Samsung Notebook 9(2017)용 공개 도구의 설정 예제에 나오는 키보드 백라이트 DLL입니다. 배터리 제어 후보의 근거가 아닙니다. 그 예제의 `Settings\CmdServer` 경로를 현재 사용자의 `Setting` 경로로 대체하지 않습니다.
- Windows 공용 DLL과 Visual C++ 실행 라이브러리는 배터리 제어 DLL 목록으로 보지 않습니다.

## 실제 확인한 출처

1. [SamsungBIOSInterface.cs 고정 커밋](https://github.com/akastormseeker/samsung-hotkeys/blob/0d3947eea0003dd8e9372c36925c0fd0a8fd28d3/SamsungHotkeys/Controls/SamsungBIOSInterface.cs): 88–118행은 배터리 보호 조회·변경, 264–265행은 기능 번호, 291–305행은 `Sabi3.dll` 참조입니다.
2. [같은 프로젝트 README](https://github.com/akastormseeker/samsung-hotkeys/blob/0d3947eea0003dd8e9372c36925c0fd0a8fd28d3/README.md): 구형 도구의 삼성 DLL·드라이버 의존성을 설명합니다. 현재 노트북의 지원 검증은 아닙니다.
3. [App.xaml.cs](https://github.com/akastormseeker/samsung-hotkeys/blob/0d3947eea0003dd8e9372c36925c0fd0a8fd28d3/SamsungHotkeys/App.xaml.cs): 51행의 일반 오류 메시지와 실제 DLL 참조를 구분했습니다.
4. [기존 자체 하드웨어 조사 기록](HARDWARE_RESEARCH.md): `wsabi.dll`의 WMI/COM 중계와 팬·정숙 모드 정적 분석 결과입니다. 원본 삼성 파일은 저장소에 넣지 않습니다.
5. [Notebook 9용 공개 도구의 App.config](https://github.com/HubKing/KeyboardBrightness/blob/abbe813e25828738a23281bbf43e3bba818db4d9/Backlight/App.config): 7행은 `ModuleKeyboardBacklit.dll`을 참조합니다. [프로젝트 설명](https://github.com/HubKing/KeyboardBrightness/blob/abbe813e25828738a23281bbf43e3bba818db4d9/README.md)은 대상이 Notebook 9(2017)의 키보드 백라이트임을 명시합니다.

이 목록은 폴더 참고와 후보 조사용입니다. 이번 단계에서 삼성 DLL을 추출·로드·실행하거나 앱의 탐색 경로·하드웨어 제어를 변경하지 않았습니다. 문서 변경만 수행했으며 빌드·테스트를 다시 실행하지 않았습니다.
