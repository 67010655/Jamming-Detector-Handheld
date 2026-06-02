# ESP32-S3 Desk Widget

A MicroPython desk widget for the ESP32-S3 with a 3.5" ILI9488 TFT display (480×320, SPI).

Displays a live clock / date, Pepe the Frog pixel art, and Claude Code + Codex quota stats.

---

## Wiring table

| ILI9488 pin | ESP32-S3 GPIO | Notes |
|-------------|---------------|-------|
| VCC         | 3.3 V         | Some boards accept 5 V — check yours |
| GND         | GND           | |
| CS          | **GPIO 10**   | Chip select (active LOW) |
| RESET       | **GPIO 8**    | Hardware reset |
| DC / RS     | **GPIO 9**    | Data / command select |
| SDI (MOSI)  | **GPIO 11**   | SPI MOSI |
| SCK         | **GPIO 12**   | SPI clock |
| LED / BL    | **GPIO 46**   | Backlight PWM — add 10–33 Ω series resistor |
| SDO (MISO)  | **GPIO 13**   | SPI MISO (optional — read-back only) |

All pins are configurable in `config.py`.

---

## MicroPython firmware

1. Download the latest ESP32-S3 MicroPython firmware from  
   <https://micropython.org/download/ESP32_GENERIC_S3/>

2. Erase flash and write firmware:

```bash
pip install esptool
esptool.py --chip esp32s3 --port /dev/ttyUSB0 erase_flash
esptool.py --chip esp32s3 --port /dev/ttyUSB0 \
    write_flash -z 0x0 ESP32_GENERIC_S3-*.bin
```

---

## Uploading project files

Using **mpremote** (recommended):

```bash
pip install mpremote

# Upload all desk_widget files to the board root
mpremote connect /dev/ttyUSB0 cp desk_widget/config.py  :config.py
mpremote connect /dev/ttyUSB0 cp desk_widget/display.py :display.py
mpremote connect /dev/ttyUSB0 cp desk_widget/pepe.py    :pepe.py
mpremote connect /dev/ttyUSB0 cp desk_widget/quota.py   :quota.py
mpremote connect /dev/ttyUSB0 cp desk_widget/main.py    :main.py
```

Or use **Thonny** (GUI): connect to the board, open each file, save to device.

---

## Configuration

Edit `config.py` before uploading:

| Key | What to set |
|-----|-------------|
| `WIFI_SSID` | Your WiFi network name |
| `WIFI_PASSWORD` | Your WiFi password |
| `CLAUDE_QUOTA_URL` | IP:port of the companion server on your desktop |
| `CODEX_QUOTA_URL` | Same server, different endpoint |
| `OPENAI_API_KEY` | Only needed for direct HTTPS mode in `quota.py` |

---

## Companion server (desktop)

The widget fetches quota data from a tiny HTTP server you run on your desktop.

### `host_server/quota_server.py` (create this on your machine)

```python
# Minimal Flask server — serves Claude Code and Codex usage to the widget
# pip install flask

from flask import Flask, jsonify
import json, pathlib, datetime, os

app = Flask(__name__)

CLAUDE_USAGE_FILE = pathlib.Path.home() / ".claude" / "usage.json"
CLAUDE_SETTINGS   = pathlib.Path.home() / ".claude" / "settings.json"

@app.route("/claude_quota")
def claude_quota():
    try:
        usage    = json.loads(CLAUDE_USAGE_FILE.read_text())
        settings = json.loads(CLAUDE_SETTINGS.read_text())
        return jsonify({
            "session_tokens"     : usage.get("session_tokens", 0),
            "session_limit"      : settings.get("session_limit", 200000),
            "session_minutes"    : usage.get("session_minutes", 0),
            "weekly_tokens"      : usage.get("weekly_tokens", 0),
            "weekly_limit"       : settings.get("weekly_limit", 1000000),
            "weekly_minutes_rem" : usage.get("weekly_minutes_remaining", 0),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/codex_quota")
def codex_quota():
    # TODO: read from OpenAI usage API or local cache
    return jsonify({
        "session_tokens"     : 80000,
        "session_limit"      : 150000,
        "session_minutes"    : 95,
        "weekly_tokens"      : 310000,
        "weekly_limit"       : 750000,
        "weekly_minutes_rem" : 3120,
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8765)
```

Run it with:

```bash
python host_server/quota_server.py
```

Then set `CLAUDE_QUOTA_URL = "http://<your-desktop-ip>:8765/claude_quota"` in `config.py`.

---

## Layout

```
┌──────────────────── 480 px ─────────────────────┐
│           HH:MM:SS   (large white text)          │  ← clock
│          Mon 31 May 2026  (cyan)                 │  ← date
├─────────────────── separator ───────────────────┤
│                                                  │
│                  [Pepe 80×80]                    │  ← pixel art
│                                                  │
├─────────────────── separator ───────────────────┤
│  Claude               │  Codex                  │
│  Sess  63%  2h00m     │  Sess  38%  1h15m        │
│  [====        ]       │  [===         ]          │
│  Week  45%  1d10h     │  Week  22%   2d4h        │
│  [====        ]       │  [==          ]          │
└──────────────────────────────────────────────────┘
```

---

## Troubleshooting

**Display shows nothing / all white**  
→ Check DC and RST wiring.  SPI polarity must be `CPOL=0, CPHA=0`.

**Colours look wrong**  
→ ILI9488 uses RGB666 (18-bit), not RGB565.  The driver converts automatically.

**WiFi connects but quota shows "No data"**  
→ Check that the companion server is running and the IP in `config.py` is correct.  
→ Ensure the ESP32-S3 and your desktop are on the same subnet.

**NTP sync fails**  
→ The widget falls back to the RTC clock (may drift).  Configure your router to allow UDP port 123.
