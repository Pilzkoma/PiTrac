#!/usr/bin/env python3
"""
Jetson LM — Stats Dashboard
Project: Jetson LM (SP4)
Purpose: Local web dashboard showing shot history, club averages, and session data.
         Accessible from any device on the local WiFi network.

Usage:
    python3 dashboard.py                          # default: port 5000
    python3 dashboard.py --port 8080              # custom port
    python3 dashboard.py --db /path/to/jetson_lm.db

Then open http://<jetson-ip>:5000 on your phone, tablet, or laptop.

Requirements: Flask (pip install flask --break-system-packages)
"""

import argparse
import csv
import io
import os
import sys
from typing import Optional, List, Dict

# Check Flask availability early with helpful message
try:
    from flask import Flask, render_template_string, jsonify, request, Response
except ImportError:
    print("[Dashboard] Flask is not installed. Install it with:")
    print("  pip3 install flask")
    sys.exit(1)

from shot_db import ShotDB
from ball_physics import compute_flight

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__)
db = None  # initialized in main()

# ---------------------------------------------------------------------------
# HTML Template — single-page dashboard with tabs
# ---------------------------------------------------------------------------

DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Jetson LM — Stats</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=JetBrains+Mono:wght@400;500&display=swap');

  :root {
    --bg: #0c1117;
    --surface: #161b22;
    --surface2: #1c2333;
    --border: #2a3140;
    --text: #e6edf3;
    --text2: #8b949e;
    --green: #3fb950;
    --green-dim: #238636;
    --blue: #58a6ff;
    --orange: #d29922;
    --red: #f85149;
    --accent: #3fb950;
    --radius: 10px;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: 'DM Sans', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
  }

  /* Header */
  .header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 16px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 100;
  }
  .header h1 {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: -0.02em;
  }
  .header h1 span { color: var(--green); }
  .header .player-badge {
    font-size: 13px;
    color: var(--text2);
    background: var(--surface2);
    padding: 4px 12px;
    border-radius: 20px;
    border: 1px solid var(--border);
  }

  /* Tabs */
  .tabs {
    display: flex;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 0 16px;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  .tab {
    padding: 12px 20px;
    font-size: 14px;
    font-weight: 500;
    color: var(--text2);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    white-space: nowrap;
    transition: all 0.15s;
    user-select: none;
  }
  .tab:hover { color: var(--text); }
  .tab.active { color: var(--green); border-bottom-color: var(--green); }

  /* Content */
  .content { padding: 20px; max-width: 1100px; margin: 0 auto; }
  .panel { display: none; }
  .panel.active { display: block; }

  /* Stat cards */
  .stat-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px;
    margin-bottom: 24px;
  }
  .stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
  }
  .stat-card .label {
    font-size: 12px;
    color: var(--text2);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 4px;
  }
  .stat-card .value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 28px;
    font-weight: 700;
    color: var(--text);
  }
  .stat-card .unit {
    font-size: 14px;
    color: var(--text2);
    font-weight: 400;
  }

  /* Tables */
  .table-wrap {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow-x: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }
  th {
    text-align: left;
    padding: 10px 14px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text2);
    background: var(--surface2);
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
    position: sticky;
    top: 0;
  }
  td {
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    white-space: nowrap;
  }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: var(--surface2); }

  .club-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
  }
  .club-DR { background: #f8514922; color: var(--red); }
  .club-3W, .club-5W { background: #d2992222; color: var(--orange); }
  .club-default { background: #58a6ff22; color: var(--blue); }
  .club-PW, .club-GW, .club-SW, .club-LW { background: #3fb95022; color: var(--green); }
  .club-PT { background: #8b949e22; color: var(--text2); }

  /* Section headers */
  .section-title {
    font-size: 15px;
    font-weight: 700;
    margin-bottom: 12px;
    color: var(--text);
  }

  /* Session list */
  .session-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
    margin-bottom: 10px;
    cursor: pointer;
    transition: border-color 0.15s;
  }
  .session-card:hover { border-color: var(--green); }
  .session-card .meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  .session-card .meta .id { font-weight: 700; font-size: 15px; }
  .session-card .meta .date { font-size: 13px; color: var(--text2); }
  .session-card .stats {
    display: flex;
    gap: 20px;
    font-size: 13px;
    color: var(--text2);
  }
  .session-card .stats span strong { color: var(--text); }

  /* Chart container */
  .chart-container {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    margin-top: 16px;
    position: relative;
    height: 400px;
  }

  /* Empty state */
  .empty {
    text-align: center;
    padding: 60px 20px;
    color: var(--text2);
  }
  .empty .icon { font-size: 48px; margin-bottom: 12px; }
  .empty p { font-size: 15px; }

  /* Responsive */
  @media (max-width: 600px) {
    .stat-card .value { font-size: 22px; }
    .content { padding: 14px; }
    td, th { padding: 8px 10px; }
  }

  /* Back button */
  .back-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: var(--blue);
    font-size: 14px;
    cursor: pointer;
    margin-bottom: 16px;
    padding: 4px 0;
  }
  .back-btn:hover { text-decoration: underline; }

  /* Export button */
  .export-btn {
    font-family: 'DM Sans', sans-serif;
    font-size: 13px;
    color: var(--green);
    background: var(--surface);
    border: 1px solid var(--green-dim);
    border-radius: 6px;
    padding: 6px 14px;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .export-btn:hover { background: var(--green-dim); color: var(--text); }
</style>
</head>
<body>

<div class="header">
  <h1><span>&#9971;</span> Jetson <span>LM</span></h1>
  <select id="playerSelect" onchange="switchPlayer()" style="
    font-family: 'DM Sans', sans-serif;
    font-size: 13px;
    color: var(--text);
    background: var(--surface2);
    padding: 6px 12px;
    border-radius: 20px;
    border: 1px solid var(--border);
    cursor: pointer;
    outline: none;
  ">
    <option value="">Loading...</option>
  </select>
</div>

<div class="tabs">
  <div class="tab active" onclick="showTab('home')">Dashboard</div>
  <div class="tab" onclick="showTab('sessions')">Sessions</div>
  <div class="tab" onclick="showTab('clubs')">Club Averages</div>
  <div class="tab" onclick="showTab('dispersion')">Dispersion</div>
  <div class="tab" onclick="showTab('compare')">Compare</div>
</div>

<div class="content">

  <!-- HOME -->
  <div id="home" class="panel active">
    <div class="stat-grid" id="homeStats"></div>
    <div class="section-title">Latest Session</div>
    <div id="latestSession"></div>
  </div>

  <!-- SESSIONS -->
  <div id="sessions" class="panel">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
      <div class="section-title" style="margin-bottom:0">All Sessions</div>
      <button class="export-btn" onclick="exportCSV('all_shots')">&#11123; Export All Shots CSV</button>
    </div>
    <div id="sessionList"></div>
    <div id="sessionDetail" style="display:none"></div>
  </div>

  <!-- CLUBS -->
  <div id="clubs" class="panel">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
      <div class="section-title" style="margin-bottom:0">Club Averages</div>
      <button class="export-btn" onclick="exportCSV('club_averages')">&#11123; Export Club Averages CSV</button>
    </div>
    <div class="table-wrap" id="clubTable"></div>
  </div>

  <!-- DISPERSION -->
  <div id="dispersion" class="panel">
    <div class="section-title">Range View — Carry Distance vs Offline</div>
    <p style="font-size:13px; color:var(--text2); margin-bottom:12px;">Top-down view of the driving range. Center line = 0°. Carry estimated from ball speed, launch angle, and spin.</p>
    <div class="chart-container" style="height:500px;">
      <canvas id="rangeChart"></canvas>
    </div>
    <div class="section-title" style="margin-top:24px;">Shot Dispersion — HLA vs Ball Speed</div>
    <div class="chart-container">
      <canvas id="dispersionChart"></canvas>
    </div>
  </div>

  <!-- COMPARE -->
  <div id="compare" class="panel">
    <div class="section-title">Compare Sessions (up to 4)</div>
    <div style="display:flex; gap:10px; margin-bottom:20px; flex-wrap:wrap;" id="compareSelectors">
      <div style="flex:1; min-width:170px;" class="compare-slot" data-idx="0">
        <label style="font-size:12px; color:#58a6ff; text-transform:uppercase; letter-spacing:0.05em;">Session A</label>
        <select class="compare-select" onchange="loadComparison()" style="
          width:100%; margin-top:4px; font-family:'DM Sans',sans-serif; font-size:13px;
          color:var(--text); background:var(--surface); padding:8px 10px;
          border-radius:var(--radius); border:1px solid var(--border); cursor:pointer; outline:none;
        "><option value="">Select...</option></select>
      </div>
      <div style="flex:1; min-width:170px;" class="compare-slot" data-idx="1">
        <label style="font-size:12px; color:#d29922; text-transform:uppercase; letter-spacing:0.05em;">Session B</label>
        <select class="compare-select" onchange="loadComparison()" style="
          width:100%; margin-top:4px; font-family:'DM Sans',sans-serif; font-size:13px;
          color:var(--text); background:var(--surface); padding:8px 10px;
          border-radius:var(--radius); border:1px solid var(--border); cursor:pointer; outline:none;
        "><option value="">Select...</option></select>
      </div>
      <div style="flex:1; min-width:170px;" class="compare-slot" data-idx="2">
        <label style="font-size:12px; color:#3fb950; text-transform:uppercase; letter-spacing:0.05em;">Session C</label>
        <select class="compare-select" onchange="loadComparison()" style="
          width:100%; margin-top:4px; font-family:'DM Sans',sans-serif; font-size:13px;
          color:var(--text); background:var(--surface); padding:8px 10px;
          border-radius:var(--radius); border:1px solid var(--border); cursor:pointer; outline:none;
        "><option value="">Select...</option></select>
      </div>
      <div style="flex:1; min-width:170px;" class="compare-slot" data-idx="3">
        <label style="font-size:12px; color:#f85149; text-transform:uppercase; letter-spacing:0.05em;">Session D</label>
        <select class="compare-select" onchange="loadComparison()" style="
          width:100%; margin-top:4px; font-family:'DM Sans',sans-serif; font-size:13px;
          color:var(--text); background:var(--surface); padding:8px 10px;
          border-radius:var(--radius); border:1px solid var(--border); cursor:pointer; outline:none;
        "><option value="">Select...</option></select>
      </div>
    </div>
    <div id="compareResult"></div>
  </div>

</div>

<script>
const API = '';
let dispChart = null;
let currentPlayerId = null;

function clubClass(club) {
  if (!club) return 'club-default';
  if (['DR'].includes(club)) return 'club-DR';
  if (['3W','5W'].includes(club)) return 'club-3W';
  if (['PW','GW','SW','LW'].includes(club)) return 'club-PW';
  if (['PT'].includes(club)) return 'club-PT';
  return 'club-default';
}

function clubBadge(club) {
  return `<span class="club-badge ${clubClass(club)}">${club || '—'}</span>`;
}

function fmt(v, dec=1) {
  return v != null ? Number(v).toFixed(dec) : '—';
}

function pq() {
  return currentPlayerId ? `?player_id=${currentPlayerId}` : '';
}

// Player dropdown
async function loadPlayers() {
  const players = await fetch(API + '/api/players').then(r => r.json());
  const sel = document.getElementById('playerSelect');
  sel.innerHTML = '<option value="">All Players</option>';
  players.forEach(p => {
    sel.innerHTML += `<option value="${p.id}">${p.name} (${p.handedness})</option>`;
  });
  if (players.length === 1) {
    sel.value = players[0].id;
    currentPlayerId = players[0].id;
  }
}

function switchPlayer() {
  const sel = document.getElementById('playerSelect');
  currentPlayerId = sel.value ? parseInt(sel.value) : null;
  loadHome();
  const activeTab = document.querySelector('.tab.active');
  if (activeTab) {
    const tabId = ['home','sessions','clubs','dispersion'][
      Array.from(document.querySelectorAll('.tab')).indexOf(activeTab)
    ];
    if (tabId === 'sessions') loadSessions();
    if (tabId === 'clubs') loadClubs();
    if (tabId === 'dispersion') loadDispersion();
  }
}

// Tab switching
function showTab(id) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  const tabIds = ['home','sessions','clubs','dispersion','compare'];
  document.querySelectorAll('.tab')[tabIds.indexOf(id)].classList.add('active');

  if (id === 'sessions') { loadSessions(); document.getElementById('sessionDetail').style.display='none'; document.getElementById('sessionList').style.display='block'; }
  if (id === 'clubs') loadClubs();
  if (id === 'dispersion') loadDispersion();
  if (id === 'compare') loadCompareSelectors();
}

// HOME
async function loadHome() {
  const data = await fetch(API + '/api/home' + pq()).then(r => r.json());

  const sg = document.getElementById('homeStats');
  sg.innerHTML = `
    <div class="stat-card"><div class="label">Total Shots</div><div class="value">${data.total_shots}</div></div>
    <div class="stat-card"><div class="label">Sessions</div><div class="value">${data.total_sessions}</div></div>
    <div class="stat-card"><div class="label">Avg Ball Speed</div><div class="value">${fmt(data.avg_speed)} <span class="unit">mph</span></div></div>
    <div class="stat-card"><div class="label">Clubs Used</div><div class="value">${data.clubs_used}</div></div>
  `;

  const ls = document.getElementById('latestSession');
  if (data.latest_session) {
    const s = data.latest_session;
    ls.innerHTML = `
      <div class="session-card" onclick="loadSessionDetail(${s.id})">
        <div class="meta">
          <span class="id">Session #${s.id}</span>
          <span class="date">${s.started_at || ''}</span>
        </div>
        <div class="stats">
          <span><strong>${s.shot_count}</strong> shots</span>
          <span>Avg <strong>${fmt(s.avg_speed)}</strong> mph</span>
          <span>${s.target || ''}</span>
        </div>
      </div>`;
  } else {
    ls.innerHTML = '<div class="empty"><div class="icon">&#9971;</div><p>No sessions yet. Send some shots!</p></div>';
  }
}

// SESSIONS
async function loadSessions() {
  const sessions = await fetch(API + '/api/sessions' + pq()).then(r => r.json());
  const el = document.getElementById('sessionList');
  if (!sessions.length) { el.innerHTML = '<div class="empty"><div class="icon">&#128203;</div><p>No sessions yet.</p></div>'; return; }
  el.innerHTML = sessions.map(s => {
    const date = (s.started_at || '').slice(0, 10).split('-').reverse().join('.');
    const time = (s.started_at || '').slice(11, 16);
    const title = `${date} — ${time} — ${s.player || '?'} #${s.daily_num || s.id}`;
    return `
    <div class="session-card" onclick="loadSessionDetail(${s.id})">
      <div class="meta">
        <span class="id">${title}</span>
      </div>
      <div class="stats">
        <span><strong>${s.shot_count}</strong> shots</span>
        <span>Avg <strong>${fmt(s.avg_speed)}</strong> mph</span>
      </div>
    </div>`;
  }).join('');
}

async function loadSessionDetail(sessionId) {
  const shots = await fetch(API + `/api/sessions/${sessionId}/shots`).then(r => r.json());
  document.getElementById('sessionList').style.display = 'none';
  const el = document.getElementById('sessionDetail');
  el.style.display = 'block';

  let html = `<div style="display:flex; justify-content:space-between; align-items:center;">
    <div class="back-btn" onclick="document.getElementById('sessionList').style.display='block'; document.getElementById('sessionDetail').style.display='none';">&#8592; Back to sessions</div>
    <button class="export-btn" onclick="exportCSV(null, ${sessionId})">&#11123; Export Session CSV</button>
  </div>`;
  html += `<div class="section-title">Session #${sessionId} — ${shots.length} shots</div>`;
  html += `<div class="table-wrap"><table>
    <tr><th>#</th><th>Club</th><th>Speed</th><th>VLA</th><th>HLA</th><th>Spin</th><th>Spin Axis</th><th>Carry</th></tr>`;
  shots.forEach(s => {
    html += `<tr>
      <td>${s.shot_number}</td>
      <td>${clubBadge(s.club)}</td>
      <td>${fmt(s.ball_speed)}</td>
      <td>${fmt(s.vla)}°</td>
      <td>${fmt(s.hla)}°</td>
      <td>${fmt(s.total_spin, 0)}</td>
      <td>${fmt(s.spin_axis)}°</td>
      <td>${s.carry_distance ? fmt(s.carry_distance) + ' yd' : '—'}</td>
    </tr>`;
  });
  html += '</table></div>';
  el.innerHTML = html;
}

// CLUBS
async function loadClubs() {
  const clubs = await fetch(API + '/api/clubs' + pq()).then(r => r.json());
  const el = document.getElementById('clubTable');
  if (!clubs.length) { el.innerHTML = '<div class="empty" style="padding:40px"><p>No shot data yet.</p></div>'; return; }
  let html = `<table>
    <tr><th>Club</th><th>Shots</th><th>Avg Speed</th><th>Avg VLA</th><th>Avg HLA</th><th>Avg Spin</th><th>Avg Carry</th></tr>`;
  clubs.forEach(c => {
    html += `<tr>
      <td>${clubBadge(c.club)}</td>
      <td>${c.shot_count}</td>
      <td>${fmt(c.avg_ball_speed)} mph</td>
      <td>${fmt(c.avg_vla)}°</td>
      <td>${fmt(c.avg_hla)}°</td>
      <td>${fmt(c.avg_total_spin, 0)} rpm</td>
      <td>${c.avg_carry ? fmt(c.avg_carry) + ' yd' : '—'}</td>
    </tr>`;
  });
  html += '</table>';
  el.innerHTML = html;
}

// DISPERSION
let rangeChart = null;

async function loadDispersion() {
  const shots = await fetch(API + '/api/dispersion' + pq()).then(r => r.json());

  // --- Range View (top-down) — uses physics-calculated carry and offline ---
  if (rangeChart) rangeChart.destroy();
  const rangeCtx = document.getElementById('rangeChart').getContext('2d');

  const clubColors = {
    'DR': '#f85149', '3W': '#d29922', '5W': '#d29922',
    'PW': '#3fb950', 'GW': '#3fb950', 'SW': '#3fb950', 'LW': '#3fb950',
    'PT': '#8b949e'
  };
  const defaultColor = '#58a6ff';

  const rangeDatasets = {};
  let maxCarry = 0;
  shots.forEach(s => {
    const club = s.club || 'Unknown';
    const carry = s.calc_carry || 0;
    const offline = s.calc_offline || 0;
    if (!carry) return;
    maxCarry = Math.max(maxCarry, carry);

    if (!rangeDatasets[club]) {
      rangeDatasets[club] = {
        label: club,
        data: [],
        backgroundColor: (clubColors[club] || defaultColor) + '99',
        borderColor: clubColors[club] || defaultColor,
        borderWidth: 1.5,
        pointRadius: 7,
        pointHoverRadius: 10,
      };
    }
    rangeDatasets[club].data.push({ x: offline, y: carry });
  });

  const rangeMax = Math.ceil((maxCarry + 20) / 50) * 50;
  const offlineMax = Math.max(40, Math.ceil(rangeMax * 0.15 / 10) * 10);

  rangeChart = new Chart(rangeCtx, {
    type: 'scatter',
    data: { datasets: Object.values(rangeDatasets) },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#8b949e', font: { family: 'DM Sans' } } },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              const off = ctx.parsed.x;
              const dir = off >= 0 ? off + 'R' : Math.abs(off) + 'L';
              return `${ctx.dataset.label}: ${ctx.parsed.y} yds carry, ${dir} offline`;
            }
          }
        },
        // Center line annotation via plugin
        annotation: undefined,
      },
      scales: {
        x: {
          title: { display: true, text: '← Left    Offline (yards)    Right →', color: '#8b949e' },
          min: -offlineMax,
          max: offlineMax,
          grid: { color: function(ctx) { return ctx.tick.value === 0 ? '#3fb95066' : '#2a3140'; },
                  lineWidth: function(ctx) { return ctx.tick.value === 0 ? 2 : 1; } },
          ticks: { color: '#8b949e', callback: function(v) { return v === 0 ? '0' : (v > 0 ? v + 'R' : Math.abs(v) + 'L'); } }
        },
        y: {
          title: { display: true, text: 'Carry Distance (yards)', color: '#8b949e' },
          min: 0,
          max: rangeMax,
          grid: { color: '#2a3140' },
          ticks: { color: '#8b949e' }
        }
      }
    }
  });

  // --- HLA vs Ball Speed chart ---
  if (dispChart) dispChart.destroy();
  const ctx = document.getElementById('dispersionChart').getContext('2d');

  const datasets = {};
  shots.forEach(s => {
    const club = s.club || 'Unknown';
    if (!datasets[club]) {
      datasets[club] = {
        label: club,
        data: [],
        backgroundColor: (clubColors[club] || defaultColor) + '88',
        borderColor: clubColors[club] || defaultColor,
        borderWidth: 1,
        pointRadius: 6,
        pointHoverRadius: 9,
      };
    }
    datasets[club].data.push({ x: s.hla || 0, y: s.ball_speed || 0 });
  });

  dispChart = new Chart(ctx, {
    type: 'scatter',
    data: { datasets: Object.values(datasets) },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#8b949e', font: { family: 'DM Sans' } } },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              return `${ctx.dataset.label}: HLA ${ctx.parsed.x.toFixed(1)}°, Speed ${ctx.parsed.y.toFixed(1)} mph`;
            }
          }
        }
      },
      scales: {
        x: {
          title: { display: true, text: 'HLA (degrees)', color: '#8b949e' },
          grid: { color: '#2a3140' },
          ticks: { color: '#8b949e' }
        },
        y: {
          title: { display: true, text: 'Ball Speed (mph)', color: '#8b949e' },
          grid: { color: '#2a3140' },
          ticks: { color: '#8b949e' }
        }
      }
    }
  });
}

