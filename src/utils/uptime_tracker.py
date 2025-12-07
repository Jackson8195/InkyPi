import json
import os
from datetime import datetime, timezone

STATE_FILE = os.path.join(
    os.path.dirname(__file__),
    "..",
    "config",
    "uptime.json"
)

def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "battery_full_charge_time": None,
            "total_runtime_seconds": 0
        }

    with open(STATE_FILE, "r") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def seconds_to_hms(sec):
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h}h {m}m {s}s"

def append_runtime(seconds):
    """
    Adds seconds to total_runtime_seconds — only called on shutdown.
    """
    state = load_state()
    state["total_runtime_seconds"] = state.get("total_runtime_seconds", 0) + int(seconds)
    save_state(state)

def get_total_runtime():
    """
    Returns H:M:S for total runtime since last full charge.
    """
    state = load_state()
    return seconds_to_hms(state.get("total_runtime_seconds", 0))

def set_full_charge_now():
    """
    Reset runtime counter and mark a new full charge timestamp.
    """
    state = load_state()
    now = datetime.now(timezone.utc).isoformat()

    state["battery_full_charge_time"] = now
    state["total_runtime_seconds"] = 0  # reset cycle

    save_state(state)
    return now

def get_battery_uptime():
    """
    Return time since full charge in H:M:S.
    """
    state = load_state()
    if not state["battery_full_charge_time"]:
        return None

    fc = datetime.fromisoformat(state["battery_full_charge_time"])
    now = datetime.now(timezone.utc)
    return seconds_to_hms(int((now - fc).total_seconds()))