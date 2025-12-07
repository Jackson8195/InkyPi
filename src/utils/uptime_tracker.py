# src/utils/uptime_tracker.py
import json
import os
from datetime import datetime, timezone

STATE_FILE = os.path.join(
    os.path.dirname(__file__),  # /src/utils
    "..",                        # /src
    "config",
    "uptime.json"
)

def load_state():
    """Load uptime state from JSON file. Ensures all expected keys exist."""
    if not os.path.exists(STATE_FILE):
        # Initialize state for first run
        state = {
            "battery_full_charge_time": None,
            "total_runtime_seconds": 0,
            "last_update": datetime.now(timezone.utc).isoformat()
        }
        save_state(state)
        return state

    with open(STATE_FILE, "r") as f:
        try:
            state = json.load(f)
        except json.JSONDecodeError:
            state = {}

    # Ensure all keys exist
    state.setdefault("battery_full_charge_time", None)
    state.setdefault("total_runtime_seconds", 0)
    state.setdefault("last_update", datetime.now(timezone.utc).isoformat())

    return state

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
    return state["battery_full_charge_time"]