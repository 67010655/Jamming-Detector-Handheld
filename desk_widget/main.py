# =============================================================================
# main.py — ESP32-S3 Desk Widget  (MicroPython)
# Displays: clock/date · Pepe pixel art · Claude + Codex quota stats
# Refreshes every REFRESH_SECONDS via WiFi
# =============================================================================

import time
import network
import ntptime

import config
from display import ILI9488
from pepe    import draw_pepe
import quota  as Q

# ---------------------------------------------------------------------------
# Helper: connect to WiFi
# ---------------------------------------------------------------------------

def connect_wifi(ssid, password, retries=10):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return True
    wlan.connect(ssid, password)
    for _ in range(retries):
        if wlan.isconnected():
            return True
        time.sleep(1)
    return False


# ---------------------------------------------------------------------------
# Helper: format time / date strings
# ---------------------------------------------------------------------------

def get_time_str():
    """Return (time_str, date_str) using local RTC."""
    t = time.localtime()
    time_str = f"{t[3]:02d}:{t[4]:02d}:{t[5]:02d}"
    days  = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    months = ("Jan","Feb","Mar","Apr","May","Jun",
               "Jul","Aug","Sep","Oct","Nov","Dec")
    date_str = f"{days[t[6]]}  {t[2]} {months[t[1]-1]} {t[0]}"
    return time_str, date_str


# ---------------------------------------------------------------------------
# UI layout constants  (480 × 320 landscape)
# ---------------------------------------------------------------------------
W = config.DISPLAY_WIDTH   # 480
H = config.DISPLAY_HEIGHT  # 320

# Zones
CLOCK_Y      = 6    # top: clock row
DATE_Y       = 28   # top: date row
SEP1_Y       = 46   # horizontal separator line
PEPE_X       = (W - 80) // 2   # centre Pepe (80 wide)
PEPE_Y       = SEP1_Y + 4
SEP2_Y       = PEPE_Y + 80 + 4
STATS_Y      = SEP2_Y + 6
COL_L_X      = 8                # left stats column x
COL_R_X      = W // 2 + 4      # right stats column x
STATS_LINE_H = 14               # pixels per stats line

BG  = config.COLOR_BG
FG  = config.COLOR_TEXT
CYN = config.COLOR_CYAN
GRN = config.COLOR_GREEN
DIM = config.COLOR_DIMGREY
ORG = config.COLOR_ORANGE


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def draw_header(disp, time_str, date_str):
    """Draw clock and date at top of screen."""
    disp.fill_rect(0, 0, W, SEP1_Y, BG)
    disp.text_centered(time_str, W // 2, CLOCK_Y, fg=FG,  scale=3)
    disp.text_centered(date_str, W // 2, DATE_Y,  fg=CYN, scale=1)


def draw_separator(disp, y):
    disp.hline(8, y, W - 16, DIM)


def draw_quota_column(disp, x, title, q):
    """
    Draw a single quota column at x position.
    q = result dict from quota.get_*_quota()
    """
    # Title
    disp.text(title, x, STATS_Y, fg=CYN, scale=2)
    y = STATS_Y + STATS_LINE_H * 2 + 2

    if not q["ok"]:
        disp.text("No data", x, y, fg=ORG, scale=1)
        disp.text(str(q["error"])[:22], x, y + STATS_LINE_H, fg=ORG, scale=1)
        return

    # Session row: "Session   63%  2h00m"
    bar_w = 80
    bar_h = 6
    bar_x = x
    bar_y = y + STATS_LINE_H - 2

    disp.text(f"Sess {q['session_pct']:3d}%  {q['session_time']}", x, y, fg=FG, scale=1)
    y += STATS_LINE_H
    # Thin progress bar
    disp.fill_rect(bar_x,          bar_y, bar_w,                   bar_h, DIM)
    disp.fill_rect(bar_x,          bar_y, bar_w * q['session_pct'] // 100, bar_h,
                   GRN if q['session_pct'] < 80 else ORG)
    y += bar_h + 2

    # Weekly row: "Week  45%  1d10h"
    disp.text(f"Week  {q['weekly_pct']:3d}%  {q['weekly_time']}", x, y, fg=FG, scale=1)
    y += STATS_LINE_H
    disp.fill_rect(bar_x, y - 2,  bar_w,                   bar_h, DIM)
    disp.fill_rect(bar_x, y - 2,  bar_w * q['weekly_pct'] // 100,  bar_h,
                   CYN if q['weekly_pct'] < 80 else ORG)


def draw_stats(disp, claude_q, codex_q):
    """Draw the two-column stats panel."""
    disp.fill_rect(0, SEP2_Y, W, H - SEP2_Y, BG)
    draw_separator(disp, SEP2_Y)
    # Vertical divider between columns
    disp.vline(W // 2, SEP2_Y, H - SEP2_Y, DIM)
    draw_quota_column(disp, COL_L_X, "Claude", claude_q)
    draw_quota_column(disp, COL_R_X, "Codex",  codex_q)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    # Initialise display
    disp = ILI9488()
    disp.fill(BG)
    disp.backlight(900)

    # Startup splash
    disp.text_centered("Connecting WiFi...", W // 2, H // 2 - 8, fg=CYN, scale=1)

    wifi_ok = connect_wifi(config.WIFI_SSID, config.WIFI_PASSWORD)

    if wifi_ok:
        try:
            ntptime.settime()   # sync RTC over NTP
        except Exception:
            pass                # continue with whatever time the RTC has

    # Draw Pepe (static — only drawn once)
    disp.fill(BG)
    draw_separator(disp, SEP1_Y)
    draw_pepe(disp, PEPE_X, PEPE_Y, bg=BG)
    draw_separator(disp, SEP2_Y)

    last_refresh = -1

    while True:
        now = time.time()

        # Always update clock every second
        ts, ds = get_time_str()
        draw_header(disp, ts, ds)

        # Refresh quota every REFRESH_SECONDS
        if now - last_refresh >= config.REFRESH_SECONDS:
            last_refresh = now

            if wifi_ok and network.WLAN(network.STA_IF).isconnected():
                claude_q = Q.get_claude_quota()
                codex_q  = Q.get_codex_quota()
            else:
                # Fall back to mock data when offline
                claude_q = Q.get_claude_quota_mock()
                codex_q  = Q.get_codex_quota_mock()

            draw_stats(disp, claude_q, codex_q)

        time.sleep(1)


main()
