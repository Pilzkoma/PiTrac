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

# Generous: twenty pairs of 1280x800 through calibrateCamera plus a stereo
# solve is slow on a Jetson, and a spurious timeout mid-run would be worse
# than waiting.
ANALYSIS_TIMEOUT_S = 600

# Stream at a rate that is comfortable to focus by. Higher costs lock time
# that every other caller waits behind, and buys nothing for turning a lens.
STREAM_FPS = 15

CALIBRATION_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Jetson LM — Calibration</title>
<style>
  :root { --bg:#0c1117; --surface:#161b22; --line:#26303d;
          --text:#e6edf3; --muted:#8b949e; --ok:#3fb950; --bad:#f85149; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font-family: 'DM Sans', system-ui, sans-serif; padding:24px; }
  h1 { font-size:20px; margin:0 0 4px; }
  p.sub { color:var(--muted); margin:0 0 24px; font-size:14px; max-width:70ch; }
  a.back { color:var(--muted); text-decoration:none; font-size:14px; }
  .cams { display:flex; gap:16px; flex-wrap:wrap; }
  .cam { background:var(--surface); border:1px solid var(--line);
         border-radius:10px; padding:12px; flex:1 1 420px; }
  .cam img { width:100%; border-radius:6px; display:block; background:#000; }
  .score { font-family:'JetBrains Mono', monospace; font-size:22px;
           margin-top:8px; }
  .score small { color:var(--muted); font-size:12px; font-family:inherit; }
  .bar { height:6px; background:var(--line); border-radius:3px;
         margin-top:6px; overflow:hidden; }
  .bar > div { height:100%; background:var(--ok); width:0%; transition:width .2s; }
  .controls { margin-top:24px; display:flex; gap:12px; align-items:center;
              flex-wrap:wrap; }
  button { background:#238636; color:#fff; border:0; border-radius:6px;
           padding:10px 18px; font-size:14px; cursor:pointer; }
  button.secondary { background:var(--surface); border:1px solid var(--line);
                     color:var(--text); }
  button:disabled { opacity:.5; cursor:not-allowed; }
  #log { margin-top:20px; background:var(--surface); border:1px solid var(--line);
         border-radius:10px; padding:14px; font-family:'JetBrains Mono', monospace;
         font-size:13px; max-height:420px; overflow-y:auto; white-space:pre-wrap; }
  .ok { color:var(--ok); } .bad { color:var(--bad); } .muted { color:var(--muted); }
</style>
</head>
<body>
<a class="back" href="/">&larr; Dashboard</a>
<h1>Camera Calibration</h1>
<p class="sub">Focus each lens until its score peaks, then capture around 20 board pairs.
Hold the board at working distance, reaching the image corners as well as the centre,
in ordinary room light. Retake any pair that does not report a board in both cameras —
a pair is only useful if both halves found it.
Switch away from this tab and the previews stop, so the cameras are handed back
after two idle minutes rather than running hot for as long as the page is open.</p>

<div class="cams">
  <div class="cam">
    <img src="/calibration/stream/1" alt="camera 1">
    <div class="score">cam 1 &nbsp; <span id="s1">—</span> <small>sharpness</small></div>
    <div class="bar"><div id="b1"></div></div>
  </div>
  <div class="cam">
    <img src="/calibration/stream/2" alt="camera 2">
    <div class="score">cam 2 &nbsp; <span id="s2">—</span> <small>sharpness</small></div>
    <div class="bar"><div id="b2"></div></div>
  </div>
</div>

<p id="mode" style="margin:14px 0 0; font-size:14px">&nbsp;</p>

<div class="controls">
  <button id="cap">Capture pair</button>
  <button id="run" class="secondary">Run calibration</button>
  <button id="rel" class="secondary">Release cameras</button>
  <span id="count" style="color:var(--muted)"></span>
</div>

<div id="log">ready</div>

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
    ? '<span class="muted">paused — tab hidden</span>' : '&nbsp;';
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
      ? '<span class="ok">measuring the board</span>'
      : '<span class="bad">no board in view — measuring the frame centre, '
        + 'which is the room, not your lens</span>';
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
  document.getElementById('count').textContent = d.pairs + ' pairs captured';
}
refreshCount();

document.getElementById('cap').onclick = async (e) => {
  e.target.disabled = true;
  try {
    const r = await fetch('/calibration/capture', {method: 'POST'});
    const d = await r.json();
    if (d.error) log('capture failed: ' + d.error, 'bad');
    else log('pair ' + d.index + ':  cam1 ' + (d.found1 ? 'board' : '  --  ') +
             '   cam2 ' + (d.found2 ? 'board' : '  --  ') +
             '   skew ' + d.skew_ms.toFixed(1) + ' ms' +
             (d.found1 && d.found2 ? '' : '   <- move the board and retry'),
             d.found1 && d.found2 ? 'ok' : 'bad');
    await refreshCount();
  } finally {
    e.target.disabled = false;
  }
};

document.getElementById('run').onclick = async (e) => {
  e.target.disabled = true;
  log('\nrunning calibration - this takes a while, the page is not stuck...');
  try {
    const r = await fetch('/calibration/run', {method: 'POST'});
    const d = await r.json();
    if (d.report) log(d.report);
    if (d.error) log(d.error, 'bad');
    else log('done', 'ok');
  } catch (err) {
    log('calibration request failed: ' + err, 'bad');
  } finally {
    e.target.disabled = false;
  }
};

document.getElementById('rel').onclick = async () => {
  await fetch('/calibration/release', {method: 'POST'});
  log('cameras released - pitrac_lm can open them again');
};
</script>
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
    return render_template_string(CALIBRATION_HTML)


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
            pair, _ = calibration_capture.SESSION.grab()
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
