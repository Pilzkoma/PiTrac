"""
Golf Ball Flight Physics — Carry Distance & Offline Calculator
Project: Jetson LM (SP4)
Purpose: Calculate carry distance, offline distance, apex height from launch data.
         Based on the same aerodynamic principles as OpenShotGolf's physics engine:
         Reynolds-number-dependent Cd/Cl, Magnus lift, gravity, and air drag.

References:
    - OpenShotGolf physics/aerodynamics.gd (Reynolds-regime Cd/Cl models)
    - Jenkins et al., "Drag Coefficients of Golf Balls," World Journal of Mechanics 2018
    - Bearman & Harvey, "Golf Ball Aerodynamics," Aeronautical Quarterly 1976
    - USGA distance studies on Cd/Cl vs spin factor

Usage:
    from ball_physics import compute_flight

    result = compute_flight(
        ball_speed_mph=132.0,
        vla_deg=18.5,
        hla_deg=-1.2,
        total_spin_rpm=3200.0,
        spin_axis_deg=-3.5,
    )
    print(result)
    # {'carry_yards': 168, 'offline_yards': -4, 'apex_yards': 28, 'flight_time_s': 5.1}
"""

import math
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BALL_DIAMETER_M = 0.04267       # 1.68 inches — regulation golf ball
BALL_RADIUS_M = BALL_DIAMETER_M / 2
BALL_MASS_KG = 0.04593          # 1.62 oz — regulation golf ball
BALL_AREA_M2 = math.pi * BALL_RADIUS_M ** 2  # cross-sectional area

# Standard atmosphere at sea level, ~20°C
AIR_DENSITY = 1.225             # kg/m³
AIR_VISCOSITY = 1.81e-5         # Pa·s (dynamic viscosity at ~20°C)

GRAVITY = 9.81                  # m/s²

# Simulation
DT = 0.001                      # time step (seconds) — 1ms for accuracy
MAX_TIME = 15.0                 # max flight time (seconds)

# Conversions
MPH_TO_MS = 0.44704
MS_TO_MPH = 1.0 / MPH_TO_MS
M_TO_YARDS = 1.09361
RPM_TO_RADS = 2.0 * math.pi / 60.0


# ---------------------------------------------------------------------------
# Aerodynamics — Reynolds-number-dependent Cd and Cl
# ---------------------------------------------------------------------------

def calc_reynolds(speed_ms: float) -> float:
    """Calculate Reynolds number for a golf ball at given speed."""
    if speed_ms <= 0:
        return 0
    return (AIR_DENSITY * speed_ms * BALL_DIAMETER_M) / AIR_VISCOSITY


def calc_spin_factor(spin_rpm: float, speed_ms: float) -> float:
    """Calculate spin factor S = (omega * r) / V."""
    if speed_ms <= 0:
        return 0
    omega = spin_rpm * RPM_TO_RADS
    return (omega * BALL_RADIUS_M) / speed_ms


def calc_cd(re: float, spin_factor: float) -> float:
    """
    Drag coefficient based on Reynolds number regime.
    Matches OpenShotGolf's aerodynamics model:
    - Re < 50k:  High drag (slow chips/wedges) — Cd ~0.45-0.50
    - 50k-75k:   Transition zone — polynomial interpolation
    - 75k-200k:  Normal golf shots — linear model Cd ~0.23-0.28
    - Re > 200k: Very high speed — clamped
    Spin increases drag slightly.
    """
    # Base Cd from Reynolds regime
    if re < 50000:
        cd = 0.48
    elif re < 75000:
        # Polynomial interpolation through drag crisis
        t = (re - 50000) / 25000  # 0 to 1
        cd = 0.48 - 0.20 * (3 * t * t - 2 * t * t * t)  # smooth step
    elif re < 200000:
        # Linear model for normal golf shots
        cd = 0.28 - 0.04 * ((re - 75000) / 125000)
    else:
        cd = 0.24

    # Spin increases drag slightly
    cd += 0.05 * min(spin_factor, 0.3)

    return max(cd, 0.20)


