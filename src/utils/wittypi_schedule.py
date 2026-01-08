"""
Witty Pi Schedule Generator

This module creates Witty Pi schedule scripts (.wpi files) for managing power cycles
on Raspberry Pi systems. It handles the conversion from human-readable time windows
and intervals to Witty Pi's minute-based scheduling format.

Example schedule format:
    BEGIN   2025-12-09 22:00:00
    END     2026-12-04 13:00:00
    
    ON M10 WAIT
    OFF M50
    ON M10 WAIT
    OFF M50
"""

import os
import logging
from datetime import datetime, timedelta
from pytz import timezone as pytz_timezone

logger = logging.getLogger(__name__)

WITTYPI_SCHEDULE_PATH = "/home/pi/wittypi/schedule.wpi"


class WittyPiScheduleGenerator:
    """Generates Witty Pi schedule scripts based on time windows and cycle intervals."""
    
    def __init__(self, start_time_str, end_time_str, cycle_minutes, timezone_str="UTC"):
        """
        Initialize the schedule generator.
        
        Args:
            start_time_str (str): Start time in 24-hour format "HH:MM" (e.g., "06:00")
            end_time_str (str): End time in 24-hour format "HH:MM" (e.g., "22:00")
            cycle_minutes (int): Duration of each power cycle in minutes
            timezone_str (str): Timezone string (e.g., "America/New_York")
        """
        self.start_time_str = start_time_str
        self.end_time_str = end_time_str
        self.cycle_minutes = cycle_minutes
        self.timezone_str = timezone_str
        
        try:
            self.tz = pytz_timezone(timezone_str)
        except Exception as e:
            logger.warning(f"Invalid timezone '{timezone_str}', using UTC: {e}")
            self.tz = pytz_timezone("UTC")
    
    def _get_next_cycle_time(self, current_dt, start_time_str, end_time_str):
        """
        Calculate the next ON/OFF cycle based on current time and daily time window.
        
        Args:
            current_dt (datetime): Current datetime with timezone
            start_time_str (str): Start time in "HH:MM" format
            end_time_str (str): End time in "HH:MM" format
            
        Returns:
            tuple: (cycle_start_dt, cycle_end_dt) or (None, None) if outside window
        """
        # Parse start and end times
        start_hour, start_min = map(int, start_time_str.split(":"))
        end_hour, end_min = map(int, end_time_str.split(":"))
        
        # Create today's start and end times with timezone
        today_start = current_dt.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
        today_end = current_dt.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
        
        # If end time is before start time (wraps to next day), adjust
        if today_end <= today_start:
            if current_dt < today_start:
                # Before start time today, use today's window
                pass
            else:
                # After start time, end time is tomorrow
                today_end += timedelta(days=1)
        
        # Check if current time is within the window
        if current_dt < today_start:
            # Not yet in today's window, start at beginning
            cycle_start = today_start
        elif current_dt >= today_end:
            # Past today's window, start at beginning tomorrow
            tomorrow_start = today_start + timedelta(days=1)
            cycle_start = tomorrow_start
        else:
            # Within window, calculate next cycle boundary
            time_in_window = (current_dt - today_start).total_seconds() / 60
            cycles_completed = int(time_in_window // self.cycle_minutes)
            next_cycle_start_minutes = (cycles_completed + 1) * self.cycle_minutes
            cycle_start = today_start + timedelta(minutes=next_cycle_start_minutes)
            
            # If calculated start goes past end time, start at beginning tomorrow
            if cycle_start >= today_end:
                tomorrow_start = today_start + timedelta(days=1)
                cycle_start = tomorrow_start
        
        # Calculate cycle end time (when system powers off)
        cycle_end = cycle_start + timedelta(minutes=self.cycle_minutes)
        
        # If cycle_end extends past daily end time, cap it at daily end time
        # (for cycles that span across the end of the window)
        end_boundary = cycle_start.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
        # Handle wrapping windows
        if end_boundary <= cycle_start:
            end_boundary += timedelta(days=1)
        if cycle_end > end_boundary:
            cycle_end = end_boundary
        
        return cycle_start, cycle_end
    
    def generate_schedule_content(self, current_dt=None):
        """
        Generate the Witty Pi schedule file content.
        
        Args:
            current_dt (datetime): Current datetime (defaults to now in configured timezone)
            
        Returns:
            str: The schedule file content as a string
        """
        if current_dt is None:
            current_dt = datetime.now(self.tz)
        else:
            # Ensure timezone awareness
            if current_dt.tzinfo is None:
                current_dt = self.tz.localize(current_dt)
            else:
                current_dt = current_dt.astimezone(self.tz)
        
        # Get the next cycle
        cycle_start, cycle_end = self._get_next_cycle_time(
            current_dt, self.start_time_str, self.end_time_str
        )
        
        if cycle_start is None or cycle_end is None:
            logger.error("Failed to calculate cycle times")
            return None
        
        # Format dates for Witty Pi (YYYY-MM-DD HH:MM:SS)
        begin_str = cycle_start.strftime("%Y-%m-%d %H:%M:%S")
        end_str = cycle_end.strftime("%Y-%m-%d %H:%M:%S")
        
        # Calculate OFF duration in minutes
        # This is how long the system stays off until next ON cycle
        off_duration = self.cycle_minutes - 10  # 10 minutes reserved for ON/WAIT
        
        # Build schedule content
        lines = [
            f"BEGIN   {begin_str}",
            f"END     {end_str}",
            "",
            "ON M10 WAIT",
            f"OFF M{off_duration}",
        ]
        
        content = "\n".join(lines)
        return content
    
    def write_schedule_file(self, current_dt=None, file_path=WITTYPI_SCHEDULE_PATH):
        """
        Generate and write the schedule file to disk.
        
        Args:
            current_dt (datetime): Current datetime (defaults to now in configured timezone)
            file_path (str): Path to write the schedule file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            content = self.generate_schedule_content(current_dt)
            if content is None:
                return False
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Write file
            with open(file_path, 'w') as f:
                f.write(content)
            
            logger.info(f"Wrote Witty Pi schedule to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to write Witty Pi schedule: {e}")
            return False


def remove_schedule_file(file_path=WITTYPI_SCHEDULE_PATH):
    """
    Remove the Witty Pi schedule file.
    
    Args:
        file_path (str): Path to the schedule file
        
    Returns:
        bool: True if successful or file doesn't exist, False on error
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Removed Witty Pi schedule file: {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to remove Witty Pi schedule file: {e}")
        return False


def get_next_bootup_time(file_path=WITTYPI_SCHEDULE_PATH):
    """
    Read the next bootup time from the Witty Pi schedule file.
    
    Args:
        file_path (str): Path to the schedule file
        
    Returns:
        datetime: The next bootup datetime, or None if not available
    """
    try:
        if not os.path.exists(file_path):
            return None
        
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('BEGIN'):
                    # Format: BEGIN   2026-01-07 17:00:00
                    parts = line.split()
                    if len(parts) >= 3:
                        date_str = parts[1]
                        time_str = parts[2]
                        bootup_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
                        return bootup_dt
        return None
    except Exception as e:
        logger.error(f"Failed to read next bootup time: {e}")
        return None
