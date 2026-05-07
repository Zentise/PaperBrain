'use strict';

/* ═══════════════════════════════════════════════════════════════════════════
   PaperBrain — app.js
   Single-file SPA logic: state, API, DOM rendering, events.
   ═══════════════════════════════════════════════════════════════════════════ */

// ── State ──────────────────────────────────────────────────────────────────
const S = {
  ready:       false,
  hasDocuments:false,
  provider:    'gemini',
  sources:     [],
  messages:    [],
  thinking:    false,
  drawerOpen:  false,
};

// ── DOM refs (resolved once on DOMContentLoaded) ───────────────────────────
let D = {};

function resolveDOM() {
  const $ = id => document.getElementById(id);
  D = {
    shell:         document.getElementById('shell'),
    sourceList:    $('source-list'),
    sourcesEmpty:  $('sources-empty'),
    panelStats:    $('panel-stats'),
    reloadBtn:     $('reload-btn'),
    addBtn:        $('add-btn'),
    panelToggle:   $('panel-toggle'),
    sourcesPanel:  document.querySelector('.sources-panel'),
    messages:      $('messages'),
    welcome:       $('welcome'),
    welcomeCta:    $('welcome-cta'),
    chatInput:     $('chat-input'),
    sendBtn:       $('send-btn'),
    statusDot:     $('status-dot'),
    statusLabel:   $('status-label'),
    clearBtn:      $('clear-btn'),
    composerHint:  $('composer-hint'),
    contextBody:   $('context-body'),
    drawerBackdrop:$('drawer-backdrop'),
    drawer:        $('drawer'),
    drawerClose:   $('drawer-close'),
    dropZone:      $('drop-zone'),
    fileInput:     $('file-input'),
    filePreview:   $('file-preview'),
    uploadBtn:     $('upload-btn'),
    urlInput:      $('url-input'),
    ingestUrlBtn:  $('ingest-url-btn'),
    toasts:        $('toasts'),
  };
}

// ── API layer ──────────────────────────────────────────────────────────────
const API = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  },
  async post(path, body) {
    const isForm = body instanceof FormData;
    const r = await fetch(path, {
      method: 'POST',
      headers: isForm ? {} : { 'Content-Type': 'application/json' },
      body:    isForm ? body : JSON.stringify(body),
    });
    const data = await r.json();
    if (!r.ok || !data.ok) throw new Error(data.error || `HTTP ${r.status}`);
    return data;
  },
};

// ── Toasts ─────────────────────────────────────────────────────────────────
function toast(msg, type = 'info', ms = 3800) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  D.toasts.appendChild(el);
  setTimeout(() => el.remove(), ms);
}

// ── Confidence helpers ─────────────────────────────────────────────────────
function confClass(c) {
  if (c >= 75) return 'high';
  if (c >= 50) return 'medium';
  return 'low';
}

