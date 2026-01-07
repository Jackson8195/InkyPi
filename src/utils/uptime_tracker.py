# src/utils/uptime_tracker.py
import json
import os
from datetime import datetime, timezone
import re
from pathlib import Path
import time
from typing import Optional

import psutil

STATE_FILE = os.path.join(
    os.path.dirname(__file__),  # /src/utils
    "..",                        # /src
    "config",
    "uptime.json"
)

def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_boot_time_epoch() -> int:
    """Return the system boot time as an epoch (seconds)."""
    try:
        return int(psutil.boot_time())
    except Exception:
        # Fallback best-effort using proc if psutil fails
        try:
            with open("/proc/stat", "r") as f:
                # Not reliable for boot time; last resort return current time
                return int(time.time())
        except Exception:
            return int(time.time())


def _get_system_uptime_seconds() -> int:
    """Return system uptime in whole seconds since last boot."""
    bt = _get_boot_time_epoch()
    now = time.time()
    uptime = int(now - bt)
    return max(0, uptime)


def load_state():
    state_file = Path(STATE_FILE)
    
    # If file doesn't exist, create with defaults
    if not state_file.exists():
        now_iso = _now_utc_iso()
        default_state = {
            "battery_full_charge_time": now_iso,
            "total_runtime_seconds": 0,
            # Track last seen boot and uptime to avoid counting offline time
            "last_boot_time": _get_boot_time_epoch(),
            "last_uptime": _get_system_uptime_seconds(),
            "last_update": now_iso,
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

def seconds_to_dhms(sec):
    """Convert seconds to D:H:M:S string."""
    d = sec // 86400
    h = (sec % 86400) // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{d}d {h}h {m}m {s}s"

def append_runtime():
    """
    Update cumulative runtime since last full charge using OS uptime.

    We compute deltas based on system uptime so any power-off period
    is not counted. Across reboots, we only add the current session's
    uptime since boot at the first call after boot.
    """
    state = load_state()

    current_boot_time = _get_boot_time_epoch()
    current_uptime = _get_system_uptime_seconds()

    # Migrate/initialize state fields if missing
    last_boot_time = state.get("last_boot_time")
    last_uptime = state.get("last_uptime")

    delta = 0
    if isinstance(last_boot_time, int) and isinstance(last_uptime, int):
        if current_boot_time == last_boot_time:
            # Same boot session: add elapsed uptime since last update
            delta = max(0, current_uptime - last_uptime)
        else:
            # Boot changed: add uptime since new boot start (first-call-after-boot)
            delta = max(0, current_uptime)
    else:
        # No prior baseline: don't assume anything, just anchor now
        delta = 0

    state["total_runtime_seconds"] = int(state.get("total_runtime_seconds", 0)) + int(delta)
    state["last_update"] = _now_utc_iso()
    state["last_boot_time"] = current_boot_time
    state["last_uptime"] = current_uptime

    save_state(state)

    return state["total_runtime_seconds"]

def get_total_runtime():
    """Return D:H:M:S string for total runtime since last full charge."""
    state = load_state()
    return seconds_to_dhms(state.get("total_runtime_seconds", 0))

def _parse_iso_or_epoch(value: Optional[object]) -> Optional[datetime]:
    if value is None:
        return None
    # Accept ISO 8601 strings
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None
    # Accept numeric epoch seconds from older state
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except Exception:
        return None


def get_battery_uptime():
    """Return D:H:M:S string since last full charge, or None if not set."""
    state = load_state()
    fc_time = state.get("battery_full_charge_time")
    fc = _parse_iso_or_epoch(fc_time)
    if not fc:
        return None
    now = datetime.now(timezone.utc)
    return seconds_to_dhms(int((now - fc).total_seconds()))

def set_full_charge_now():
    """Reset full charge timestamp to current time and zero runtime.

    Also anchors the uptime baseline to avoid re-counting current session.
    """
    state = load_state()
    now_iso = _now_utc_iso()
    state["battery_full_charge_time"] = now_iso
    state["total_runtime_seconds"] = 0
    state["last_update"] = now_iso
    state["last_boot_time"] = _get_boot_time_epoch()
    state["last_uptime"] = _get_system_uptime_seconds()
    save_state(state)
    return state["battery_full_charge_time"]

WITTY_LOG = Path("/home/pi/wittypi/wittyPi.log")

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
