"""Static, local monitor controls; live values are rendered as text only."""

from html import escape

from image_monitor import PUBLIC_VERSION

_PAGE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Image Monitor · 새 글 목록 감시</title>
<style nonce="__SCRIPT_NONCE__">
:root{color-scheme:light;--ink:#172d36;--muted:#607078;--line:#dde5e3;
  --paper:#fff;--canvas:#f5f6f1;--teal:#087c70;--teal-soft:#e7f3ef;
  --amber:#966413;--amber-soft:#fbf2df;--red:#a1423b}
*{box-sizing:border-box}
body{margin:0;background:var(--canvas);color:var(--ink);
  font:16px/1.6 "Segoe UI","Malgun Gothic","맑은 고딕","Noto Sans KR",sans-serif}
button,input{font:inherit}
button{cursor:pointer}
button:disabled{cursor:default;opacity:.42}
button:focus-visible,input:focus-visible{outline:3px solid #67b7aa;outline-offset:3px}
.app{width:min(1100px,100%);margin:auto;padding:24px 28px}
.header{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:24px}
.header-actions{display:flex;align-items:center;gap:15px}
.header-actions .button{font-size:12px;min-height:36px;padding:6px 12px;background:transparent}
.brand{display:flex;align-items:center;gap:13px}
.brand-mark{width:41px;height:41px;border-radius:12px;background:var(--ink);display:grid;
  grid-template-columns:repeat(2,7px);grid-template-rows:repeat(2,7px);place-content:center;gap:4px}
.brand-mark i{display:block;background:#d7e9d9;border-radius:2px}
.brand-mark i:last-child{background:#70b9aa}
.brand-name{font-size:20px;font-weight:750;letter-spacing:-.6px;line-height:1.25}
.brand-caption{font-size:12px;color:var(--muted);margin-top:3px;letter-spacing:.2px}
.connection{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--muted)}
.connection-dot{width:7px;height:7px;border-radius:50%;background:#82a595}
.connection[data-state="lost"] .connection-dot{background:#bb8b47}
.intro{margin-bottom:16px}
h1{font-size:28px;line-height:1.4;letter-spacing:-1.3px;margin:0 0 6px;font-weight:750}
.intro p{color:var(--muted);margin:0;font-size:15px}
.scope{display:inline-flex;align-items:center;gap:8px;margin-top:12px;padding:5px 12px;
  border:1px solid #d4dfd9;border-radius:8px;background:#edf2eb;font-size:13px;font-weight:600}
.scope-dot{height:6px;width:6px;border-radius:50%;background:var(--teal)}
.operations-panel{padding:17px 21px;margin-bottom:20px}
.operations-panel[hidden]{display:none}
.operations-heading{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}
.operations-heading h2{font-size:18px}
.operations-actions{display:flex;gap:8px;flex-wrap:wrap}
.operations-actions .button{font-size:12px;min-height:37px;padding:7px 11px}
.operations-state{margin:9px 0 3px;color:var(--teal);font-size:13px;font-weight:650}
.operations-state[data-state="needs_review"],.operations-state[data-state="busy"]{color:var(--amber)}
.operations-help,.operations-finish{margin:0;color:var(--muted);font-size:13px;line-height:1.65}
.operations-counts{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:7px;
  margin:12px 0 9px}
.operations-count{padding:7px 9px;background:#f3f6f2;border-radius:7px;min-width:0}
.operations-count dt{font-size:11px;color:var(--muted);overflow-wrap:anywhere}
.operations-count dd{font-size:20px;font-weight:700;margin:1px 0 0;line-height:1.3;
  overflow-wrap:anywhere}
.operations-count:first-child,.operations-count:nth-child(5){background:var(--teal-soft)}
.operations-wait{font-size:12px;color:var(--amber);margin:5px 0 0}
.operations-wait:empty,.operations-finish:empty{display:none}
.operations-records{font-size:12px;color:var(--muted);margin-top:8px}
.operations-records summary{cursor:pointer}
.operations-table{width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px;text-align:left}
.operations-table th,.operations-table td{padding:7px 5px;border-bottom:1px solid #edf0ee;
  overflow-wrap:anywhere;vertical-align:top}
.operations-table th:first-child{width:15%}.operations-table th:nth-child(2){width:23%}
.operations-table th:last-child{width:15%}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:18px 0 16px}
.metric{border:1px solid var(--line);border-radius:14px;background:var(--paper);padding:15px 22px}
.metric-label{color:var(--muted);font-size:13px;margin-bottom:8px}
.metric-value{font-size:30px;line-height:1.2;font-weight:730;letter-spacing:-1px}
.metric-value small{font-size:13px;letter-spacing:0;font-weight:500;margin-left:7px;
  color:var(--muted)}
.main-grid{display:grid;grid-template-columns:minmax(0,1fr) 294px;gap:18px;align-items:start}
.panel{background:var(--paper);border:1px solid var(--line);border-radius:16px;overflow:hidden}
.monitor-panel{padding:21px 25px 18px;min-height:300px}
.section-label{color:var(--muted);font-size:12px;font-weight:650;letter-spacing:.5px;margin:0}
.status-line{display:flex;align-items:center;gap:14px;margin:20px 0 11px}
.status-mark{width:41px;height:41px;flex-shrink:0;background:#eff3f2;border-radius:50%;
  display:grid;place-items:center}
.status-mark::after{content:"";display:block;width:12px;height:12px;border-radius:50%;background:#a0ada9}
.status-mark.active{background:var(--teal-soft)}
.status-mark.active::after{background:var(--teal);box-shadow:0 0 0 5px #d5ebe2}
.status-mark.attention{background:var(--amber-soft)}
.status-mark.attention::after{background:#b38431}
h2{margin:0;font-size:21px;font-weight:700;letter-spacing:-.8px;line-height:1.45}
.status-detail{margin:0 0 17px;color:var(--muted);font-size:14px;min-height:38px}
.list-diagnosis{margin:0 0 15px;color:var(--muted);font-size:13px}
.list-diagnosis summary{cursor:pointer}
.list-diagnosis p{white-space:pre-line;margin:6px 0 0}
.coverage{margin:0 0 15px;padding:8px 12px;border-radius:7px;background:var(--amber-soft);
  color:#705015;font-size:13px}
.times{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:14px 0;
  border-top:1px solid #edf0ee;border-bottom:1px solid #edf0ee}
.time-label{font-size:12px;color:var(--muted);margin-bottom:5px}
.time-value{font-size:13px;font-weight:600;word-break:keep-all}
.countdown{font-weight:500;color:var(--teal);margin-left:5px;white-space:nowrap}
.controls{display:flex;align-items:center;gap:8px;margin-top:16px;flex-wrap:wrap}
.button{border:1px solid #d4ded9;border-radius:8px;padding:9px 15px;font-size:14px;
  font-weight:600;min-height:43px;background:#fff;color:var(--ink);transition:background .12s}
.button:not(:disabled):hover{background:#f0f5f1}
.button.primary{background:var(--teal);border-color:var(--teal);color:#fff;padding-inline:21px}
.button.primary:not(:disabled):hover{background:#08665e}
.button.stop{color:var(--red)}
.settings{padding:21px 22px}
.settings h2{font-size:16px;letter-spacing:-.4px;margin-top:4px}
.setting-label{display:block;font-size:13px;font-weight:600;margin:19px 0 8px}
.input-row{display:flex;align-items:center;gap:10px}
input{width:100%;min-width:0;border:1px solid #cbd8d0;border-radius:8px;background:#fff;
  color:var(--ink);padding:9px 12px;font-size:19px;font-weight:600;line-height:1.4}
input:disabled{background:#f4f6f4;color:#7d8985}
.unit{font-size:14px;color:var(--muted);flex-shrink:0}
.setting-help{font-size:12px;color:var(--muted);margin:9px 0 15px;line-height:1.65}
.settings .button{width:100%}
.browser-note{display:flex;align-items:center;gap:8px;margin-top:20px;padding-top:17px;
  border-top:1px solid #edf0ee;color:var(--muted);font-size:12px}
.mini-dot{width:7px;height:7px;background:#8aa995;border-radius:50%}
.details-panel{margin-top:18px;padding:21px 25px}
.details-heading{display:flex;align-items:center;justify-content:space-between;gap:15px;flex-wrap:wrap}
.details-heading h2{font-size:18px;margin:2px 0 0;letter-spacing:-.5px}
.details-help{color:var(--muted);font-size:13px;margin:12px 0 8px}
.details-counts{color:var(--teal);font-size:13px;margin:0 0 15px}
.details-table{width:100%;table-layout:fixed;border-collapse:collapse;font-size:13px;text-align:left}
.details-table th{color:var(--muted);font-weight:600;font-size:12px;padding:8px 7px;
  border-block:1px solid #e6ebe6}
.details-table td{padding:11px 7px;border-bottom:1px solid #edf0ee;vertical-align:top;
  overflow-wrap:anywhere}
.details-table th:first-child{width:26%}.details-table th:nth-child(2){width:43%}
.details-table td small{display:block;color:var(--muted);font-size:11px;margin-top:2px}
.details-empty{color:var(--muted);font-size:13px;margin:15px 0 0}
.saved-panel{margin-top:18px;padding:21px 25px}
.saved-panel h2{font-size:18px;margin-top:2px;letter-spacing:-.5px}
.saved-state{color:var(--teal);font-size:13px;font-weight:650;margin:13px 0 3px}
.saved-state[data-state="needs_review"],.saved-state[data-state="busy"]{color:var(--amber)}
.saved-help{color:var(--muted);font-size:13px;margin:0;line-height:1.8}
.saved-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:16px}
.saved-grid:empty{display:none}
.saved-card{min-width:0;border:1px solid var(--line);border-radius:12px;overflow:hidden}
.saved-image{display:grid;place-items:center;min-height:120px;background:#f1f4f0;padding:12px}
.saved-image img{display:block;width:100%;height:auto;max-height:430px;object-fit:contain}
.saved-fallback{font-size:13px;color:var(--muted);padding:22px 8px;text-align:center}
.saved-caption{padding:12px 15px}
.saved-caption h3{font-size:14px;margin:0 0 5px;overflow-wrap:anywhere}
.saved-caption p{font-size:12px;color:var(--muted);margin:0;overflow-wrap:anywhere}
.message{font-size:13px;color:var(--teal);min-height:25px;padding:0 2px;margin:13px 0 0}
.message[data-kind="error"]{color:var(--red)}
.footer{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:19px;
  padding-top:18px;border-top:1px solid #dde4db;color:var(--muted);font-size:12px}
@media(max-width:760px){.app{padding:23px 17px}.header{margin-bottom:28px}
  .brand-name{font-size:18px}
  .connection{font-size:11px}.main-grid{grid-template-columns:1fr}
  .metrics{gap:9px;grid-template-columns:repeat(2,1fr)}
  .metric{padding:16px 13px}.metric-value{font-size:26px}.metric-label{font-size:11px}
  h1{font-size:26px}.monitor-panel{padding:23px 20px}.settings{padding:21px}
  .details-panel,.saved-panel{padding:21px 20px}.saved-grid{grid-template-columns:1fr}
  .setting-label{margin-top:17px}
  .settings form{display:grid;grid-template-columns:1fr 140px;gap:0 15px;align-items:end}
  .settings .setting-label,.settings .setting-help{grid-column:1/-1}
  .settings .setting-help{margin-bottom:2px}.settings .button{grid-column:2;grid-row:2}
  .browser-note{margin-top:17px}.footer{align-items:flex-start}}
@media(max-width:900px){.operations-counts{grid-template-columns:repeat(4,minmax(0,1fr))}}
@media(max-width:420px){.connection{max-width:88px;line-height:1.5}.metrics{grid-template-columns:1fr}
  .header-actions{flex-direction:column;align-items:flex-end;gap:6px}
  .metric{display:flex;align-items:center;justify-content:space-between}.metric-label{margin:0;font-size:13px}
  .metric-value{font-size:25px}.times{grid-template-columns:1fr;gap:13px}.controls{gap:7px}
  .controls .button{flex:1;padding-inline:10px}.footer{font-size:11px}
  .settings form{grid-template-columns:1fr 120px}
  .operations-panel{padding:14px;margin-bottom:18px}.operations-heading{gap:9px}
  .operations-actions{display:grid;grid-template-columns:1fr 1fr;width:100%;gap:6px}
  .operations-actions .button{font-size:11px;padding:7px 5px;min-width:0}
  .operations-counts{gap:5px}.operations-count{padding:6px}
  .operations-count dt{font-size:10px}.operations-count dd{font-size:18px}
  .operations-help,.operations-finish{font-size:12px}}
</style>
</head>
<body>
<main class="app">
  <header class="header">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i><i></i></span>
      <div><div class="brand-name">Image Monitor</div>
        <div class="brand-caption">__PUBLIC_VERSION__</div></div>
    </div>
    <div class="header-actions">
      <div class="connection" id="connection" data-state="connecting">
        <span class="connection-dot" aria-hidden="true"></span>
        <span id="connection-text">연결 확인 중</span>
      </div>
      <button class="button" id="exit" type="button">프로그램 종료</button>
    </div>
  </header>

  <section class="panel operations-panel" id="operations-panel"
    aria-labelledby="operations-title" hidden>
    <div class="operations-heading">
      <h2 id="operations-title">작업 현황</h2>
      <div class="operations-actions">
        <button class="button primary" id="save-one" type="button" disabled>후보 1건 저장</button>
        <button class="button" id="refresh-operations" type="button" disabled>
          작업 현황 새로 확인</button>
        <button class="button" id="finish-completed" type="button" disabled>
          완료 상태 다시 확인</button>
      </div>
    </div>
    <p class="operations-state" id="operations-state" data-state="disabled" role="status">
      현황 확인 준비 중</p>
    <p class="operations-help" id="operations-help"></p>
    <dl class="operations-counts" aria-label="마지막 현황 확인 시점의 작업별 개수">
      <div class="operations-count"><dt>내용 미확인</dt>
        <dd id="operation-candidate-uninspected">0</dd></div>
      <div class="operations-count"><dt>저장 가능</dt><dd id="operation-save-ready">0</dd></div>
      <div class="operations-count"><dt>저장 계획됨</dt><dd id="operation-save-planned">0</dd></div>
      <div class="operations-count"><dt>저장 진행 중</dt><dd id="operation-save-active">0</dd></div>
      <div class="operations-count"><dt>저장 완료</dt><dd id="operation-save-completed">0</dd></div>
      <div class="operations-count"><dt>저장 불가</dt>
        <dd id="operation-save-unavailable">0</dd></div>
      <div class="operations-count"><dt>저장 확인 필요</dt>
        <dd id="operation-save-needs-review">0</dd></div>
    </dl>
    <p class="operations-help">위 개수와 사유는 마지막 현황 확인 시점의 기록입니다.
      감시를 중지하면 현황을 한 번 갱신합니다. 저장할 때는 ‘후보 1건 저장’을 누른 뒤
      전용 Chrome에서 ‘저장 시작’을 누르고 완료될 때까지 그 창을 앞에 두세요.</p>
    <p class="operations-wait" id="operations-wait" role="status"></p>
    <p class="operations-finish" id="operations-finish" role="status"></p>
    <p class="operations-finish" id="save-outcome" role="status"></p>
    <details class="operations-records" id="operations-records" hidden>
      <summary>최근 작업 기록 · 최대 20개</summary>
      <table class="operations-table" aria-label="익명 작업 현황">
        <thead><tr><th scope="col">순서</th><th scope="col">상태</th>
          <th scope="col">사유</th><th scope="col">이미지</th></tr></thead>
        <tbody id="operations-rows"></tbody>
      </table>
    </details>
  </section>

  <section class="intro" aria-labelledby="page-title">
    <h1 id="page-title">새 글 감시</h1>
    <p>감시 시작을 누르면 목록을 읽습니다. 내용 미확인 후보가 있으면 한 건을 자동으로 확인한 뒤
      목록으로 돌아옵니다.</p>
    <div class="scope"><span class="scope-dot" aria-hidden="true"></span>만화 · ai · 제목+내용</div>
  </section>

  <section class="metrics" aria-label="발견 현황">
    <div class="metric"><div class="metric-label">기록된 후보</div>
      <div class="metric-value"><span id="candidate-count">0</span><small>개</small></div></div>
    <div class="metric"><div class="metric-label">이번 실행에서 추가</div>
      <div class="metric-value"><span id="new-count">0</span><small>개</small></div></div>
    <div class="metric"><div class="metric-label">이번 실행의 목록 확인</div>
      <div class="metric-value"><small>완료</small> <span id="cycle-count">0</span>
        <small>부분</small> <span id="partial-cycles">0</span></div></div>
    <div class="metric"><div class="metric-label">이번 실행의 자동 후보 확인</div>
      <div class="metric-value"><span id="auto-details-checked">0</span><small>건</small></div>
    </div>
  </section>

  <div class="main-grid">
    <section class="panel monitor-panel" aria-labelledby="status-title">
      <p class="section-label">감시 상태</p>
      <div class="status-line" aria-live="polite">
        <span class="status-mark" id="status-mark" aria-hidden="true"></span>
        <h2 id="status-title">상태를 확인하고 있습니다.</h2>
      </div>
      <p class="status-detail" id="status-detail">잠시 기다려 주세요.</p>
      <p class="coverage" id="coverage-gap" hidden></p>
      <details class="list-diagnosis" id="list-diagnosis" hidden>
        <summary>최근 목록 구조 확인 실패 기록</summary>
        <p id="list-diagnosis-details"></p>
      </details>
      <div class="times">
        <div><div class="time-label">마지막 목록 확인</div>
          <div class="time-value" id="last-scan">아직 없음</div></div>
        <div><div class="time-label">다음 확인 가능 시각</div>
          <div class="time-value"><span id="next-scan">—</span>
            <span class="countdown" id="countdown"></span></div></div>
      </div>
      <div class="controls" aria-label="감시 제어">
        <button class="button primary" id="start" type="button" disabled>감시 시작</button>
        <button class="button" id="pause" type="button" disabled>일시정지</button>
        <button class="button stop" id="stop" type="button" disabled>중지</button>
      </div>
    </section>

    <aside class="panel settings" aria-labelledby="settings-title">
      <h2 id="settings-title">확인 간격</h2>
      <form id="settings-form">
        <label class="setting-label" for="interval">확인 사이의 최소 간격</label>
        <div class="input-row"><input id="interval" type="number" min="60" max="300"
          step="1" value="60" inputmode="numeric" required disabled>
          <span class="unit">초</span></div>
        <p class="setting-help" id="setting-help">목록이나 후보 하나를 확인한 뒤 기본 60초를
          기다립니다. 감시를 중지하면 60~300초로 변경할 수 있습니다.</p>
        <button class="button" id="apply" type="submit" disabled>간격 적용</button>
      </form>
      <div class="browser-note"><span class="mini-dot" aria-hidden="true"></span>
        Chrome이 백그라운드에서 목록과 후보 내용을 확인합니다.</div>
    </aside>
  </div>

  <section class="panel saved-panel" aria-labelledby="saved-title">
    <div class="details-heading">
      <div><p class="section-label">이미 저장한 이미지</p>
        <h2 id="saved-title">저장 결과를 바로 확인합니다.</h2></div>
      <button class="button" id="refresh-saved" type="button" disabled>저장 결과 새로 확인</button>
    </div>
    <p class="saved-state" id="saved-state" data-state="disabled" role="status">
      저장 결과 확인 꺼짐</p>
    <p class="saved-help" id="saved-help">저장 결과 확인을 사용할 수 없습니다.</p>
    <p class="saved-help" id="saved-limits">파일 정보는 최대 20개 표시합니다.
      미리보기 원본 캐시는 파일당 최대 16 MiB · 전체 최대 32 MiB입니다.</p>
    <div class="saved-grid" id="saved-files"></div>
  </section>

  <section class="panel details-panel" aria-labelledby="details-title">
    <div class="details-heading">
      <div><p class="section-label">기록된 후보의 내용</p>
        <h2 id="details-title">작성 시각과 본문 이미지를 확인합니다.</h2></div>
      <button class="button" id="inspect-candidates" type="button" disabled>후보 내용 확인</button>
    </div>
    <p class="details-help">감시 중에는 목록 확인 사이에 후보 한 건씩 처리합니다.
      중지 상태에서 ‘후보 내용 확인’을 누르면 최대 두 건을 확인하고 멈춥니다.</p>
    <p class="details-counts" id="details-counts">완료 0개 · 확인 필요 0개 · 미시도 0개</p>
    <table class="details-table" aria-label="최근 후보 내용 확인 결과" id="details-table" hidden>
      <thead><tr><th scope="col">확인 기록</th><th scope="col">작성 시각 판정</th>
        <th scope="col">본문 이미지</th></tr></thead>
      <tbody id="detail-rows"></tbody>
    </table>
    <p class="details-empty" id="details-empty">아직 내용을 확인한 후보가 없습니다.</p>
  </section>

  <p class="message" id="message" role="status" aria-live="polite"></p>

  <footer class="footer">
    <span>목록과 본문을 확인하는 동안 다른 작업을 계속하셔도 됩니다.<br>
      중지하면 현재 확인을 마친 뒤 멈춥니다.</span>
  </footer>
</main>
<script nonce="__SCRIPT_NONCE__">
(() => {
  'use strict';
  const base = new URL('.', location.href);
  const token = location.pathname.split('/')[1];
  const element = id => document.getElementById(id);
  const timeFormat = new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
  });
  const phases = {
    stopped: {title: '감시를 시작할 준비가 됐습니다.',
      detail: '감시 시작을 누르면 목록 확인부터 시작합니다.', tone: ''},
    starting: {title: '감시를 준비하고 있습니다.',
      detail: '기존 기록과 다음 확인 시각을 살펴봅니다.', tone: 'active'},
    scanning: {title: '목록을 확인하고 있습니다.',
      detail: '이번에 발견한 후보를 기록하고 있습니다.', tone: 'active'},
    inspecting: {title: '후보 내용을 확인하고 있습니다.',
      detail: '기존 후보의 작성 시각과 본문 이미지 정보를 읽고 있습니다. ' +
        '이미지 저장은 하지 않습니다.',
      tone: 'active'},
    verifying_saved: {title: '저장 결과를 확인하고 있습니다.',
      detail: '이 PC에 저장된 파일과 완료 기록을 읽고 있습니다. ' +
        '목록 확인이나 이미지 저장은 시작하지 않습니다.', tone: 'active'},
    verifying_operations: {title: '작업 현황을 확인하고 있습니다.',
      detail: '기존 후보와 저장 기록, 대기 사유를 읽고 있습니다.', tone: 'active'},
    verifying_overview: {title: '작업 현황과 저장 결과를 확인하고 있습니다.',
      detail: '기존 기록과 저장 파일을 읽고 있습니다. 확인을 마치면 멈춥니다.', tone: 'active'},
    finishing_completed: {title: '완료 상태를 다시 확인하고 있습니다.',
      detail: '이미 저장한 파일을 검증하고 기록된 작업의 종료 상태를 확인합니다. ' +
        '이미지를 새로 저장하지 않습니다.', tone: 'active'},
    saving_candidate: {title: '후보 한 건의 저장을 진행하고 있습니다.',
      detail: '전용 Chrome이 열리면 ‘저장 시작’을 누르고 저장이 끝날 때까지 그 창을 앞에 두세요.',
      tone: 'active'},
    waiting: {title: '다음 목록 확인을 기다리고 있습니다.',
      detail: '앞 확인을 마친 뒤 정해진 간격만큼 기다립니다.', tone: 'active'},
    pausing: {title: '일시정지를 준비하고 있습니다.',
      detail: '진행 중인 확인을 마친 뒤 잠시 멈춥니다.', tone: ''},
    paused: {title: '감시를 잠시 멈췄습니다.',
      detail: '계속 감시를 누르면 남아 있는 대기 시간을 지켜 다시 시작합니다.', tone: ''},
    stopping: {title: '감시를 중지하고 있습니다.',
      detail: '진행 중인 확인과 정리를 마칠 때까지 잠시 기다려 주세요.', tone: ''},
    needs_review: {title: '확인이 필요합니다.',
      detail: '확인 결과를 살펴봐야 하므로 자동 감시를 멈췄습니다. 기존 기록은 유지됩니다.',
      tone: 'attention'},
    unknown: {title: '상태를 확인하고 있습니다.', detail: '잠시 기다려 주세요.', tone: ''}
  };
  const reasons = {
    access_block_requires_review: '접근 제한이 확인돼 자동 감시를 멈췄습니다. ' +
      '기존 기록은 유지됩니다.',
    list_profile_unverified_or_incomplete: '목록 구조를 확인하지 못해 멈췄습니다. ' +
      '결과 TXT를 보내주시면 확인할 수 있습니다.',
    list_transport_or_inspection_failure: '목록을 끝까지 확인하지 못해 멈췄습니다. ' +
      '결과 TXT에서 확인 결과를 볼 수 있습니다.',
    insufficient_free_space: '남은 저장 공간을 확인해 주세요. 새 목록 확인은 멈춘 상태입니다.',
    low_disk_space: '남은 저장 공간을 확인해 주세요. 새 목록 확인은 멈춘 상태입니다.',
    owned_browser_not_closed: '확인 창의 종료를 확인하지 못했습니다. 결과 TXT를 보내주세요.',
    owned_browser_cleanup_unconfirmed: '확인 창의 종료를 확인하지 못해 감시를 멈췄습니다.',
    native_save_requires_review: '직전 저장 상태를 확인해야 합니다. 결과 TXT를 보내주세요.',
    another_worker_active: '다른 확인 작업이 끝나기를 기다리고 있습니다.',
    another_scan_owns_this_scope: '다른 확인 작업이 끝나기를 기다리고 있습니다.',
    waiting_for_worker: '다른 확인 작업이 끝나기를 기다리고 있습니다.',
    service_retry_after: '다음 확인까지 기다립니다. 서버에서 요청한 대기 시간도 지킵니다.',
    max_pages: '이전 확인 지점까지 살펴보지 못해 멈췄습니다. 이전 기록과 미확인 구간은 유지됩니다.',
    historical_cursor_unverified: '지난 검색 구간을 확인할 수 없어 멈췄습니다. ' +
      '이전 기록은 유지됩니다.',
    pagination_ambiguous: '다음 목록을 확실히 구분하지 못해 멈췄습니다. 이전 기록은 유지됩니다.',
    pagination_unverified: '다음 목록을 확인하지 못해 멈췄습니다. 이전 기록은 유지됩니다.',
    excluded_rows_unverified: '목록의 일부 행을 구분하지 못해 멈췄습니다. 이전 기록은 유지됩니다.',
    order_unverified: '목록 순서를 확인하지 못해 멈췄습니다. 이전 기록은 유지됩니다.',
    detail_inspection_failed: '후보 내용을 확인하지 못해 멈췄습니다. 결과 TXT를 보내주세요.',
    detail_requires_review: '후보 내용을 확인하지 못해 감시를 멈췄습니다. 결과 TXT를 보내주세요.',
    candidate_identity_or_baseline_invalid: '기존 후보의 기준 정보를 확인하지 못했습니다. ' +
      '기록을 유지하고 확인을 멈췄습니다.',
    no_unattempted_candidates: '아직 내용을 확인하지 않은 후보가 없습니다.',
    candidate_unavailable: '해당 후보가 삭제되었거나 더 이상 공개되어 있지 않습니다.'
  };
  let current = null;
  let requesting = false;
  let closing = false;
  let ended = false;
  let dirtyInterval = false;
  let connectionLost = false;
  let commandRevision = 0;
  let timer = null;
  let savedSignature = null;
  let refreshAfterStop = false;

  function text(id, value) {
    const node = element(id);
    if (node.textContent !== String(value)) node.textContent = String(value);
  }
  function count(value) { return Number.isSafeInteger(value) && value >= 0 ? value : 0; }
  const profileIssues = {
    scope_unreviewed: '감시 대상과 검색 범위가 다름',
    list_not_observed: '게시글 목록을 읽지 못함',
    no_ordinary_rows: '일반 게시글을 식별하지 못함',
    ordinary_title_missing: '제목이 비어 있는 글이 있음',
    ordinary_author_missing: '작성자가 비어 있는 글이 있음',
    ordinary_date_missing: '작성 시각이 비어 있는 글이 있음',
    row_number_count: '글번호 칸을 한 개로 식별하지 못함',
    row_author_count: '작성자 칸을 한 개로 식별하지 못함',
    row_date_count: '작성 시각 칸을 한 개로 식별하지 못함',
    row_title_link_count: '제목 링크를 한 개로 식별하지 못함',
    container_inventory: '목록 표의 개수나 구성을 확인하지 못함',
    container_selection: '게시글을 읽을 표를 하나로 특정하지 못함',
    main_table_shape: '주 목록 표의 구조가 예상과 다름',
    secondary_table_shape: '보조 목록 표의 구조가 예상과 다름',
    main_table_row_count: '주 목록 표의 전체 행 수가 맞지 않음',
    main_ordinary_row_count: '주 목록 표의 게시글 행 수가 맞지 않음',
    main_number_field_count: '주 목록 표의 글번호 칸 수가 맞지 않음',
    main_writer_field_count: '주 목록 표의 작성자 칸 수가 맞지 않음',
    main_date_field_count: '주 목록 표의 작성 시각 칸 수가 맞지 않음',
    main_title_link_count: '주 목록 표의 제목 링크 수가 맞지 않음',
    secondary_rows: '보조 목록 표의 행 구성을 확인하지 못함',
    secondary_table_empty: '보조 목록 표에서 행을 찾지 못함',
    secondary_number_field_count: '보조 목록 표의 글번호 칸 수가 맞지 않음',
    secondary_date_field_count: '보조 목록 표의 작성 시각 칸 수가 맞지 않음',
    secondary_title_link_count: '보조 목록 표의 제목 링크 수가 맞지 않음',
    multiple_profile_checks: '목록의 여러 항목이 검증 조건과 다름'
  };
  const plannerIssues = {
    snapshot_layout: '목록 구조', snapshot_identity: '목록 주소와 검색 범위',
    observation_time: '관찰 시각', list_status: '목록 상태', row_identity: '글번호와 링크',
    row_order: '게시글 순서', exclusion_evidence: '목록에서 제외한 행',
    pagination_identity: '페이지 이동 링크', no_page_evidence: '관찰한 페이지'
  };
  const authorRowGroups = {
    ad: '광고', pinned: '공지', survey: '설문',
    ambiguous_row_fields: '열을 구분하지 못한 행', other_excluded: '기타 제외 행'
  };
  function renderListDiagnosis(diagnosis) {
    const visible = diagnosis?.reason === 'list_profile_unverified_or_incomplete';
    element('list-diagnosis').hidden = !visible;
    if (!visible) {
      text('list-diagnosis-details', '');
      return;
    }
    const listStates = {missing_list: '목록 표를 찾지 못함', ambiguous_list: '목록 표가 여러 개임',
      empty: '빈 목록이 표시됨', unrecognized_empty: '빈 목록인지 확인하지 못함',
      conflicting_empty_marker: '빈 목록 표시와 관찰한 행이 서로 맞지 않음'};
    const lines = [];
    let pageIssue = false;
    const pages = Array.isArray(diagnosis.pages) ? diagnosis.pages.slice(0, 2) : [];
    for (const page of pages) {
      if (!page || ![1, 2].includes(page.page)) continue;
      const issue = page.profile_issue;
      const knownIssue = typeof issue === 'string' && Object.hasOwn(profileIssues, issue);
      const statusLabel = typeof page.status === 'string' &&
        Object.hasOwn(listStates, page.status) ? listStates[page.status] : null;
      const label = statusLabel || (knownIssue ? profileIssues[issue] :
        page.layout_status === 'site_verified' ? '검증된 목록 구조' : '세부 원인을 특정할 수 없음');
      pageIssue ||= !!statusLabel || knownIssue;
      const rows = Number.isSafeInteger(page.ordinary_rows) && page.ordinary_rows >= 0 ?
        ` · 일반 글 ${page.ordinary_rows}개` : '';
      lines.push(`${page.page}페이지 · ${label}${rows}`);
      if (issue === 'row_author_count' || page.layout_status === 'site_verified') {
        for (const [key, group] of Object.entries(authorRowGroups)) {
          const counts = page.author_cell_mismatches?.[key];
          const parts = [];
          for (const [kind, description] of [['missing', '없음'], ['multiple', '여러 개']]) {
            const n = counts?.[kind];
            if (Number.isSafeInteger(n) && n > 0 && n <= 200) parts.push(`${description} ${n}행`);
          }
          if (parts.length) lines.push(`${group} · 작성자 칸 ${parts.join(', ')}`);
        }
      }
    }
    const issue = diagnosis.planner_issue;
    if (typeof issue === 'string' && Object.hasOwn(plannerIssues, issue)) {
      if (issue !== 'snapshot_layout' || !pageIssue) {
        lines.push(`확인하지 못한 항목 · ${plannerIssues[issue]}`);
      }
    } else if (!pageIssue) {
      lines.push('기록에서 실패한 검증 단계를 특정할 수 없습니다.');
    }
    text('list-diagnosis-details', lines.join('\n'));
  }
  function formatTime(value, missing) {
    if (typeof value !== 'string' || !value) return missing;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? missing : timeFormat.format(date);
  }
  function message(value, isError = false) {
    text('message', value);
    element('message').dataset.kind = isError ? 'error' : 'info';
  }
  function connection(value, lost = false) {
    text('connection-text', value);
    element('connection').dataset.state = lost ? 'lost' : 'ready';
  }
  function renderOperations(state) {
    const labels = {
      candidate_uninspected: '내용 미확인', save_ready: '저장 가능', save_planned: '저장 계획됨',
      save_active: '저장 진행 중', save_completed: '저장 완료', save_unavailable: '저장 불가',
      save_needs_review: '저장 확인 필요'
    };
    const rowLabels = {...labels, candidate_detail_needs_review: '내용 확인 필요'};
    const reasons = {
      no_existing_work: '기록된 후보나 저장 작업이 없습니다.',
      candidate_detail_required: '내용을 확인하지 않은 후보가 있습니다. ' +
        '감시 중에 순서대로 확인합니다.',
      candidate_detail_requires_review: '이전 후보 내용 확인을 마치지 못했습니다. ' +
        '기존 기록을 유지했습니다. 결과 TXT를 보내주세요.',
      save_ready: '내용 확인을 마쳐 저장할 수 있는 후보입니다.',
      save_planned: '저장 계획이 기록되어 있습니다. 현황 확인으로 저장을 시작하지 않습니다.',
      save_completed: '저장 완료 기록이 있습니다. 아래에서 저장 결과를 확인할 수 있습니다.',
      save_unavailable: '삭제되었거나 저장 조건을 충족하지 않는 후보입니다.',
      save_requires_review: '이전 저장 결과를 확인해야 합니다. 결과 TXT를 보내주세요.',
      pending_save_requires_review: '이전 저장의 보류 사유를 확인해야 합니다. ' +
        '기존 파일은 유지됩니다. 결과 TXT를 보내주세요.',
      completed_save_can_finish: '이전 저장의 완료 기록이 있습니다. ' +
        '완료 상태 다시 확인으로 파일과 종료 상태를 검증할 수 있습니다.',
      service_cooldown: '서버가 요청한 대기 시간이 남아 있습니다. ' +
        '표시된 시각 이후에 확인할 수 있습니다.',
      service_access_blocked: '접근 제한이 확인되었습니다. 기존 기록을 유지하고 확인을 멈췄습니다.',
      navigation_in_progress: '다른 목록 또는 내용 확인이 진행 중입니다.',
      another_scan_owns_this_scope: '다른 확인 작업이 끝나기를 기다리고 있습니다.',
      native_save_in_progress: '다른 저장 작업이 진행 중입니다. 완료될 때까지 기다려 주세요.',
      operations_require_review: '기존 작업 기록을 확인해야 합니다. 결과 TXT를 보내주세요.',
      requested_stop: '현황 확인을 중지했습니다. 기존 기록과 파일은 유지됩니다.'
    };
    const states = {
      disabled: '현황 확인 꺼짐', empty: '기존 작업 없음', checking: '작업 현황 확인 중',
      ready: '작업 현황 확인 완료', busy: '다른 작업 또는 대기 사유 있음',
      needs_review: '기존 작업 확인 필요', cancelled: '작업 현황 확인 중지'
    };
    const status = typeof state.operations_status === 'string' &&
      Object.hasOwn(states, state.operations_status) ? state.operations_status : 'disabled';
    element('operations-panel').hidden = status === 'disabled';
    text('operations-state', states[status]);
    element('operations-state').dataset.state = status;
    const reason = typeof state.operations_reason === 'string' &&
      Object.hasOwn(reasons, state.operations_reason) ? state.operations_reason : null;
    text('operations-help', status === 'checking' ? '기존 기록과 대기 사유를 확인하고 있습니다.' :
      reason === 'service_cooldown' && state.operations_can_save === true ?
        '대기 시간이 지났습니다. 후보 한 건의 저장을 요청할 수 있습니다.' :
      reason ? reasons[reason] : status === 'empty' ? reasons.no_existing_work :
        status === 'needs_review' ? reasons.operations_require_review :
          '마지막으로 확인한 후보와 저장 작업의 기록입니다.');
    const counts = state.operations_counts && typeof state.operations_counts === 'object' &&
      !Array.isArray(state.operations_counts) ? state.operations_counts : {};
    for (const key of Object.keys(labels)) {
      text('operation-' + key.replaceAll('_', '-'), count(counts[key]).toLocaleString('ko-KR'));
    }
    const remaining = count(state.operations_remaining_seconds);
    text('operations-wait', remaining > 0 ?
      `다음 확인 가능: ${formatTime(state.operations_wait_until, '시각 확인 중')} · ` +
        (remaining < 60 ? `${remaining}초 후` :
          `${Math.floor(remaining / 60)}분 ${remaining % 60}초 후`) : '');
    const finishLabels = {
      batch_finish_completed: '완료 상태를 확인했습니다. ' +
        `파일 ${count(state.operations_finish_files_verified)}개를 검증하고 ` +
        '저장 완료 기록을 정리했습니다.',
      batch_finish_no_pending: '다시 확인할 미완료 저장 기록이 없습니다.',
      batch_finish_busy: '다른 작업이 진행 중이라 완료 상태를 확인하지 못했습니다.',
      batch_finish_cancelled: '완료 상태 확인을 중지했습니다. 기존 파일은 유지됩니다.',
      batch_finish_manual_review: '완료 상태를 확인하지 못했습니다. ' +
        '기존 파일을 유지했습니다. 결과 TXT를 보내주세요.'
    };
    text('operations-finish', typeof state.operations_finish_status === 'string' &&
      Object.hasOwn(finishLabels, state.operations_finish_status) ?
        finishLabels[state.operations_finish_status] : '');
    const savedFiles = count(state.operations_save_files_verified);
    const saveLabels = {
      monitor_batch_completed: count(state.operations_save_tasks_completed) === 1 ?
        `후보 한 건의 저장을 마치고 파일 ${savedFiles}개를 검증했습니다.` :
        '대상 후보의 이미지를 저장할 수 없습니다.',
      monitor_batch_waiting: '대기 시간이 남아 저장을 시작하지 못했습니다.',
      monitor_batch_busy: '다른 작업이 진행 중입니다. 종료 후 현황을 확인해 주세요.',
      monitor_batch_no_candidates: '현재 저장할 수 있는 후보가 없습니다.',
      monitor_batch_manual_review: '저장 결과를 확인해야 합니다. 결과 TXT를 보내주세요.',
      monitor_batch_cancelled: '저장 요청을 중지했습니다. 작업 현황에서 결과를 확인해 주세요.',
      save_not_started: '저장 조건이 달라졌습니다. 작업 현황에서 현재 상태를 확인해 주세요.'
    };
    text('save-outcome', typeof state.operations_save_status === 'string' &&
      Object.hasOwn(saveLabels, state.operations_save_status) ?
        saveLabels[state.operations_save_status] : '');
    const body = element('operations-rows');
    body.replaceChildren();
    const rows = Array.isArray(state.operations_rows) ? state.operations_rows.slice(0, 20) : [];
    for (const row of rows) {
      if (!row || typeof row !== 'object' || Array.isArray(row)) continue;
      const line = document.createElement('tr');
      const values = [String(count(row.order)),
        typeof row.status === 'string' && Object.hasOwn(rowLabels, row.status) ?
          rowLabels[row.status] : '확인 필요',
        typeof row.reason === 'string' && Object.hasOwn(reasons, row.reason) ?
          reasons[row.reason] : '기록 확인 필요',
        Number.isSafeInteger(row.image_count) && row.image_count >= 0 ?
          `${row.image_count}개` : '미확인'];
      for (const value of values) {
        const cell = document.createElement('td');
        cell.textContent = value;
        line.appendChild(cell);
      }
      body.appendChild(line);
    }
    element('operations-records').hidden = !body.childElementCount;
    const omitted = count(state.operations_rows_omitted);
    element('operations-records').querySelector('summary').textContent =
      '최근 작업 기록 · 최대 20개' + (omitted > 0 ? ` · 생략 ${omitted}개` : '');
  }
  function renderDetails(state) {
    const pending = count(state.detail_pending_count);
    text('details-counts', `완료 ${count(state.detail_completed_count)}개 · ` +
      `확인 필요 ${count(state.detail_failed_count)}개 · 미시도 ${pending}개`);
    const rows = Array.isArray(state.details) ? state.details.slice(0, 10) : [];
    const body = element('detail-rows');
    body.replaceChildren();
    const timeLabels = {
      at_or_after_baseline: '감시 기준 시각 이후',
      before_baseline: '감시 기준 시각 이전',
      unknown: '확인 못함'
    };
    const statusLabels = {completed: '확인 완료', failed: '확인 필요', started: '확인 미완료'};
    for (const row of rows) {
      if (!row || typeof row !== 'object' || Array.isArray(row)) continue;
      const line = document.createElement('tr');
      const orderCell = document.createElement('td');
      orderCell.textContent = `확인 ${count(row.order)}`;
      const label = document.createElement('small');
      label.textContent = Object.hasOwn(statusLabels, row.status) ?
        statusLabels[row.status] : '확인 필요';
      orderCell.appendChild(label);
      const timeCell = document.createElement('td');
      timeCell.textContent = row.reason === 'candidate_deleted' ? '삭제되었거나 공개되지 않음' :
        Object.hasOwn(timeLabels, row.time_status) ?
          timeLabels[row.time_status] : timeLabels.unknown;
      const imageCell = document.createElement('td');
      imageCell.textContent = Number.isSafeInteger(row.image_count) && row.image_count >= 0 ?
        `${row.image_count}개` : '확인 못함';
      if (Number.isSafeInteger(row.pending_images) && row.pending_images > 0) {
        const pendingLabel = document.createElement('small');
        pendingLabel.textContent = `로딩 미완료 ${row.pending_images}개`;
        imageCell.appendChild(pendingLabel);
      }
      line.append(orderCell, timeCell, imageCell);
      body.appendChild(line);
    }
    element('details-table').hidden = !body.childElementCount;
    element('details-empty').hidden = !!body.childElementCount;
    text('details-empty', count(state.candidate_count) === 0 ?
      '기록된 후보가 없습니다. 감시에서 새 후보를 찾은 뒤 확인할 수 있습니다.' :
      pending > 0 ? '미확인 후보가 있습니다. 감시를 시작하면 순서대로 확인합니다.' :
        '아직 내용을 확인한 후보가 없습니다.');
  }
  function renderSaved(state) {
    const formats = ['JPEG', 'PNG', 'WEBP', 'GIF', 'BMP', 'TIFF'];
    const source = state.saved_status === 'ready' && Array.isArray(state.saved_files) ?
      state.saved_files.slice(0, 20) : [];
    const groups = new Map();
    const files = source.filter(row => row && typeof row === 'object' && !Array.isArray(row))
      .map(row => {
        const groupId = typeof row.group_id === 'string' && /^[0-9a-f]{32}$/.test(row.group_id) ?
          row.group_id : null;
        if (!groups.has(groupId)) groups.set(groupId, groups.size + 1);
        return {
          name: typeof row.saved_filename === 'string' &&
            /^00[12]\.(?:jpg|png|webp|gif|bmp|tiff)$/.test(row.saved_filename) ?
            row.saved_filename : '저장 이미지',
          group: groupId === null ? null : groups.get(groupId),
          format: formats.includes(row.detected_format) ? row.detected_format : '형식 확인 필요',
          size: count(row.file_size), width: count(row.width), height: count(row.height),
          frames: count(row.frames),
          id: row.preview_available === true && typeof row.preview_id === 'string' &&
            /^[0-9a-f]{32}$/.test(row.preview_id) ? row.preview_id : null
        };
      });
    const savedStates = {
      disabled: ['저장 결과 확인 꺼짐', '저장 결과 확인을 사용할 수 없습니다.'],
      checking: ['저장 결과 확인 중',
        '기존 파일과 완료 기록을 확인하고 있습니다. 이미지를 다시 저장하지 않습니다.'],
      ready: ['검증 완료',
        `검증한 묶음 ${state.saved_groups_verified === undefined ?
          groups.size : count(state.saved_groups_verified)}개 · ` +
        `검증한 파일 ${count(state.saved_files_verified)}개 · ` +
        `표시 ${files.length}개 · 생략 ${count(state.saved_files_omitted)}개 · ` +
        `미리보기 ${count(state.saved_preview_count)}개`],
      empty: ['저장 결과 없음', '완료된 감시 후보의 저장 결과가 아직 없습니다.'],
      busy: ['저장 중 또는 보류',
        '다른 작업이 진행 중이거나 보류된 저장이 있습니다. 기존 파일은 유지됩니다.'],
      needs_review: ['확인 필요',
        '저장 파일과 완료 기록을 확인하지 못했습니다. 결과 TXT를 보내주세요.'],
      cancelled: ['확인 중지', '저장 결과 확인을 멈췄습니다. 기존 파일은 유지됩니다.']
    };
    const status = typeof state.saved_status === 'string' &&
      Object.hasOwn(savedStates, state.saved_status) ? state.saved_status : 'disabled';
    text('saved-state', savedStates[status][0]);
    element('saved-state').dataset.state = status;
    text('saved-help', savedStates[status][1]);
    const signature = JSON.stringify(files);
    if (signature === savedSignature) return;
    savedSignature = signature;
    const container = element('saved-files');
    container.replaceChildren();
    for (const file of files) {
      const card = document.createElement('article');
      card.className = 'saved-card';
      const picture = document.createElement('div');
      picture.className = 'saved-image';
      const fallback = document.createElement('p');
      fallback.className = 'saved-fallback';
      fallback.textContent = '이 파일은 미리보기를 제공하지 않습니다. 저장 파일은 유지됩니다.';
      picture.appendChild(fallback);
      if (file.id !== null) {
        const image = document.createElement('img');
        image.alt = file.group === null ? `저장 이미지 ${file.name}` :
          `저장 묶음 ${file.group} · ${file.name}`;
        image.decoding = 'async';
        fallback.hidden = true;
        image.addEventListener('error', () => {
          image.remove();
          fallback.textContent = '미리보기를 불러오지 못했습니다. 저장 파일은 유지됩니다.';
          fallback.hidden = false;
        }, {once: true});
        image.src = new URL(`images/${file.id}`, base).href;
        picture.appendChild(image);
      }
      const caption = document.createElement('div');
      caption.className = 'saved-caption';
      const name = document.createElement('h3');
      name.textContent = file.group === null ? file.name : `저장 묶음 ${file.group} · ${file.name}`;
      const metadata = document.createElement('p');
      const size = file.size >= 1024 * 1024 ?
        `${(file.size / (1024 * 1024)).toLocaleString('ko-KR', {maximumFractionDigits: 1})} MB` :
        file.size >= 1024 ?
          `${(file.size / 1024).toLocaleString('ko-KR', {maximumFractionDigits: 1})} KB` :
          `${file.size.toLocaleString('ko-KR')} 바이트`;
      metadata.textContent = `${file.format} · ${file.width} × ${file.height} · ${size}` +
        (file.frames > 0 ? ` · ${file.frames}프레임` : '');
      caption.append(name, metadata);
      card.append(picture, caption);
      container.appendChild(card);
    }
  }
  function render(state) {
    current = state;
    const phase = typeof state.phase === 'string' ? state.phase : 'unknown';
    const detailTask = state.task_kind === 'details';
    const savedTask = state.task_kind === 'saved';
    const localTask = savedTask ||
      ['operations', 'finish', 'overview', 'save'].includes(state.task_kind);
    let info = phases[phase] || phases.unknown;
    if (state.task_kind === 'auto_details' && phase === 'waiting') {
      info = {title: '후보 자동 확인을 기다리고 있습니다.',
        detail: '대기 시간이 지나면 미확인 후보 한 건을 읽습니다.', tone: 'active'};
    } else if (state.task_kind === 'auto_details' && phase === 'inspecting') {
      info = {title: '후보 내용을 자동으로 확인하고 있습니다.',
        detail: '작성 시각과 본문 이미지 개수를 기록한 뒤 목록 감시로 돌아갑니다.', tone: 'active'};
    } else if (detailTask) {
      const detailPhases = {
        starting: {title: '후보 내용 확인을 준비하고 있습니다.',
          detail: '기존 후보와 필요한 대기 시간을 살펴봅니다.', tone: 'active'},
        waiting: {title: '다음 후보 확인을 기다리고 있습니다.',
          detail: '앞 확인이 끝난 뒤의 간격을 지킵니다. ' +
            '최대 두 개를 확인한 뒤 멈춥니다.', tone: 'active'},
        paused: {title: '후보 내용 확인을 잠시 멈췄습니다.',
          detail: '내용 확인 계속을 누르면 남은 대기를 지켜 이어갑니다.', tone: ''},
        stopped: {title: '후보 내용 확인을 마쳤습니다.',
          detail: '아래 결과를 확인할 수 있습니다. ' +
            '목록 감시는 자동으로 다시 시작하지 않습니다.', tone: ''}
      };
      info = detailPhases[phase] || info;
      if (phase === 'stopped' && state.reason === 'service_retry_after') {
        info = {title: '후보 내용 확인을 멈췄습니다.',
          detail: '서버 요청으로 내용 확인을 멈췄습니다. 기존 기록과 대기 시간을 유지합니다.',
          tone: ''};
      } else if (phase === 'stopped' && state.reason === 'no_unattempted_candidates') {
        info = {title: '확인할 후보가 없습니다.',
          detail: '아직 내용을 확인하지 않은 후보가 없습니다. 기존 확인 기록은 유지됩니다.',
          tone: ''};
      } else if (phase === 'stopped' && state.reason === 'existing_baseline_required') {
        info = {title: '기존 감시 기준점이 필요합니다.',
          detail: '감시에서 기준점과 새 후보를 기록한 뒤 내용을 확인할 수 있습니다.', tone: ''};
      }
    }
    if (['operations', 'finish', 'overview'].includes(state.task_kind) && phase === 'stopped') {
      info = {title: state.task_kind === 'finish' ? '완료 상태 확인을 마쳤습니다.' :
        '기존 작업 확인을 마쳤습니다.',
      detail: '위 작업 현황에서 결과와 대기 사유를 확인할 수 있습니다. 확인을 마치고 멈췄습니다.',
      tone: ''};
    }
    if (state.task_kind === 'save' && phase === 'stopped') {
      info = {title: '저장 요청 처리를 마쳤습니다.',
        detail: '위 작업 현황과 저장 결과에서 처리한 후보를 확인할 수 있습니다.', tone: ''};
    }
    const editable = state.settings_editable === true ||
      (state.settings_editable === undefined && phase === 'stopped');
    text('candidate-count', count(state.candidate_count).toLocaleString('ko-KR'));
    text('new-count', count(state.new_candidates).toLocaleString('ko-KR'));
    text('cycle-count', count(state.completed_cycles).toLocaleString('ko-KR'));
    text('partial-cycles', count(state.partial_cycles).toLocaleString('ko-KR'));
    text('auto-details-checked', count(state.auto_details_checked).toLocaleString('ko-KR'));
    text('status-title', closing ? '프로그램을 종료하고 있습니다.' : info.title);
    const reason = typeof state.reason === 'string' ? state.reason : '';
    const gap = typeof state.gap_reason === 'string' ? state.gap_reason : '';
    const explanation = Object.hasOwn(reasons, reason) ? reasons[reason] :
      (phase === 'needs_review' && Object.hasOwn(reasons, gap) ? reasons[gap] : null);
    const coverageText = gap === 'anchor_not_reached' ?
      '최근 두 페이지에서 이전 확인 지점을 찾지 못했습니다. ' +
      '그 사이의 글은 일부 누락됐을 수 있습니다.' :
      gap === 'overlap_incomplete' ?
        '이전 확인 지점에 도달했습니다. 다음 페이지까지 겹쳐 확인하는 절차가 남았습니다.' : '';
    text('coverage-gap', coverageText);
    element('coverage-gap').hidden = !coverageText;
    renderListDiagnosis(state.list_diagnosis);
    text('status-detail', closing ? '진행 중인 확인을 마치고 최종 결과를 정리합니다.' :
      ((phase === 'needs_review' || phase === 'waiting') && explanation ?
        explanation : info.detail));
    element('status-mark').className = 'status-mark ' + (closing ? '' : info.tone);
    text('last-scan', formatTime(state.last_scan_at, '아직 없음'));
    text('next-scan', formatTime(state.next_eligible_at, '—'));
    const remaining = count(state.remaining_seconds);
    text('countdown', remaining > 0 && phase === 'waiting' ?
      (remaining < 60 ? `${remaining}초 후` :
        `${Math.floor(remaining / 60)}분 ${remaining % 60}초 후`) : '');
    if (!dirtyInterval && document.activeElement !== element('interval') &&
        Number.isSafeInteger(state.interval_seconds)) {
      element('interval').value = String(state.interval_seconds);
    }
    text('start', phase === 'paused' ? (detailTask ? '내용 확인 계속' : '계속 감시') : '감시 시작');
    element('start').disabled = requesting || closing || !['stopped', 'paused'].includes(phase) ||
      (localTask && phase === 'paused');
    element('pause').disabled = requesting || closing || localTask ||
      !['starting', 'scanning', 'inspecting', 'waiting'].includes(phase);
    element('stop').disabled = requesting || closing ||
      ['stopped', 'stopping', 'unknown'].includes(phase);
    element('interval').disabled = requesting || closing || !editable;
    element('apply').disabled = requesting || closing || !editable || !dirtyInterval;
    element('exit').disabled = requesting || closing;
    element('inspect-candidates').disabled = requesting || closing || phase !== 'stopped' ||
      state.settings_editable !== true || state.browser_closed !== true ||
      count(state.candidate_count) === 0 || count(state.detail_pending_count) === 0;
    const savedConfigured = ['checking', 'ready', 'empty', 'busy', 'needs_review', 'cancelled']
      .includes(state.saved_status);
    element('refresh-saved').disabled = requesting || closing || phase !== 'stopped' ||
      state.settings_editable !== true || state.browser_closed !== true || !savedConfigured;
    const operationsConfigured = ['checking', 'ready', 'empty', 'busy', 'needs_review', 'cancelled']
      .includes(state.operations_status);
    element('refresh-operations').disabled = requesting || closing ||
      !['stopped', 'needs_review'].includes(phase) || !operationsConfigured;
    element('finish-completed').disabled = requesting || closing ||
      !['stopped', 'needs_review'].includes(phase) || state.browser_closed !== true ||
      !operationsConfigured ||
      state.operations_can_finish !== true;
    element('save-one').disabled = requesting || closing || refreshAfterStop ||
      phase !== 'stopped' || state.browser_closed !== true ||
      !operationsConfigured || state.operations_can_save !== true;
    renderOperations(state);
    renderDetails(state);
    renderSaved(state);
  }
  function finishScreen() {
    ended = true;
    if (timer !== null) clearTimeout(timer);
    connection('종료됨');
    text('status-title', '프로그램이 종료되었습니다.');
    text('status-detail', '자동으로 열린 결과 TXT에서 최종 상태를 확인할 수 있습니다. ' +
      '이 창은 닫아도 됩니다.');
    element('status-mark').className = 'status-mark';
    text('countdown', '');
    const controls = ['start', 'pause', 'stop', 'apply', 'exit', 'interval',
      'inspect-candidates', 'refresh-saved', 'refresh-operations', 'finish-completed', 'save-one'];
    for (const id of controls) {
      element(id).disabled = true;
    }
  }
  function accept(payload) {
    if (!payload || typeof payload !== 'object' || !payload.status ||
        typeof payload.status !== 'object' || Array.isArray(payload.status)) {
      throw new Error('Invalid response');
    }
    if (connectionLost) { message(''); connectionLost = false; }
    closing = closing || payload.closing === true;
    connection(closing ? '종료 중' : '연결됨');
    render(payload.status);
  }
  async function poll() {
    if (ended) return;
    const revision = commandRevision;
    let responseReceived = false;
    try {
      const response = await fetch(new URL('api/status', base), {
        cache: 'no-store', signal: AbortSignal.timeout(5000),
        headers: {'X-Image-Monitor-Token': token}
      });
      responseReceived = true;
      if (!response.ok) throw new Error('Status unavailable');
      const payload = await response.json();
      if (revision === commandRevision && !requesting) {
        accept(payload);
        if (refreshAfterStop && (closing || current.phase !== 'stopping')) {
          refreshAfterStop = false;
          if (!closing && current.phase === 'stopped') await action('refresh_operations');
        }
      }
    } catch (error) {
      if (closing && !responseReceived && error instanceof TypeError) {
        finishScreen();
        return;
      }
      if (closing) {
        connection('종료 중');
        message('종료 확인을 기다리고 있습니다. 잠시 기다려 주세요.');
        timer = setTimeout(poll, 1000);
        return;
      }
      connectionLost = true;
      connection('연결 확인 필요', true);
      message('화면 연결을 확인하지 못했습니다. 프로그램 창이 열려 있는지 확인해 주세요.', true);
    }
    if (!ended) timer = setTimeout(poll, 1000);
  }
  async function action(name, interval) {
    if (requesting || closing || ended) return;
    const updateOnStop = name === 'stop' && current &&
      ['list', 'auto_details', 'details'].includes(current.task_kind) &&
      ['starting', 'scanning', 'inspecting', 'waiting', 'paused', 'pausing']
        .includes(current.phase) &&
      ['ready', 'empty', 'busy', 'needs_review', 'cancelled'].includes(current.operations_status);
    refreshAfterStop = false;
    requesting = true;
    commandRevision += 1;
    if (current) render(current);
    if (name === 'refresh_saved') {
      savedSignature = null;
      element('saved-files').replaceChildren();
    }
    message('');
    const body = {action: name};
    if (name === 'configure') body.interval_seconds = interval;
    try {
      const response = await fetch(new URL('api/action', base), {
        method: 'POST', cache: 'no-store', signal: AbortSignal.timeout(5000),
        headers: {'Content-Type': 'application/json', 'X-Image-Monitor-Token': token},
        body: JSON.stringify(body)
      });
      if (!response.ok) throw new Error('Action unavailable');
      const payload = await response.json();
      if (name === 'configure') dirtyInterval = false;
      if (name === 'exit') closing = true;
      if (name === 'stop') refreshAfterStop = updateOnStop;
      accept(payload);
      if (name === 'configure') message('확인 간격을 저장했습니다. 기존 대기 시간은 유지됩니다.');
      if (name === 'exit') message('마지막 확인을 마치고 종료합니다. 잠시 기다려 주세요.');
    } catch (_error) {
      message('요청을 완료하지 못했습니다. 현재 상태를 확인한 뒤 다시 눌러 주세요.', true);
    } finally {
      requesting = false;
      if (current) render(current);
    }
  }
  element('start').addEventListener('click', () => action('start'));
  element('inspect-candidates').addEventListener('click', () => action('inspect_candidates'));
  element('refresh-saved').addEventListener('click', () => action('refresh_saved'));
  element('refresh-operations').addEventListener('click', () => action('refresh_operations'));
  element('finish-completed').addEventListener('click', () => action('finish_completed'));
  element('save-one').addEventListener('click', () => action('save_one'));
  element('pause').addEventListener('click', () => action('pause'));
  element('stop').addEventListener('click', () => action('stop'));
  element('exit').addEventListener('click', () => action('exit'));
  element('interval').addEventListener('input', () => {
    dirtyInterval = true;
    if (current) render(current);
  });
  element('settings-form').addEventListener('submit', event => {
    event.preventDefault();
    const interval = Number(element('interval').value);
    if (!Number.isInteger(interval) || interval < 60 || interval > 300) {
      message('간격은 60~300 사이의 정수로 입력해 주세요.', true);
      element('interval').reportValidity();
      return;
    }
    action('configure', interval);
  });
  poll();
})();
</script>
</body>
</html>
"""


def render_monitor_page(*, script_nonce: str) -> str:
    """Render the application version and the escaped server-generated CSP nonce."""
    if not isinstance(script_nonce, str) or not script_nonce:
        raise ValueError("A script nonce is required")
    return _PAGE.replace("__PUBLIC_VERSION__", PUBLIC_VERSION).replace(
        "__SCRIPT_NONCE__", escape(script_nonce, quote=True)
    )