def calc_cl(re: float, spin_factor: float) -> float:
    """
    Lift coefficient based on Reynolds number and spin factor.
    Magnus effect: spinning ball generates lift perpendicular to velocity.
    Matches OpenShotGolf's regime model:
    - Re < 50k:  Low Reynolds — Cl ~0.10 (minimal lift)
    - 50k-75k:   Transition — interpolated
    - 75k-200k:  Normal shots — Cl proportional to spin factor
    - Re > 200k: Clamped
    """
    if re < 50000:
        cl = 0.10
    elif re < 75000:
        t = (re - 50000) / 25000
        cl_low = 0.10
        cl_high = 0.45 * spin_factor
        cl = cl_low + (cl_high - cl_low) * t
    else:
        # Main regime: Cl roughly proportional to spin factor
        # Typical: S=0.1 → Cl≈0.15, S=0.2 → Cl≈0.22, S=0.3 → Cl≈0.28
        cl = 0.12 + 0.9 * spin_factor

    return min(max(cl, 0.0), 0.40)


# ---------------------------------------------------------------------------
# 3D Flight Simulation
# ---------------------------------------------------------------------------

def compute_flight(
    ball_speed_mph: float,
    vla_deg: float,
    hla_deg: float = 0.0,
    total_spin_rpm: float = 3000.0,
    spin_axis_deg: float = 0.0,
    temperature_c: float = 20.0,
    altitude_m: float = 0.0,
) -> dict:
    """
    Simulate golf ball flight and return carry distance, offline, apex.

    Args:
        ball_speed_mph: Ball speed off the face (mph)
        vla_deg: Vertical launch angle (degrees, positive = up)
        hla_deg: Horizontal launch angle (degrees, negative = left, positive = right)
        total_spin_rpm: Total spin rate (RPM)
        spin_axis_deg: Spin axis (degrees, negative = draw/right-to-left, positive = fade)
        temperature_c: Air temperature (°C, affects air density)
        altitude_m: Altitude above sea level (m, affects air density)

    Returns:
        dict with: carry_yards, offline_yards, apex_yards, apex_feet,
                   flight_time_s, max_speed_mph, landing_angle_deg
    """
    if ball_speed_mph <= 0 or vla_deg <= 0:
        return {
            "carry_yards": 0, "offline_yards": 0, "apex_yards": 0,
            "apex_feet": 0, "flight_time_s": 0, "max_speed_mph": ball_speed_mph,
            "landing_angle_deg": 0,
        }

    # Adjust air density for temperature and altitude
    # Simple model: density decreases ~1.2% per °C above 15°C, ~12% per 1000m altitude
    rho = AIR_DENSITY
    rho *= (288.15 / (273.15 + temperature_c))  # temperature correction
    rho *= math.exp(-0.00012 * altitude_m)       # altitude correction

    # Convert inputs to SI
    speed = ball_speed_mph * MPH_TO_MS
    vla_rad = math.radians(vla_deg)
    hla_rad = math.radians(hla_deg)

    # Initial velocity components (x=forward, y=up, z=lateral/offline)
    vx = speed * math.cos(vla_rad) * math.cos(hla_rad)
    vy = speed * math.sin(vla_rad)
    vz = speed * math.cos(vla_rad) * math.sin(hla_rad)

    # Decompose spin into backspin and sidespin using spin axis
    # spin_axis = 0 → pure backspin, spin_axis = ±90 → pure sidespin
    spin_axis_rad = math.radians(spin_axis_deg)
    backspin_rpm = total_spin_rpm * math.cos(spin_axis_rad)
    sidespin_rpm = total_spin_rpm * math.sin(spin_axis_rad)

    # Position
    x, y, z = 0.0, 0.0, 0.0

    # Tracking
    apex_y = 0.0
    t = 0.0
    landed = False

    while t < MAX_TIME and not landed:
        # Current speed
        v = math.sqrt(vx * vx + vy * vy + vz * vz)
        if v < 0.1:
            break

        # Aerodynamic coefficients
        re = (rho * v * BALL_DIAMETER_M) / AIR_VISCOSITY
        sf = calc_spin_factor(abs(backspin_rpm), v)
        cd = calc_cd(re, sf)
        cl = calc_cl(re, sf)

        # Dynamic pressure
        q = 0.5 * rho * v * v * BALL_AREA_M2

        # Drag force (opposes velocity)
        drag = cd * q
        fd_x = -drag * (vx / v)
        fd_y = -drag * (vy / v)
        fd_z = -drag * (vz / v)

        # Lift force (Magnus effect)
        # Backspin creates lift in the plane of velocity (upward when ball moves forward)
        # Sidespin creates lateral force
        lift = cl * q

        # Backspin lift: perpendicular to velocity in the vertical plane
        # Simplified: lift acts mostly upward, slightly opposing forward motion at high angles
        horizontal_speed = math.sqrt(vx * vx + vz * vz)
        if horizontal_speed > 0.1:
            # Backspin lift (upward component)
            fl_y = lift * (horizontal_speed / v) * (1.0 if backspin_rpm >= 0 else -1.0)
            fl_x = -lift * (vy / v) * (vx / horizontal_speed) * (1.0 if backspin_rpm >= 0 else -1.0)

            # Sidespin lateral force
            side_lift_factor = abs(sidespin_rpm) / (abs(total_spin_rpm) + 1.0)
            fl_z = lift * side_lift_factor * (1.0 if sidespin_rpm > 0 else -1.0)
        else:
            fl_y = 0.0
            fl_x = 0.0
            fl_z = 0.0

        # Total forces
        ax = (fd_x + fl_x) / BALL_MASS_KG
        ay = (fd_y + fl_y) / BALL_MASS_KG - GRAVITY
        az = (fd_z + fl_z) / BALL_MASS_KG

        # Euler integration
        vx += ax * DT
        vy += ay * DT
        vz += az * DT

        x += vx * DT
        y += vy * DT
        z += vz * DT

        t += DT

        # Track apex
        if y > apex_y:
            apex_y = y

        # Landing detection (ball below ground after going up)
        if y < 0 and t > 0.1:
            landed = True

    # Calculate landing angle
    final_speed = math.sqrt(vx * vx + vy * vy + vz * vz)
    landing_angle = 0
    if final_speed > 0:
        landing_angle = abs(math.degrees(math.asin(min(abs(vy) / final_speed, 1.0))))

    carry_yards = math.sqrt(x * x + z * z) * M_TO_YARDS
    offline_yards = z * M_TO_YARDS

    return {
        "carry_yards": round(carry_yards),
        "offline_yards": round(offline_yards),
        "apex_yards": round(apex_y * M_TO_YARDS),
        "apex_feet": round(apex_y * 3.28084),
        "flight_time_s": round(t, 1),
        "max_speed_mph": round(ball_speed_mph),
        "landing_angle_deg": round(landing_angle),
    }


