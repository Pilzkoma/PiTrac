"""
Shot Database — SQLite storage for Jetson LM
Project: Jetson LM (SP4)
Purpose: Stores all shot data, sessions, players, and courses locally on the Jetson.

Usage:
    from shot_db import ShotDB

    db = ShotDB()                              # creates jetson_lm.db in current dir
    db = ShotDB("/path/to/jetson_lm.db")       # custom path

    player_id = db.add_player("Max", "RH")
    course_id = db.add_course("OpenShotGolf Driving Range", "OpenShotGolf", "range")
    session_id = db.start_session(player_id, course_id, "OpenShotGolf", "192.168.178.20", 49152)

    db.log_shot(session_id, shot_number=1, club="7I", ball_data={...}, club_data={...}, response_code=200)
    db.log_shot(session_id, shot_number=2, club="DR", ball_data={...}, club_data={...}, response_code=200)

    db.end_session(session_id)

    # Query examples
    shots = db.get_session_shots(session_id)
    stats = db.get_club_averages(player_id, "7I")
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

DEFAULT_DB_PATH = "jetson_lm.db"

SCHEMA_VERSION = 1

SCHEMA_SQL = """
-- Players
CREATE TABLE IF NOT EXISTS players (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    handedness      TEXT NOT NULL DEFAULT 'RH',  -- RH or LH
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Courses / Locations
CREATE TABLE IF NOT EXISTS courses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    platform        TEXT NOT NULL DEFAULT 'OpenShotGolf',  -- OpenShotGolf, GSPro, etc.
    course_type     TEXT NOT NULL DEFAULT 'range',          -- range, course
    holes           INTEGER DEFAULT NULL,                   -- NULL for range
    par             INTEGER DEFAULT NULL,                   -- NULL for range
    notes           TEXT DEFAULT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Sessions
CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id       INTEGER NOT NULL REFERENCES players(id),
    course_id       INTEGER REFERENCES courses(id),
    target          TEXT NOT NULL DEFAULT 'OpenShotGolf',   -- OpenShotGolf, GSPro
    target_ip       TEXT NOT NULL,
    target_port     INTEGER NOT NULL DEFAULT 49152,
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at        TEXT DEFAULT NULL,
    notes           TEXT DEFAULT NULL
);

