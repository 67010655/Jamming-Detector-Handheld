# =============================================================================
# quota.py — Claude Code & Codex quota fetcher
# =============================================================================
#
# Claude Code stores session usage data in ~/.claude/  (on the HOST machine).
# Key files:
#   ~/.claude/usage.json           — current session token/time counters
#   ~/.claude/settings.json        — weekly limits etc.
#
# Codex (OpenAI Codex / ChatGPT code model) usage is available via:
#   GET https://api.openai.com/v1/usage   (date-scoped)
#   or a local proxy if you don't want to store API keys on the device.
#
# For the ESP32-S3 we implement:
#   1. A simple HTTP GET to a local companion server (recommended).
#   2. Direct HTTPS calls as an alternative stub.
#
# Run `host_server/quota_server.py` on your desktop to serve the data.
# =============================================================================

import ujson
import config

try:
    import urequests as requests
except ImportError:
    import requests   # fallback for desktop testing

# ---------------------------------------------------------------------------
# Data structure returned by get_*_quota()
# ---------------------------------------------------------------------------
# {
#   "session_pct"  : 63,        # 0-100
#   "session_time" : "2h00m",   # time consumed this session
#   "weekly_pct"   : 45,        # 0-100
#   "weekly_time"  : "1d10h",   # time remaining this week
#   "label"        : "5h 63% 2h00m / wk 45% 1d10h",
#   "ok"           : True,
#   "error"        : None,
# }

_EMPTY = {
    "session_pct"  : 0,
    "session_time" : "--",
    "weekly_pct"   : 0,
    "weekly_time"  : "--",
    "label"        : "-- --% --:-- / wk --% --",
    "ok"           : False,
    "error"        : "no data",
}


def _fmt_label(d):
    """Build the Claude Code CLI-style one-liner label."""
    return (
        f"{d['session_time']} {d['session_pct']}% "
        f"{d['session_time']} / wk {d['weekly_pct']}% {d['weekly_time']}"
    )


# ---------------------------------------------------------------------------
# Internal HTTP helper
# ---------------------------------------------------------------------------

