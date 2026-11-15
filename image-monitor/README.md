# Image Monitor — 개발 중

Windows에서 공개 게시글의 본문 이미지를 실제 우클릭과 브라우저의 네이티브 저장 창으로
저장하는 별도 프로젝트입니다. 기존 Image Duplicate Finder는 그대로 유지합니다.
현재 단계는 **검증한 예제 게시글 하나의 Chrome 저장 작업자**입니다.
정기 감시·검색 목록 탐색·설정 UI는 아직 구현하지 않았습니다.

Windows 사용자는 ZIP 안의 [짧은 TXT 안내](WINDOWS_TEST_GUIDE.txt)에 따라
처음 시험은 `RUN_POST_SAVE_TEST.cmd`, 안내된 v9 중단 건의 재개는 `RETRY_POST_SAVE_TEST.cmd`를
더블클릭합니다. 전용 Chrome에 표시된 게시글·완료 수·저장 위치를 확인하고
`저장 시작`을 한 번 누르면 됩니다. 이미지 사이에 전경을 잃으면 새 `계속 저장` 버튼으로
재개하며 결과 TXT는 자동으로 열립니다.
안내는 `image-monitor/WINDOWS_TEST_GUIDE.txt` 하나만 동봉합니다.
개발용 패키징은 `python scripts/build_windows_bundle.py --version v10`이며 기존 ZIP을 덮어쓰지 않습니다.

## 현재 구현

- 본문 `.write_div` 안의 로딩·decode가 완료된 일반 이미지 수집과 디시콘·광고·댓글·영상 제외.
- 유일한 게시글 헤더에서 제목·작성자·공개 부분 IP·Asia/Seoul 작성 시각 추출.
- 확인한 본문/첨부 엔드포인트의 공통 `no`로 원본명 대응과 안정적 작업 키 산출.
  순서·파일명·다른 속성으로 대응을 추측하지 않습니다.
- SQLite 발견·불변 관찰 결과·작업 선점·재시도 정책·파일 슬롯·최초 폴더 계획 보존.
- 전용 프로필·Windows 세션 공통 잠금·미해결 저장 표시와 전경/창 소유권 보호.
- 이미지 사이의 전경 이탈 시 선점 전 일시정지, 새 사용자 클릭과 게시글 재검사 후 재개.
- 입력 전 중단이 기록·원본 관찰·빈 임시 폴더·브라우저 종료로 입증된 v9 실패의 개별 재개.
- 저장 직전에 정확한 이미지 `currentSrc`, 본문 소속, 게시글 URL과 예상 헤더 재검사.
- 실제 우클릭 → UIA 메뉴 Invoke → Windows Save As에 고유 staging 경로 입력.
- Chrome의 소유한 백그라운드 다운로드 목록에서 정확한 원본 URL·저장 경로와 완료 상태 확인.
- 배타적 파일 읽기와 Pillow 전체 프레임 검증으로 형식·크기·SHA-256 산출.
- 최종 파일 덮어쓰기 거부, 확정 저널, DB 완료 처리와 원자적 `metadata.json` 기록.
  확정 도중 중단된 작업은 네이티브 저장을 반복하지 않고 로컬 파일과 저널로 복구합니다.

실사이트 저장 대상은 사용자 v7/v8 관찰로 검증한 일반 갤러리 `comic_new6`의
게시글 `7036949` 한 개로 제한합니다. 다른 게시글·마이너·미니 갤러리는 아직 미검증입니다.
v9 사용자 TXT에서 실제 WEBP 한 개의 저장·검증·최종 확정을 확인했습니다.
두 번째 이미지는 첫 조작 전 전경 보호 검사에서 중단됐으며 나머지 저장과 재개 인수 시험이 남아 있습니다.
Edge와 Chrome의 기본 합성 이미지 저장은 Windows CI와 사용자 보고에서 성공했으며,
이번 통합 작업자의 완료 판독은 Chrome만 지원합니다.

원본 공개 첨부명·저장 창 제안명·최종 저장명은 메타데이터에 별도로 보존합니다.
저장 경로는 `감시이름/실제ID/날짜/작성자/글번호/001.실제확장자` 형태입니다.
금지 문자·예약 이름·이름 충돌·루트 이탈·심볼릭 링크와 경로 길이를 검사하며,
공개 IP는 화면에 보이는 표시값만 사용합니다.

## 실행과 개발

사용자 시험은 위 CMD를 사용하면 uv·관리형 Python 3.12.14·잠금 의존성을 준비합니다.
개발자는 이 디렉터리에서 실행합니다.

```powershell
uv sync --locked --extra windows
uv run --locked --extra windows image-monitor save-post --work-root C:/IMPost --browser chrome
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
```

Linux에서는 로컬 정책·검증·대기열·DOM fixture 시험을 실행할 수 있습니다.
실제 Windows UI 시험과 모의 시험의 결과는 [검증 기록](docs/validation.md)에 구분합니다.

- [게시글 저장 작업자와 장애 복구](docs/native-post-save.md)
- [본문 분석과 검증 범위](docs/post-inspection.md), [실사이트 관찰 근거](docs/live-dom-observations.md)
- [SQLite 대기열과 확정 저널](docs/queue.md)
- [Edge/Chrome 합성 이미지 기본 저장 시험](docs/native-probe.md)

중단 뒤 자동으로 재저장하거나 보류 상태를 초기화하지 않습니다.
먼저 결과 TXT를 확인하고, 개발자 안내를 받은 경우에만 이전 전용 브라우저를 닫은 뒤
`RETRY_POST_SAVE_TEST.cmd`를 사용합니다. 이 실행기는 브라우저 종료 확인과 로컬 복구를
수행하며, 기록과 파일을 대조해 검증한 입력 전 실패 작업 하나만 다시 대기열에 넣습니다.
이미 저장한 파일·확정 기록·재시도 이력은 유지합니다. 입력이 시작됐거나 근거가 불명확한
보류 작업은 검토 상태를 유지합니다.

직접 HTTP 이미지 저장·응답 바이트 추출·`download.save_as`·스크린샷·재인코딩은 사용하지 않습니다.
알려진 원본 해시 비교는 합성 fixture 시험에만 사용하며 실제 게시글에서는 저장 파일의 해시를 기록합니다.
남은 작업은 정기 감시·검색과 누락 구간 재탐색·다중 갤러리·설정/열람 UI·용량 관리,
보류 작업 수동 처리, 화면 잠금·다중 모니터·배율의 추가 인수 시험,
Pillow 단일 디코딩 호출의 프로세스 격리입니다.
