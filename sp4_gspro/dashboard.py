#!/usr/bin/env python3
"""
Jetson LM — Stats Dashboard
Project: Jetson LM (SP4)
Purpose: Local web dashboard showing the shots cached on the Jetson, laid out
         like Golfinator's statistics page, plus camera calibration and the
         power-off button. Accessible from any device on the local network.

Usage:
    python3 dashboard.py                          # default: port 5000
    python3 dashboard.py --port 8080              # custom port
    python3 dashboard.py --db /path/to/jetson_lm.db

Then open http://<jetson-ip>:5000 on your phone, tablet, or laptop.

The numbers are computed in dashboard_stats.py with Golfinator's definitions;
the look lives in look.py. Powering off needs the sudoers drop-in from
install_system_permissions.sh.

Requirements: Flask (pip install flask --break-system-packages)
"""

import argparse
import csv
import io
import os
import sys

# Check Flask availability early with helpful message
try:
    from flask import Flask, render_template_string, jsonify, request, Response
except ImportError:
    print("[Dashboard] Flask is not installed. Install it with:")
    print("  pip3 install flask")
    sys.exit(1)

import dashboard_stats as stats
import look
import system_control
from shot_db import ShotDB
from ball_physics import compute_flight
from calibration_page import calibration_bp

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__)

# Camera calibration lives on its own page, in its own module. It has to be
# easy to re-run - every adjustment to a camera mount invalidates the previous
# result - and a button here beats a remembered command line.
app.register_blueprint(calibration_bp)

db = None  # initialized in main()

# A stored shot never changes, and its side and apex need a flight
# simulation each, so its view is computed once per process.
_shot_views = {}

# A shot counts unless the simulator rejected it.
ACCEPTED = "(s.response_code IS NULL OR s.response_code = 200)"

# ---------------------------------------------------------------------------
# HTML — the statistics page
# ---------------------------------------------------------------------------

