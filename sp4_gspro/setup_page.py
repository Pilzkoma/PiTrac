#!/usr/bin/env python3
"""Setup page ("Aufbau") for the Jetson LM dashboard.

Agreed with the owner 2026-11-18: the unit is set up once and then left
alone, and the ball has its own spot. This page is for that setup: one
flash, the ball's stereo position on its spot against the target (50 cm in
front of the rear camera for the chosen handedness), and how far to move
the unit. Measured with the flash because ambient-lit ball detection is
unreliable (CLAUDE.md issues #19/#21).

Like calibration_page.py: a blueprint registered from dashboard.py, which
runs from sp4_gspro/ and so needs the repo root on sys.path for sp1_vision.
"""

import base64
import os
import sys
import threading

import cv2
import numpy as np
from flask import Blueprint, jsonify, render_template_string, request

import look

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sp1_vision import (ball_pair, calibration_capture, flash_pair,  # noqa: E402
                        setup_check, stereo_geometry)

setup_bp = Blueprint("setup", __name__)

PULSE_US = 100
IMAGE_WIDTH = 640
# Either camera offering more circles than this is a noise image (no ball,
# only the lit floor, stretched): refused unsearched, as strobe_event does.
# Uncapped, such a pair took ~420 s in test and held the lock throughout.
MAX_CANDIDATES = 200

# Replaced in tests; the real one fires the strobe.
_capture = flash_pair.capture_flash_pair
_lock = threading.Lock()
_last = None        # (FlashPair, BallPair or None, reason, unlit) of the last measurement


def _rig():
    # Absolute paths: the dashboard's working directory is sp4_gspro/.
    return stereo_geometry.load_rig(
        os.path.join(_REPO_ROOT, stereo_geometry.DEFAULT_EXTRINSICS_PATH),
        os.path.join(_REPO_ROOT, stereo_geometry.DEFAULT_CONFIG_PATH))


def _handedness():
    hand = (request.get_json(silent=True) or {}).get("handedness")
    setup_check.flight_sign(hand)       # ValueError for anything but RH / LH
    return hand


def _project(rig, xyz, n):
    """Pixel of a camera-1-frame point in camera n."""
    if n == 1:
        rvec, tvec, k, d = np.zeros(3), np.zeros(3), rig.k1, rig.d1
    else:
        rvec, tvec, k, d = cv2.Rodrigues(rig.r)[0].ravel(), rig.t_m, rig.k2, rig.d2
    uv, _ = cv2.projectPoints(np.asarray(xyz, dtype=np.float64).reshape(1, 3), rvec, tvec, k, d)
    return uv.ravel()


