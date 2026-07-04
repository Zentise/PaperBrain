// js/chat.js — Chat page logic
import { API, MODELS, TIER_COLORS, DEFAULT_MODEL } from './config.js'

// ── State ─────────────────────────────────────────────────────────
let model     = DEFAULT_MODEL
let sessionId = getOrCreateSession()
let streaming = false
let streamStart = 0

// ── Session ───────────────────────────────────────────────────────
function getOrCreateSession() {
  let id = sessionStorage.getItem('pb_sid')
  if (!id) {
    id = 'pb_' + Date.now() + '_' + Math.random().toString(36).slice(2)
    sessionStorage.setItem('pb_sid', id)
  }
  return id
}

// ── DOM refs ──────────────────────────────────────────────────────
const messagesEl      = document.getElementById('messages')
const emptyState      = document.getElementById('empty-state')
const msgInput        = document.getElementById('msg-input')
const sendBtn         = document.getElementById('send-btn')
const charCount       = document.getElementById('char-count')
const typingEl        = document.getElementById('typing')
const confDisplay     = document.getElementById('conf-display')
const confScore       = document.getElementById('conf-score')
const topbarModelName = document.getElementById('topbar-model-name')
const topbarModelDesc = document.getElementById('topbar-model-desc')
const sidebarModels   = document.getElementById('sidebar-models')
const pickerEl        = document.getElementById('model-picker')
const pickerModels    = document.getElementById('picker-models')
const modelIndicator  = document.getElementById('model-indicator')
const indicatorDot    = document.getElementById('indicator-dot')
const indicatorLabel  = document.getElementById('indicator-label')
const sessionDisplay  = document.getElementById('session-display')
const newChatBtn      = document.getElementById('new-chat-btn')
const indexedList     = document.getElementById('indexed-list')
const attachBtn       = document.getElementById('attach-btn')
const attachInput     = document.getElementById('attach-input')

// ── Model rendering ───────────────────────────────────────────────
function groupedModelHTML(onClickAttr) {
  const tiers = ['fast', 'balanced', 'powerful']
  let html = ''
  tiers.forEach(tier => {
    const group = MODELS.filter(m => m.tier === tier)
    if (!group.length) return
    const label = tier.toUpperCase()
    html += `<div class="tier-sep">
      <span class="tier-line"></span>
      <span class="tier-label-text">${label}</span>
      <span class="tier-line"></span>
    </div>`
    group.forEach(m => {
      const selected = m.id === model.id ? 'selected' : ''
      const color = TIER_COLORS[m.tier] || '#888'
      html += `<div class="model-row ${selected}" data-model-id="${m.id}" ${onClickAttr}>
        <div class="tier-dot ${m.tier}" style="background:${color}"></div>
        <div class="model-info">
          <span class="model-label">${esc(m.name)}</span>
          <span class="model-desc">${esc(m.description)}</span>
        </div>
        <span class="model-context">${esc(m.context)}</span>
      </div>`
    })
  })
  return html
}

function renderModelLists() {
  sidebarModels.innerHTML = groupedModelHTML('')
  pickerModels.innerHTML  = groupedModelHTML('')

  ;[sidebarModels, pickerModels].forEach(container => {
    container.querySelectorAll('.model-row').forEach(row => {
      row.addEventListener('click', () => {
        const m = MODELS.find(x => x.id === row.dataset.modelId)
        if (m) setModel(m)
      })
    })
  })
}

function setModel(m) {
  model = m
  // Update selected state
  document.querySelectorAll('.model-row').forEach(row => {
    row.classList.toggle('selected', row.dataset.modelId === m.id)
  })
  // Update indicator
  const color = TIER_COLORS[m.tier] || '#888'
  indicatorDot.style.background = color
  indicatorLabel.textContent = m.label.toUpperCase()
  // Update topbar
  topbarModelName.textContent = m.name
  topbarModelDesc.textContent = m.description
  // Close picker
  closePicker()
}

// ── Model picker ──────────────────────────────────────────────────
function togglePicker() {
  pickerEl.classList.toggle('hidden')
}
function closePicker() {
  pickerEl.classList.add('hidden')
}

