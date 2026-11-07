#!/usr/bin/env python3
"""Statistics for the dashboard, computed the way Golfinator computes them.

The dashboard shows the shots cached in jetson_lm.db in the layout of
Golfinator's statistics page, so the numbers have to mean the same thing
there and here:

- metric units (km/h, m), the simulator's default;
- spread is the sample standard deviation (n - 1), shown from 2 shots;
- the dispersion ellipse is the covariance ellipse scaled to hold about 68 %
  of a 2D normal distribution, shown from 3 shots;
- a point is x = length, y = side (+ right).

Those definitions are copied from Golfinator's Source/Golfinator/Private/
Players/ShotStats.cpp. Club ids, names and colours from GolfClubs.cpp and
GolfStyle.cpp.

Pure Python on purpose: no Flask, no database handle. dashboard.py feeds it
rows and serialises what comes back, and the tests run on any machine.
"""

import math
from datetime import datetime, timedelta

from ball_physics import compute_flight

MPH_TO_KMH = 1.609344
YARDS_TO_M = 0.9144

MIN_SHOTS_FOR_SPREAD = 2
MIN_SHOTS_FOR_ELLIPSE = 3
# sqrt(-2 ln(1 - 0.68)), Golfinator::Stats::EllipseScale68.
ELLIPSE_SCALE_68 = 1.5095921854516636

PERIOD_DAYS = 30

# Golfinator's standard bag in its own order, with its display names.
CLUBS = [
    ("DR", "Driver"), ("3W", "3W"), ("5W", "5W"), ("7W", "7W"),
    ("3H", "3H"), ("4H", "4H"), ("3I", "3i"), ("4I", "4i"), ("5I", "5i"),
    ("6I", "6i"), ("7I", "7i"), ("8I", "8i"), ("9I", "9i"), ("PW", "PW"),
    ("GW", "GW"), ("SW", "SW"), ("LW", "LW"), ("PT", "Putter"),
]
CLUB_ORDER = {cid: i for i, (cid, _) in enumerate(CLUBS)}
CLUB_NAMES = dict(CLUBS)

# Golfinator::Style::ClubColor, the fixed colours of the standard clubs.
CLUB_COLORS = {
    "DR": "#E3B260", "3W": "#C480B1", "5W": "#579BD7", "7W": "#7AA164",
    "3H": "#CDADC0", "4H": "#21A6A9", "3I": "#B78E68", "4I": "#9FE1AB",
    "5I": "#FFA2AA", "6I": "#9C985A", "7I": "#A9A7DC", "8I": "#CFD790",
    "9I": "#FCBEF7", "PW": "#8FB59A", "GW": "#B48C8B", "SW": "#5AD5FC",
    "LW": "#F5C8B0", "PT": "#6BE5DA",
}
# Golfinator's colours for user clubs; anything outside the standard bag.
OTHER_COLORS = ["#BBD4EF", "#82ACBB", "#ABDADF", "#D4CEEC"]

UNKNOWN_CLUB = "?"


def club_id(raw):
    """The stored club as a Golfinator id; None and blanks become UNKNOWN_CLUB."""
    return (raw or "").strip().upper() or UNKNOWN_CLUB


def club_name(cid):
    if cid == UNKNOWN_CLUB:
        return "Ohne Schläger"
    return CLUB_NAMES.get(cid, cid)


def club_color(cid):
    if cid in CLUB_COLORS:
        return CLUB_COLORS[cid]
    return OTHER_COLORS[sum(map(ord, cid)) % len(OTHER_COLORS)]


def club_sort_key(cid):
    """Bag order; clubs outside the bag after it, alphabetically."""
    return (CLUB_ORDER.get(cid, len(CLUB_ORDER)), cid)


def parse_time(text):
    """SQLite's 'YYYY-MM-DD HH:MM:SS' (UTC); None for anything else."""
    if not text:
        return None
    try:
        return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def shot_view(row):
    """One stored shot as the dashboard shows it, in metric units.

    `row` is a mapping with the shots-table columns. Carry is the stored value
    when there is one (the simulator's, or the backfill's); side and apex come
    from ball_physics, which the stored row does not carry.
    """
    speed_mph = row.get("ball_speed")
    flight = None
    if speed_mph:
        flight = compute_flight(
            ball_speed_mph=speed_mph,
            vla_deg=row.get("vla") or 0,
            hla_deg=row.get("hla") or 0,
            total_spin_rpm=row.get("total_spin") or 3000,
            spin_axis_deg=row.get("spin_axis") or 0,
        )

    carry_yd = row.get("carry_distance")
    if carry_yd is None and flight:
        carry_yd = flight["carry_yards"]

    cid = club_id(row.get("club"))
    return {
        "id": row.get("id"),
        "session_id": row.get("session_id"),
        "shot_number": row.get("shot_number"),
        "timestamp": row.get("timestamp"),
        "club": cid,
        "club_name": club_name(cid),
        "color": club_color(cid),
        "ball_kmh": None if speed_mph is None else speed_mph * MPH_TO_KMH,
        "vla": row.get("vla"),
        "hla": row.get("hla"),
        "spin": row.get("total_spin"),
        "spin_axis": row.get("spin_axis"),
        "carry_m": None if carry_yd is None else carry_yd * YARDS_TO_M,
        "side_m": None if flight is None else flight["offline_yards"] * YARDS_TO_M,
        "apex_m": None if flight is None else flight["apex_yards"] * YARDS_TO_M,
    }


