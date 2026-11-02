# WMI 권한 결과와 전송 준비 — 2026-11-03 한국 시간

## 확인한 사실

사용자가 첨부한 samsung-files-20261102T152127 보고서를 관측 자료로 읽었습니다. 원본 TXT와 삼성 원본 바이너리는 저장소·배포 ZIP에 추가하지 않았습니다.

| 관측 | 결과 | 해석 한계 |
| --- | --- | --- |
| SABI 연결 이름 | NotFound | 현재 이름 조회에서 미관측이며 미설치·펌웨어 기능 부재 판정 아님 |
| 커널 드라이버 목록 | 정상 조회 완료 | 이름 조건의 제한된 범위 |
| 이름 후보 | Samsung 분류 7개, 모두 Stopped/Manual | SABI 드라이버인지, 충전 기능과 관련 있는지는 미확인 |
| WmiAcpiVersion | AccessDenied | Active·version은 미관측, 클래스 부재나 비활성으로 바꾸지 않음 |
| WmiAcpiMethod | AccessDenied | 실제 메서드 호출 허가나 동작은 미검증 |
| 파일 검사 | Partial·범위 제한, 항목 9개·서로 다른 해시 8개 | 미표시 파일의 부재·전체 유일성 판정 불가 |

관측된 x64 Sabi3.dll은 이미 정적 분석한 28,976바이트·3.2.0.0 파일과 해시가 같습니다. 새 DLL을 요청할 이유가 없습니다. 현재 Settings의 wsabi 변형들은 기존 서비스 폴더에서 분석한 해시와 다르므로, 서비스 wsabi의 규약을 모든 Settings DLL에 일반화하지 않습니다.

앱이 정상 실행되고 TXT가 만들어진 사실과 각 조회의 성공은 별개입니다. 이번 자료는 WMI 속성 조회가 오류 없이 성공했다는 결과가 아니라, 앱이 권한 거부를 정상적으로 기록했다는 실제 Windows 관측입니다. 두 경로는 독립되어 있으므로 후보 드라이버 중지나 SABI 이름 미관측을 WMI 권한 거부의 원인으로 단정하지 않습니다.

## 일반 권한의 연결 설정 보완

기존 ConnectionOptions의 기본 Impersonation은 이미 Impersonate이며 Authentication은 Unchanged입니다. 따라서 Impersonate를 다시 지정하는 것만으로 권한 오류가 해결된다고 설명하지 않습니다.

Microsoft 문서는 RequiresEncryption 네임스페이스가 명시적인 암호화 인증을 사용하지 않은 데이터 요청을 거부할 수 있다고 설명합니다. 이에 로컬 ROOT\WMI 인스턴스 조회에 AuthenticationLevel.PacketPrivacy를 명시하고 Impersonate를 함께 적었습니다. EnablePrivileges=false와 현재 사용자 토큰을 유지합니다. 암호화가 되지 않으면 약한 인증으로 재시도하지 않습니다.

이는 ACL이나 제공자 권한을 바꾸는 기능이 아닙니다. 해당 노트북에서 암호화 요구가 거부 원인이었는지, 새 설정으로 조회되는지는 아직 미검증입니다. 관리자 실행이 해결한다는 근거도 없으므로 권한 상승·ACL 수정·보안 설정 변경·서비스 시작으로 전환하지 않습니다. 기존 클래스 메타데이터 전용 조회기는 변경하지 않았습니다.

공식 근거:

