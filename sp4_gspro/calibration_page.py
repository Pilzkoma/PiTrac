#!/usr/bin/env python3
"""Calibration page for the Jetson LM dashboard.

Calibration is not a one-off - every adjustment to a camera mount invalidates
it - so it needs to be a button in the UI that already runs, not a remembered
command line.

Kept out of dashboard.py, which is already around 1400 lines. Registered as a
blueprint from there.

dashboard.py runs with its working directory set to sp4_gspro/ and imports its
siblings flat, so sp1_vision - a sibling of sp4_gspro under the repo root - is
not importable without help. Hence the sys.path insert below.
"""

import os
import subprocess
import sys
import time

import cv2
from flask import Blueprint, Response, jsonify, render_template_string

import look

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sp1_vision import calibration_capture, frame_analysis  # noqa: E402

calibration_bp = Blueprint("calibration", __name__)

# Where captured pairs land. Under the repo root so the CLI and the dashboard
# agree on one location.
IMAGE_ROOT = os.path.join(_REPO_ROOT, "sp1_vision", "calibration_images")

# The analysis scripts, run as subprocesses from their own directory.
CALIB_DIR = os.path.join(_REPO_ROOT, "Software", "CalibrateCameraDistortions")

# The printed board's square, measured with a ruler over 8 and 5 squares on
# 2026-09-24. It scales the stereo translation and so sets the baseline; the
# solver's own default is the 24.0 mm that was 1.1 % short.
SQUARE_MM = 24.27

# Generous: twenty pairs of 1280x800 through calibrateCamera plus a stereo
# solve is slow on a Jetson, and a spurious timeout mid-run would be worse
# than waiting.
ANALYSIS_TIMEOUT_S = 600

# Stream at a rate that is comfortable to focus by. Higher costs lock time
# that every other caller waits behind, and buys nothing for turning a lens.
STREAM_FPS = 15

