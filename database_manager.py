import sqlite3
import os
import time
from datetime import datetime

DB_NAME = "jamming_events.db"

def init_db():
    """Initializes the database and creates the events table if it doesn't exist."""
    conn = sqlite3.connect(DB_NAME)
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
            noise_floor REAL
        )
    ''')
    conn.commit()
    conn.close()
    print(f"[DATABASE] Initialized: {DB_NAME}")

def log_event(state, score, peak_p, floor_rise, noise_floor, uptime_sec):
    """Records a detection event into the database and prunes old records."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # Use local time with d/m/Y format
        local_time = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        cursor.execute('''
            INSERT INTO events (timestamp, uptime_sec, state, score, peak_p, floor_rise, noise_floor)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (local_time, uptime_sec, state, score, peak_p, floor_rise, noise_floor))
        
        # Prune database: Keep only the latest 1000 non-startup records
        # Startup records are kept permanently to preserve session baselines
        cursor.execute('''
            DELETE FROM events WHERE state != 'STARTUP' AND id NOT IN (
                SELECT id FROM events WHERE state != 'STARTUP' ORDER BY id DESC LIMIT 1000
            )
        ''')
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DATABASE] Error logging event: {e}")

def get_history(limit=50):
    """Fetches the most recent events from the database (all states)."""
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM events ORDER BY id DESC LIMIT ?', (limit,))
        rows = cursor.fetchall()
        
        history = []
        for row in rows:
            history.append(dict(row))
        
        conn.close()
        return history
    except Exception as e:
        print(f"[DATABASE] Error fetching history: {e}")
        return []

import time

def get_filtered_history(limit=5000):
    """Fetches history and applies heartbeat filtering for CSV (15s for Scanning, 1s for Events)."""
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # Fetch all candidate rows (oldest first for chronological filtering)
        cursor.execute('SELECT * FROM events ORDER BY id ASC LIMIT ?', (limit,))
        rows = cursor.fetchall()
        conn.close()

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
                    curr_ts = time.mktime(time.strptime(row['timestamp'], '%d/%m/%Y %H:%M:%S'))
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

def clear_db():
    """Deletes all records from the events table."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM events')
        conn.commit()
        conn.close()
        print("[DATABASE] History cleared")
        return True
    except Exception as e:
        print(f"[DATABASE] Error clearing history: {e}")
        return False

if __name__ == "__main__":
    # Test initialization
    init_db()
    log_event("TEST", 50, -20.5, 5.2)
    print(get_history(1))
