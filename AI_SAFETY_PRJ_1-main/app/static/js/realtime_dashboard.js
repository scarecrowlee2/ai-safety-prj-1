const page = document.querySelector('.monitor-page');
const eventList = document.querySelector('#event-list');
const refreshLabel = document.querySelector('#event-refresh-label');
const eventsEndpoint = page?.dataset.eventsEndpoint;
const statusEndpoint = buildStatusEndpoint(eventsEndpoint);
const overlayEndpoint =
  page?.dataset.overlayEndpoint || document.querySelector('.video-frame')?.dataset.overlayEndpoint || null;
const videoImage = document.querySelector('#realtime-video');
const overlayCanvas = document.querySelector('#realtime-overlay');
const overlayContext = overlayCanvas?.getContext('2d') || null;

const eventTypeLabel = {
  fall: '낙상 / 기절',
  inactive: '비활동 / 무응답',
  violence: '폭행',
};

const statusTypes = ['fall', 'inactive', 'violence'];
const overlayPollMs = 400;
const overlayColor = {
  normal: '#22c55e',
  watch: '#f59e0b',
  alert: '#ef4444',
  text: '#f8fafc',
  panel: 'rgba(15, 23, 42, 0.78)',
};

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

function clearOverlay() {
  if (!overlayCanvas || !overlayContext) return;
  overlayContext.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
}

function syncOverlayCanvasSize() {
  if (!videoImage || !overlayCanvas) return;

  const rect = videoImage.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));

  if (overlayCanvas.width !== width) {
    overlayCanvas.width = width;
  }
  if (overlayCanvas.height !== height) {
    overlayCanvas.height = height;
  }

  overlayCanvas.style.width = `${width}px`;
  overlayCanvas.style.height = `${height}px`;
  overlayCanvas.style.left = `${videoImage.offsetLeft}px`;
  overlayCanvas.style.top = `${videoImage.offsetTop}px`;
}