-- Shots
CREATE TABLE IF NOT EXISTS shots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES sessions(id),
    shot_number     INTEGER NOT NULL,
    club            TEXT DEFAULT NULL,           -- DR, 3W, 5W, 4I-9I, PW, GW, SW, LW, PT
    timestamp       TEXT NOT NULL DEFAULT (datetime('now')),

    -- BallData (from GSPro Open Connect v1)
    ball_speed          REAL DEFAULT NULL,       -- mph
    spin_axis           REAL DEFAULT NULL,       -- degrees (negative = draw)
    total_spin          REAL DEFAULT NULL,       -- RPM
    back_spin           REAL DEFAULT NULL,       -- RPM
    side_spin           REAL DEFAULT NULL,       -- RPM (negative = draw)
    hla                 REAL DEFAULT NULL,       -- horizontal launch angle (degrees)
    vla                 REAL DEFAULT NULL,       -- vertical launch angle (degrees)
    carry_distance      REAL DEFAULT NULL,       -- yards (optional in protocol)

    -- ClubData (from GSPro Open Connect v1)
    club_speed              REAL DEFAULT NULL,   -- mph
    angle_of_attack         REAL DEFAULT NULL,   -- degrees
    face_to_target          REAL DEFAULT NULL,   -- degrees
    lie                     REAL DEFAULT NULL,   -- degrees
    loft                    REAL DEFAULT NULL,   -- degrees
    path                    REAL DEFAULT NULL,   -- degrees
    speed_at_impact         REAL DEFAULT NULL,   -- mph
    vertical_face_impact    REAL DEFAULT NULL,   -- degrees
    horizontal_face_impact  REAL DEFAULT NULL,   -- degrees
    closure_rate            REAL DEFAULT NULL,   -- degrees

    -- Response
    response_code   INTEGER DEFAULT NULL,        -- 200 = OK, 501+ = error
    notes           TEXT DEFAULT NULL
);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_info (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_shots_session ON shots(session_id);
CREATE INDEX IF NOT EXISTS idx_shots_club ON shots(club);
CREATE INDEX IF NOT EXISTS idx_sessions_player ON sessions(player_id);
CREATE INDEX IF NOT EXISTS idx_sessions_course ON sessions(course_id);
"""

# Default seed data
SEED_COURSES = [
    ("OpenShotGolf Driving Range", "OpenShotGolf", "range", None, None, "Default test target — free, open source"),
    ("GSPro Driving Range", "GSPro", "range", None, None, "GSPro default driving range — requires license"),
]


class ShotDB:
    """SQLite database for storing shot data, sessions, players, and courses."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        is_new = not os.path.exists(db_path)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.row_factory = sqlite3.Row

        if is_new:
            self._create_schema()
            self._seed_data()
            print(f"[ShotDB] Created new database: {db_path}")
        else:
            print(f"[ShotDB] Opened existing database: {db_path}")

    def _create_schema(self):
        self.conn.executescript(SCHEMA_SQL)
        self.conn.execute(
            "INSERT OR REPLACE INTO schema_info (key, value) VALUES (?, ?)",
            ("version", str(SCHEMA_VERSION))
        )
        self.conn.commit()

    def _seed_data(self):
        for course in SEED_COURSES:
            self.conn.execute(
                "INSERT INTO courses (name, platform, course_type, holes, par, notes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                course
            )
        self.conn.commit()

    def close(self):
        self.conn.close()

    # ------------------------------------------------------------------
    # Players
    # ------------------------------------------------------------------

    def add_player(self, name: str, handedness: str = "RH") -> int:
        """Add a player. Returns the player ID."""
        cur = self.conn.execute(
            "INSERT INTO players (name, handedness) VALUES (?, ?)",
            (name, handedness)
        )
        self.conn.commit()
        return cur.lastrowid

    def get_player(self, player_id: int) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT * FROM players WHERE id = ?", (player_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_players(self) -> List[Dict]:
        rows = self.conn.execute("SELECT * FROM players ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Courses
    # ------------------------------------------------------------------

    def add_course(self, name: str, platform: str = "GSPro",
                   course_type: str = "course", holes: Optional[int] = 18,
                   par: Optional[int] = 72, notes: Optional[str] = None) -> int:
        """Add a course. Returns the course ID."""
        cur = self.conn.execute(
            "INSERT INTO courses (name, platform, course_type, holes, par, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, platform, course_type, holes, par, notes)
        )
        self.conn.commit()
        return cur.lastrowid

    def get_course_by_name(self, name: str) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT * FROM courses WHERE name = ?", (name,)
        ).fetchone()
        return dict(row) if row else None

    def list_courses(self) -> List[Dict]:
        rows = self.conn.execute("SELECT * FROM courses ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def start_session(self, player_id: int, course_id: int,
                      target: str, target_ip: str, target_port: int,
                      notes: Optional[str] = None) -> int:
        """Start a new session. Returns the session ID."""
        cur = self.conn.execute(
            "INSERT INTO sessions (player_id, course_id, target, target_ip, target_port, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (player_id, course_id, target, target_ip, target_port, notes)
        )
        self.conn.commit()
        return cur.lastrowid

    def end_session(self, session_id: int):
        """Mark a session as ended (sets ended_at to now)."""
        self.conn.execute(
            "UPDATE sessions SET ended_at = datetime('now') WHERE id = ?",
            (session_id,)
        )
        self.conn.commit()

    def get_session(self, session_id: int) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_sessions(self, player_id: Optional[int] = None) -> List[Dict]:
        if player_id:
            rows = self.conn.execute(
                "SELECT * FROM sessions WHERE player_id = ? ORDER BY started_at DESC",
                (player_id,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM sessions ORDER BY started_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Shots
    # ------------------------------------------------------------------

    def log_shot(self, session_id: int, shot_number: int,
                 club: Optional[str] = None,
                 ball_data: Optional[Dict] = None,
                 club_data: Optional[Dict] = None,
                 response_code: Optional[int] = None,
                 notes: Optional[str] = None) -> int:
        """Log a single shot. Returns the shot ID."""
        bd = ball_data or {}
        cd = club_data or {}

        cur = self.conn.execute(
            """INSERT INTO shots (
                session_id, shot_number, club,
                ball_speed, spin_axis, total_spin, back_spin, side_spin,
                hla, vla, carry_distance,
                club_speed, angle_of_attack, face_to_target, lie, loft,
                path, speed_at_impact, vertical_face_impact,
                horizontal_face_impact, closure_rate,
                response_code, notes
            ) VALUES (
                ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?
            )""",
            (
                session_id, shot_number, club,
                bd.get("Speed"), bd.get("SpinAxis"), bd.get("TotalSpin"),
                bd.get("BackSpin"), bd.get("SideSpin"),
                bd.get("HLA"), bd.get("VLA"), bd.get("CarryDistance"),
                cd.get("Speed"), cd.get("AngleOfAttack"), cd.get("FaceToTarget"),
                cd.get("Lie"), cd.get("Loft"), cd.get("Path"),
                cd.get("SpeedAtImpact"), cd.get("VerticalFaceImpact"),
                cd.get("HorizontalFaceImpact"), cd.get("ClosureRate"),
                response_code, notes
            )
        )
        self.conn.commit()
        return cur.lastrowid

    def get_session_shots(self, session_id: int) -> List[Dict]:
        """Get all shots for a session, ordered by shot number."""
        rows = self.conn.execute(
            "SELECT * FROM shots WHERE session_id = ? ORDER BY shot_number",
            (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_club_averages(self, player_id: int, club: str) -> Optional[Dict]:
        """Get average ball data for a specific club across all sessions for a player."""
        row = self.conn.execute(
            """SELECT
                club,
                COUNT(*) as shot_count,
                ROUND(AVG(ball_speed), 1) as avg_ball_speed,
                ROUND(AVG(total_spin), 0) as avg_total_spin,
                ROUND(AVG(back_spin), 0) as avg_back_spin,
                ROUND(AVG(side_spin), 0) as avg_side_spin,
                ROUND(AVG(spin_axis), 1) as avg_spin_axis,
                ROUND(AVG(vla), 1) as avg_vla,
                ROUND(AVG(hla), 1) as avg_hla,
                ROUND(AVG(carry_distance), 1) as avg_carry
            FROM shots s
            JOIN sessions sess ON s.session_id = sess.id
            WHERE sess.player_id = ? AND s.club = ? AND s.response_code = 200
            GROUP BY s.club""",
            (player_id, club)
        ).fetchone()
        return dict(row) if row else None

    def get_player_summary(self, player_id: int) -> List[Dict]:
        """Get per-club averages for a player across all sessions."""
        rows = self.conn.execute(
            """SELECT
                s.club,
                COUNT(*) as shot_count,
                ROUND(AVG(s.ball_speed), 1) as avg_ball_speed,
                ROUND(AVG(s.total_spin), 0) as avg_total_spin,
                ROUND(AVG(s.vla), 1) as avg_vla,
                ROUND(AVG(s.hla), 1) as avg_hla,
                ROUND(AVG(s.carry_distance), 1) as avg_carry
            FROM shots s
            JOIN sessions sess ON s.session_id = sess.id
            WHERE sess.player_id = ? AND s.response_code = 200 AND s.club IS NOT NULL
            GROUP BY s.club
            ORDER BY AVG(s.ball_speed) DESC""",
            (player_id,)
        ).fetchall()
        return [dict(r) for r in rows]