// COMPARE
let compareChart = null;
let compareRangeChart = null;
const COMPARE_COLORS = ['#58a6ff', '#d29922', '#3fb950', '#f85149'];
const COMPARE_LABELS = ['A', 'B', 'C', 'D'];

function sessionLabel(s) {
  // Format: "21.03.2026 — 19:32 — Max #2 (6 shots)"
  const date = (s.started_at || '').slice(0, 10).split('-').reverse().join('.');
  const time = (s.started_at || '').slice(11, 16);
  return `${date} — ${time} — ${s.player || '?'} #${s.daily_num || s.id} (${s.shot_count} shots)`;
}

function sessionShortLabel(s, idx) {
  const date = (s.started_at || '').slice(0, 10).split('-').reverse().join('.');
  return `${COMPARE_LABELS[idx]}: ${s.player || '?'} #${s.daily_num || s.id} ${date}`;
}

async function loadCompareSelectors() {
  const sessions = await fetch(API + '/api/sessions' + pq()).then(r => r.json());
  const validSessions = sessions.filter(s => s.shot_count > 0);

  document.querySelectorAll('.compare-select').forEach(sel => {
    const current = sel.value;
    sel.innerHTML = '<option value="">Select...</option>';
    validSessions.forEach(s => {
      sel.innerHTML += `<option value="${s.id}" data-session='${JSON.stringify(s)}'>${sessionLabel(s)}</option>`;
    });
    sel.value = current;
  });
}