def _get_json(url, headers=None, timeout=5):
    """
    Perform a GET request and parse JSON.
    Returns (dict_or_None, error_string_or_None).
    """
    try:
        resp = requests.get(url, headers=headers or {}, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            resp.close()
            return data, None
        else:
            err = f"HTTP {resp.status_code}"
            resp.close()
            return None, err
    except OSError as e:
        return None, f"OSError: {e}"
    except Exception as e:
        return None, str(e)


# ---------------------------------------------------------------------------
# Claude Code quota
# ---------------------------------------------------------------------------

def get_claude_quota():
    """
    Fetch Claude Code session and weekly quota from the local companion server.

    The companion server reads  ~/.claude/usage.json  and  ~/.claude/settings.json
    and exposes them as a simple JSON endpoint.

    Expected response shape:
    {
      "session_tokens"     : 125000,
      "session_limit"      : 200000,
      "session_minutes"    : 120,
      "weekly_tokens"      : 450000,
      "weekly_limit"       : 1000000,
      "weekly_minutes_rem" : 2040
    }
    """
    # TODO: replace URL in config.py with your actual host IP
    data, err = _get_json(config.CLAUDE_QUOTA_URL)
    if err or data is None:
        result = dict(_EMPTY)
        result["error"] = err
        return result

    try:
        sess_pct = min(100, int(data["session_tokens"] / data["session_limit"] * 100))
        sess_h   = data["session_minutes"] // 60
        sess_m   = data["session_minutes"] %  60
        sess_str = f"{sess_h}h{sess_m:02d}m"

        wk_pct   = min(100, int(data["weekly_tokens"] / data["weekly_limit"] * 100))
        wk_rem   = data["weekly_minutes_rem"]
        wk_d     = wk_rem // (60 * 24)
        wk_h     = (wk_rem % (60 * 24)) // 60
        wk_str   = f"{wk_d}d{wk_h}h"

        result = {
            "session_pct"  : sess_pct,
            "session_time" : sess_str,
            "weekly_pct"   : wk_pct,
            "weekly_time"  : wk_str,
            "ok"           : True,
            "error"        : None,
        }
        result["label"] = _fmt_label(result)
        return result

    except (KeyError, ZeroDivisionError) as e:
        result = dict(_EMPTY)
        result["error"] = f"parse: {e}"
        return result


# ---------------------------------------------------------------------------
# Codex quota  (OpenAI usage API — requires OPENAI_API_KEY in config)
# ---------------------------------------------------------------------------

def get_codex_quota():
    """
    Fetch Codex / OpenAI usage for today via the local companion server
    (recommended) or directly from api.openai.com.

    Direct endpoint (stub):
      GET https://api.openai.com/v1/usage?date=YYYY-MM-DD
      Authorization: Bearer <OPENAI_API_KEY>

    Companion server re-exposes the same data in the same schema as Claude:
    {
      "session_tokens"     : 80000,
      "session_limit"      : 150000,
      "session_minutes"    : 95,
      "weekly_tokens"      : 310000,
      "weekly_limit"       : 750000,
      "weekly_minutes_rem" : 3120
    }

    TODO: if you prefer direct HTTPS, uncomment the block below and set
          OPENAI_API_KEY in config.py.
    """
    # --- Option A: local companion server (recommended for ESP32) ----------
    data, err = _get_json(config.CODEX_QUOTA_URL)

    # --- Option B: direct OpenAI API (uncomment to use) --------------------
    # import utime
    # t = utime.localtime()
    # date_str = f"{t[0]}-{t[1]:02d}-{t[2]:02d}"
    # url = f"https://api.openai.com/v1/usage?date={date_str}"
    # headers = {"Authorization": f"Bearer {config.OPENAI_API_KEY}"}
    # raw, err = _get_json(url, headers=headers)
    # if raw:
    #     # TODO: map OpenAI usage response fields → our schema
    #     data = {
    #         "session_tokens"     : raw.get("total_tokens", 0),
    #         "session_limit"      : 150000,
    #         "session_minutes"    : raw.get("total_tokens", 0) // 1000,
    #         "weekly_tokens"      : raw.get("total_tokens", 0),
    #         "weekly_limit"       : 750000,
    #         "weekly_minutes_rem" : 3000,
    #     }
    # -----------------------------------------------------------------------

    if err or data is None:
        result = dict(_EMPTY)
        result["error"] = err
        return result

    try:
        sess_pct = min(100, int(data["session_tokens"] / data["session_limit"] * 100))
        sess_h   = data["session_minutes"] // 60
        sess_m   = data["session_minutes"] %  60
        sess_str = f"{sess_h}h{sess_m:02d}m"

        wk_pct   = min(100, int(data["weekly_tokens"] / data["weekly_limit"] * 100))
        wk_rem   = data["weekly_minutes_rem"]
        wk_d     = wk_rem // (60 * 24)
        wk_h     = (wk_rem % (60 * 24)) // 60
        wk_str   = f"{wk_d}d{wk_h}h"

        result = {
            "session_pct"  : sess_pct,
            "session_time" : sess_str,
            "weekly_pct"   : wk_pct,
            "weekly_time"  : wk_str,
            "ok"           : True,
            "error"        : None,
        }
        result["label"] = _fmt_label(result)
        return result

    except (KeyError, ZeroDivisionError) as e:
        result = dict(_EMPTY)
        result["error"] = f"parse: {e}"
        return result


# ---------------------------------------------------------------------------
# Mock data — returned when WiFi is unavailable (useful for UI development)
# ---------------------------------------------------------------------------

def get_claude_quota_mock():
    return {
        "session_pct"  : 63,
        "session_time" : "2h00m",
        "weekly_pct"   : 45,
        "weekly_time"  : "1d10h",
        "label"        : "5h 63% 2h00m / wk 45% 1d10h",
        "ok"           : True,
        "error"        : None,
    }

def get_codex_quota_mock():
    return {
        "session_pct"  : 38,
        "session_time" : "1h15m",
        "weekly_pct"   : 22,
        "weekly_time"  : "2d4h",
        "label"        : "3h 38% 1h15m / wk 22% 2d4h",
        "ok"           : True,
        "error"        : None,
    }