STATS_HTML = r"""
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Jetson LM — Statistik</title>
{{ head|safe }}
<style>
  .stats-head { display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
  .player { position: relative; display: flex; align-items: center; gap: 8px;
            padding: 4px 6px 4px 4px; border-radius: 999px; border: 1px solid var(--ctl); }
  .avatar { width: 26px; height: 26px; border-radius: 50%; background: var(--gold); color: var(--ink);
            font: 600 16px var(--serif); display: flex; align-items: center; justify-content: center; }
  select.bare { appearance: none; -webkit-appearance: none; border: 0; background: transparent;
                color: var(--cream); font: 400 14px var(--sans); padding: 0 22px 0 0; cursor: pointer;
                background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='9' height='9' viewBox='0 0 24 24' fill='none' stroke='%23ECE5D8' stroke-width='2.4' stroke-linecap='round'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
                background-repeat: no-repeat; background-position: right 6px center; }
  select.bare option { background: #1b231d; color: var(--cream); }
  .exports { margin-left: auto; display: flex; gap: 14px; font-size: 12px; letter-spacing: 0.14em;
             text-transform: uppercase; color: var(--muted); }
  .exports a { text-decoration: none; }

  .filters { display: flex; flex-wrap: wrap; align-items: center; gap: 22px; margin: 20px 0;
             padding: 14px 18px; border-radius: 16px; background: var(--chip); }
  .filter { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; min-width: 0; max-width: 100%; }
  .seg select.bare { min-height: 34px; padding: 0 30px 0 16px; border-radius: 999px; color: var(--muted);
                     font-size: 13px; background-position: right 12px center; max-width: 260px;
                     min-width: 0; flex: 0 1 auto; text-overflow: ellipsis; }
  .seg select.bare.on { background-color: var(--green); color: var(--cream); font-weight: 500; }
  .chip { min-height: 34px; padding: 0 14px; border-radius: 999px; border: 1px solid var(--ctl);
          background: transparent; color: var(--cream); font: 400 13px var(--sans);
          display: flex; align-items: center; gap: 8px; }
  .chip[aria-pressed="false"] { border-style: dashed; color: var(--muted); }
  .swatch { width: 8px; height: 8px; border-radius: 50%; flex: none; }
  .chip[aria-pressed="false"] .swatch { background: transparent !important; border: 1px solid currentColor; }

  .cols { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); gap: 40px; }
  .col { min-width: 0; display: flex; flex-direction: column; }
  .scroll { overflow-x: auto; }
  .shots-scroll { max-height: 470px; overflow-y: auto; }
  table { width: 100%; border-collapse: separate; border-spacing: 0; }
  th { font: 400 11px var(--sans); letter-spacing: 0.16em; text-transform: uppercase; color: var(--muted);
       text-align: right; padding: 0 12px 8px; border-bottom: 1px solid var(--line); white-space: nowrap;
       position: sticky; top: 0; background: #121915; }
  th.l, td.l { text-align: left; }
  td { padding: 0 12px; height: 54px; text-align: right; border-bottom: 1px solid var(--line);
       font-variant-numeric: tabular-nums lining-nums; white-space: nowrap; }
  tr.newest td { background: var(--gold-tint); border-bottom-color: transparent; }
  tr.newest td:first-child { border-radius: 12px 0 0 12px; }
  tr.newest td:last-child { border-radius: 0 12px 12px 0; }
  td.idx { color: var(--muted); }
  td.big { font: 600 24px var(--serif); font-variant-numeric: tabular-nums lining-nums; }
  td.gold { color: var(--gold); }
  .club { display: inline-flex; align-items: center; gap: 8px; }
  .unit { color: var(--muted); font: 400 13px var(--sans); }
  .avg td { height: 50px; }
  .empty { padding: 40px 12px; color: var(--muted); text-align: center; }

  .plot-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
  .plot-head .label { margin-left: auto; }
  .plot { flex: 1; min-height: 460px; position: relative; border-radius: 16px; background: var(--plot);
          overflow: hidden; }
  .plot svg { position: absolute; inset: 0; width: 100%; height: 100%; }

  @media (max-width: 1100px) { .cols { grid-template-columns: minmax(0, 1fr); } .plot { min-height: 420px; } }
  @media (max-width: 720px) {
    .exports { margin-left: 0; width: 100%; }
    .filters { padding: 12px; gap: 14px; }
    .plot { min-height: 360px; }
  }
</style>
</head>
<body>
{{ header|safe }}
<main class="sheet">
  <div class="stats-head">
    <h1 class="title">Statistik <i id="period-title">&nbsp;</i></h1>
    <label class="player"><span class="avatar" id="avatar">?</span>
      <select class="bare" id="player" aria-label="Spieler"></select></label>
    <div class="exports"><span>CSV</span>
      <a id="csv-shots" href="/api/export/all_shots">Schüsse</a>
      <a id="csv-clubs" href="/api/export/club_averages">Durchschnitte</a></div>
  </div>

  <div class="filters">
    <div class="filter"><span class="label">Zeitraum</span>
      <div class="seg">
        <select class="bare" id="session" aria-label="Session"></select>
        <button type="button" data-period="30d">30 Tage</button>
        <button type="button" data-period="all">Alle</button>
      </div></div>
    <div class="filter" id="club-filter"><span class="label">Schläger</span></div>
  </div>

  <div class="cols">
    <section class="col">
      <div class="section" style="margin-bottom: 6px">Schüsse</div>
      <div class="scroll shots-scroll"><table>
        <thead><tr><th class="l">#</th><th class="l">Schläger</th><th>Ball</th><th>Abflug</th>
          <th>Spin</th><th>Carry</th><th>Höhe</th><th>Seite</th></tr></thead>
        <tbody id="shots"></tbody></table></div>

      <div class="section" style="margin: 28px 0 6px">Durchschnitt je Schläger</div>
      <div class="scroll"><table class="avg">
        <thead><tr><th class="l">Schläger</th><th>Schüsse</th><th>Ball</th><th>Carry</th><th>Höhe</th>
          <th>Streuung seitl.</th><th>Streuung Länge</th></tr></thead>
        <tbody id="averages"></tbody></table></div>
    </section>

    <section class="col">
      <div class="plot-head"><span class="section">Streubild</span><span class="label">Carry · 68 %</span></div>
      <div class="plot" id="plot"></div>
    </section>
  </div>
</main>

<script>
const nf = (d) => new Intl.NumberFormat('de-DE', {minimumFractionDigits: d, maximumFractionDigits: d});
const N0 = nf(0), N1 = nf(1);
const dash = '–';
const f0 = (v) => v == null ? dash : N0.format(v);
const f1 = (v) => v == null ? dash : N1.format(v);
const side = (v) => v == null ? dash : (Math.abs(v) < 0.05 ? '0,0' : N1.format(Math.abs(v)) + (v > 0 ? ' R' : ' L'));
const esc = (s) => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const swatch = (c) => '<span class="swatch" style="background:' + c + '"></span>';

// The database stores UTC without a zone; the browser shows local time.
const toDate = (t) => t ? new Date(t.replace(' ', 'T') + 'Z') : null;
function dayLabel(t) {
  const d = toDate(t);
  if (!d) return 'ohne Datum';
  const hm = d.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'});
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const day = new Date(d); day.setHours(0, 0, 0, 0);
  const diff = Math.round((today - day) / 86400000);
  if (diff === 0) return 'Heute, ' + hm;
  if (diff === 1) return 'Gestern, ' + hm;
  return d.toLocaleDateString('de-DE', {day: '2-digit', month: '2-digit', year: 'numeric'}) + ', ' + hm;
}

// Player and period can come from the address, so a view can be bookmarked.
const initial = new URLSearchParams(location.search);
const intOrNull = (v) => v === null || v === '' || isNaN(Number(v)) ? null : Number(v);
const state = {player: intOrNull(initial.get('player_id')), period: initial.get('period'),
               session: intOrNull(initial.get('session_id')), hidden: new Set()};
let lastSig = null;

async function load(force) {
  const q = new URLSearchParams();
  if (state.player !== null) q.set('player_id', state.player);
  if (state.period) q.set('period', state.period);
  if (state.session) q.set('session_id', state.session);
  if (state.hidden.size) q.set('hidden', [...state.hidden].join(','));
  const r = await fetch('/api/stats?' + q);
  const d = await r.json();
  state.player = d.player_id; state.period = d.period; state.session = d.session_id;
  const sig = JSON.stringify([d.player_id, d.period, d.session_id, [...state.hidden],
                              d.shots.length, d.shots.length ? d.shots[0].id : 0, d.sessions.length]);
  if (!force && sig === lastSig) return;
  lastSig = sig;
  render(d);
}

function render(d) {
  // Player
  const ps = document.getElementById('player');
  ps.innerHTML = '<option value="0">Alle Spieler</option>' +
    d.players.map(p => '<option value="' + p.id + '">' + esc(p.name) + '</option>').join('');
  ps.value = String(d.player_id);
  const me = d.players.find(p => p.id === d.player_id);
  document.getElementById('avatar').textContent = me ? me.name.charAt(0).toUpperCase() : '∑';
  const pq = d.player_id ? '?player_id=' + d.player_id : '';
  document.getElementById('csv-shots').href = '/api/export/all_shots' + pq;
  document.getElementById('csv-clubs').href = '/api/export/club_averages' + pq;

  // Period
  const ss = document.getElementById('session');
  ss.innerHTML = d.sessions.length
    ? d.sessions.map(s => '<option value="' + s.id + '">' + esc(dayLabel(s.time)) + ' · ' + s.shot_count +
        (s.shot_count === 1 ? ' Schuss' : ' Schüsse') + '</option>').join('')
    : '<option value="">keine Session</option>';
  if (d.session_id) ss.value = String(d.session_id);
  ss.classList.toggle('on', d.period === 'session');
  document.querySelectorAll('[data-period]').forEach(b =>
    b.setAttribute('aria-pressed', String(b.dataset.period === d.period)));
  const cur = d.sessions.find(s => s.id === d.session_id);
  document.getElementById('period-title').textContent =
    d.period === 'session' ? (cur ? dayLabel(cur.time) : 'Session') : d.period === '30d' ? 'Letzte 30 Tage' : 'Alle Schüsse';

  // Club chips: every club in the period, hidden ones dashed.
  const cf = document.getElementById('club-filter');
  cf.querySelectorAll('.chip').forEach(c => c.remove());
  d.clubs_in_period.forEach(c => {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'chip';
    b.setAttribute('aria-pressed', String(!state.hidden.has(c.club)));
    b.innerHTML = swatch(c.color) + esc(c.club_name);
    b.onclick = () => { state.hidden.has(c.club) ? state.hidden.delete(c.club) : state.hidden.add(c.club); load(true); };
    cf.appendChild(b);
  });

  // Shots, newest first, numbered within the selection.
  const n = d.shots.length;
  document.getElementById('shots').innerHTML = n ? d.shots.map((s, i) =>
    '<tr' + (i === 0 ? ' class="newest"' : '') + '>' +
    '<td class="l idx">' + (n - i) + '</td>' +
    '<td class="l"><span class="club">' + swatch(s.color) + esc(s.club_name) + '</span></td>' +
    '<td>' + f0(s.ball_kmh) + '</td>' +
    '<td>' + (s.vla == null ? dash : f1(s.vla) + '°') + '</td>' +
    '<td>' + f0(s.spin) + '</td>' +
    '<td class="big gold">' + f0(s.carry_m) + '</td>' +
    '<td>' + f0(s.apex_m) + '</td>' +
    '<td>' + side(s.side_m) + '</td></tr>').join('')
    : '<tr><td colspan="8" class="empty">Keine Schüsse in diesem Zeitraum.</td></tr>';

  document.getElementById('averages').innerHTML = d.averages.length ? d.averages.map(a =>
    '<tr><td class="l"><span class="club">' + swatch(a.color) + esc(a.club_name) + '</span></td>' +
    '<td>' + a.n + '</td>' +
    '<td>' + f0(a.ball_kmh) + ' <span class="unit">km/h</span></td>' +
    '<td class="big gold">' + f0(a.carry_m) + ' <span class="unit">m</span></td>' +
    '<td>' + f0(a.apex_m) + ' <span class="unit">m</span></td>' +
    '<td>' + (a.spread_side_m == null ? dash : '± ' + f1(a.spread_side_m) + ' m') + '</td>' +
    '<td>' + (a.spread_length_m == null ? dash : '± ' + f1(a.spread_length_m) + ' m') + '</td></tr>').join('')
    : '<tr><td colspan="7" class="empty">–</td></tr>';

  lastData = d;
  drawPlot(d);
}

// Streubild: the tee at the bottom centre, rings around it, carry points and
// the 68 % ellipse of each club, the newest shot ringed in cream.
let lastData = null;
function drawPlot(d) {
  const box = document.getElementById('plot');
  const W = box.clientWidth, H = box.clientHeight;
  const pad = 24, teeX = W / 2, teeY = H - pad;
  const pts = d.shots.filter(s => s.carry_m != null && s.side_m != null);
  let far = 50;
  pts.forEach(s => { far = Math.max(far, Math.hypot(s.carry_m, s.side_m)); });
  d.averages.forEach(a => { if (a.ellipse) far = Math.max(far, a.ellipse.length_m + a.ellipse.semi_major_m); });
  // The finest ring step that keeps the rings to six at most.
  const step = [10, 25, 50, 100].find(st => Math.ceil(far * 1.05 / st) <= 6) || 100;
  const top = Math.ceil(far * 1.05 / step) * step;
  const px = (H - 2 * pad) / top;
  const X = (sideM) => teeX + sideM * px, Y = (lenM) => teeY - lenM * px;

  let svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Streubild">';
  for (let r = step; r <= top; r += step) {
    svg += '<circle cx="' + teeX + '" cy="' + teeY + '" r="' + (r * px) + '" fill="none" stroke="rgba(214,194,155,0.3)"/>';
    svg += '<text x="' + (teeX + 6) + '" y="' + (Y(r) - 4) + '" fill="#A8A294" font-size="11" font-family="Inter, sans-serif">' +
           r + (r + step > top ? ' m' : '') + '</text>';
  }
  d.averages.forEach(a => {
    const e = a.ellipse;
    if (!e) return;
    // angle_deg turns the major axis from the length axis toward the side axis;
    // on screen length points up (-y) and side right (+x).
    const th = e.angle_deg * Math.PI / 180;
    const rot = Math.atan2(-Math.cos(th), Math.sin(th)) * 180 / Math.PI;
    svg += '<ellipse cx="' + X(e.side_m) + '" cy="' + Y(e.length_m) + '" rx="' + (e.semi_major_m * px) +
           '" ry="' + Math.max(1, e.semi_minor_m * px) + '" transform="rotate(' + rot + ' ' + X(e.side_m) + ' ' +
           Y(e.length_m) + ')" fill="' + a.color + '" fill-opacity="0.08" stroke="' + a.color + '"/>';
  });
  pts.slice().reverse().forEach((s, i, all) => {
    const newest = i === all.length - 1;
    svg += '<circle cx="' + X(s.side_m) + '" cy="' + Y(s.carry_m) + '" r="' + (newest ? 6 : 4) + '" fill="' + s.color + '"' +
           (newest ? ' stroke="#ECE5D8" stroke-width="2"' : '') + '><title>' + esc(s.club_name) + ' · ' + f0(s.carry_m) +
           ' m · ' + side(s.side_m) + '</title></circle>';
  });
  svg += '<circle cx="' + teeX + '" cy="' + teeY + '" r="5" fill="#ECE5D8"/></svg>';
  box.innerHTML = svg;
}

document.getElementById('player').onchange = (e) => {
  state.player = Number(e.target.value); state.period = null; state.session = null; state.hidden.clear(); load(true);
};
document.getElementById('session').onchange = (e) => {
  state.period = 'session'; state.session = Number(e.target.value) || null; load(true);
};
// A click on the session select while another period is shown switches back
// to the selected session even when the user does not pick a different one.
document.getElementById('session').onclick = (e) => {
  if (state.period !== 'session' && e.target.value) { state.period = 'session'; state.session = Number(e.target.value); load(true); }
};
document.querySelectorAll('[data-period]').forEach(b => b.onclick = () => {
  state.period = b.dataset.period; load(true);
});
window.addEventListener('resize', () => { if (lastData) drawPlot(lastData); });

// New shots appear on their own while the page is visible.
load(true);
setInterval(() => { if (!document.hidden) load(false); }, 5000);
</script>
{{ header_script|safe }}
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template_string(STATS_HTML, head=look.HEAD,
                                  header=look.header_html("stats"),
                                  header_script=look.HEADER_SCRIPT)


# ---------------------------------------------------------------------------
# Statistics API
# ---------------------------------------------------------------------------

@app.route("/api/players")
def api_players():
    """List all players."""
    rows = db.conn.execute("SELECT id, name, handedness FROM players ORDER BY name").fetchall()
    return jsonify([dict(r) for r in rows])


def _shot_rows(player_id):
    """Every accepted shot, for one player or (player_id 0) for everyone."""
    sql = """
        SELECT s.id, s.session_id, s.shot_number, s.club, s.timestamp, s.ball_speed,
               s.vla, s.hla, s.total_spin, s.spin_axis, s.carry_distance
        FROM shots s JOIN sessions sess ON s.session_id = sess.id
        WHERE {}""".format(ACCEPTED)
    args = ()
    if player_id:
        sql += " AND sess.player_id = ?"
        args = (player_id,)
    return db.conn.execute(sql, args).fetchall()


def _views(rows):
    out = []
    for row in rows:
        view = _shot_views.get(row["id"])
        if view is None:
            view = stats.shot_view(dict(row))
            _shot_views[row["id"]] = view
        out.append(view)
    return out


def _sessions_with_shots(player_id, shots):
    """Sessions that hold at least one accepted shot, newest first."""
    first_shot = {}
    counts = {}
    for s in shots:
        sid = s["session_id"]
        counts[sid] = counts.get(sid, 0) + 1
        t = s["timestamp"]
        if t and (sid not in first_shot or t < first_shot[sid]):
            first_shot[sid] = t
    if not counts:
        return []
    marks = ",".join("?" * len(counts))
    rows = db.conn.execute(
        "SELECT id, player_id, started_at, ended_at FROM sessions WHERE id IN ({})".format(marks),
        tuple(counts)).fetchall()
    out = []
    for r in rows:
        t = stats.session_label_time(dict(r), first_shot.get(r["id"]))
        out.append({"id": r["id"], "player_id": r["player_id"], "shot_count": counts[r["id"]],
                    "time": t.strftime("%Y-%m-%d %H:%M:%S") if t else None})
    # Ids grow with time; the stored start times cannot be trusted for order
    # (see session_label_time), the ids can.
    out.sort(key=lambda s: s["id"], reverse=True)
    return out


@app.route("/api/stats")
def api_stats():
    """Everything the statistics page shows, for one player and period.

    Without parameters: the player of the newest session that has shots, and
    that session. period is "session", "30d" or "all"; hidden is a comma
    list of club ids switched off.
    """
    players = [dict(r) for r in db.conn.execute(
        "SELECT id, name FROM players ORDER BY name").fetchall()]

    player_id = request.args.get("player_id", type=int)
    if player_id is None:
        newest = db.conn.execute("""
            SELECT sess.player_id FROM shots s JOIN sessions sess ON s.session_id = sess.id
            WHERE {} ORDER BY s.session_id DESC LIMIT 1""".format(ACCEPTED)).fetchone()
        player_id = newest["player_id"] if newest else 0

    all_shots = _views(_shot_rows(player_id))
    sessions = _sessions_with_shots(player_id, all_shots)

    period = request.args.get("period") or "session"
    if period not in ("session", "30d", "all"):
        period = "session"
    session_id = request.args.get("session_id", type=int)
    if session_id not in {s["id"] for s in sessions}:
        session_id = sessions[0]["id"] if sessions else None

    hidden = [c for c in (request.args.get("hidden") or "").split(",") if c]
    in_period = stats.select(all_shots, period, session_id)
    shown = stats.select(all_shots, period, session_id, hidden)

    return jsonify({
        "players": players,
        "player_id": player_id,
        "sessions": sessions,
        "period": period,
        "session_id": session_id,
        "clubs_in_period": [{"club": c, "club_name": stats.club_name(c), "color": stats.club_color(c)}
                            for c in stats.clubs_in(in_period)],
        "shots": shown,
        "averages": stats.averages_by_club(shown),
    })


# ---------------------------------------------------------------------------
# System API — powering off, for the header button and for Golfinator
# ---------------------------------------------------------------------------

@app.route("/api/system/status")
def api_system_status():
    return jsonify(system_control.status())


@app.route("/api/system/shutdown", methods=["POST"])
def api_system_shutdown():
    if not request.headers.get(system_control.REQUEST_HEADER):
        return jsonify({"ok": False, "error": "missing {} header".format(
            system_control.REQUEST_HEADER)}), 403
    ok, error = system_control.power_off()
    if not ok:
        return jsonify({"ok": False, "error": error}), 500
    print("[Dashboard] Power-off requested by {}".format(request.remote_addr), flush=True)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

@app.route("/api/export/all_shots")
def export_all_shots():
    """Export all shots as CSV, optionally filtered by player."""
    pid = request.args.get("player_id", type=int)
    sql = """
        SELECT s.shot_number, s.club, s.timestamp, s.ball_speed, s.vla, s.hla,
               s.total_spin, s.back_spin, s.side_spin, s.spin_axis,
               s.carry_distance, s.club_speed, s.angle_of_attack,
               s.face_to_target, s.path, s.response_code,
               sess.id as session_id, p.name as player
        FROM shots s
        JOIN sessions sess ON s.session_id = sess.id
        JOIN players p ON sess.player_id = p.id
        WHERE {}""".format(ACCEPTED)
    args = ()
    if pid:
        sql += " AND sess.player_id = ?"
        args = (pid,)
    rows = db.conn.execute(sql + " ORDER BY s.timestamp", args).fetchall()
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
    sql = """
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
        WHERE {} AND s.club IS NOT NULL""".format(ACCEPTED)
    args = ()
    if pid:
        sql += " AND sess.player_id = ?"
        args = (pid,)
    rows = db.conn.execute(sql + " GROUP BY s.club ORDER BY AVG(s.ball_speed) DESC",
                           args).fetchall()
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