async function loadComparison() {
  const selects = document.querySelectorAll('.compare-select');
  const selected = [];
  selects.forEach((sel, idx) => {
    if (sel.value) {
      const opt = sel.selectedOptions[0];
      let sData = {};
      try { sData = JSON.parse(opt.dataset.session || '{}'); } catch(e) {}
      selected.push({ id: parseInt(sel.value), idx: idx, session: sData });
    }
  });

  const el = document.getElementById('compareResult');

  if (selected.length < 2) {
    el.innerHTML = '<div class="empty"><p>Select at least 2 sessions to compare.</p></div>';
    return;
  }

  // Check for duplicates
  const ids = selected.map(s => s.id);
  if (new Set(ids).size !== ids.length) {
    el.innerHTML = '<div class="empty"><p>Select different sessions.</p></div>';
    return;
  }

  // Fetch shots and physics for all selected sessions
  const [allShots, allPhysics] = await Promise.all([
    Promise.all(selected.map(s => fetch(API + `/api/sessions/${s.id}/shots`).then(r => r.json()))),
    Promise.all(selected.map(s => fetch(API + `/api/sessions/${s.id}/physics`).then(r => r.json()))),
  ]);

  const allStats = allShots.map(shots => calcStats(shots));

  // Stat cards — show each session's values
  let html = '<div class="stat-grid" style="grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));">';
  const metrics = [
    ['Shots', 'count', '', 0],
    ['Avg Speed', 'avg_speed', ' mph', 1],
    ['Avg VLA', 'avg_vla', '°', 1],
    ['Avg HLA', 'avg_hla', '°', 1],
    ['Avg Spin', 'avg_spin', ' rpm', 0],
  ];
  metrics.forEach(([label, key, unit, dec]) => {
    html += `<div class="stat-card"><div class="label">${label}</div><div style="display:flex; flex-wrap:wrap; gap:8px;">`;
    selected.forEach((s, i) => {
      const val = allStats[i][key];
      html += `<div>
        <span style="font-size:11px; color:${COMPARE_COLORS[s.idx]};">${COMPARE_LABELS[s.idx]}</span>
        <span style="font-family:'JetBrains Mono',monospace; font-size:18px; font-weight:700;">${val != null ? val.toFixed(dec) : '—'}${unit}</span>
      </div>`;
    });
    html += '</div></div>';
  });
  html += '</div>';

  // Charts
  html += '<div class="chart-container" style="margin-top:20px;"><canvas id="compareChart"></canvas></div>';
  html += '<div class="chart-container" style="margin-top:20px; height:500px;"><canvas id="compareRangeChart"></canvas></div>';
  el.innerHTML = html;

  // HLA vs Ball Speed chart
  if (compareChart) compareChart.destroy();
  const ctx = document.getElementById('compareChart').getContext('2d');
  compareChart = new Chart(ctx, {
    type: 'scatter',
    data: {
      datasets: selected.map((s, i) => ({
        label: sessionShortLabel(s.session, s.idx),
        data: allShots[i].filter(sh => sh.ball_speed).map(sh => ({x: sh.hla || 0, y: sh.ball_speed})),
        backgroundColor: COMPARE_COLORS[s.idx] + '88',
        borderColor: COMPARE_COLORS[s.idx],
        borderWidth: 1, pointRadius: 6, pointHoverRadius: 9,
      }))
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#8b949e', font: { family: 'DM Sans' } } },
        title: { display: true, text: 'HLA vs Ball Speed', color: '#8b949e' },
      },
      scales: {
        x: { title: { display: true, text: 'HLA (degrees)', color: '#8b949e' }, grid: { color: '#2a3140' }, ticks: { color: '#8b949e' } },
        y: { title: { display: true, text: 'Ball Speed (mph)', color: '#8b949e' }, grid: { color: '#2a3140' }, ticks: { color: '#8b949e' } },
      }
    }
  });

  // Range View chart
  if (compareRangeChart) compareRangeChart.destroy();
  const rangeCtx = document.getElementById('compareRangeChart').getContext('2d');

  let maxCarry = 0;
  allPhysics.flat().forEach(s => { if (s.calc_carry > maxCarry) maxCarry = s.calc_carry; });
  const rangeMax = Math.ceil((maxCarry + 20) / 50) * 50;
  const offMax = Math.max(40, Math.ceil(rangeMax * 0.15 / 10) * 10);

  compareRangeChart = new Chart(rangeCtx, {
    type: 'scatter',
    data: {
      datasets: selected.map((s, i) => ({
        label: sessionShortLabel(s.session, s.idx),
        data: allPhysics[i].filter(sh => sh.calc_carry).map(sh => ({x: sh.calc_offline || 0, y: sh.calc_carry})),
        backgroundColor: COMPARE_COLORS[s.idx] + '99',
        borderColor: COMPARE_COLORS[s.idx],
        borderWidth: 1.5, pointRadius: 7, pointHoverRadius: 10,
      }))
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#8b949e', font: { family: 'DM Sans' } } },
        title: { display: true, text: 'Range View — Carry vs Offline', color: '#8b949e' },
        tooltip: {
          callbacks: {
            label: function(ctx) {
              const off = ctx.parsed.x;
              const dir = off >= 0 ? off + 'R' : Math.abs(off) + 'L';
              return `${ctx.dataset.label}: ${ctx.parsed.y} yds, ${dir} offline`;
            }
          }
        },
      },
      scales: {
        x: {
          title: { display: true, text: '← Left    Offline (yards)    Right →', color: '#8b949e' },
          min: -offMax, max: offMax,
          grid: { color: function(ctx) { return ctx.tick.value === 0 ? '#3fb95066' : '#2a3140'; },
                  lineWidth: function(ctx) { return ctx.tick.value === 0 ? 2 : 1; } },
          ticks: { color: '#8b949e', callback: function(v) { return v === 0 ? '0' : (v > 0 ? v + 'R' : Math.abs(v) + 'L'); } }
        },
        y: {
          title: { display: true, text: 'Carry Distance (yards)', color: '#8b949e' },
          min: 0, max: rangeMax,
          grid: { color: '#2a3140' }, ticks: { color: '#8b949e' }
        }
      }
    }
  });
}

