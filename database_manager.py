import sqlite3
import os
import time
from datetime import datetime

DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jamming_events.db")

def _get_connection():
    """Open a SQLite connection with WAL mode for concurrent read/write safety."""
    conn = sqlite3.connect(DB_NAME)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn
    except Exception:
        conn.close()
        raise

def init_db():
    """Initializes the database and creates the events table if it doesn't exist."""
    conn = None
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                uptime_sec INTEGER,
                state TEXT NOT NULL,
                score INTEGER,
                peak_p REAL,
                floor_rise REAL,
                noise_floor REAL,
                bearing_deg INTEGER DEFAULT 0
            )
        ''')

        # Migration: Check if bearing_deg column exists (for older database files)
        cursor.execute("PRAGMA table_info(events)")
        columns = [info[1] for info in cursor.fetchall()]
        if 'bearing_deg' not in columns:
            print("[DATABASE] Migrating schema: Adding missing 'bearing_deg' column")
            try:
                cursor.execute("ALTER TABLE events ADD COLUMN bearing_deg INTEGER DEFAULT 0")
            except Exception as e:
                print(f"[DATABASE] Migration failed: {e}")

        conn.commit()
        print(f"[DATABASE] Initialized: {DB_NAME}")
    finally:
        if conn:
            conn.close()

def log_event(state, score, peak_p, floor_rise, noise_floor, uptime_sec, bearing_deg=0):
    """Records a detection event into the database and prunes old records."""
    conn = None
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        # Use local time with ISO 8601 format
        local_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO events (timestamp, uptime_sec, state, score, peak_p, floor_rise, noise_floor, bearing_deg)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (local_time, uptime_sec, state, score, peak_p, floor_rise, noise_floor, bearing_deg))
        
        # Prune database: Keep only the latest 1000 non-startup records
        # Startup records are kept permanently to preserve session baselines
        cursor.execute('''
            DELETE FROM events WHERE state != 'STARTUP' AND id NOT IN (
                SELECT id FROM events WHERE state != 'STARTUP' ORDER BY id DESC LIMIT 1000
            )
        ''')
        
        conn.commit()
    except Exception as e:
        print(f"[DATABASE] Error logging event: {e}")
    finally:
        if conn:
            conn.close()

def get_history(limit=50):
    """Fetches the most recent events from the database (all states)."""
    conn = None
    try:
        conn = _get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM events ORDER BY id DESC LIMIT ?', (limit,))
        rows = cursor.fetchall()
        
        history = []
        for row in rows:
            history.append(dict(row))
        
        return history
    except Exception as e:
        print(f"[DATABASE] Error fetching history: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_filtered_history(limit=5000):
    """Fetches history and applies heartbeat filtering for CSV (15s for Scanning, 1s for Events)."""
    conn = None
    try:
        conn = _get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # Fetch all candidate rows (oldest first for chronological filtering)
        cursor.execute('SELECT * FROM events ORDER BY id ASC LIMIT ?', (limit,))
        rows = cursor.fetchall()

        filtered = []
        last_scanning_time = 0
        
        for row in rows:
            state = row['state']
            # Always keep STARTUP, WATCH, JAMMING, TEST
            if state in ['STARTUP', 'WATCH', 'JAMMING', 'TEST']:
                filtered.append(dict(row))
            elif state == 'SCANNING':
                # Only keep SCANNING every 30 seconds
                try:
                    curr_ts = time.mktime(time.strptime(row['timestamp'], '%Y-%m-%d %H:%M:%S'))
                    if curr_ts - last_scanning_time >= 30:
                        filtered.append(dict(row))
                        last_scanning_time = curr_ts
                except:
                    # Fallback if timestamp format is weird
                    filtered.append(dict(row))
        
        # Return reversed (newest first) to match dashboard expectations
        return filtered[::-1]
    except Exception as e:
        print(f"[DATABASE] Error fetching filtered history: {e}")
        return []
    finally:
        if conn:
            conn.close()

def clear_db():
    """Deletes all records from the events table."""
    conn = None
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM events')
        # Reset AUTOINCREMENT counter
        cursor.execute('DELETE FROM sqlite_sequence WHERE name="events"')
        conn.commit()
        print("[DATABASE] History and ID counter cleared")
        return True
    except Exception as e:
        print(f"[DATABASE] Error clearing history: {e}")
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    # Test initialization
    init_db()
    log_event("TEST", 50, -20.5, 5.2, -89.9, 0, bearing_deg=0)
    print(get_history(1))