CALIBRATION_HTML = r"""
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Jetson LM — Kalibrierung</title>
{{ head|safe }}
<style>
  p.sub { color:var(--muted); margin:12px 0 24px; font-size:14px; line-height:1.55; max-width:80ch; }
  .cams { display:flex; gap:16px; flex-wrap:wrap; }
  .cam { background:var(--chip); border:1px solid var(--line);
         border-radius:16px; padding:12px; flex:1 1 420px; min-width:0; }
  .cam img { width:100%; border-radius:10px; display:block; background:#000; aspect-ratio:16/10; }
  .score { font:600 26px var(--serif); margin-top:10px; font-variant-numeric:tabular-nums lining-nums; }
  .score small { color:var(--muted); font:400 11px var(--sans); letter-spacing:0.2em; text-transform:uppercase; }
  .bar { height:6px; background:var(--line); border-radius:3px;
         margin-top:6px; overflow:hidden; }
  .bar > div { height:100%; background:var(--sage); width:0%; transition:width .2s; }
  .controls { margin-top:24px; display:flex; gap:12px; align-items:center;
              flex-wrap:wrap; }
  #count { color:var(--muted); font-size:13px; }
  #log { margin-top:20px; background:rgba(0,0,0,0.25); border:1px solid var(--line);
         border-radius:16px; padding:14px; font-family:ui-monospace, 'JetBrains Mono', Consolas, monospace;
         font-size:13px; max-height:420px; overflow-y:auto; white-space:pre-wrap; }
  .ok { color:var(--sage); } .bad { color:var(--alert); } .muted { color:var(--muted); }
</style>
</head>
<body>
{{ header|safe }}
<main class="sheet">
<h1 class="title">Kalibrierung <i>Kameras</i></h1>
<p class="sub">Jedes Objektiv drehen, bis sein Wert am höchsten ist, dann rund 24 Brettpaare aufnehmen:
Brett aufgestellt oder angelehnt, nicht in der Hand, Abstände über 30–90 cm verteilt, 20–45° gekippt,
das untere Bilddrittel mit abgedeckt. Ein Paar, bei dem nicht beide Kameras das Brett finden, neu aufnehmen —
nur Paare mit Brett in beiden Hälften zählen.
Wechselst du den Tab, halten die Vorschauen an; die Kameras werden dann nach zwei Minuten
freigegeben, statt heiß zu laufen, solange die Seite offen ist.</p>

<div class="cams">
  <div class="cam">
    <img src="/calibration/stream/1" alt="Kamera 1">
    <div class="score">cam 1 &nbsp; <span id="s1">—</span> <small>Schärfe</small></div>
    <div class="bar"><div id="b1"></div></div>
  </div>
  <div class="cam">
    <img src="/calibration/stream/2" alt="Kamera 2">
    <div class="score">cam 2 &nbsp; <span id="s2">—</span> <small>Schärfe</small></div>
    <div class="bar"><div id="b2"></div></div>
  </div>
</div>

<p id="mode" style="margin:14px 0 0; font-size:14px">&nbsp;</p>

<div class="controls">
  <button id="cap" class="pill primary">Paar aufnehmen</button>
  <button id="run" class="pill">Kalibrierung rechnen</button>
  <button id="rel" class="pill">Kameras freigeben</button>
  <span id="count"></span>
</div>

<div id="log">bereit</div>
</main>

<script>
const log = (msg, cls) => {
  const el = document.getElementById('log');
  const safe = String(msg).replace(/&/g, '&amp;').replace(/</g, '&lt;');
  el.innerHTML += '\n' + (cls ? '<span class="' + cls + '">' + safe + '</span>' : safe);
  el.scrollTop = el.scrollHeight;
};

// The score's absolute value is meaningless - it depends on what the camera is
// looking at - so it is shown against the highest value seen so far. Turning
// the lens until the bar peaks is the whole technique.
//
// What it is measuring matters just as much, and is shown: with a board in
// view it measures the board, otherwise the middle of the frame. Those are
// wildly different scales, so the running peak resets whenever it switches -
// otherwise the bar stays pinned at nothing after a mode change.
// Everything below stops while the tab is hidden. The cameras run hot after an
// hour, and the session already hands them back after two idle minutes - but
// a poll every 500 ms keeps it awake for as long as the page is open, so the
// release never fired. Going quiet when nobody is looking is what makes the
// idle timeout mean anything, and it also gives pitrac_lm a way to get the
// devices without anyone pressing a button.
const streams = [];
document.querySelectorAll('.cam img').forEach(img => {
  streams.push([img, img.src]);
});

function setStreams(on) {
  streams.forEach(([img, src]) => {
    if (on && !img.src.includes('/calibration/stream/')) {
      img.src = src + '?t=' + Date.now();   // fresh connection, not the cache
    } else if (!on) {
      img.removeAttribute('src');
    }
  });
}

document.addEventListener('visibilitychange', () => {
  setStreams(!document.hidden);
  if (!document.hidden) poll();
  document.getElementById('mode').innerHTML = document.hidden
    ? '<span class="muted">angehalten — Tab im Hintergrund</span>' : '&nbsp;';
});

let peak = {1: 1, 2: 1};
let lastMode = null;
async function poll() {
  if (document.hidden) return;   // resumed by the visibilitychange handler
  try {
    const r = await fetch('/calibration/sharpness');
    const d = await r.json();
    if (d.on_board !== lastMode) {
      peak = {1: 1, 2: 1};
      lastMode = d.on_board;
    }
    document.getElementById('mode').innerHTML = d.on_board
      ? '<span class="ok">misst das Brett</span>'
      : '<span class="bad">kein Brett im Bild — gemessen wird die Bildmitte, '
        + 'also der Raum, nicht dein Objektiv</span>';
    for (const n of [1, 2]) {
      const v = d['cam' + n];
      if (v === null) continue;
      document.getElementById('s' + n).textContent = v.toFixed(1);
      peak[n] = Math.max(peak[n], v);
      document.getElementById('b' + n).style.width =
        Math.round(100 * v / peak[n]) + '%';
    }
  } catch (e) { /* page probably closing */ }
  setTimeout(poll, 500);
}
poll();

async function refreshCount() {
  const r = await fetch('/calibration/status');
  const d = await r.json();
  document.getElementById('count').textContent = d.pairs + (d.pairs === 1 ? ' Paar' : ' Paare') + ' aufgenommen';
}
refreshCount();

document.getElementById('cap').onclick = async (e) => {
  e.target.disabled = true;
  try {
    const r = await fetch('/calibration/capture', {method: 'POST'});
    const d = await r.json();
    if (d.error) log('Aufnahme fehlgeschlagen: ' + d.error, 'bad');
    else log('Paar ' + d.index + ':  cam1 ' + (d.found1 ? 'Brett' : '  --  ') +
             '   cam2 ' + (d.found2 ? 'Brett' : '  --  ') +
             '   Versatz ' + d.skew_ms.toFixed(1) + ' ms' +
             (d.found1 && d.found2 ? '' : '   <- Brett verschieben und neu aufnehmen'),
             d.found1 && d.found2 ? 'ok' : 'bad');
    await refreshCount();
  } finally {
    e.target.disabled = false;
  }
};

document.getElementById('run').onclick = async (e) => {
  e.target.disabled = true;
  log('\nKalibrierung läuft - das dauert, die Seite hängt nicht...');
  try {
    const r = await fetch('/calibration/run', {method: 'POST'});
    const d = await r.json();
    if (d.report) log(d.report);
    if (d.error) log(d.error, 'bad');
    else log('fertig', 'ok');
  } catch (err) {
    log('Anfrage fehlgeschlagen: ' + err, 'bad');
  } finally {
    e.target.disabled = false;
  }
};

document.getElementById('rel').onclick = async () => {
  await fetch('/calibration/release', {method: 'POST'});
  log('Kameras freigegeben - pitrac_lm kann sie wieder öffnen');
};
</script>
{{ header_script|safe }}
</body>
</html>
"""