# ---------------------------------------------------------------------------
# Quick test / CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Test with typical shots
    tests = [
        ("Driver",          155.0, 12.0,  0.5, 2800.0,  2.0),
        ("7-Iron",          132.0, 18.5, -1.2, 3200.0, -3.5),
        ("Pitching Wedge",  105.0, 26.0, -0.5, 6500.0, -1.0),
        ("Sand Wedge",       85.0, 32.0, -0.3, 8500.0, -0.5),
        ("5-Iron",          140.0, 15.0, -0.8, 4200.0, -2.0),
    ]

    print(f"{'Club':<20} {'Speed':>6} {'VLA':>5} {'Carry':>7} {'Offline':>8} "
          f"{'Apex':>6} {'Flight':>7} {'Land°':>6}")
    print("-" * 75)

    for name, speed, vla, hla, spin, axis in tests:
        r = compute_flight(speed, vla, hla, spin, axis)
        off_str = f"{abs(r['offline_yards'])}{'L' if r['offline_yards'] < 0 else 'R'}"
        print(f"{name:<20} {speed:>5.0f}  {vla:>4.1f}  {r['carry_yards']:>5}yd  "
              f"{off_str:>6}  {r['apex_feet']:>4}ft  {r['flight_time_s']:>5.1f}s  "
              f"{r['landing_angle_deg']:>4}°")
