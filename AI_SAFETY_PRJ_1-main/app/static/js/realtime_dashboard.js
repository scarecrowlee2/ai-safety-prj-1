const page = document.querySelector('.monitor-page');
const eventList = document.querySelector('#event-list');
const refreshLabel = document.querySelector('#event-refresh-label');
const endpoint = page?.dataset.eventsEndpoint;

const eventTypeLabel = {
  fall: '낙상 / 기절',
  inactive: '비활동 / 무응답',
  violence: '폭행',
};

function formatLoggedAt(value) {
  if (!value) return '시간 정보 없음';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'short',
    timeStyle: 'medium',
  }).format(date);
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
  if (!endpoint || !eventList || !refreshLabel) return;

  try {
    const response = await fetch(endpoint, { headers: { Accept: 'application/json' } });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const payload = await response.json();
    renderEvents(payload.events || payload.items || []);
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

renderEmptyState();
loadRecentEvents();
window.setInterval(loadRecentEvents, 10000);