function calcStats(shots) {
  const valid = shots.filter(s => s.response_code === 200 || s.response_code === null);
  const speeds = valid.map(s => s.ball_speed).filter(v => v != null);
  const vlas = valid.map(s => s.vla).filter(v => v != null);
  const hlas = valid.map(s => s.hla).filter(v => v != null);
  const spins = valid.map(s => s.total_spin).filter(v => v != null);
  const avg = arr => arr.length ? arr.reduce((a,b) => a+b, 0) / arr.length : null;

  // Per-club breakdown
  const clubs = {};
  valid.forEach(s => {
    if (!s.club) return;
    if (!clubs[s.club]) clubs[s.club] = { speeds: [], vlas: [], count: 0 };
    clubs[s.club].count++;
    if (s.ball_speed != null) clubs[s.club].speeds.push(s.ball_speed);
    if (s.vla != null) clubs[s.club].vlas.push(s.vla);
  });
  const clubStats = {};
  Object.entries(clubs).forEach(([club, d]) => {
    clubStats[club] = {
      count: d.count,
      avg_speed: avg(d.speeds),
      avg_vla: avg(d.vlas),
    };
  });

  return {
    count: valid.length,
    avg_speed: avg(speeds),
    avg_vla: avg(vlas),
    avg_hla: avg(hlas),
    avg_spin: avg(spins),
    clubs: clubStats,
  };
}