def moments(values):
    """(mean, sample standard deviation); deviation None below MIN_SHOTS_FOR_SPREAD."""
    vals = [v for v in values if v is not None]
    if not vals:
        return None, None
    mean = sum(vals) / len(vals)
    if len(vals) < MIN_SHOTS_FOR_SPREAD:
        return mean, None
    var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
    return mean, math.sqrt(var)


def covariance_ellipse(points):
    """The 68 % ellipse of (length, side) points, or None below MIN_SHOTS_FOR_ELLIPSE.

    A line-for-line copy of Golfinator::Stats::CovarianceEllipse. angle_deg
    turns the major axis from the length axis toward the side axis.
    """
    n = len(points)
    if n < MIN_SHOTS_FOR_ELLIPSE:
        return None
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    sxx = sum((p[0] - mx) ** 2 for p in points) / (n - 1)
    syy = sum((p[1] - my) ** 2 for p in points) / (n - 1)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in points) / (n - 1)
    half = 0.5 * (sxx + syy)
    root = math.sqrt(max(0.0, (0.5 * (sxx - syy)) ** 2 + sxy * sxy))
    return {
        "length_m": mx,
        "side_m": my,
        "semi_major_m": ELLIPSE_SCALE_68 * math.sqrt(half + root),
        "semi_minor_m": ELLIPSE_SCALE_68 * math.sqrt(max(0.0, half - root)),
        "angle_deg": math.degrees(0.5 * math.atan2(2.0 * sxy, sxx - syy)),
    }


def select(shots, period, session_id=None, hidden_clubs=(), now=None):
    """Shots in the period, without the hidden clubs, newest first.

    period is "session" (needs session_id), "30d" or "all". Shots are
    shot_view dicts. 30 days counts from `now` (UTC) back by timestamp; a
    shot without a readable timestamp only shows under "all" and "session".
    """
    hidden = set(hidden_clubs)
    if period == "session":
        picked = [s for s in shots if s["session_id"] == session_id]
    elif period == "30d":
        cutoff = (now or datetime.utcnow()) - timedelta(days=PERIOD_DAYS)
        picked = [s for s in shots
                  if (parse_time(s["timestamp"]) or datetime.min) >= cutoff]
    else:
        picked = list(shots)
    picked = [s for s in picked if s["club"] not in hidden]
    picked.sort(key=lambda s: (s["session_id"] or 0, s["shot_number"] or 0),
                reverse=True)
    return picked


def clubs_in(shots):
    """Club ids present in `shots`, in bag order."""
    return sorted({s["club"] for s in shots}, key=club_sort_key)


def averages_by_club(shots):
    """One row per club in bag order: count, means and the two spreads."""
    rows = []
    for cid in clubs_in(shots):
        mine = [s for s in shots if s["club"] == cid]
        ball, _ = moments(s["ball_kmh"] for s in mine)
        carry, carry_sd = moments(s["carry_m"] for s in mine)
        apex, _ = moments(s["apex_m"] for s in mine)
        side, side_sd = moments(s["side_m"] for s in mine)
        spin, _ = moments(s["spin"] for s in mine)
        vla, _ = moments(s["vla"] for s in mine)
        points = [(s["carry_m"], s["side_m"]) for s in mine
                  if s["carry_m"] is not None and s["side_m"] is not None]
        rows.append({
            "club": cid,
            "club_name": club_name(cid),
            "color": club_color(cid),
            "n": len(mine),
            "ball_kmh": ball,
            "vla": vla,
            "spin": spin,
            "carry_m": carry,
            "apex_m": apex,
            "side_m": side,
            "spread_side_m": side_sd,
            "spread_length_m": carry_sd,
            "ellipse": covariance_ellipse(points),
        })
    return rows


def session_label_time(session, first_shot_time):
    """When a session happened, for its label.

    The Jetson has no battery-backed clock, so a session opened before NTP
    sync is stamped 2000-01-01. The first shot's time is the honest answer;
    failing that the end, failing that the start.
    """
    for candidate in (first_shot_time, session.get("ended_at"),
                      session.get("started_at")):
        t = parse_time(candidate)
        if t and t.year > 2000:
            return t
    return None
