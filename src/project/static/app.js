// app.js - CallRadar Frontend Controller

let currentCallId = null;
let allRadarCalls = [];
let allCustomers = [];

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initAudioPlayer();
  initSearchAndFilters();
  loadAllData();

  document.getElementById('btnRefresh').addEventListener('click', () => {
    loadAllData();
  });
});

// ----------------- Tab Navigation -----------------
function initTabs() {
  const tabs = document.querySelectorAll('.nav-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

      tab.classList.add('active');
      const targetId = `pane-${tab.dataset.tab}`;
      const targetPane = document.getElementById(targetId);
      if (targetPane) targetPane.classList.add('active');

      if (tab.dataset.tab === 'customers') loadCustomers();
      if (tab.dataset.tab === 'agents') loadAgents();
      if (tab.dataset.tab === 'trends') loadTrends();
    });
  });
}

function switchTab(tabName) {
  const tabBtn = document.querySelector(`.nav-tab[data-tab="${tabName}"]`);
  if (tabBtn) tabBtn.click();
}

// ----------------- Data Fetching -----------------
async function loadAllData() {
  await Promise.all([
    loadStats(),
    loadRadarQueue()
  ]);
}

async function loadStats() {
  try {
    const res = await fetch('/api/dashboard/stats');
    if (!res.ok) return;
    const stats = await res.json();

    document.getElementById('statTotalCalls').textContent = stats.total_calls;
    document.getElementById('statHighUrgency').textContent = stats.high_urgency_calls;
    document.getElementById('statAvgScore').textContent = `${stats.avg_attention_score}/100`;
    document.getElementById('statResolutionRate').textContent = `${stats.resolution_rate}%`;
    document.getElementById('statAvgHandleTime').textContent = `Avg Handle: ${Math.round(stats.avg_handle_time_sec)}s`;
  } catch (err) {
    console.error('Failed to load stats:', err);
  }
}