// CSV Export
function exportCSV(type, sessionId) {
  let url = API + '/api/export/' + type + pq();
  if (sessionId) url = API + '/api/export/session/' + sessionId;
  window.open(url, '_blank');
}

// Auto-refresh — polls every 5 seconds and refreshes the active tab
let autoRefreshInterval = null;
let lastShotCount = 0;

function getActiveTab() {
  const tabs = ['home','sessions','clubs','dispersion','compare'];
  const active = document.querySelector('.panel.active');
  if (active) return active.id;
  return 'home';
}

async function autoRefresh() {
  try {
    // Quick check if shot count changed
    const data = await fetch(API + '/api/home' + pq()).then(r => r.json());
    const newCount = data.total_shots || 0;
    if (newCount === lastShotCount) return; // nothing changed
    lastShotCount = newCount;

    // Refresh the active tab
    const tab = getActiveTab();
    if (tab === 'home') loadHome();
    else if (tab === 'sessions') loadSessions();
    else if (tab === 'clubs') loadClubs();
    else if (tab === 'dispersion') loadDispersion();
    // compare: don't auto-refresh (user has selected sessions manually)
  } catch(e) {
    // silently ignore fetch errors during auto-refresh
  }
}

function startAutoRefresh() {
  if (autoRefreshInterval) clearInterval(autoRefreshInterval);
  autoRefreshInterval = setInterval(autoRefresh, 5000);
}

