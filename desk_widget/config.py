# =============================================================================
# config.py — Desk Widget Configuration
# ESP32-S3 + ILI9488 3.5" TFT (480x320, SPI)
# =============================================================================

# --- WiFi -------------------------------------------------------------------
WIFI_SSID     = "YOUR_SSID"
WIFI_PASSWORD = "YOUR_PASSWORD"

# --- API Keys / Endpoints ---------------------------------------------------
# Claude Code usage is read from local ~/.claude/ JSON files on the host
# machine and served via a tiny local HTTP server (see quota.py for details)
CLAUDE_QUOTA_URL = "http://192.168.1.100:8765/claude_quota"  # TODO: set host IP

# Codex usage endpoint (OpenAI usage API or a local proxy)
CODEX_QUOTA_URL  = "http://192.168.1.100:8765/codex_quota"   # TODO: set host IP

# Optional: direct OpenAI API key for usage queries
OPENAI_API_KEY = "sk-..."   # TODO: replace or leave empty if using proxy

# --- Display SPI Pins (ESP32-S3) -------------------------------------------
PIN_MOSI = 11
PIN_MISO = 13
PIN_SCK  = 12
PIN_CS   = 10
PIN_DC   =  9
PIN_RST  =  8
PIN_BL   = 46   # Backlight (PWM capable)

SPI_ID       = 1          # Hardware SPI bus id (SPI(1, ...))
SPI_BAUDRATE = 40_000_000 # 40 MHz — safe for most ILI9488 boards

# --- Display geometry -------------------------------------------------------
DISPLAY_WIDTH  = 480
DISPLAY_HEIGHT = 320

# --- UI colours (RGB565) ----------------------------------------------------
COLOR_BG       = 0x0000   # Black background  (#000000)
COLOR_TEXT     = 0xFFFF   # White
COLOR_CYAN     = 0x07FF   # Cyan accent
COLOR_GREEN    = 0x07E0   # Green
COLOR_DIMGREY  = 0x4208   # Dim separator / labels
COLOR_ORANGE   = 0xFD20   # Warn colour

# --- Refresh interval -------------------------------------------------------
REFRESH_SECONDS = 30
