import json
import os
from datetime import datetime, timezone

# Path to uptime.json inside /src/config/
STATE_FILE = os.path.join(
    os.path.dirname(__file__),   # /src/utils
    "..",                        # /src
    "config",
    "uptime.json"
)

def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "full_charge_time": None,
            "total_uptime_seconds": 0,
            "last_boot_time": datetime.now(timezone.utc).isoformat()
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

def update_uptime():
    """
    Call this ONCE per boot or wake cycle from inkypi.py.
    Updates cumulative uptime and time since 'full charge'.
    Returns (total_uptime_hms, since_full_charge_hms or None).
    """
    state = load_state()
    now = datetime.now(timezone.utc)
    boot_time = datetime.fromisoformat(state["last_boot_time"])

    # Add uptime of this cycle
    uptime_this_cycle = int((now - boot_time).total_seconds())
    state["total_uptime_seconds"] += uptime_this_cycle

    total_hms = seconds_to_hms(state["total_uptime_seconds"])

    # Full charge tracking
    if state["full_charge_time"]:
        fc_time = datetime.fromisoformat(state["full_charge_time"])
        since_full_charge = seconds_to_hms(int((now - fc_time).total_seconds()))
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
    now = datetime.now(timezone.utc).isoformat()
    state["full_charge_time"] = now
    save_state(state)
    return now