// ── Messages ──────────────────────────────────────────────────────
function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function appendUserMsg(text) {
  const el = document.createElement('div')
  el.className = 'msg user'
  el.textContent = text
  messagesEl.appendChild(el)
}

function appendAssistantWrap() {
  const wrap = document.createElement('div')
  wrap.className = 'msg-wrap'
  wrap.innerHTML = `
    <span class="msg-tag"></span>
    <div class="msg assistant">
      <div class="msg-text"></div>
      <div class="msg-meta"></div>
    </div>`
  messagesEl.appendChild(wrap)
  return wrap
}

function setModelTag(wrap, text) {
  wrap.querySelector('.msg-tag').textContent = text
}

function confClass(score) {
  if (score >= 75) return 'high'
  if (score >= 50) return 'medium'
  return 'low'
}

function showMeta(wrap, confidence, sources) {
  const meta = wrap.querySelector('.msg-meta')
  const cls = confClass(confidence)
  const sourcesHTML = renderSourceBadges(sources)
  meta.innerHTML = `
    <span class="conf-pill ${cls}">● ${confidence}%</span>
    <div class="sources-row">${sourcesHTML}</div>`
  meta.classList.add('visible')
}

function renderSourceBadges(sources) {
  return (sources || []).map(s => {
    if (s.type === 'pdf') {
      return `<span class="badge badge-pdf">PDF · ${esc(s.label)} · p.${s.page}</span>`
    }
    if (s.type === 'youtube') {
      return `<span class="badge badge-yt">YT · ${esc(s.label)}</span>`
    }
    const domain = (s.url || s.label || '').replace(/^https?:\/\//, '').split('/')[0].slice(0, 30)
    return `<span class="badge badge-web">WEB · ${esc(domain)}</span>`
  }).join('')
}

function updateConfDisplay(score) {
  confDisplay.classList.remove('hidden')
  const cls = confClass(score)
  confScore.textContent = '· ' + score + '%'
  confScore.className = 'conf-score ' + cls
}

// ── Typing indicator ──────────────────────────────────────────────
function showTyping() { typingEl.classList.remove('hidden') }
function hideTyping()  { typingEl.classList.add('hidden') }

// ── Scroll ────────────────────────────────────────────────────────
function scroll() {
  messagesEl.scrollTo({ top: messagesEl.scrollHeight, behavior: 'smooth' })
}

// ── Input helpers ─────────────────────────────────────────────────
function autoResize() {
  msgInput.style.height = 'auto'
  msgInput.style.height = Math.min(msgInput.scrollHeight, 140) + 'px'
}

function updateCharCount() {
  const n = msgInput.value.length
  charCount.textContent = n + '/2000'
  charCount.classList.toggle('warn', n > 1800)
}

function clearInput() {
  msgInput.value = ''
  autoResize()
  updateCharCount()
}

// ── Send / stream ─────────────────────────────────────────────────
function sendMessage() {
  if (streaming) return
  const text = msgInput.value.trim()
  if (!text) return
  if (text.length > 2000) {
    charCount.classList.add('warn')
    return
  }

  streaming = true
  streamStart = Date.now()
  clearInput()
  emptyState.classList.add('hidden')
  appendUserMsg(text)
  showTyping()
  scroll()

  const qs = new URLSearchParams({ session_id: sessionId, message: text, model_id: model.id })
  const es = new EventSource(API + '/api/chat/stream?' + qs)
  const wrap = appendAssistantWrap()
  const msgText = wrap.querySelector('.msg-text')
  let full = ''

  es.onmessage = e => {
    try {
      const d = JSON.parse(e.data)
      if (d.token) {
        full += d.token
        msgText.textContent = full
        scroll()
      }
      if (d.done) {
        const elapsed = ((Date.now() - streamStart) / 1000).toFixed(1)
        hideTyping()
        setModelTag(wrap, model.label.toUpperCase() + ' · ' + elapsed + 's')
        showMeta(wrap, d.confidence, d.sources)
        updateConfDisplay(d.confidence)
        streaming = false
        es.close()
        scroll()
      }
      if (d.error) {
        hideTyping()
        msgText.textContent = '⚠ ' + d.error
        streaming = false
        es.close()
      }
    } catch { /* ignore parse errors */ }
  }

  es.onerror = () => {
    hideTyping()
    if (!full) msgText.textContent = 'Connection error. Please try again.'
    streaming = false
    es.close()
  }
}

// ── New chat ──────────────────────────────────────────────────────
function newChat() {
  // Fire-and-forget clear
  fetch(API + '/api/session/' + sessionId, { method: 'DELETE' }).catch(() => {})
  sessionId = 'pb_' + Date.now() + '_' + Math.random().toString(36).slice(2)
  sessionStorage.setItem('pb_sid', sessionId)
  // Clear UI
  messagesEl.innerHTML = ''
  messagesEl.appendChild(emptyState)
  emptyState.classList.remove('hidden')
  typingEl.classList.add('hidden')
  confDisplay.classList.add('hidden')
  streaming = false
  updateSessionDisplay()
}

function updateSessionDisplay() {
  if (sessionDisplay) sessionDisplay.textContent = sessionId.slice(0, 8) + '…'
}

// ── Indexed docs (sidebar mini list) ─────────────────────────────
async function loadIndexedDocs() {
  if (!indexedList) return
  try {
    const res = await fetch(API + '/api/documents')
    const docs = await res.json()
    indexedList.innerHTML = docs.slice(0, 5).map(d => {
      const name = d.name.replace(/^https?:\/\//, '').slice(0, 30)
      return `<div class="indexed-item" title="${esc(d.name)}">${esc(name)}</div>`
    }).join('')
  } catch { /* silent */ }
}

// ── Attach (in-chat upload) ───────────────────────────────────────
async function uploadAndIngest(file) {
  if (!file || !file.name.toLowerCase().endsWith('.pdf')) return
  if (file.size > 50 * 1024 * 1024) { alert('File too large. Max 50 MB.'); return }
  const fd = new FormData()
  fd.append('file', file)
  try {
    const res = await fetch(API + '/api/ingest/upload', { method: 'POST', body: fd })
    const data = await res.json()
    if (data.ok) {
      loadIndexedDocs()
      // Subtle confirmation in input area
      const hint = document.createElement('div')
      hint.style.cssText = 'font-family:var(--mono);font-size:11px;color:var(--success);padding:4px 0'
      hint.textContent = '✓ ' + file.name + ' ingested'
      msgInput.parentElement.parentElement.prepend(hint)
      setTimeout(() => hint.remove(), 3000)
    }
  } catch { /* silent */ }
}

// ── Setup events ──────────────────────────────────────────────────
function syncSendBtn() {
  sendBtn.disabled = streaming || msgInput.value.trim().length === 0
}

function setupInput() {
  msgInput.addEventListener('input', () => { autoResize(); updateCharCount(); syncSendBtn() })
  msgInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
  })
  sendBtn.addEventListener('click', sendMessage)

  if (attachBtn && attachInput) {
    attachBtn.addEventListener('click', () => attachInput.click())
    attachInput.addEventListener('change', () => {
      if (attachInput.files[0]) uploadAndIngest(attachInput.files[0])
      attachInput.value = ''
    })
  }

  modelIndicator.addEventListener('click', e => {
    e.stopPropagation()
    togglePicker()
  })

  document.addEventListener('click', e => {
    if (!pickerEl.contains(e.target) && e.target !== modelIndicator) {
      closePicker()
    }
  })

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closePicker()
  })
}

// ── Init ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  renderModelLists()
  setModel(DEFAULT_MODEL)
  loadIndexedDocs()
  setupInput()
  updateSessionDisplay()
  updateCharCount()

  if (newChatBtn) newChatBtn.addEventListener('click', newChat)

  // Move typing indicator into messages
  if (typingEl && !messagesEl.contains(typingEl)) {
    messagesEl.appendChild(typingEl)
  }
})
