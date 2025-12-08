# src/utils/uptime_tracker.py
import json
import os
from datetime import datetime, timezone
import re
from pathlib import Path
import time

STATE_FILE = os.path.join(
    os.path.dirname(__file__),  # /src/utils
    "..",                        # /src
    "config",
    "uptime.json"
)

def load_state():
    state_file = Path(STATE_FILE)
    
    # If file doesn't exist, create with defaults
    if not state_file.exists():
        default_state = {
            "full_charge_time": time.time(),
            "total_runtime_seconds": 0,
            "battery_uptime_seconds": 0
        }
        with open(state_file, 'w') as f:
            json.dump(default_state, f)
        return default_state
    
    # File exists — load it without overwriting
    with open(state_file, 'r') as f:
        return json.load(f)

def save_state(state):
    """Save uptime state to JSON file."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def seconds_to_hms(sec):
    """Convert seconds to H:M:S string."""
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h}h {m}m {s}s"

def record_runtime_slice():
    """
    Update cumulative runtime since last full charge.
    Called from main Python code or shutdown script.
    """
    state = load_state()
    now = datetime.now(timezone.utc)

    try:
        last_update = datetime.fromisoformat(state.get("last_update", now.isoformat()))
    except Exception:
        last_update = now

    delta = int((now - last_update).total_seconds())
    if delta < 0:
        delta = 0

    state["total_runtime_seconds"] += delta
    state["last_update"] = now.isoformat()
    save_state(state)

    return state["total_runtime_seconds"]

def get_total_runtime():
    """Return H:M:S string for total runtime since last full charge."""
    state = load_state()
    return seconds_to_hms(state.get("total_runtime_seconds", 0))

def get_battery_uptime():
    """Return H:M:S string since last full charge, or None if not set."""
    state = load_state()
    fc_time = state.get("battery_full_charge_time")
    if not fc_time:
        return None

    now = datetime.now(timezone.utc)
    try:
        fc = datetime.fromisoformat(fc_time)
    except Exception:
        return None

    return seconds_to_hms(int((now - fc).total_seconds()))

def set_full_charge_now():
    """Reset full charge timestamp to current time and zero runtime."""
    state = load_state()
    now = datetime.now(timezone.utc)
    state["battery_full_charge_time"] = now.isoformat()
    state["total_runtime_seconds"] = 0
    state["last_update"] = now.isoformat()
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
