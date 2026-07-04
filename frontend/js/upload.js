// js/upload.js — Upload / sources page logic
import { API } from './config.js'

// ── DOM refs ──────────────────────────────────────────────────────
const dropZone     = document.getElementById('drop-zone')
const fileInput    = document.getElementById('file-input')
const urlInput     = document.getElementById('url-input')
const addUrlBtn    = document.getElementById('add-url-btn')
const statusBar    = document.getElementById('status-bar')
const statusIcon   = document.getElementById('status-icon')
const statusText   = document.getElementById('status-text')
const docsSection  = document.getElementById('docs-section')
const docList      = document.getElementById('doc-list')
const docsCount    = document.getElementById('docs-count')
const openChatBtn  = document.getElementById('open-chat-btn')
const uploadCount  = document.getElementById('upload-count')

// ── Status bar ────────────────────────────────────────────────────
let statusTimer = null

function showStatus(msg, type = 'loading') {
  clearTimeout(statusTimer)
  statusBar.className = 'status-bar ' + type
  statusText.textContent = msg

  if (type === 'loading') {
    statusIcon.innerHTML = spinnerSVG()
  } else if (type === 'success') {
    statusIcon.innerHTML = checkSVG()
  } else {
    statusIcon.innerHTML = errorSVG()
  }

  if (type !== 'loading') {
    statusTimer = setTimeout(() => {
      statusBar.classList.add('hidden')
    }, 4000)
  }
}

function hideStatus() {
  statusBar.classList.add('hidden')
}

// ── Drop zone ─────────────────────────────────────────────────────
function setupDropZone() {
  dropZone.addEventListener('click', e => {
    if (e.target !== fileInput) fileInput.click()
  })
  dropZone.addEventListener('dragover', e => {
    e.preventDefault()
    dropZone.classList.add('drag-over')
  })
  dropZone.addEventListener('dragenter', e => {
    e.preventDefault()
    dropZone.classList.add('drag-over')
  })
  dropZone.addEventListener('dragleave', e => {
    if (!dropZone.contains(e.relatedTarget)) {
      dropZone.classList.remove('drag-over')
    }
  })
  dropZone.addEventListener('drop', e => {
    e.preventDefault()
    dropZone.classList.remove('drag-over')
    const files = Array.from(e.dataTransfer.files).filter(f =>
      f.name.toLowerCase().endsWith('.pdf'))
    if (!files.length) {
      showStatus('Only PDF files are supported.', 'error')
      return
    }
    uploadFile(files[0])
  })
  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) uploadFile(fileInput.files[0])
    fileInput.value = ''
  })
}

// ── Upload ────────────────────────────────────────────────────────
async function uploadFile(file) {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    showStatus('Only PDF files are supported.', 'error')
    return
  }
  if (file.size > 50 * 1024 * 1024) {
    showStatus('File too large. Max 50 MB.', 'error')
    return
  }
  showStatus('Processing ' + file.name + '…')
  const fd = new FormData()
  fd.append('file', file)
  try {
    const res = await fetch(API + '/api/ingest/upload', { method: 'POST', body: fd })
    const data = await res.json()
    if (!res.ok || !data.ok) throw new Error(data.detail || 'Upload failed')
    showStatus('Added · ' + data.chunks + ' chunks', 'success')
    loadDocs()
  } catch (err) {
    showStatus(err.message || 'Upload failed', 'error')
  }
}

// ── URL ingest ────────────────────────────────────────────────────
function setupUrlInput() {
  addUrlBtn.addEventListener('click', submitUrl)
  urlInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') submitUrl()
  })
}

