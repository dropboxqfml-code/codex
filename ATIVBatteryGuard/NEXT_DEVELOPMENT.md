# 현재 유지보수 재개 메모

2026-11-26 한국 시간 기준. **0.3.1 개인용 안정판으로 개발·검증을 마쳤으며 현재 예정된 필수 개발은 없습니다.** 새 대화에서는 사용자에게서 보고된 구체적인 오류나 불편을 기준으로 수정합니다.

## 시작 순서

1. 명령 실행, Git 상태, 현재 브랜치/HEAD, 미커밋 작업부터 확인합니다.
2. [AGENTS.md](AGENTS.md)와 [MAINTENANCE_HANDOFF.md](MAINTENANCE_HANDOFF.md)를 읽습니다.
3. [FILE_INDEX.md](FILE_INDEX.md)에서 관련 기능/근거를 찾고, 새 환경이면 [DEV_ENVIRONMENT.md](DEV_ENVIRONMENT.md)를 따릅니다.
4. 사용자 증상과 관계있는 변경·검증만 수행하고 기존 파일/개인 자료를 보존합니다.

## 현재 기준

- 저장소/브랜치: `dropboxqfml-code/codex` / `feature/ativ-acpi-routing-readonly-20261104`.
- 제품:0.3.1 / 파일0.3.1.0 / Windows10 x64 / 940X3G.
- 현재 배포: [매뉴얼 동봉 ZIP](../downloads/ATIVBatteryGuard-0.3.1-WIN10-X64-MANUAL.zip). 기존 검증된 프로그램6파일과 동일하며 외부 사용자 매뉴얼만 교체했습니다.
- [현장 결과](FIELD_031_PERSONAL_RESULT.md): Windows 파일 전후/GUI/버튼 색 전환 통과, 오류·바인딩0, 사용자도 강조 정상 확인.
- 이전 제품 회귀1275개·배포27개 통과와 세 빌드 경고·오류0 근거를 보존합니다. 문서 정리에서 다시 실행하지 않았습니다.
- 미서명 개인용입니다. 인증서 구매·서명·공개 배포를 후속 필수 작업으로 두지 않습니다. 서명 안내는 매뉴얼에만 유지합니다.

## 다음 문제가 생겼을 때

[새 대화 시작문](NEW_CHAT_START.txt)에 현상·재현 순서·오류 문구/버전을 적습니다. 기존 디자인·동작·설정·기록을 유지하며 필요한 부분만 수정합니다. 과거 패치를 재적용하거나 하드웨어/IME/20분 시험을 일괄 반복하지 않습니다.

길었던 기존 재개 메모 전체는 [과거 이력](docs/history/NEXT_DEVELOPMENT_20261126.md)에 보존했습니다. 자세한 코드/커밋/해시/제약은 [MAINTENANCE_HANDOFF.md](MAINTENANCE_HANDOFF.md)가 현재 인수인계 기준입니다.
