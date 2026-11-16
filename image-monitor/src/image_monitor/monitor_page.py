"""Static, local monitor controls; live values are rendered as text only."""

from html import escape

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
.eyebrow{font-size:12px;color:var(--teal);font-weight:700;letter-spacing:1.2px;margin:0 0 7px}
h1{font-size:28px;line-height:1.4;letter-spacing:-1.3px;margin:0 0 6px;font-weight:750}
.intro p:last-child{color:var(--muted);margin:0;font-size:15px}
.scope{display:inline-flex;align-items:center;gap:8px;margin-top:12px;padding:5px 12px;
  border:1px solid #d4dfd9;border-radius:8px;background:#edf2eb;font-size:13px;font-weight:600}
.scope-dot{height:6px;width:6px;border-radius:50%;background:var(--teal)}
.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:18px 0 16px}
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
.notice{border:1px solid #e1e7db;border-radius:12px;padding:14px 20px;margin-top:16px;
  background:#edf1e7;font-size:13px;color:#536553;line-height:1.8}
.notice strong{font-weight:650;color:#304d3c}
.message{font-size:13px;color:var(--teal);min-height:25px;padding:0 2px;margin:13px 0 0}
.message[data-kind="error"]{color:var(--red)}
.footer{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:19px;
  padding-top:18px;border-top:1px solid #dde4db;color:var(--muted);font-size:12px}
@media(max-width:760px){.app{padding:23px 17px}.header{margin-bottom:28px}
  .brand-name{font-size:18px}
  .connection{font-size:11px}.main-grid{grid-template-columns:1fr}.metrics{gap:9px}
  .metric{padding:16px 13px}.metric-value{font-size:26px}.metric-label{font-size:11px}
  h1{font-size:26px}.monitor-panel{padding:23px 20px}.settings{padding:21px}
  .setting-label{margin-top:17px}
  .settings form{display:grid;grid-template-columns:1fr 140px;gap:0 15px;align-items:end}
  .settings .setting-label,.settings .setting-help{grid-column:1/-1}
  .settings .setting-help{margin-bottom:2px}.settings .button{grid-column:2;grid-row:2}
  .browser-note{margin-top:17px}.footer{align-items:flex-start}}
@media(max-width:420px){.connection{max-width:88px;line-height:1.5}.metrics{grid-template-columns:1fr}
  .header-actions{flex-direction:column;align-items:flex-end;gap:6px}
  .metric{display:flex;align-items:center;justify-content:space-between}.metric-label{margin:0;font-size:13px}
  .metric-value{font-size:25px}.times{grid-template-columns:1fr;gap:13px}.controls{gap:7px}
  .controls .button{flex:1;padding-inline:10px}.footer{font-size:11px}
  .settings form{grid-template-columns:1fr 120px}}
</style>
</head>
<body>
<main class="app">
  <header class="header">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i><i></i></span>
      <div><div class="brand-name">Image Monitor</div>
        <div class="brand-caption">새 글 목록 감시</div></div>
    </div>
    <div class="header-actions">
      <div class="connection" id="connection" data-state="connecting">
        <span class="connection-dot" aria-hidden="true"></span>
        <span id="connection-text">연결 확인 중</span>
      </div>
      <button class="button" id="exit" type="button">프로그램 종료</button>
    </div>
  </header>

  <section class="intro" aria-labelledby="page-title">
    <p class="eyebrow">목록 감시</p>
    <h1 id="page-title">새 글을 차근차근 확인합니다.</h1>
    <p>새로 보이는 글의 후보를 기록합니다.</p>
    <div class="scope"><span class="scope-dot" aria-hidden="true"></span>만화 · ai · 제목+내용</div>
  </section>

  <section class="metrics" aria-label="발견 현황">
    <div class="metric"><div class="metric-label">기록된 후보</div>
      <div class="metric-value"><span id="candidate-count">0</span><small>개</small></div></div>
    <div class="metric"><div class="metric-label">이번 실행에서 추가</div>
      <div class="metric-value"><span id="new-count">0</span><small>개</small></div></div>
    <div class="metric"><div class="metric-label">완료한 확인</div>
      <div class="metric-value"><span id="cycle-count">0</span><small>회</small></div></div>
  </section>

  <div class="main-grid">
    <section class="panel monitor-panel" aria-labelledby="status-title">
      <p class="section-label">감시 상태</p>
      <div class="status-line" aria-live="polite">
        <span class="status-mark" id="status-mark" aria-hidden="true"></span>
        <h2 id="status-title">상태를 확인하고 있습니다.</h2>
      </div>
      <p class="status-detail" id="status-detail">잠시 기다려 주세요.</p>
      <div class="times">
        <div><div class="time-label">마지막 확인</div>
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
      <p class="section-label">확인 간격</p><h2 id="settings-title">서두르지 않고, 규칙적으로</h2>
      <form id="settings-form">
        <label class="setting-label" for="interval">확인 사이의 최소 간격</label>
        <div class="input-row"><input id="interval" type="number" min="60" max="300"
          step="1" value="60" inputmode="numeric" required disabled>
          <span class="unit">초</span></div>
        <p class="setting-help" id="setting-help">60~300초로 설정할 수 있습니다.<br>
          감시를 중지한 뒤 변경해 주세요.</p>
        <button class="button" id="apply" type="submit" disabled>간격 적용</button>
      </form>
      <div class="browser-note"><span class="mini-dot" aria-hidden="true"></span>
        Chrome에서 화면 없이 목록을 확인합니다.</div>
    </aside>
  </div>

  <div class="notice">
    <strong>감시 시작 이후의 새 글부터 기록합니다.</strong><br>
    이전 시험 기록과 저장 파일은 유지됩니다. 이미지 자동 저장은 아직 연결하지 않았습니다.
  </div>
  <p class="message" id="message" role="status" aria-live="polite"></p>

  <footer class="footer">
    <span>감시 중에도 다른 작업을 계속하셔도 됩니다.<br>
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
      detail: '시작을 누르면 목록을 확인하고 새 후보를 기록합니다.', tone: ''},
    starting: {title: '감시를 준비하고 있습니다.',
      detail: '기존 기록과 다음 확인 시각을 살펴봅니다.', tone: 'active'},
    scanning: {title: '목록을 확인하고 있습니다.',
      detail: '이번에 발견한 후보를 기록하고 있습니다.', tone: 'active'},
    waiting: {title: '다음 확인을 기다리고 있습니다.',
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
    another_scan_owns_this_scope: '다른 확인 작업이 끝나기를 기다리고 있습니다.',
    waiting_for_worker: '다른 확인 작업이 끝나기를 기다리고 있습니다.',
    service_retry_after: '다음 확인까지 기다립니다. 서버에서 요청한 대기 시간도 지킵니다.',
    max_pages: '이전 확인 지점까지 살펴보지 못해 멈췄습니다. 이전 기록과 미확인 구간은 유지됩니다.',
    historical_cursor_unverified: '지난 검색 구간을 확인할 수 없어 멈췄습니다. ' +
      '이전 기록은 유지됩니다.',
    pagination_ambiguous: '다음 목록을 확실히 구분하지 못해 멈췄습니다. 이전 기록은 유지됩니다.',
    pagination_unverified: '다음 목록을 확인하지 못해 멈췄습니다. 이전 기록은 유지됩니다.',
    excluded_rows_unverified: '목록의 일부 행을 구분하지 못해 멈췄습니다. 이전 기록은 유지됩니다.',
    order_unverified: '목록 순서를 확인하지 못해 멈췄습니다. 이전 기록은 유지됩니다.'
  };
  let current = null;
  let requesting = false;
  let closing = false;
  let ended = false;
  let dirtyInterval = false;
  let connectionLost = false;
  let commandRevision = 0;
  let timer = null;

  function text(id, value) {
    const node = element(id);
    if (node.textContent !== String(value)) node.textContent = String(value);
  }
  function count(value) { return Number.isSafeInteger(value) && value >= 0 ? value : 0; }
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
  function render(state) {
    current = state;
    const phase = typeof state.phase === 'string' ? state.phase : 'unknown';
    const info = phases[phase] || phases.unknown;
    const editable = state.settings_editable === true ||
      (state.settings_editable === undefined && phase === 'stopped');
    text('candidate-count', count(state.candidate_count).toLocaleString('ko-KR'));
    text('new-count', count(state.new_candidates).toLocaleString('ko-KR'));
    text('cycle-count', count(state.completed_cycles).toLocaleString('ko-KR'));
    text('status-title', closing ? '프로그램을 종료하고 있습니다.' : info.title);
    const reason = typeof state.reason === 'string' ? state.reason : '';
    const gap = typeof state.gap_reason === 'string' ? state.gap_reason : '';
    const explanation = reasons[reason] || reasons[gap];
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
    text('start', phase === 'paused' ? '계속 감시' : '감시 시작');
    element('start').disabled = requesting || closing || !['stopped', 'paused'].includes(phase);
    element('pause').disabled = requesting || closing ||
      !['starting', 'scanning', 'waiting'].includes(phase);
    element('stop').disabled = requesting || closing ||
      ['stopped', 'stopping', 'unknown'].includes(phase);
    element('interval').disabled = requesting || closing || !editable;
    element('apply').disabled = requesting || closing || !editable || !dirtyInterval;
    element('exit').disabled = requesting || closing;
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
    for (const id of ['start', 'pause', 'stop', 'apply', 'exit', 'interval']) {
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
      if (revision === commandRevision && !requesting) accept(payload);
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
    requesting = true;
    commandRevision += 1;
    if (current) render(current);
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
    """Render fixed markup with only a safely escaped server-generated CSP nonce."""
    if not isinstance(script_nonce, str) or not script_nonce:
        raise ValueError("A script nonce is required")
    return _PAGE.replace("__SCRIPT_NONCE__", escape(script_nonce, quote=True))