async function loadRadarQueue() {
  const tbody = document.getElementById('radarTableBody');
  try {
    const res = await fetch('/api/dashboard/attention-queue?limit=100');
    if (!res.ok) throw new Error('Failed to fetch radar queue');
    allRadarCalls = await res.json();
    renderRadarTable(allRadarCalls);

    // Auto-inspect the first call if none selected
    if (allRadarCalls.length > 0 && !currentCallId) {
      inspectCall(allRadarCalls[0].call_id, false);
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center py-6 text-danger">Error loading radar: ${err.message}</td></tr>`;
  }
}

function renderRadarTable(calls) {
  const tbody = document.getElementById('radarTableBody');
  if (!calls || calls.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty-state">No calls found matching criteria.</td></tr>`;
    return;
  }

  tbody.innerHTML = calls.map(c => {
    const scoreClass = c.attention_score >= 70 ? 'score-high' : c.attention_score >= 40 ? 'score-med' : 'score-low';
    const resBadge = c.is_resolved 
      ? `<span class="badge-resolved yes">Resolved</span>` 
      : `<span class="badge-resolved no">Unresolved</span>`;
      
    const moodShift = c.mood && c.mood.shift_occurred 
      ? `<span class="badge-tag" style="color:#fda4af;">${c.mood.initial_mood} &rarr; ${c.mood.final_mood}</span>`
      : `<span class="badge-tag">${c.mood ? c.mood.final_mood || 'Neutral' : 'Neutral'}</span>`;

    return `
      <tr onclick="inspectCall('${c.call_id}', true)">
        <td><span class="score-pill ${scoreClass}">${c.attention_score} / 100</span></td>
        <td>
          <div style="font-weight:600; font-family:var(--font-mono); font-size:0.82rem; color:#a5b4fc;">${c.call_id}</div>
          <div style="font-size:0.75rem; color:var(--text-muted); max-width:280px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
            ${escapeHtml(c.summary || c.intent || '—')}
          </div>
        </td>
        <td><strong>${escapeHtml(c.customer || 'Unknown')}</strong></td>
        <td>${escapeHtml(c.agent || 'Unknown')}</td>
        <td><span class="badge-tag">${escapeHtml(c.category || 'General')}</span></td>
        <td>${resBadge}</td>
        <td>${moodShift}</td>
        <td style="text-align: right;">
          <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); inspectCall('${c.call_id}', true)">Inspect</button>
        </td>
      </tr>
    `;
  }).join('');
}

// ----------------- Call Inspector -----------------
async function inspectCall(callId, switchView = true) {
  currentCallId = callId;
  if (switchView) switchTab('inspector');

  try {
    const res = await fetch(`/api/calls/${callId}`);
    if (!res.ok) throw new Error('Call not found');
    const data = await res.json();

    // Populate Audio Player
    document.getElementById('playerCallId').textContent = `Call ID: ${data.call_id}`;
    document.getElementById('playerCallMeta').textContent = `Agent: ${data.agent_name} | Customer: ${data.customer_name} | Duration: ${Math.round(data.duration_seconds)}s`;
    
    const urgencyBadge = document.getElementById('playerUrgencyBadge');
    urgencyBadge.className = `score-pill ${data.attention_score >= 70 ? 'score-high' : data.attention_score >= 40 ? 'score-med' : 'score-low'}`;
    urgencyBadge.textContent = `Attention: ${data.attention_score}/100`;

    const audio = document.getElementById('audioPlayer');
    audio.src = data.audio_url;
    audio.load();

    // Populate Transcript Turns
    renderTranscript(data.transcript);

    // Populate Intelligence
    renderIntelligence(data.intelligence);

  } catch (err) {
    console.error('Error inspecting call:', err);
  }
}

function renderTranscript(turns) {
  const container = document.getElementById('transcriptContainer');
  document.getElementById('transcriptTurnCount').textContent = turns.length;

  if (!turns || turns.length === 0) {
    container.innerHTML = `<div class="empty-state">No transcript turns available for this call.</div>`;
    return;
  }

  container.innerHTML = turns.map((t, idx) => {
    const speakerClass = t.speaker.toLowerCase().includes('agent') ? 'speaker-agent' : 'speaker-customer';
    return `
      <div class="turn-bubble ${speakerClass}" data-start="${t.start}" data-end="${t.end}" onclick="seekAudio(${t.start})">
        <div class="turn-meta">
          <span class="turn-speaker">${escapeHtml(t.speaker)}</span>
          <span class="turn-time">${formatTime(t.start)} - ${formatTime(t.end)}</span>
        </div>
        <div class="turn-text">${escapeHtml(t.text)}</div>
      </div>
    `;
  }).join('');
}

function renderIntelligence(intel) {
  if (!intel) return;

  // Resolved Badge
  const resBadge = document.getElementById('intelResolvedBadge');
  if (intel.is_resolved) {
    resBadge.className = 'badge-resolved yes';
    resBadge.textContent = 'Issue Resolved';
  } else {
    resBadge.className = 'badge-resolved no';
    resBadge.textContent = 'Unresolved Issue';
  }

  // Summary & Intent
  document.getElementById('intelSummary').textContent = intel.summary || '—';
  document.getElementById('intelIntent').textContent = intel.intent || '—';

  // Intent Evidence
  if (intel.intent_evidence) {
    document.getElementById('intentEvidenceQuote').textContent = `"${intel.intent_evidence.quote}"`;
    document.getElementById('intentTimeTag').textContent = `@ ${intel.intent_evidence.timestamp_start}s`;
    document.getElementById('btnJumpIntent').onclick = () => seekAudio(intel.intent_evidence.timestamp_start);
  }

  // Mood Flow
  const mood = intel.mood_analysis || {};
  document.getElementById('initialMood').textContent = `Initial: ${mood.initial_mood || 'Neutral'}`;
  document.getElementById('finalMood').textContent = `Final: ${mood.final_mood || 'Neutral'}`;

  if (mood.evidence) {
    document.getElementById('moodEvidenceQuote').textContent = `"${mood.evidence.quote}"`;
    document.getElementById('moodTimeTag').textContent = `@ ${mood.evidence.timestamp_start}s`;
    document.getElementById('btnJumpMood').onclick = () => seekAudio(mood.evidence.timestamp_start);
  } else {
    document.getElementById('moodEvidenceQuote').textContent = 'No significant mood pivot detected.';
    document.getElementById('moodTimeTag').textContent = '—';
  }

  // Resolution Evidence
  if (intel.resolution_evidence) {
    document.getElementById('resolutionEvidenceQuote').textContent = `"${intel.resolution_evidence.quote}"`;
    document.getElementById('resTimeTag').textContent = `@ ${intel.resolution_evidence.timestamp_start}s`;
    document.getElementById('btnJumpResolution').onclick = () => seekAudio(intel.resolution_evidence.timestamp_start);
  }

  // Escalation Reasons
  const reasonsList = document.getElementById('escalationReasonsList');
  if (intel.escalation_reasons && intel.escalation_reasons.length > 0) {
    reasonsList.innerHTML = intel.escalation_reasons.map(r => `<li>${escapeHtml(r)}</li>`).join('');
  } else {
    reasonsList.innerHTML = `<li style="color:var(--text-muted);">Standard routine interaction. No escalation triggers.</li>`;
  }
}

// ----------------- Audio Synchronizer -----------------
function initAudioPlayer() {
  const audio = document.getElementById('audioPlayer');
  const btnPlay = document.getElementById('btnPlayPause');
  const playIcon = document.getElementById('playIcon');
  const pauseIcon = document.getElementById('pauseIcon');
  const timeDisplay = document.getElementById('playerTime');
  const scrubber = document.getElementById('audioScrubber');

  btnPlay.addEventListener('click', () => {
    if (audio.paused) {
      audio.play();
    } else {
      audio.pause();
    }
  });

  audio.addEventListener('play', () => {
    playIcon.style.display = 'none';
    pauseIcon.style.display = 'block';
  });

  audio.addEventListener('pause', () => {
    playIcon.style.display = 'block';
    pauseIcon.style.display = 'none';
  });

  audio.addEventListener('timeupdate', () => {
    const current = audio.currentTime || 0;
    const duration = audio.duration || 1;
    timeDisplay.textContent = `${formatTime(current)} / ${formatTime(duration)}`;
    scrubber.value = (current / duration) * 100;

    // Highlight the active turn bubble
    highlightActiveTurn(current);
  });

  scrubber.addEventListener('input', () => {
    if (audio.duration) {
      audio.currentTime = (scrubber.value / 100) * audio.duration;
    }
  });
}

function seekAudio(seconds) {
  const audio = document.getElementById('audioPlayer');
  if (audio) {
    audio.currentTime = seconds;
    audio.play();
  }
}

function highlightActiveTurn(currentTime) {
  const bubbles = document.querySelectorAll('.turn-bubble');
  bubbles.forEach(b => {
    const start = parseFloat(b.dataset.start);
    const end = parseFloat(b.dataset.end);
    if (currentTime >= start && currentTime <= end) {
      if (!b.classList.contains('active-playing')) {
        bubbles.forEach(el => el.classList.remove('active-playing'));
        b.classList.add('active-playing');
        b.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }
  });
}

// ----------------- Customers Tab -----------------
async function loadCustomers() {
  const container = document.getElementById('customerListContainer');
  try {
    const res = await fetch('/api/customers');
    if (!res.ok) throw new Error('Failed to load customers');
    allCustomers = await res.json();
    renderCustomerList(allCustomers);

    if (allCustomers.length > 0) {
      showCustomerTimeline(allCustomers[0].customer_name);
    }
  } catch (err) {
    container.innerHTML = `<div class="empty-state">Error loading customers: ${err.message}</div>`;
  }
}

function renderCustomerList(customers) {
  const container = document.getElementById('customerListContainer');
  if (!customers || customers.length === 0) {
    container.innerHTML = `<div class="empty-state">No customers found.</div>`;
    return;
  }

  container.innerHTML = customers.map(c => `
    <div class="customer-item" onclick="showCustomerTimeline('${escapeHtml(c.customer_name)}')">
      <div>
        <div class="customer-item-name">${escapeHtml(c.customer_name)}</div>
        <div class="customer-item-meta">${c.call_count} call(s) | Risk Avg: ${c.avg_attention_score}/100</div>
      </div>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"></polyline></svg>
    </div>
  `).join('');
}

async function showCustomerTimeline(customerName) {
  const container = document.getElementById('customerDetailContainer');
  try {
    const res = await fetch(`/api/customers/${encodeURIComponent(customerName)}`);
    if (!res.ok) throw new Error('Customer timeline not found');
    const data = await res.json();

    container.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.25rem;">
        <div>
          <h3 style="font-family:var(--font-display); font-size:1.3rem;">${escapeHtml(data.customer_name)}</h3>
          <p style="font-size:0.8rem; color:var(--text-muted);">Total Ingested Calls: ${data.total_calls}</p>
        </div>
      </div>
      <div style="display:flex; flex-direction:column; gap:1rem;">
        ${data.history.map(h => `
          <div class="card" style="padding:1rem; cursor:pointer;" onclick="inspectCall('${h.call_id}', true)">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem;">
              <span style="font-family:var(--font-mono); font-weight:600; color:#a5b4fc;">${h.call_id}</span>
              <span class="score-pill ${h.attention_score >= 70 ? 'score-high' : h.attention_score >= 40 ? 'score-med' : 'score-low'}">Score: ${h.attention_score}</span>
            </div>
            <div style="font-size:0.85rem; margin-bottom:0.4rem;">${escapeHtml(h.intelligence.summary || h.intelligence.intent || '—')}</div>
            <div style="display:flex; justify-content:space-between; font-size:0.75rem; color:var(--text-dim);">
              <span>Agent: ${escapeHtml(h.agent_name)}</span>
              <span>Category: ${escapeHtml(h.category)}</span>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div class="empty-state">Error loading customer history: ${err.message}</div>`;
  }
}

// ----------------- Agent Scorecards Tab -----------------
async function loadAgents() {
  const container = document.getElementById('agentCardsContainer');
  try {
    const res = await fetch('/api/agents');
    if (!res.ok) throw new Error('Failed to load agents');
    const agents = await res.json();

    if (!agents || agents.length === 0) {
      container.innerHTML = `<div class="empty-state">No agent metrics available.</div>`;
      return;
    }

    container.innerHTML = agents.map(a => `
      <div class="agent-card">
        <div class="agent-name-row">
          <h3>${escapeHtml(a.agent_name)}</h3>
          <span class="badge-tag">Staff Member</span>
        </div>
        <div class="agent-stats-grid">
          <div class="agent-stat-box">
            <div class="agent-stat-title">Call Volume</div>
            <div class="agent-stat-val">${a.call_volume}</div>
          </div>
          <div class="agent-stat-box">
            <div class="agent-stat-title">Resolution Rate</div>
            <div class="agent-stat-val" style="color:var(--urgency-low);">${a.resolution_rate}%</div>
          </div>
          <div class="agent-stat-box">
            <div class="agent-stat-title">Avg Handle Time</div>
            <div class="agent-stat-val">${Math.round(a.avg_handle_time_sec)}s</div>
          </div>
          <div class="agent-stat-box">
            <div class="agent-stat-title">Avg Attention Risk</div>
            <div class="agent-stat-val ${a.avg_attention_score >= 60 ? 'text-danger' : ''}">${a.avg_attention_score}</div>
          </div>
        </div>
      </div>
    `).join('');
  } catch (err) {
    container.innerHTML = `<div class="empty-state">Error: ${err.message}</div>`;
  }
}

// ----------------- Trending Issues Tab -----------------
async function loadTrends() {
  const container = document.getElementById('trendsContainer');
  try {
    const res = await fetch('/api/dashboard/trending-issues');
    if (!res.ok) throw new Error('Failed to load trends');
    const trends = await res.json();

    if (!trends || trends.length === 0) {
      container.innerHTML = `<div class="empty-state">No trend data available.</div>`;
      return;
    }

    container.innerHTML = trends.map(t => `
      <div class="trend-row-card">
        <div class="trend-top">
          <div class="trend-title">${escapeHtml(t.category)}</div>
          <div style="font-weight:700; font-family:var(--font-display);">${t.count} calls (${t.percentage}%)</div>
        </div>
        <div class="trend-bar-wrapper">
          <div class="trend-bar-fill" style="width: ${Math.max(t.percentage, 5)}%;"></div>
        </div>
        <div class="trend-metrics">
          <span>Avg Attention Score: <strong>${t.avg_attention_score}/100</strong></span>
          <span>Resolution Rate: <strong>${t.resolution_rate}%</strong></span>
        </div>
      </div>
    `).join('');
  } catch (err) {
    container.innerHTML = `<div class="empty-state">Error: ${err.message}</div>`;
  }
}

// ----------------- Search & Filters -----------------
function initSearchAndFilters() {
  const search = document.getElementById('radarSearch');
  const catFilter = document.getElementById('radarCategoryFilter');

  function filterQueue() {
    const term = search.value.toLowerCase().trim();
    const cat = catFilter.value;

    const filtered = allRadarCalls.filter(c => {
      const matchesTerm = !term || 
        (c.customer && c.customer.toLowerCase().includes(term)) ||
        (c.agent && c.agent.toLowerCase().includes(term)) ||
        (c.call_id && c.call_id.toLowerCase().includes(term)) ||
        (c.summary && c.summary.toLowerCase().includes(term));

      const matchesCat = !cat || c.category === cat;
      return matchesTerm && matchesCat;
    });

    renderRadarTable(filtered);
  }

  search.addEventListener('input', filterQueue);
  catFilter.addEventListener('change', filterQueue);

  // Customer search
  const custSearch = document.getElementById('customerSearchInput');
  custSearch.addEventListener('input', () => {
    const term = custSearch.value.toLowerCase().trim();
    const filtered = allCustomers.filter(c => c.customer_name.toLowerCase().includes(term));
    renderCustomerList(filtered);
  });
}

// Helpers
function formatTime(seconds) {
  if (isNaN(seconds)) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