// Init
async function init() {
  await loadPlayers();
  await loadHome();
  lastShotCount = 0; // force first refresh
  startAutoRefresh();
}
init();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)


@app.route("/api/players")
def api_players():
    """List all players."""
    rows = db.conn.execute("SELECT id, name, handedness FROM players ORDER BY name").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/home")
def api_home():
    """Dashboard home — summary stats, optionally filtered by player."""
    pid = request.args.get("player_id", type=int)

    if pid:
        row = db.conn.execute("""
            SELECT COUNT(*) as total_shots, ROUND(AVG(ball_speed), 1) as avg_speed,
                   COUNT(DISTINCT club) as clubs_used
            FROM shots s JOIN sessions sess ON s.session_id = sess.id
            WHERE s.(response_code IS NULL OR response_code = 200) AND sess.player_id = ?
        """, (pid,)).fetchone()
        session_count = db.conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE player_id = ?", (pid,)
        ).fetchone()[0]
        latest = db.conn.execute("""
            SELECT s.id, s.started_at, s.target, c.name as course,
                (SELECT COUNT(*) FROM shots WHERE session_id = s.id AND (response_code IS NULL OR response_code = 200)) as shot_count,
                (SELECT ROUND(AVG(ball_speed), 1) FROM shots WHERE session_id = s.id AND (response_code IS NULL OR response_code = 200)) as avg_speed
            FROM sessions s LEFT JOIN courses c ON s.course_id = c.id
            WHERE s.player_id = ? ORDER BY s.started_at DESC LIMIT 1
        """, (pid,)).fetchone()
    else:
        row = db.conn.execute("""
            SELECT COUNT(*) as total_shots, ROUND(AVG(ball_speed), 1) as avg_speed,
                   COUNT(DISTINCT club) as clubs_used
            FROM shots WHERE (response_code IS NULL OR response_code = 200)
        """).fetchone()
        session_count = db.conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        latest = db.conn.execute("""
            SELECT s.id, s.started_at, s.target, c.name as course,
                (SELECT COUNT(*) FROM shots WHERE session_id = s.id AND (response_code IS NULL OR response_code = 200)) as shot_count,
                (SELECT ROUND(AVG(ball_speed), 1) FROM shots WHERE session_id = s.id AND (response_code IS NULL OR response_code = 200)) as avg_speed
            FROM sessions s LEFT JOIN courses c ON s.course_id = c.id
            ORDER BY s.started_at DESC LIMIT 1
        """).fetchone()

    return jsonify({
        "total_shots": row["total_shots"] if row else 0,
        "avg_speed": row["avg_speed"] if row else None,
        "clubs_used": row["clubs_used"] if row else 0,
        "total_sessions": session_count,
        "latest_session": dict(latest) if latest else None,
    })