async function submitUrl() {
  const url = urlInput.value.trim()
  if (!url) { showStatus('Paste a URL first.', 'error'); return }
  showStatus('Fetching…')
  try {
    const res = await fetch(API + '/api/ingest/url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    })
    const data = await res.json()
    if (!res.ok || !data.ok) throw new Error(data.detail || 'Ingest failed')
    urlInput.value = ''
    showStatus('Added · ' + data.chunks + ' chunks', 'success')
    loadDocs()
  } catch (err) {
    showStatus(err.message || 'Ingest failed', 'error')
  }
}

// ── Documents ─────────────────────────────────────────────────────
async function loadDocs() {
  try {
    const res = await fetch(API + '/api/documents')
    const docs = await res.json()
    renderDocs(docs)
  } catch {
    // silent
  }
}

function renderDocs(docs) {
  const count = docs.length
  docsSection.classList.toggle('hidden', count === 0)
  docsCount.textContent = '· ' + count
  uploadCount.textContent = count + ' source' + (count !== 1 ? 's' : '') + ' indexed'
  openChatBtn.disabled = count === 0

  docList.innerHTML = ''
  docs.forEach(doc => {
    const row = document.createElement('div')
    row.className = 'doc-row'
    row.innerHTML = renderDocRow(doc)
    row.querySelector('.doc-delete').addEventListener('click', () => deleteDoc(doc.name))
    docList.appendChild(row)
  })
}

function renderDocRow(doc) {
  const icon = docIconSVG(doc.source_type)
  const badgeClass = { pdf: 'badge-pdf', url: 'badge-web', youtube: 'badge-yt' }[doc.source_type] || 'badge-web'
  const badgeLabel = { pdf: 'PDF', url: 'WEB', youtube: 'YT' }[doc.source_type] || doc.source_type.toUpperCase()
  const displayName = doc.name.replace(/^https?:\/\//, '').slice(0, 60)
  return `
    <div class="doc-icon">${icon}</div>
    <div class="doc-info">
      <div class="doc-name" title="${esc(doc.name)}">${esc(displayName)}</div>
      <div class="doc-meta">
        <span class="badge ${badgeClass}">${badgeLabel}</span>
        <span class="doc-chunks">· ${doc.chunks} chunks</span>
      </div>
    </div>
    <button class="btn-icon doc-delete" title="Delete source" aria-label="Delete">
      ${trashSVG()}
    </button>`
}

async function deleteDoc(name) {
  if (!confirm('Remove "' + name + '" from the knowledge base?')) return
  try {
    await fetch(API + '/api/documents/' + encodeURIComponent(name), { method: 'DELETE' })
    loadDocs()
  } catch {
    showStatus('Delete failed', 'error')
  }
}

// ── SVG helpers ───────────────────────────────────────────────────
function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function spinnerSVG() {
  return `<svg class="spinner" viewBox="0 0 16 16" fill="none">
    <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5" stroke-dasharray="28" stroke-dashoffset="10" stroke-linecap="round"/>
  </svg>`
}
function checkSVG() {
  return `<svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <path d="M3 8l4 4 6-7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`
}
function errorSVG() {
  return `<svg width="16" height="16" viewBox="0 0 16 16" fill="none">
    <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/>
    <path d="M8 5v4M8 11v.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
  </svg>`
}
function trashSVG() {
  return `<svg width="14" height="14" viewBox="0 0 14 14" fill="none">
    <path d="M2 3.5h10M5.5 3.5V2.5a.5.5 0 01.5-.5h2a.5.5 0 01.5.5v1M5.5 6v4.5M8.5 6v4.5M3 3.5l.7 7.5a.5.5 0 00.5.5h5.6a.5.5 0 00.5-.5L11 3.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`
}
function docIconSVG(type) {
  if (type === 'pdf') {
    return `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><rect x="2" y="1" width="9" height="12" rx="1" stroke="#a78bfa" stroke-width="1.2"/><path d="M5 7h6M5 9.5h4" stroke="#a78bfa" stroke-width="1" stroke-linecap="round"/><path d="M9 1v3.5h3.5" stroke="#a78bfa" stroke-width="1" stroke-linejoin="round"/></svg>`
  }
  if (type === 'youtube') {
    return `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><rect x="1" y="3" width="14" height="10" rx="2" stroke="#f87171" stroke-width="1.2"/><path d="M6.5 6l4 2-4 2V6z" fill="#f87171"/></svg>`
  }
  return `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="#60a5fa" stroke-width="1.2"/><path d="M5.5 8a2.5 2.5 0 005 0M5.5 8a2.5 2.5 0 000 0" stroke="#60a5fa" stroke-width="1" stroke-linecap="round"/><path d="M2 8h12M8 2a10 10 0 000 12M8 2a10 10 0 010 12" stroke="#60a5fa" stroke-width="1" stroke-linecap="round"/></svg>`
}

// ── Init ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  setupDropZone()
  setupUrlInput()
  loadDocs()
  openChatBtn.addEventListener('click', () => {
    window.location.href = 'chat.html'
  })
})