def _annotated(rig, img, n, ball, target):
    out = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if target is not None:
        u, v = _project(rig, target, n)
        cam_xyz = target if n == 1 else rig.r @ target + rig.t_m
        r = ball_pair.apparent_radius_px((rig.k1 if n == 1 else rig.k2)[0, 0],
                                         float(np.linalg.norm(cam_xyz)))
        cv2.circle(out, (int(round(u)), int(round(v))), int(round(r)), (60, 200, 240), 2)
        cv2.drawMarker(out, (int(round(u)), int(round(v))), (60, 200, 240),
                       cv2.MARKER_CROSS, 24, 2)
    if ball is not None:
        (u, v), r = (ball.uv1, ball.radius1_px) if n == 1 else (ball.uv2, ball.radius2_px)
        cv2.circle(out, (int(round(u)), int(round(v))), int(round(r)), (90, 200, 90), 2)
    h, w = out.shape[:2]
    out = cv2.resize(out, (IMAGE_WIDTH, int(round(h * IMAGE_WIDTH / w))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", out, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    return base64.b64encode(buf.tobytes()).decode("ascii") if ok else ""


def _result(hand):
    """The JSON for the last measurement, seen with the given handedness."""
    fp, ball, reason, unlit = _last
    rig = _rig()
    out = {"found": ball is not None, "reason": reason, "unlit": unlit,
           "along_mm": None, "depth_mm": None, "ok": False, "margin_ok": False,
           "advice": [], "xyz_mm": None, "handedness": hand,
           "rear_camera": setup_check.rear_camera(rig, hand)}
    target = None
    if ball is not None:
        target = setup_check.target_xyz_m(rig, hand, float(ball.xyz_m[1]))
        off = setup_check.offsets(ball.xyz_m, target, hand)
        out.update(along_mm=off.along_mm, depth_mm=off.depth_mm,
                   margin_ok=setup_check.margin_ok(ball, rig.image_size),
                   advice=setup_check.advice(off),
                   xyz_mm=[float(x) * 1000.0 for x in ball.xyz_m])
        out["ok"] = off.ok and out["margin_ok"]
        if not out["margin_ok"]:
            out["advice"] = out["advice"] + ["Ball zu nah am Bildrand"]
    out["images"] = {str(n): _annotated(rig, fp.diff[n], n, ball, target) for n in (1, 2)}
    return out


@setup_bp.route("/setup")
def setup_page():
    return render_template_string(SETUP_HTML, head=look.HEAD,
                                  header=look.header_html("setup"),
                                  header_script=look.HEADER_SCRIPT)


@setup_bp.route("/setup/measure", methods=["POST"])
def setup_measure():
    global _last
    try:
        hand = _handedness()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if not _lock.acquire(False):
        return jsonify({"error": "Messung läuft bereits"})
    try:
        fp = _capture(pulse_us=PULSE_US, release=calibration_capture.SESSION.release)
        unlit = flash_pair.unlit_cameras(fp.rises)
        if unlit:
            ball, reason = None, "Blitz in {} nicht gesehen".format(
                " und ".join("Kamera {}".format(n) for n in unlit))
        else:
            rig = _rig()
            bgr = {n: cv2.cvtColor(fp.diff[n], cv2.COLOR_GRAY2BGR) for n in (1, 2)}
            ball, reason = ball_pair.find_ball_pair(rig, bgr[1], bgr[2],
                                                    max_candidates=MAX_CANDIDATES)
        _last = (fp, ball, reason, unlit)
        return jsonify(_result(hand))
    except Exception as e:      # noqa: BLE001 - the page must say what went wrong
        return jsonify({"error": "Messung fehlgeschlagen: {}".format(e)})
    finally:
        _lock.release()


@setup_bp.route("/setup/recompute", methods=["POST"])
def setup_recompute():
    try:
        hand = _handedness()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if _last is None:
        return jsonify({"error": "noch keine Messung"})
    return jsonify(_result(hand))


SETUP_HTML = r"""
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Jetson LM — Aufbau</title>
{{ head|safe }}
<style>
  p.sub { color:var(--muted); margin:12px 0 24px; font-size:14px; line-height:1.55; max-width:80ch; }
  .controls { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-bottom:20px; }
  .verdict { border:1px solid var(--line); border-radius:16px; padding:16px 18px; margin-bottom:20px;
             background:var(--chip); }
  .verdict.ok { border-color:var(--sage); }
  .verdict.bad { border-color:var(--alert); }
  .verdict .head { font:600 24px var(--serif); margin-bottom:6px; }
  .verdict.ok .head { color:var(--sage); } .verdict.bad .head { color:var(--alert); }
  .verdict ul { margin:6px 0 0; padding-left:20px; font-size:15px; line-height:1.6; }
  .nums { color:var(--muted); font-size:13px; margin-top:8px; font-variant-numeric:tabular-nums; }
  .cams { display:flex; gap:16px; flex-wrap:wrap; }
  .cam { background:var(--chip); border:1px solid var(--line); border-radius:16px; padding:12px;
         flex:1 1 420px; min-width:0; }
  .cam img { width:100%; border-radius:10px; display:block; background:#000; aspect-ratio:16/10; }
  .cam .label { color:var(--muted); font-size:12px; letter-spacing:0.14em; text-transform:uppercase; margin-top:8px; }
  .legend { color:var(--muted); font-size:13px; margin-top:12px; }
</style>
</head>
<body>
{{ header|safe }}
<main class="sheet">
<h1 class="title">Aufbau <i>prüfen</i></h1>
<p class="sub">Ball auf seinen Platz legen, Händigkeit wählen, „Messen“ drücken: ein Blitz, dann steht hier,
wie weit die <b>Einheit</b> zu verschieben ist, damit der Ball 50 cm vor der hinteren Kamera liegt
(Kameraplatine bis Ballmitte) —
der Kamera, von der der Ball wegfliegt, damit möglichst viele Bilder vom Flug entstehen.
Grün heißt: innerhalb ±10 mm.</p>

<div class="controls">
  <nav class="seg" aria-label="Händigkeit">
    <button type="button" id="hand-RH" class="seg-btn">Rechtshänder</button>
    <button type="button" id="hand-LH" class="seg-btn">Linkshänder</button>
  </nav>
  <button type="button" id="measure" class="pill primary">Messen</button>
</div>

<div id="verdict" class="verdict"><div class="head">Noch nicht gemessen</div></div>

<div class="cams">
  <div class="cam"><img id="img1" alt="Kamera 1"><div class="label">Kamera 1</div></div>
  <div class="cam"><img id="img2" alt="Kamera 2"><div class="label">Kamera 2</div></div>
</div>
<p class="legend">Gelb: Zielposition. Grün: gefundener Ball.</p>
</main>

<style>
  .seg-btn { min-height:36px; padding:0 16px; border-radius:999px; border:0; background:transparent;
             color:var(--muted); font:400 13px var(--sans); }
  .seg-btn[aria-pressed="true"] { background:var(--green); color:var(--cream); font-weight:500; }
</style>
<script>
let hand = 'RH';
try { const h = localStorage.getItem('lm-setup-hand'); if (h === 'RH' || h === 'LH') hand = h; } catch (e) {}
let measured = false;

const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');

function showHand() {
  for (const h of ['RH', 'LH'])
    document.getElementById('hand-' + h).setAttribute('aria-pressed', h === hand ? 'true' : 'false');
}

function show(d) {
  const v = document.getElementById('verdict');
  if (d.error) {
    v.className = 'verdict bad';
    v.innerHTML = '<div class="head">' + esc(d.error) + '</div>';
    return;
  }
  for (const n of ['1', '2'])
    if (d.images && d.images[n]) document.getElementById('img' + n).src = 'data:image/jpeg;base64,' + d.images[n];
  if (!d.found) {
    v.className = 'verdict bad';
    v.innerHTML = '<div class="head">Kein Ball gefunden</div><div class="nums">' + esc(d.reason || '') + '</div>';
    return;
  }
  v.className = 'verdict ' + (d.ok ? 'ok' : 'bad');
  v.innerHTML = '<div class="head">' + (d.ok ? 'Passt' : 'Einheit verschieben') + '</div>'
    + '<ul>' + d.advice.map(a => '<li>' + esc(a) + '</li>').join('') + '</ul>'
    + '<div class="nums">Ball gegenüber Ziel: ' + d.along_mm.toFixed(0) + ' mm in Schlagrichtung, '
    + d.depth_mm.toFixed(0) + ' mm in der Tiefe · hintere Kamera: ' + d.rear_camera
    + ' · Ball bei X ' + d.xyz_mm[0].toFixed(0) + ', Z ' + d.xyz_mm[2].toFixed(0) + ' mm</div>';
}

async function post(url) {
  const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'},
                              body: JSON.stringify({handedness: hand})});
  let d = await r.json();
  // The toggle may have changed while the request ran (a measurement takes
  // ~9 s): never show a result computed for the other handedness.
  while (!d.error && d.handedness && d.handedness !== hand) {
    const again = await fetch('/setup/recompute', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                                   body: JSON.stringify({handedness: hand})});
    d = await again.json();
  }
  return d;
}

for (const h of ['RH', 'LH']) {
  document.getElementById('hand-' + h).onclick = async () => {
    hand = h;
    try { localStorage.setItem('lm-setup-hand', h); } catch (e) {}
    showHand();
    if (measured) show(await post('/setup/recompute'));
  };
}

document.getElementById('measure').onclick = async (e) => {
  e.target.disabled = true;
  const v = document.getElementById('verdict');
  v.className = 'verdict';
  v.innerHTML = '<div class="head">Misst …</div><div class="nums">Kameras einstellen, blitzen — ein paar Sekunden.</div>';
  try {
    const d = await post('/setup/measure');
    if (!d.error) measured = true;
    show(d);
  } catch (err) {
    show({error: 'Anfrage fehlgeschlagen: ' + err});
  } finally {
    e.target.disabled = false;
  }
};

showHand();
</script>
{{ header_script|safe }}
</body>
</html>
"""