@app.route("/api/sessions")
def api_sessions():
    """List all sessions with player name and daily numbering."""
    pid = request.args.get("player_id", type=int)

    if pid:
        rows = db.conn.execute("""
            SELECT s.id, s.started_at, s.ended_at, s.target, p.name as player,
                (SELECT COUNT(*) FROM shots WHERE session_id = s.id AND (response_code IS NULL OR response_code = 200)) as shot_count,
                (SELECT ROUND(AVG(ball_speed), 1) FROM shots WHERE session_id = s.id AND (response_code IS NULL OR response_code = 200)) as avg_speed
            FROM sessions s
            JOIN players p ON s.player_id = p.id
            WHERE s.player_id = ? ORDER BY s.started_at DESC
        """, (pid,)).fetchall()
    else:
        rows = db.conn.execute("""
            SELECT s.id, s.started_at, s.ended_at, s.target, p.name as player,
                (SELECT COUNT(*) FROM shots WHERE session_id = s.id AND (response_code IS NULL OR response_code = 200)) as shot_count,
                (SELECT ROUND(AVG(ball_speed), 1) FROM shots WHERE session_id = s.id AND (response_code IS NULL OR response_code = 200)) as avg_speed
            FROM sessions s
            JOIN players p ON s.player_id = p.id
            ORDER BY s.started_at DESC
        """).fetchall()

    # Add daily session number
    results = []
    daily_counts = {}  # "YYYY-MM-DD_playerName" -> count
    # Process in chronological order to assign daily numbers
    sorted_rows = sorted([dict(r) for r in rows], key=lambda x: x["started_at"] or "")
    for r in sorted_rows:
        date_str = (r["started_at"] or "")[:10]
        key = f"{date_str}_{r['player']}"
        daily_counts[key] = daily_counts.get(key, 0) + 1
        r["daily_num"] = daily_counts[key]

    # Return in descending order (newest first)
    results = sorted(sorted_rows, key=lambda x: x["started_at"] or "", reverse=True)
    return jsonify(results)