function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Source panel ───────────────────────────────────────────────────────────
function renderSources(sources) {
  S.sources = sources;
  D.sourceList.innerHTML = '';

  const empty = sources.length === 0;
  D.sourcesEmpty.classList.toggle('hidden', !empty);

  if (empty) {
    D.panelStats.textContent = '';
    return;
  }

  sources.forEach(src => {
    const icons = { pdf: '📄', youtube: '▶', url: '🔗' };
    const icon  = icons[src.type] || '📎';
    const label = src.name.replace(/^https?:\/\//, '').slice(0, 50);

    const div = document.createElement('div');
    div.className = 'source-item';
    div.innerHTML = `
      <div class="source-icon ${esc(src.type)}">${icon}</div>
      <span class="source-name" title="${esc(src.name)}">${esc(label)}</span>
    `;
    D.sourceList.appendChild(div);
  });
}

function updatePanelStats(status) {
  if (!status.hasDocuments) { D.panelStats.textContent = ''; return; }
  const n = status.sources ? status.sources.length : 0;
  D.panelStats.textContent =
    `${n} source${n !== 1 ? 's' : ''} · ${status.chunkCount} chunks`;
}

// ── Status bar ─────────────────────────────────────────────────────────────
function renderStatus(status) {
  S.ready        = status.ready;
  S.hasDocuments = status.hasDocuments;
  S.provider     = status.provider;

  // Status dot
  D.statusDot.className = 'status-dot ' + (status.ready ? 'ready' : '');
  D.statusLabel.textContent = status.ready
    ? `${status.providerLabel}`
    : status.hasDocuments ? 'Not loaded' : 'No sources';

  // Model buttons
  document.querySelectorAll('.model-btn').forEach(btn =>
    btn.classList.toggle('active', btn.dataset.provider === status.provider));

  // Composer
  D.chatInput.disabled = !status.ready;
  D.composerHint.textContent = status.ready
    ? 'Ask anything about your sources'
    : status.hasDocuments
      ? 'Click Reload in the sources panel to load the knowledge base'
      : 'Add sources to start chatting';

  updatePanelStats(status);
  syncSendBtn();
}

// ── Messages ───────────────────────────────────────────────────────────────
function renderMessages(messages) {
  S.messages = messages;
  // Remove existing message elements
  document.querySelectorAll('.msg-user, .msg-ai').forEach(el => el.remove());

  const hasMessages = messages.length > 0;
  D.welcome.classList.toggle('hidden', hasMessages);

  messages.forEach(m => {
    if (m.role === 'user') _appendUser(m.content, false);
    else _appendAI(m, false);
  });

  if (hasMessages) scrollBottom();
}

function _appendUser(content, animate = true) {
  const el = document.createElement('div');
  el.className = 'msg-user';
  if (!animate) el.style.animation = 'none';
  el.innerHTML = `<div class="msg-user-inner">${esc(content)}</div>`;
  D.messages.appendChild(el);
}

function _appendAI(msg, animate = true) {
  const lv = confClass(msg.confidence);

  const chips = (msg.sources || []).map(s => {
    let label;
    if (s.type === 'pdf')     label = `${s.label} · p.${s.page}`;
    else if (s.type === 'youtube') label = `▶ ${s.label}`;
    else label = (s.url || s.label || '').replace(/^https?:\/\//, '').slice(0, 48);
    return `<span class="src-chip" title="${esc(s.url || s.label || '')}">${esc(label)}</span>`;
  }).join('');

  const el = document.createElement('div');
  el.className = 'msg-ai';
  if (!animate) el.style.animation = 'none';
  el.innerHTML = `
    <div class="msg-ai-card">
      <div class="conf-bar ${lv}"></div>
      <div class="msg-ai-body">${esc(msg.content)}</div>
      <div class="msg-ai-footer">
        <span class="conf-tag ${lv}">${msg.confidence}% confidence</span>
        ${chips}
      </div>
    </div>`;
  D.messages.appendChild(el);
}

function showThinking() {
  const el = document.createElement('div');
  el.className = 'msg-thinking';
  el.id = 'thinking-el';
  el.innerHTML = `
    <div class="thinking-card">
      <div class="thinking-dots"><span></span><span></span><span></span></div>
      <span>Thinking…</span>
    </div>`;
  D.messages.appendChild(el);
  scrollBottom();
}

function hideThinking() {
  const el = document.getElementById('thinking-el');
  if (el) el.remove();
}

function scrollBottom() {
  D.messages.scrollTo({ top: D.messages.scrollHeight, behavior: 'smooth' });
}

// ── Context panel ──────────────────────────────────────────────────────────
function renderContext(msg) {
  if (!msg) {
    D.contextBody.innerHTML = `
      <div class="context-idle">
        <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true">
          <circle cx="16" cy="16" r="12" stroke="currentColor" stroke-width="1.2" stroke-dasharray="3 3" opacity=".3"/>
          <circle cx="16" cy="16" r="4" fill="currentColor" opacity=".15"/>
        </svg>
        <span>Cited sources and confidence appear here after each answer</span>
      </div>`;
    return;
  }

  const lv = confClass(msg.confidence);
  const srcItems = (msg.sources || []).map(s => {
    const lbl = s.type === 'pdf'
      ? `${s.label} p.${s.page}`
      : (s.url || s.label || '').replace(/^https?:\/\//, '').slice(0, 52);
    return `<div class="ctx-src-item" title="${esc(s.url || s.label || '')}">${esc(lbl)}</div>`;
  }).join('');

  D.contextBody.innerHTML = `
    <div class="ctx-card">
      <div class="ctx-card-hd">Confidence</div>
      <div class="ctx-conf-wrap">
        <div class="ctx-conf-row">
          <span>Match quality</span>
          <strong>${msg.confidence}%</strong>
        </div>
        <div class="conf-track">
          <div class="conf-fill ${lv}" style="width:${msg.confidence}%"></div>
        </div>
      </div>
    </div>
    ${srcItems ? `
    <div class="ctx-card">
      <div class="ctx-card-hd">Cited (${msg.sources.length})</div>
      <div class="ctx-src-list">${srcItems}</div>
    </div>` : ''}`;
}

// ── Composer ───────────────────────────────────────────────────────────────
function syncSendBtn() {
  const hasText = D.chatInput.value.trim().length > 0;
  D.sendBtn.disabled = !hasText || S.thinking || !S.ready;
}

function autoresize() {
  D.chatInput.style.height = 'auto';
  D.chatInput.style.height = `${Math.min(D.chatInput.scrollHeight, 180)}px`;
}

async function sendMessage() {
  const text = D.chatInput.value.trim();
  if (!text || S.thinking || !S.ready) return;

  S.thinking = true;
  D.chatInput.value = '';
  autoresize();
  syncSendBtn();

  D.welcome.classList.add('hidden');
  _appendUser(text);
  showThinking();
  scrollBottom();

  try {
    const data = await API.post('/api/chat', { message: text });
    hideThinking();
    _appendAI(data.message);
    renderStatus(data.status);
    renderSources(data.status.sources || []);
    renderContext(data.message);
    scrollBottom();
  } catch (err) {
    hideThinking();
    // Remove the user bubble we appended optimistically
    const userBubbles = document.querySelectorAll('.msg-user');
    if (userBubbles.length) userBubbles[userBubbles.length - 1].remove();
    // If there are no messages left, show welcome again
    if (!document.querySelectorAll('.msg-user, .msg-ai').length) {
      D.welcome.classList.remove('hidden');
    }
    toast(err.message || 'Chat failed', 'error');
  }

  S.thinking = false;
  syncSendBtn();
  D.chatInput.focus();
}

// ── Upload ─────────────────────────────────────────────────────────────────
async function uploadFiles() {
  const files = D.fileInput.files;
  if (!files.length) return;

  const prev = D.uploadBtn.textContent;
  D.uploadBtn.disabled = true;
  D.uploadBtn.textContent = 'Ingesting…';

  const fd = new FormData();
  Array.from(files).forEach(f => fd.append('files', f));

  try {
    const data = await API.post('/api/upload', fd);
    renderSources(data.status.sources || []);
    renderStatus(data.status);
    renderMessages(data.status.messages || []);
    toast(`Ingested ${data.ingested.length} file${data.ingested.length !== 1 ? 's' : ''}`, 'success');
    closeDrawer();
    D.fileInput.value = '';
    D.filePreview.innerHTML = '';
  } catch (err) {
    toast(err.message || 'Upload failed', 'error');
  }

  D.uploadBtn.disabled = false;
  D.uploadBtn.textContent = prev;
}

async function ingestUrl() {
  const url = D.urlInput.value.trim();
  if (!url) { toast('Paste a URL first', 'error'); return; }

  const prev = D.ingestUrlBtn.textContent;
  D.ingestUrlBtn.disabled = true;
  D.ingestUrlBtn.textContent = 'Ingesting…';

  try {
    const data = await API.post('/api/ingest-url', { url });
    renderSources(data.status.sources || []);
    renderStatus(data.status);
    renderMessages(data.status.messages || []);
    toast('Source ingested', 'success');
    closeDrawer();
    D.urlInput.value = '';
  } catch (err) {
    toast(err.message || 'Ingest failed', 'error');
  }

  D.ingestUrlBtn.disabled = false;
  D.ingestUrlBtn.textContent = prev;
}

// ── Reload / Clear ─────────────────────────────────────────────────────────
async function reloadChain() {
  D.statusDot.className = 'status-dot loading';
  D.statusLabel.textContent = 'Loading…';
  D.reloadBtn.disabled = true;

  try {
    const data = await API.post('/api/reload', {});
    renderStatus(data.status);
    renderMessages(data.status.messages || []);
    toast('Knowledge base loaded', 'success');
  } catch (err) {
    toast(err.message || 'Reload failed', 'error');
    renderStatus(S);        // restore last known
  }

  D.reloadBtn.disabled = false;
}

async function clearChat() {
  try {
    const data = await API.post('/api/clear', {});
    renderMessages([]);
    renderContext(null);
    renderStatus(data.status);
    toast('Conversation cleared', 'info');
  } catch (err) {
    toast(err.message || 'Clear failed', 'error');
  }
}

async function setProvider(provider) {
  if (provider === S.provider) return;
  try {
    const data = await API.post('/api/provider', { provider });
    renderStatus(data.status);
    renderMessages(data.status.messages || []);
    renderContext(null);
    toast(`Switched to ${data.status.providerLabel}`, 'info');
  } catch (err) {
    toast(err.message || 'Switch failed', 'error');
  }
}

// ── Drawer ─────────────────────────────────────────────────────────────────
function openDrawer() {
  S.drawerOpen = true;
  D.drawer.classList.add('open');
  D.drawerBackdrop.classList.add('visible');
  D.drawer.removeAttribute('aria-hidden');
  document.body.style.overflow = 'hidden';
}

function closeDrawer() {
  S.drawerOpen = false;
  D.drawer.classList.remove('open');
  D.drawerBackdrop.classList.remove('visible');
  D.drawer.setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
}

// ── Events ─────────────────────────────────────────────────────────────────
function bindEvents() {

  // Add source
  D.addBtn.addEventListener('click', openDrawer);
  D.welcomeCta.addEventListener('click', openDrawer);
  D.drawerClose.addEventListener('click', closeDrawer);
  D.drawerBackdrop.addEventListener('click', closeDrawer);

  // Mobile panel toggle
  D.panelToggle.addEventListener('click', () => {
    D.sourcesPanel.classList.toggle('open');
  });
  // Click outside sources panel on mobile
  D.shell && D.messages.addEventListener('click', () => {
    if (window.innerWidth <= 840) {
      D.sourcesPanel.classList.remove('open');
    }
  });

  // Topbar actions
  D.clearBtn.addEventListener('click', clearChat);
  D.reloadBtn.addEventListener('click', reloadChain);

  // Model toggle
  document.querySelectorAll('.model-btn').forEach(btn =>
    btn.addEventListener('click', () => setProvider(btn.dataset.provider)));

  // Drawer tabs
  document.querySelectorAll('.dtab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.dtab').forEach(t => {
        t.classList.remove('active');
        t.setAttribute('aria-selected', 'false');
      });
      tab.classList.add('active');
      tab.setAttribute('aria-selected', 'true');
      const panel = tab.dataset.tab;
      document.querySelectorAll('.dtab-panel').forEach(p =>
        p.classList.toggle('hidden', p.dataset.panel !== panel));
    });
  });

  // File input
  D.fileInput.addEventListener('change', () => {
    const files = Array.from(D.fileInput.files);
    D.filePreview.innerHTML = files.map(f =>
      `<span class="file-tag">${esc(f.name)}</span>`).join('');
    D.uploadBtn.disabled = files.length === 0;
  });

  // Drag-and-drop onto drop zone
  D.dropZone.addEventListener('dragover', e => {
    e.preventDefault();
    D.dropZone.classList.add('drag-over');
  });
  D.dropZone.addEventListener('dragleave', e => {
    if (!D.dropZone.contains(e.relatedTarget)) {
      D.dropZone.classList.remove('drag-over');
    }
  });
  D.dropZone.addEventListener('drop', e => {
    e.preventDefault();
    D.dropZone.classList.remove('drag-over');
    const pdfs = Array.from(e.dataTransfer.files)
      .filter(f => f.name.toLowerCase().endsWith('.pdf'));
    if (!pdfs.length) { toast('Only PDF files are supported', 'error'); return; }
    try {
      const dt = new DataTransfer();
      pdfs.forEach(f => dt.items.add(f));
      D.fileInput.files = dt.files;
      D.fileInput.dispatchEvent(new Event('change'));
    } catch (_) {
      toast('Drag & drop not supported in this browser. Use the file picker.', 'info');
    }
  });

  // Upload / ingest
  D.uploadBtn.addEventListener('click', uploadFiles);
  D.ingestUrlBtn.addEventListener('click', ingestUrl);
  D.urlInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') ingestUrl();
  });

  // Composer
  D.chatInput.addEventListener('input', () => { autoresize(); syncSendBtn(); });
  D.chatInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  D.sendBtn.addEventListener('click', sendMessage);

  // Global keyboard shortcuts
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      if (S.drawerOpen) closeDrawer();
      else if (window.innerWidth <= 840) D.sourcesPanel.classList.remove('open');
    }
  });
}

// ── Init ───────────────────────────────────────────────────────────────────
async function init() {
  resolveDOM();
  bindEvents();
  autoresize();

  try {
    const status = await API.get('/api/status');
    renderSources(status.sources || []);
    renderStatus(status);
    renderMessages(status.messages || []);

    // Restore context panel if session has prior messages
    const lastAI = [...(status.messages || [])].reverse().find(m => m.role === 'assistant');
    if (lastAI) renderContext(lastAI);

  } catch (err) {
    toast('Could not connect to server', 'error');
    D.statusDot.className = 'status-dot error';
    D.statusLabel.textContent = 'Error';
  }
}

document.addEventListener('DOMContentLoaded', init);
