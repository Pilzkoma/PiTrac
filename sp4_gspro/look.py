#!/usr/bin/env python3
"""The dashboard's look, shared by the statistics page and the calibration page.

Taken from Golfinator so the launch monitor and the simulator read as one
product: the tokens of Source/Golfinator/Public/UI/GolfStyle.h, the glass
panels and pills of the 2026-10-09 mockups (Stats.dc.html, Main.dc.html),
Cormorant Garamond for titles and numbers, Inter for everything else.

HEAD goes inside <head>, header_html() first inside <body>, HEADER_SCRIPT
before </body>. The header carries the one control both pages share: the
power-off button.
"""

HEAD = r"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;1,500&family=Inter:wght@400;500&display=swap">
<style>
  :root {
    --glass: rgba(16,22,18,0.90);
    --overlay: rgba(16,22,18,0.94);
    --cream: #ECE5D8;
    --muted: #A8A294;
    --gold: #E3B260;
    --gold-light: #F0CC86;
    --ink: #1A1408;
    --green: #2E5B44;
    --green-hover: #3A6E53;
    --sage: #8FB59A;
    --alert: rgb(232,130,106);
    --line: rgba(214,194,155,0.3);
    --ctl: rgba(236,229,216,0.18);
    --chip: rgba(236,229,216,0.04);
    --gold-tint: rgba(227,178,96,0.12);
    --plot: rgba(46,91,68,0.35);
    --serif: 'Cormorant Garamond', Georgia, serif;
    --sans: Inter, system-ui, sans-serif;
  }
  * { box-sizing: border-box; }
  html { background: #2b4521; }
  body {
    margin: 0; min-height: 100vh; color: var(--cream); font-family: var(--sans);
    font-size: 15px; -webkit-font-smoothing: antialiased;
    background: linear-gradient(180deg, #cdb88f 0%, #b98d55 24%, #3d5226 36%, #2b4521 100%) fixed;
  }
  a { color: var(--gold); } a:hover { color: var(--cream); }
  button { font-family: var(--sans); cursor: pointer; }
  button:disabled { opacity: .5; cursor: not-allowed; }
  :focus-visible { outline: 2px solid var(--gold); outline-offset: 2px; }

  /* ---- header capsule ---- */
  .lm-header {
    position: sticky; top: 12px; z-index: 20; margin: 12px 16px 0;
    display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
    padding: 10px 12px 10px 24px; border-radius: 999px; background: var(--glass);
    box-shadow: 0 24px 48px -24px rgba(0,0,0,0.5);
  }
  .lm-word { font-family: var(--serif); font-size: 30px; font-weight: 600; line-height: 1;
             color: var(--cream); text-decoration: none; letter-spacing: 0.01em; }
  .lm-word i { font-weight: 500; color: var(--gold); }
  .lm-status { display: flex; align-items: center; gap: 8px; font-size: 12px;
               letter-spacing: 0.14em; text-transform: uppercase; color: var(--muted); }
  .lm-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--sage); }
  .lm-power { margin-left: auto; }

  /* ---- pills and segments ---- */
  .seg { display: flex; max-width: 100%; min-width: 0; padding: 4px; border-radius: 999px; border: 1px solid var(--ctl); }
  .seg > a, .seg > button {
    min-height: 34px; padding: 0 16px; border: 0; border-radius: 999px; background: transparent;
    color: var(--muted); font: 400 13px var(--sans); text-decoration: none;
    display: flex; align-items: center; gap: 8px; white-space: nowrap;
  }
  .seg > [aria-pressed="true"], .seg > [aria-current="page"] {
    background: var(--green); color: var(--cream); font-weight: 500;
  }
  .pill {
    min-height: 44px; padding: 0 18px; border-radius: 999px; border: 1px solid var(--ctl);
    background: transparent; color: var(--cream); font: 400 12px var(--sans);
    letter-spacing: 0.16em; text-transform: uppercase;
    display: inline-flex; align-items: center; gap: 10px; white-space: nowrap;
  }
  .pill:hover:not(:disabled) { border-color: var(--cream); }
  .pill.primary { background: var(--green); border-color: var(--green); }
  .pill.primary:hover:not(:disabled) { background: var(--green-hover); }
  .label { font-size: 11px; letter-spacing: 0.2em; text-transform: uppercase; color: var(--muted); }
  .section { font-size: 12px; letter-spacing: 0.2em; text-transform: uppercase; color: var(--gold); }

  /* ---- the glass sheet a page sits on ---- */
  .sheet { margin: 16px; padding: 30px 40px; border-radius: 22px; background: var(--overlay); }
  .title { font-family: var(--serif); font-size: 44px; font-weight: 600; line-height: 1; margin: 0;
           font-variant-numeric: lining-nums; }
  .title i { font-weight: 500; color: var(--gold); }
  .num { font-variant-numeric: tabular-nums lining-nums; }
  /* Golfinator freezes lining figures into its font files; here the browser picks them. */
  body { font-feature-settings: "lnum" 1; }

  /* ---- the screen shown while powering off ---- */
  .lm-off { position: fixed; inset: 0; z-index: 50; display: none; align-items: center;
            justify-content: center; padding: 16px; background: rgba(10,14,11,0.82); }
  .lm-off.on { display: flex; }
  .lm-off > div { max-width: 520px; padding: 36px 40px; border-radius: 22px; background: var(--glass);
                  text-align: center; display: flex; flex-direction: column; gap: 14px; }
  .lm-off p { margin: 0; color: var(--muted); line-height: 1.5; }

  @media (max-width: 720px) {
    .lm-header { border-radius: 22px; padding: 10px 12px 10px 18px; gap: 10px; }
    .lm-word { font-size: 26px; }
    .lm-status { display: none; }
    .sheet { margin: 12px 8px; padding: 22px 16px; border-radius: 18px; }
    .title { font-size: 34px; }
  }