@app.route("/api/sessions/<int:session_id>/shots")
def api_session_shots(session_id):
    """All shots for a specific session."""
    rows = db.conn.execute("""
        SELECT shot_number, club, ball_speed, vla, hla, total_spin,
               spin_axis, back_spin, side_spin, carry_distance,
               club_speed, response_code, timestamp
        FROM shots WHERE session_id = ? ORDER BY shot_number
    """, (session_id,)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/sessions/<int:session_id>/physics")
def api_session_physics(session_id):
    """Session shots with physics-calculated carry and offline."""
    rows = db.conn.execute("""
        SELECT shot_number, club, ball_speed, vla, hla, total_spin, spin_axis,
               carry_distance, response_code
        FROM shots WHERE session_id = ? AND ball_speed IS NOT NULL
        ORDER BY shot_number
    """, (session_id,)).fetchall()

    results = []
    for row in rows:
        r = dict(row)
        flight = compute_flight(
            ball_speed_mph=r.get("ball_speed") or 0,
            vla_deg=r.get("vla") or 0,
            hla_deg=r.get("hla") or 0,
            total_spin_rpm=r.get("total_spin") or 3000,
            spin_axis_deg=r.get("spin_axis") or 0,
        )
        r["calc_carry"] = flight["carry_yards"]
        r["calc_offline"] = flight["offline_yards"]
        results.append(r)
    return jsonify(results)


@app.route("/api/clubs")
def api_clubs():
    """Per-club averages, optionally filtered by player."""
    pid = request.args.get("player_id", type=int)

    if pid:
        rows = db.conn.execute("""
            SELECT s.club, COUNT(*) as shot_count,
                ROUND(AVG(s.ball_speed), 1) as avg_ball_speed,
                ROUND(AVG(s.vla), 1) as avg_vla,
                ROUND(AVG(s.hla), 1) as avg_hla,
                ROUND(AVG(s.total_spin), 0) as avg_total_spin,
                ROUND(AVG(s.carry_distance), 1) as avg_carry
            FROM shots s JOIN sessions sess ON s.session_id = sess.id
            WHERE s.(response_code IS NULL OR response_code = 200) AND s.club IS NOT NULL AND sess.player_id = ?
            GROUP BY s.club ORDER BY AVG(s.ball_speed) DESC
        """, (pid,)).fetchall()
    else:
        rows = db.conn.execute("""
            SELECT club, COUNT(*) as shot_count,
                ROUND(AVG(ball_speed), 1) as avg_ball_speed,
                ROUND(AVG(vla), 1) as avg_vla,
                ROUND(AVG(hla), 1) as avg_hla,
                ROUND(AVG(total_spin), 0) as avg_total_spin,
                ROUND(AVG(carry_distance), 1) as avg_carry
            FROM shots WHERE (response_code IS NULL OR response_code = 200) AND club IS NOT NULL
            GROUP BY club ORDER BY AVG(ball_speed) DESC
        """).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/dispersion")
def api_dispersion():
    """All shots with physics-calculated carry distance and offline."""
    pid = request.args.get("player_id", type=int)

    if pid:
        rows = db.conn.execute("""
            SELECT s.club, s.ball_speed, s.hla, s.vla, s.carry_distance,
                   s.total_spin, s.spin_axis
            FROM shots s JOIN sessions sess ON s.session_id = sess.id
            WHERE s.(response_code IS NULL OR response_code = 200) AND s.ball_speed IS NOT NULL AND sess.player_id = ?
            ORDER BY s.timestamp
        """, (pid,)).fetchall()
    else:
        rows = db.conn.execute("""
            SELECT club, ball_speed, hla, vla, carry_distance, total_spin, spin_axis
            FROM shots WHERE (response_code IS NULL OR response_code = 200) AND ball_speed IS NOT NULL
            ORDER BY timestamp
        """).fetchall()

    results = []
    for row in rows:
        r = dict(row)
        # Use physics engine to calculate carry and offline
        flight = compute_flight(
            ball_speed_mph=r.get("ball_speed") or 0,
            vla_deg=r.get("vla") or 0,
            hla_deg=r.get("hla") or 0,
            total_spin_rpm=r.get("total_spin") or 3000,
            spin_axis_deg=r.get("spin_axis") or 0,
        )
        r["calc_carry"] = flight["carry_yards"]
        r["calc_offline"] = flight["offline_yards"]
        r["calc_apex"] = flight["apex_feet"]
        results.append(r)

    return jsonify(results)


@app.route("/api/export/all_shots")
def export_all_shots():
    """Export all shots as CSV, optionally filtered by player."""
    pid = request.args.get("player_id", type=int)

    if pid:
        rows = db.conn.execute("""
            SELECT s.shot_number, s.club, s.timestamp, s.ball_speed, s.vla, s.hla,
                   s.total_spin, s.back_spin, s.side_spin, s.spin_axis,
                   s.carry_distance, s.club_speed, s.angle_of_attack,
                   s.face_to_target, s.path, s.response_code,
                   sess.id as session_id, p.name as player
            FROM shots s
            JOIN sessions sess ON s.session_id = sess.id
            JOIN players p ON sess.player_id = p.id
            WHERE s.(response_code IS NULL OR response_code = 200) AND sess.player_id = ?
            ORDER BY s.timestamp
        """, (pid,)).fetchall()
    else:
        rows = db.conn.execute("""
            SELECT s.shot_number, s.club, s.timestamp, s.ball_speed, s.vla, s.hla,
                   s.total_spin, s.back_spin, s.side_spin, s.spin_axis,
                   s.carry_distance, s.club_speed, s.angle_of_attack,
                   s.face_to_target, s.path, s.response_code,
                   sess.id as session_id, p.name as player
            FROM shots s
            JOIN sessions sess ON s.session_id = sess.id
            JOIN players p ON sess.player_id = p.id
            WHERE s.(response_code IS NULL OR response_code = 200)
            ORDER BY s.timestamp
        """).fetchall()

    return _rows_to_csv(rows, "jetson_lm_all_shots.csv")


@app.route("/api/export/session/<int:session_id>")
def export_session(session_id):
    """Export a single session's shots as CSV."""
    rows = db.conn.execute("""
        SELECT s.shot_number, s.club, s.timestamp, s.ball_speed, s.vla, s.hla,
               s.total_spin, s.back_spin, s.side_spin, s.spin_axis,
               s.carry_distance, s.club_speed, s.angle_of_attack,
               s.face_to_target, s.path, s.response_code
        FROM shots s WHERE s.session_id = ? ORDER BY s.shot_number
    """, (session_id,)).fetchall()

    return _rows_to_csv(rows, f"jetson_lm_session_{session_id}.csv")


@app.route("/api/export/club_averages")
def export_club_averages():
    """Export club averages as CSV, optionally filtered by player."""
    pid = request.args.get("player_id", type=int)

    if pid:
        rows = db.conn.execute("""
            SELECT s.club, COUNT(*) as shot_count,
                ROUND(AVG(s.ball_speed), 1) as avg_ball_speed,
                ROUND(AVG(s.vla), 1) as avg_vla,
                ROUND(AVG(s.hla), 1) as avg_hla,
                ROUND(AVG(s.total_spin), 0) as avg_total_spin,
                ROUND(AVG(s.spin_axis), 1) as avg_spin_axis,
                ROUND(AVG(s.carry_distance), 1) as avg_carry,
                ROUND(MIN(s.ball_speed), 1) as min_speed,
                ROUND(MAX(s.ball_speed), 1) as max_speed
            FROM shots s JOIN sessions sess ON s.session_id = sess.id
            WHERE s.(response_code IS NULL OR response_code = 200) AND s.club IS NOT NULL AND sess.player_id = ?
            GROUP BY s.club ORDER BY AVG(s.ball_speed) DESC
        """, (pid,)).fetchall()
    else:
        rows = db.conn.execute("""
            SELECT club, COUNT(*) as shot_count,
                ROUND(AVG(ball_speed), 1) as avg_ball_speed,
                ROUND(AVG(vla), 1) as avg_vla,
                ROUND(AVG(hla), 1) as avg_hla,
                ROUND(AVG(total_spin), 0) as avg_total_spin,
                ROUND(AVG(spin_axis), 1) as avg_spin_axis,
                ROUND(AVG(carry_distance), 1) as avg_carry,
                ROUND(MIN(ball_speed), 1) as min_speed,
                ROUND(MAX(ball_speed), 1) as max_speed
            FROM shots WHERE (response_code IS NULL OR response_code = 200) AND club IS NOT NULL
            GROUP BY club ORDER BY AVG(ball_speed) DESC
        """).fetchall()

    return _rows_to_csv(rows, "jetson_lm_club_averages.csv")


def _rows_to_csv(rows, filename: str) -> Response:
    """Convert SQLite rows to a downloadable CSV response."""
    if not rows:
        return Response("No data", mimetype="text/plain")

    output = io.StringIO()
    writer = csv.writer(output)

    # Header from column names
    writer.writerow(rows[0].keys())

    # Data
    for row in rows:
        writer.writerow(row)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def backfill_carry_distances():
    """Calculate and store carry_distance for all shots that don't have one."""
    rows = db.conn.execute("""
        SELECT id, ball_speed, vla, hla, total_spin, spin_axis
        FROM shots
        WHERE carry_distance IS NULL AND ball_speed IS NOT NULL AND vla IS NOT NULL
    """).fetchall()

    if not rows:
        return

    count = 0
    for row in rows:
        flight = compute_flight(
            ball_speed_mph=row["ball_speed"] or 0,
            vla_deg=row["vla"] or 0,
            hla_deg=row["hla"] or 0,
            total_spin_rpm=row["total_spin"] or 3000,
            spin_axis_deg=row["spin_axis"] or 0,
        )
        db.conn.execute(
            "UPDATE shots SET carry_distance = ? WHERE id = ?",
            (flight["carry_yards"], row["id"])
        )
        count += 1

    db.conn.commit()
    print(f"[Dashboard] Backfilled carry distance for {count} shots")


def main():
    global db

    parser = argparse.ArgumentParser(description="Jetson LM Stats Dashboard")
    parser.add_argument("--port", type=int, default=5000, help="Web server port (default: 5000)")
    parser.add_argument("--db", default="jetson_lm.db", help="Path to SQLite database")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"[Dashboard] Database not found: {args.db}")
        print("  -> Run gspro_sender.py first to create it, or check the path.")
        sys.exit(1)

    db = ShotDB(args.db)
    backfill_carry_distances()

    print(f"[Dashboard] Starting on http://0.0.0.0:{args.port}")
    print(f"[Dashboard] Open this URL from any device on your local network:")
    print(f"  -> http://<jetson-ip>:{args.port}")
    print()

    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