def _pair_dirs():
    dirs = {n: os.path.join(IMAGE_ROOT, "cam{}".format(n)) for n in (1, 2)}
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
    return dirs


def _pair_count():
    """Pairs captured so far.

    Counted from camera 1's directory. Capture writes both halves together or
    neither, so the two cannot drift apart.
    """
    d = os.path.join(IMAGE_ROOT, "cam1")
    if not os.path.isdir(d):
        return 0
    return len([f for f in os.listdir(d) if f.endswith(".png")])


def _run_script(name, args):
    """Run one analysis script and return its combined output as text."""
    cmd = [sys.executable, name] + args
    try:
        done = subprocess.run(
            cmd, cwd=CALIB_DIR, capture_output=True, text=True,
            timeout=ANALYSIS_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return "$ {}\nTIMED OUT after {} s\n".format(
            " ".join(cmd), ANALYSIS_TIMEOUT_S)
    body = done.stdout + (done.stderr or "")
    return "$ {}\n{}".format(" ".join(cmd), body)


@calibration_bp.route("/calibration")
def calibration_page():
    return render_template_string(CALIBRATION_HTML, head=look.HEAD,
                                  header=look.header_html("calibration"),
                                  header_script=look.HEADER_SCRIPT)


@calibration_bp.route("/calibration/stream/<int:camera_number>")
def calibration_stream(camera_number):
    """Live MJPEG, so a lens can be focused by looking rather than by guessing.

    The browser holds this open, and every frame served defers the session's
    idle release.
    """
    if camera_number not in (1, 2):
        return jsonify({"error": "no such camera"}), 404

    def frames():
        calibration_capture.SESSION.ensure_open()
        while True:
            # Not fresh: reading back to back, the held frame is one grab
            # old at most, and discarding would only cost the stream rate.
            pair, _ = calibration_capture.SESSION.grab(fresh=False)
            if pair is None:
                # Released - the user pressed the button, or it idled out.
                # Stop rather than reopening the cameras behind their back.
                return
            ok, buf = cv2.imencode(".jpg", pair[camera_number],
                                   [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ok:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                       + buf.tobytes() + b"\r\n")
            time.sleep(1.0 / STREAM_FPS)

    return Response(frames(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


@calibration_bp.route("/calibration/sharpness")
def calibration_sharpness():
    """Sharpness of the board when one is visible, of the frame centre when not.

    Which of the two it is gets reported, because the difference matters: a
    board held below the middle of the frame leaves the centred ROI measuring
    a blank wall, and the number then describes the room rather than the thing
    being focused.
    """
    calibration_capture.SESSION.ensure_open()
    pair, _ = calibration_capture.SESSION.grab()
    if pair is None:
        return jsonify({"cam1": None, "cam2": None, "on_board": False})

    s1, found1 = frame_analysis.board_sharpness(pair[1])
    s2, found2 = frame_analysis.board_sharpness(pair[2])
    return jsonify({"cam1": s1, "cam2": s2, "on_board": bool(found1 and found2)})


@calibration_bp.route("/calibration/status")
def calibration_status():
    return jsonify({"pairs": _pair_count(),
                    "cameras_open": calibration_capture.SESSION.is_open()})


@calibration_bp.route("/calibration/capture", methods=["POST"])
def calibration_capture_pair():
    """Capture one simultaneous pair and say immediately whether it is usable.

    Reporting board detection per camera right here is the point: an unusable
    shot surfaces while the board is still in hand, rather than twenty shots
    later when the analysis rejects it.
    """
    calibration_capture.SESSION.ensure_open()
    pair, skew = calibration_capture.SESSION.grab()
    if pair is None:
        return jsonify({"error": "cameras are not open"})

    dirs = _pair_dirs()
    index = _pair_count() + 1
    found = {}
    for n in (1, 2):
        found[n], _ = frame_analysis.find_board(pair[n])
        cv2.imwrite(os.path.join(dirs[n], "gs_{:02d}.png".format(index)), pair[n])

    return jsonify({"index": index, "found1": found[1], "found2": found[2],
                    "skew_ms": skew * 1000.0})


@calibration_bp.route("/calibration/run", methods=["POST"])
def calibration_run():
    """Run both analysis steps and return their output verbatim.

    The cameras are deliberately left open: the scripts only read PNGs from
    disk, and tearing down a live preview mid-calibration would be surprising.

    Output is returned raw rather than parsed. The numbers that matter -
    reprojection error per image, fx against fy, the measured focal length,
    the baseline against the CAD's 80.00 mm - are judgements a person makes,
    and summarising them into a verdict here would hide the evidence.
    """
    pairs = _pair_count()
    if pairs < 8:
        return jsonify({
            "error": "only {} pairs captured; the analysis needs at least 8, "
                     "and around 20 gives a usable result".format(pairs)})

    cam1 = os.path.join(IMAGE_ROOT, "cam1")
    cam2 = os.path.join(IMAGE_ROOT, "cam2")
    parts = []

    for n, images in ((1, cam1), (2, cam2)):
        parts.append(_run_script("CameraCalibration.py", [
            "--images", images,
            "--label", str(n),
            "--save-npz", "/tmp/cam{}.npz".format(n),
            "--undistort-check", "/tmp/undistort_cam{}.png".format(n),
        ]))

    parts.append(_run_script("StereoCalibration.py", [
        "--cam1-npz", "/tmp/cam1.npz",
        "--cam2-npz", "/tmp/cam2.npz",
        "--cam1-images", cam1,
        "--cam2-images", cam2,
        "--square-mm", str(SQUARE_MM),
    ]))

    parts.append(
        "Undistortion checks written to /tmp/undistort_cam1.png and\n"
        "/tmp/undistort_cam2.png. Look at them: the board's rows and columns\n"
        "must be straight on the right-hand side. Numbers can look reasonable\n"
        "while the result is wrong, and this is the check a person can make.")

    return jsonify({"report": "\n\n".join(parts)})


@calibration_bp.route("/calibration/release", methods=["POST"])
def calibration_release():
    calibration_capture.SESSION.release()
    return jsonify({"cameras_open": False})
