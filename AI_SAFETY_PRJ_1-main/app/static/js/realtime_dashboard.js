const page = document.querySelector('.monitor-page');
const eventList = document.querySelector('#event-list');
const refreshLabel = document.querySelector('#event-refresh-label');
const eventsEndpoint = page?.dataset.eventsEndpoint;
const statusEndpoint = buildStatusEndpoint(eventsEndpoint);

const eventTypeLabel = {
  fall: '낙상 / 기절',
  inactive: '비활동 / 무응답',
  violence: '폭행',
};

const statusTypes = ['fall', 'inactive', 'violence'];

function buildStatusEndpoint(value) {
  if (!value) return null;

  const [path] = value.split('?');
  if (!path) return null;
  if (path.endsWith('/status')) return path;
  if (path.endsWith('/events')) return `${path.slice(0, -'/events'.length)}/status`;
  return null;
}

function formatLoggedAt(value) {
  if (!value) return '시간 정보 없음';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'short',
    timeStyle: 'medium',
  }).format(date);
}

function applyStatusVisual(badgeEl, textEl, state) {
  if (!badgeEl || !textEl) return;

  badgeEl.classList.remove('normal', 'warning', 'error');

  if (state === 'warning') {
    badgeEl.classList.add('warning');
    badgeEl.style.background = 'rgba(245, 158, 11, 0.2)';
    badgeEl.style.border = '1px solid rgba(245, 158, 11, 0.35)';
    badgeEl.style.color = '#fcd34d';
    textEl.textContent = '경고';
    return;
  }

  if (state === 'error') {
    badgeEl.classList.add('error');
    badgeEl.style.background = 'rgba(239, 68, 68, 0.18)';
    badgeEl.style.border = '1px solid rgba(239, 68, 68, 0.3)';
    badgeEl.style.color = '#fca5a5';
    textEl.textContent = '오류';
    return;
  }

  badgeEl.classList.add('normal');
  badgeEl.style.background = '';
  badgeEl.style.border = '';
  badgeEl.style.color = '';
  textEl.textContent = '정상';
}

function setStatusBadge(type, state) {
  const badgeEl = document.querySelector(`#status-badge-${type}`);
  const textEl = document.querySelector(`#status-text-${type}`);
  applyStatusVisual(badgeEl, textEl, state);
}

function updateStatusBadges(statusPayload) {
  statusTypes.forEach((type) => {
    const state = statusPayload?.[type];
    if (state === 'warning' || state === 'error') {
      setStatusBadge(type, state);
      return;
    }
    setStatusBadge(type, 'normal');
  });
}

function renderEmptyState() {
  eventList.innerHTML = `
    <div class="event-empty">
      <strong>최근 이벤트 없음</strong>
      <p>감지된 경고가 없으면 이 영역에 최신 이벤트가 표시됩니다.</p>
    </div>
  `;
}

function renderEvents(events) {
  if (!Array.isArray(events) || events.length === 0) {
    renderEmptyState();
    return;
  }

  eventList.innerHTML = events
    .map((event) => {
      const type = event.event_type || 'unknown';
      const title = eventTypeLabel[type] || '기타 이벤트';
      const timestamp = formatLoggedAt(event.logged_at);
      const streamStamp = Number.isFinite(event.stream_timestamp_sec)
        ? `스트림 ${event.stream_timestamp_sec.toFixed(1)}초`
        : '스트림 시간 정보 없음';

      return `
        <article class="event-item" data-type="${type}">
          <div>
            <strong>${title}</strong>
            <p>${event.message || '이벤트 설명이 없습니다.'}</p>
          </div>
          <div class="event-meta">
            <div>${timestamp}</div>
            <div>${streamStamp}</div>
          </div>
        </article>
      `;
    })
    .join('');
}

async function loadRecentEvents() {
  if (!eventsEndpoint || !eventList || !refreshLabel) return;

  try {
    const response = await fetch(eventsEndpoint, { headers: { Accept: 'application/json' } });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const payload = await response.json();
    const events = payload.events || payload.items || [];

    renderEvents(events);
    refreshLabel.textContent = `최근 갱신 ${new Intl.DateTimeFormat('ko-KR', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(new Date())}`;
  } catch (error) {
    refreshLabel.textContent = '이벤트 목록을 불러오지 못했습니다';
    eventList.innerHTML = `
      <div class="event-empty">
        <strong>이벤트 피드 연결 실패</strong>
        <p>로그 파일 또는 API 응답을 확인해주세요.</p>
      </div>
    `;
    console.error(error);
  }
}

async function loadStatusSummary() {
  if (!statusEndpoint) {
    statusTypes.forEach((type) => setStatusBadge(type, 'error'));
    return;
  }

  try {
    const response = await fetch(statusEndpoint, { headers: { Accept: 'application/json' } });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const payload = await response.json();
    updateStatusBadges(payload);
  } catch (error) {
    statusTypes.forEach((type) => setStatusBadge(type, 'error'));
    console.error(error);
  }
}

renderEmptyState();
loadRecentEvents();
loadStatusSummary();
window.setInterval(loadRecentEvents, 10000);
window.setInterval(loadStatusSummary, 10000);