function bgrToRgba(colorBgr, alpha = 0.92) {
  if (!Array.isArray(colorBgr) || colorBgr.length < 3) return `rgba(245, 158, 11, ${alpha})`;
  const [b, g, r] = colorBgr;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function pickStateLevel(states) {
  if (!states || typeof states !== 'object') return 'normal';
  if (states.fall_alert || states.inactive_alert || states.violence_alert) return 'alert';
  if (states.fall_watch || states.inactive_watch || states.violence_watch) return 'watch';
  return 'normal';
}

function levelToColor(level) {
  if (level === 'alert') return overlayColor.alert;
  if (level === 'watch') return overlayColor.watch;
  return overlayColor.normal;
}

function boxToPixels(box, coordSystem, sourceSize, canvasWidth, canvasHeight) {
  if (!box) return null;

  if (coordSystem === 'normalized_xyxy') {
    // 정규화 좌표(0~1)를 현재 표시 중인 canvas 픽셀 크기로 변환합니다.
    return {
      x1: Number(box.x1 || 0) * canvasWidth,
      y1: Number(box.y1 || 0) * canvasHeight,
      x2: Number(box.x2 || 0) * canvasWidth,
      y2: Number(box.y2 || 0) * canvasHeight,
    };
  }

  const sourceWidth = Math.max(1, Number(sourceSize?.width || canvasWidth));
  const sourceHeight = Math.max(1, Number(sourceSize?.height || canvasHeight));
  const scaleX = canvasWidth / sourceWidth;
  const scaleY = canvasHeight / sourceHeight;

  // 절대 좌표는 원본(source_size) 기준이므로 현재 캔버스 비율로 스케일링합니다.
  return {
    x1: Number(box.x1 || 0) * scaleX,
    y1: Number(box.y1 || 0) * scaleY,
    x2: Number(box.x2 || 0) * scaleX,
    y2: Number(box.y2 || 0) * scaleY,
  };
}

function drawObjectBoxes(payload) {
  if (!overlayContext || !overlayCanvas) return;

  const objects = Array.isArray(payload?.objects) ? payload.objects : [];
  const coordSystem = payload?.box_coord_system || 'normalized_xyxy';

  objects.forEach((obj) => {
    const px = boxToPixels(obj?.box, coordSystem, payload?.source_size, overlayCanvas.width, overlayCanvas.height);
    if (!px) return;

    const style = obj?.style || {};
    const label = obj?.label || obj?.type || 'object';
    const stroke = bgrToRgba(style?.color_bgr, 0.95);
    const lineWidth = Number(style?.thickness || 2);

    overlayContext.strokeStyle = stroke;
    overlayContext.lineWidth = lineWidth;
    overlayContext.strokeRect(px.x1, px.y1, Math.max(0, px.x2 - px.x1), Math.max(0, px.y2 - px.y1));

    overlayContext.font = '600 14px Inter, sans-serif';
    const textWidth = overlayContext.measureText(label).width;
    const labelX = px.x1;
    const labelY = Math.max(18, px.y1 - 8);
    overlayContext.fillStyle = 'rgba(2, 6, 23, 0.74)';
    overlayContext.fillRect(labelX - 5, labelY - 15, textWidth + 10, 18);
    overlayContext.fillStyle = stroke;
    overlayContext.fillText(label, labelX, labelY);
  });
}

function drawBanners(payload) {
  if (!overlayContext || !overlayCanvas) return;

  const banners = Array.isArray(payload?.banners) ? payload.banners : [];
  let y = 24;

  banners.forEach((banner) => {
    const level = String(banner?.level || '').includes('alert') ? 'alert' : 'watch';
    const color = levelToColor(level);
    const text = banner?.text || 'ALERT';
    const paddingX = 12;
    const height = 30;

    overlayContext.font = '700 15px Inter, sans-serif';
    const width = Math.min(overlayCanvas.width - 24, overlayContext.measureText(text).width + paddingX * 2);

    overlayContext.fillStyle = color;
    overlayContext.fillRect(12, y, width, height);
    overlayContext.fillStyle = overlayColor.text;
    overlayContext.fillText(text, 12 + paddingX, y + 21);
    y += 38;
  });
}

function drawStatePanel(payload) {
  if (!overlayContext || !overlayCanvas) return;

  const states = payload?.states || {};
  const level = pickStateLevel(states);
  const borderColor = levelToColor(level);
  const lines = [
    `Fall: ${states.fall_alert ? 'ALERT' : states.fall_watch ? 'WATCH' : 'NORMAL'}`,
    `Inactive: ${states.inactive_alert ? 'ALERT' : states.inactive_watch ? 'WATCH' : 'NO PERSON'}`,
    `Violence: ${states.violence_alert ? 'ALERT' : states.violence_watch ? 'WATCH' : 'NORMAL'}`,
  ];

  const panelWidth = Math.min(360, overlayCanvas.width - 20);
  const panelHeight = 92;
  overlayContext.fillStyle = overlayColor.panel;
  overlayContext.fillRect(10, 10, panelWidth, panelHeight);
  overlayContext.strokeStyle = borderColor;
  overlayContext.lineWidth = 2;
  overlayContext.strokeRect(10, 10, panelWidth, panelHeight);

  overlayContext.fillStyle = '#e2e8f0';
  overlayContext.font = '600 12px Inter, sans-serif';
  lines.forEach((line, idx) => {
    overlayContext.fillStyle = idx === 0 ? levelToColor(states.fall_alert ? 'alert' : states.fall_watch ? 'watch' : 'normal') : '#e2e8f0';
    if (idx === 1) {
      overlayContext.fillStyle = levelToColor(
        states.inactive_alert ? 'alert' : states.inactive_watch ? 'watch' : 'normal',
      );
    }
    if (idx === 2) {
      overlayContext.fillStyle = levelToColor(
        states.violence_alert ? 'alert' : states.violence_watch ? 'watch' : 'normal',
      );
    }
    overlayContext.fillText(line, 20, 34 + idx * 22);
  });
}

function renderOverlay(payload) {
  if (!overlayContext || !overlayCanvas) return;

  clearOverlay();
  if (!payload?.ready) return;

  // fall/inactive는 현재 박스가 제공되지 않으므로 상태 패널/배너만 표시하고 가짜 박스를 만들지 않습니다.
  drawStatePanel(payload);
  drawBanners(payload);
  drawObjectBoxes(payload);
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

async function loadOverlaySnapshot() {
  if (!overlayEndpoint || !overlayCanvas) return;

  syncOverlayCanvasSize();

  try {
    const response = await fetch(overlayEndpoint, { headers: { Accept: 'application/json' } });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const payload = await response.json();
    if (!payload?.ready) {
      clearOverlay();
      return;
    }

    renderOverlay(payload);
  } catch (error) {
    clearOverlay();
    console.error(error);
  }
}

function registerOverlayCanvasSync() {
  if (!videoImage || !overlayCanvas) return;

  window.addEventListener('resize', syncOverlayCanvasSize);
  videoImage.addEventListener('load', syncOverlayCanvasSize);

  if (typeof ResizeObserver === 'function') {
    const observer = new ResizeObserver(syncOverlayCanvasSize);
    observer.observe(videoImage);
  }

  syncOverlayCanvasSize();
}

renderEmptyState();
registerOverlayCanvasSync();
loadRecentEvents();
loadStatusSummary();
loadOverlaySnapshot();
window.setInterval(loadRecentEvents, 10000);
window.setInterval(loadStatusSummary, 10000);
window.setInterval(loadOverlaySnapshot, overlayPollMs);
