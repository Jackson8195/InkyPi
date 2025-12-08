import json
import os
from datetime import datetime, timezone
import re
from pathlib import Path

# Path to uptime.json inside /src/config/
STATE_FILE = os.path.join(
    os.path.dirname(__file__),   # /src/utils
    "..",                        # /src
    "config",
    "uptime.json"
)

def load_state():
    """
    Load uptime state from JSON file.
    Ensures all expected keys exist.
    """
    if not os.path.exists(STATE_FILE):
        # First run — initialize state
        return {
            "full_charge_time": None,
            "total_uptime_seconds": 0,
            "last_boot_time": datetime.now(timezone.utc).isoformat()
        }

    with open(STATE_FILE, "r") as f:
        state = json.load(f)

    # Ensure expected keys exist
    state.setdefault("full_charge_time", None)
    state.setdefault("total_uptime_seconds", 0)
    state.setdefault("last_boot_time", datetime.now(timezone.utc).isoformat())

    return state

def save_state(state):
    """
    Save uptime state to JSON file.
    """
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def seconds_to_hms(sec):
    """
    Convert seconds to H:M:S string.
    """
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h}h {m}m {s}s"

def update_uptime():
    """
    Call this ONCE per boot or wake cycle from inkypi.py.
    Updates cumulative uptime and time since 'full charge'.
    Returns (total_uptime_hms, since_full_charge_hms or None).
    """
    state = load_state()
    now = datetime.now(timezone.utc)  # use UTC consistently

    # Safely parse last_boot_time
    try:
        boot_time = datetime.fromisoformat(state["last_boot_time"])
    except Exception:
        boot_time = now  # fallback if corrupted

    # Add uptime of this cycle
    uptime_this_cycle = int((now - boot_time).total_seconds())
    state["total_uptime_seconds"] += uptime_this_cycle

    total_hms = seconds_to_hms(state["total_uptime_seconds"])

    # Full charge tracking
    if state["full_charge_time"]:
        try:
            fc_time = datetime.fromisoformat(state["full_charge_time"])
            since_full_charge = seconds_to_hms(int((now - fc_time).total_seconds()))
        except Exception:
            since_full_charge = None
    else:
        since_full_charge = None

    # Update timestamp for next cycle
    state["last_boot_time"] = now.isoformat()
    save_state(state)

    return total_hms, since_full_charge

def set_full_charge_now():
    """
    Reset full charge marker to NOW.
    """
    state = load_state()
    now = datetime.now(timezone.utc)  # use UTC
    state["full_charge_time"] = now.isoformat()
    save_state(state)
    return state["full_charge_time"]

WITTY_LOG = Path("/home/pi/wittypi4/wittyPi.log")

def read_witty_vin():
    try:
        lines = WITTY_LOG.read_text().strip().splitlines()
        # find the last line containing "Current Vin"
        for line in reversed(lines):
            m = re.search(r"Current\s+Vin\s*=\s*([\d.]+)", line, re.IGNORECASE)
            if m:
                return float(m.group(1))
    except Exception:
        pass
    return None

def vin_to_percent(v, v_empty=3.3, v_full=4.2):
    if v is None:
        return None
    pct = (v - v_empty) / (v_full - v_empty) * 100
    return max(0, min(100, round(pct)))