</style>
"""

_POWER_ICON = ('<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
               'stroke-width="1.8" stroke-linecap="round" aria-hidden="true">'
               '<path d="M12 3v9M6.3 6.3a8 8 0 1 0 11.4 0"/></svg>')


def header_html(active):
    """The header capsule; `active` is "stats" or "calibration"."""
    def nav(key, href, text):
        current = ' aria-current="page"' if key == active else ""
        return '<a href="{}"{}>{}</a>'.format(href, current, text)

    return """
<header class="lm-header">
  <a class="lm-word" href="/">Jetson<i>LM</i></a>
  <nav class="seg" aria-label="Seiten">{stats}{calib}</nav>
  <span class="lm-status"><span class="lm-dot"></span>bereit</span>
  <button type="button" class="pill lm-power" id="lm-power">{icon}Herunterfahren</button>
</header>
<div class="lm-off" id="lm-off" role="alertdialog" aria-live="assertive">
  <div>
    <div class="title">Jetson<i>LM</i></div>
    <div class="section" id="lm-off-head">Fährt herunter</div>
    <p id="lm-off-text">Gib ihm etwa 30 Sekunden, bevor du ihm den Strom nimmst.</p>
  </div>
</div>
""".format(stats=nav("stats", "/", "Statistik"),
           calib=nav("calibration", "/calibration", "Kalibrierung"),
           icon=_POWER_ICON)


HEADER_SCRIPT = r"""
<script>
document.getElementById('lm-power').onclick = async (e) => {
  const btn = e.currentTarget;
  btn.disabled = true;
  const off = document.getElementById('lm-off');
  try {
    const r = await fetch('/api/system/shutdown', {method: 'POST', headers: {'X-JetsonLM': '1'}});
    const d = await r.json();
    if (!r.ok || !d.ok) throw new Error(d.error || ('HTTP ' + r.status));
    off.classList.add('on');
  } catch (err) {
    document.getElementById('lm-off-head').textContent = 'Herunterfahren fehlgeschlagen';
    document.getElementById('lm-off-text').textContent = String(err.message || err);
    off.classList.add('on');
    off.onclick = () => { off.classList.remove('on'); btn.disabled = false;
      document.getElementById('lm-off-head').textContent = 'Fährt herunter';
      document.getElementById('lm-off-text').textContent =
        'Gib ihm etwa 30 Sekunden, bevor du ihm den Strom nimmst.'; };
  }
};
</script>
"""