- [ConnectionOptions API 원문](https://raw.githubusercontent.com/dotnet/dotnet-api-docs/main/xml/System.Management/ConnectionOptions.xml): Authentication 기본값 Unchanged, Impersonation 기본값 Impersonate. 문서에는 .NET Framework의 System.Management 4.0도 포함됩니다.
- [WMI 네임스페이스의 암호화 연결 요구](https://learn.microsoft.com/en-us/windows/win32/wmisdk/requiring-an-encrypted-connection-to-a-namespace): RequiresEncryption이면 명시적 encrypted authentication 없는 요청을 거부할 수 있습니다.
- [WMI 네임스페이스 보안](https://learn.microsoft.com/en-us/windows/win32/wmisdk/securing-wmi-namespaces): 네임스페이스와 데이터 접근은 보안 설명자로 제어되며 인증 수준만으로 접근 권한이 생기지 않습니다.

## 현재 관측의 화면·보고서 해석

SamsungTransportAssessment는 현재 보고서의 SABI 이름·두 WMI 클래스 결과와 후보 수를 요약하는 순수 코드입니다. 상세 TXT 위에 같은 요약을 표시하고, 메인 화면에서도 TXT 저장 상태와 별도로 보여줍니다. 따라서 저장 성공이 조회 성공으로 보이지 않게 했습니다.

중지·수동 시작 후보 수를 보여주되 시작 대상을 선택하지 않습니다. WMI 권한 거부는 Unknown 값과 함께 유지하고 기능 부재로 바꾸지 않습니다. 새 조회 중에는 이전 요약을 지우고, 공급자 실패·시간 초과 시 이전 관측을 재사용하지 않습니다. TXT 저장만 실패하면 관측한 요약은 화면에 남습니다. 종료 뒤 늦게 끝난 작업은 요약을 갱신하지 않습니다.

이 평가는 실제 통신 경로 선택기나 하드웨어 어댑터가 아닙니다. 인스턴스·드라이버·SABI 이름이 모두 관측되어도 읽기·쓰기·메서드 실행 가능 플래그는 false이며 실제 충전 제어는 계속 Unsupported입니다.

## 실제 호출 없이 준비한 요청 프레임

기존 서비스 wsabi의 [정적 전송 분석](SABI_LINK_RESULT_AND_WMI_REVIEW.md)에 맞는 WsabiWmiRequestEncoder를 추가했습니다. 분석 해시는 기존 WsabiWmiReplyValidator와 같은 564b640d62db2a4e4b56c6331e0e526bad2ac1fcf438a41a9e5241551f457b6e에 한정합니다.

프레임은 0x5843의 little-endian 2바이트, 명령 2바이트, 0 한 바이트, payload 16바이트로 총 21바이트입니다. 명령 입력은 0..65535만 허용하고 상위 비트를 자르지 않습니다. 정확한 byte[] 16바이트만 복사하며 입력을 변경하지 않고 매번 독립 배열을 만듭니다. 실패하면 출력은 빈 배열입니다.

일반 프레임 인코딩은 명령 의미나 안전성을 입증하지 않습니다. 배터리 명령 번호·기본 요청·명령 목록을 추가하지 않았으며 앱 실행 경로에도 연결하지 않았습니다. 삼성 DLL·WMI 메서드·장치에 어떤 요청도 보내지 않습니다. Sabi3 x64의 11바이트 ABI와도 구분합니다.

## 검증과 남은 조건

이번 전체 공유 소스 suite는 228개 통과·실패/건너뜀 0개, 별도 배포 검증 6개 통과, x64 net48 WPF/XAML 빌드 경고·오류 0개입니다. 새 11개 그룹은 프레임의 형식·경계·버퍼 독립성, 관측 조합과 잘못된 인과 추론 차단, 재조회/실패/저장 실패 시 요약, 하드웨어 쓰기 차단을 검사합니다. 이전 suite의 종료 후 완료 테스트도 요약까지 확인하도록 확장했습니다.

새 PacketPrivacy 연결·요약 화면의 노트북 실기 동작과 권한 거부 해소는 아직 미검증입니다. 확인하려면 새 개발판을 일반 권한으로 실행해 같은 버튼의 현재 요약을 볼 수 있습니다. 이전 TXT·삼성 DLL/EXE·기존 진단을 다시 제출할 필요는 없습니다.

새 연결에서도 권한 거부라면 해당 사용자에게 허용된 범위의 인스턴스 읽기가 현재 외부 제약입니다. 실제 보호 상태 조회·제어는 별도로 모델 적합성·명령 의미·응답 계약과 필요한 접근 권한이 검증되어야 합니다. 이 보고서만으로 관리자 권한이나 펌웨어 작업을 승인한 것으로 간주하지 않습니다. 환경 설정 재적용이나 게시는 하지 않았습니다.
