# 0.3.0 개인용 최종 파일 확인 결과

2026-11-26 한국 시간. 사용자 Windows10 x64 / 940X3G에서 받은 [원본과 평가](reports/field-030-personal/assessment.json)를 보존합니다. 실행 시각은 15:09:18~15:09:21입니다.

- ReleaseVersion 0.3.0, 배포 소스 지문 `9b6cee36eca561866a79dae6ed00a7cbe272be8dcae37069ee32bae70a8846c2`가 전달한 일반 ZIP/FINAL-CHECK와 일치합니다.
- FilesVerifiedBefore/After, GuiExecuted/Passed 모두 true, GuiExitCode 0입니다.
- 내장 Gui와 별도 gui-0261… JSON이 같고 GUI passed, 바인딩 오류 0, 오류 배열 없음, 하드웨어 쓰기 false입니다.
- 기본 배터리 available, WMI complete입니다. Defender/서명/새 수동 검사는 실행되지 않았습니다.

현재 0.3.0 파일의 GUI·무결성 확인은 통과했습니다. 도구의 수동 검사 대기 문구는 그 실행에서 새 수동 검사를 하지 않았다는 뜻으로, 과거에 통과한 IME/충전/반복 검사 근거를 무효화하지 않습니다. 실제 서명이나 SmartScreen 평판 해소를 확인한 결과로 확대하지 않습니다. 기존 ZIP 내부의 대기 메타데이터는 원본 보존을 위해 바꾸지 않습니다.

사용자는 80% 충전 제한 버튼만 고정 파란색이라 제한 해제 상태와 혼동된다고 보고했습니다. 이것은 이번 GUI 검사의 기존 범위에서 실패한 항목이 아니라 추가로 확인된 표시 문제입니다. [0.3.1](RELEASE_031.md)에서 표시 바인딩을 수정하고 합성 조회값으로 실제 WPF 버튼 색 전환을 확인하는 새 검사를 추가했습니다. 0.3.0 통과를 새 0.3.1 Windows 실행 완료로 표시하지 않습니다.
