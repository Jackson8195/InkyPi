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
        
        return today_start, today_end
    
    def generate_schedule_content(self, current_dt=None):
        """
        Generate a 24-hour Witty Pi schedule that repeats daily.
        
        Logic:
        - BEGIN at the next cycle boundary within the configured window
        - Emit ON 10 / OFF (cycle-10) while inside the window
        - At window end, emit a single OFF spanning to the next day's window start
        - Build exactly 24 hours of instructions; Witty Pi will repeat the loop
        - END is set 100 years out (indefinite repeat)
        """
        if current_dt is None:
            current_dt = datetime.now(self.tz)
        else:
            if current_dt.tzinfo is None:
                current_dt = self.tz.localize(current_dt)
            else:
                current_dt = current_dt.astimezone(self.tz)

        # Window helpers
        start_hour, start_min = map(int, self.start_time_str.split(":"))
        end_hour, end_min = map(int, self.end_time_str.split(":"))

        def fmt_duration(minutes):
            # Prefer hours when evenly divisible to keep schedule compact
            if minutes % 60 == 0:
                hours = minutes // 60
                return f"H{hours}"
            return f"M{minutes}"

        def window_bounds(dt):
            ws = dt.replace(hour=start_hour, minute=start_min, second=0, microsecond=0)
            we = dt.replace(hour=end_hour, minute=end_min, second=0, microsecond=0)
            if we <= ws:
                we += timedelta(days=1)
            return ws, we

        window_start, window_end = window_bounds(current_dt)

        # Find the first ON time (next cycle boundary inside window)
        if current_dt < window_start:
            first_on = window_start
        elif current_dt >= window_end:
            # Past today's window, start at next day's window start
            next_day = current_dt + timedelta(days=1)
            window_start, window_end = window_bounds(next_day)
            first_on = window_start
        else:
            minutes_into_window = (current_dt - window_start).total_seconds() / 60
            cycles_completed = int(minutes_into_window // self.cycle_minutes)
            first_on = window_start + timedelta(minutes=(cycles_completed + 1) * self.cycle_minutes)
            if first_on > window_end:
                # No more slots today; start next day
                next_day = current_dt + timedelta(days=1)
                window_start, window_end = window_bounds(next_day)
                first_on = window_start

        begin_dt = first_on
        end_dt = begin_dt + timedelta(days=365*100)

        cursor = begin_dt
        day_span_end = begin_dt + timedelta(hours=24)
        lines = [
            f"BEGIN\t{begin_dt.strftime('%Y-%m-%d %H:%M:%S')}",
            f"END\t{end_dt.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        on_minutes = 10
        cycle_minutes = self.cycle_minutes

        while cursor < day_span_end:
            # Ensure we are within a window; if not, jump to next window start
            window_start, window_end = window_bounds(cursor)
            if cursor < window_start:
                # Jump to window start with an OFF covering the gap
                gap_minutes = int((window_start - cursor).total_seconds() // 60)
                if gap_minutes > 0:
                    lines.append(f"OFF\t{fmt_duration(gap_minutes)}")
                cursor = window_start
                if cursor >= day_span_end:
                    break

            # If we're past the current window, add gap OFF to next day's window
            elif cursor >= window_end:
                next_window_start = window_start + timedelta(days=1)
                gap_minutes = int((next_window_start - cursor).total_seconds() // 60)
                if gap_minutes > 0:
                    lines.append(f"OFF\t{fmt_duration(gap_minutes)}")
                cursor = next_window_start
                if cursor >= day_span_end:
                    break
                continue

            # Schedule ON
            lines.append(f"ON\tM{on_minutes}\tWAIT")
            on_end = cursor + timedelta(minutes=on_minutes)

            # Decide OFF duration
            next_cycle_start = cursor + timedelta(minutes=cycle_minutes)
            if next_cycle_start <= window_end and next_cycle_start < day_span_end:
                off_minutes = cycle_minutes - on_minutes
                lines.append(f"OFF\t{fmt_duration(off_minutes)}")
                cursor = next_cycle_start
            else:
                # Finish the 24h span exactly; last OFF bridges to next loop BEGIN
                off_minutes = int((day_span_end - on_end).total_seconds() // 60)
                if off_minutes > 0:
                    lines.append(f"OFF\t{fmt_duration(off_minutes)}")
                break

        return "\n".join(lines)
    
    def write_schedule_file(self, current_dt=None, file_path=WITTYPI_SCHEDULE_PATH):
        """
        Generate and write the full-day schedule file to disk, then activate it.
        
        This method should be called once when the schedule is set in the playlist editor.
        The schedule will remain active until the user changes it or a new mount is detected.
        
        Args:
            current_dt (datetime): Current datetime (defaults to now)
            file_path (str): Path to write the schedule file
            
        Returns:
            bool: True if successful, False otherwise
        """
        import subprocess
        
        try:
            content = self.generate_schedule_content(current_dt)
            if content is None:
                return False
            # Debug: show the entire schedule content before writing
            logger.debug("Generated Witty Pi schedule content to write:\n%s", content)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Write file with explicit LF newlines and ensure it is flushed to disk
            with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            
            logger.info(f"Wrote Witty Pi schedule to {file_path}")
            # Debug: read back and log what was saved
            try:
                with open(file_path, 'r', encoding='utf-8') as rf:
                    saved = rf.read()
                logger.debug("Saved Witty Pi schedule at %s:\n%s", file_path, saved)
            except Exception as read_err:
                logger.debug("Unable to read back saved schedule for debug: %s", read_err)
            
            # Activate the schedule by running Witty Pi's runScript.sh
            try:
                result = subprocess.run(
                    ["sudo", "/home/pi/wittypi/runScript.sh"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                # Debug: capture detailed stdout/stderr from activation
                logger.debug("runScript.sh stdout:\n%s", result.stdout)
                logger.debug("runScript.sh stderr:\n%s", result.stderr)
                if result.returncode == 0:
                    logger.info("Witty Pi schedule activated successfully")
                else:
                    logger.error(f"Failed to activate Witty Pi schedule: {result.stderr}")
                    return False
            except subprocess.TimeoutExpired:
                logger.error("Witty Pi runScript.sh timed out")
                return False
            except Exception as e:
                logger.error(f"Error running Witty Pi activation script: {e}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Failed to write Witty Pi schedule: {e}")
            return False
    
    @classmethod
    def remove_schedule(cls, file_path=WITTYPI_SCHEDULE_PATH):
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
    
    @classmethod
    def generate_for_playlist(cls, wittypi_enabled, wittypi_start_time, wittypi_end_time, wittypi_cycle_minutes, wittypi_timezone):
        """
        Generate and write Witty Pi schedule file if enabled, or remove it if disabled.
        
        This is called when a playlist is created or updated via the web UI.
        
        Args:
            wittypi_enabled (bool): Whether Witty Pi is enabled for this playlist
            wittypi_start_time (str): Start time in "HH:MM" format
            wittypi_end_time (str): End time in "HH:MM" format
            wittypi_cycle_minutes (int): Cycle interval in minutes
            wittypi_timezone (str): Timezone string
        """
        if not wittypi_enabled:
            cls.remove_schedule()
            return
        
        try:
            generator = cls(
                start_time_str=wittypi_start_time,
                end_time_str=wittypi_end_time,
                cycle_minutes=wittypi_cycle_minutes,
                timezone_str=wittypi_timezone
            )
            if generator.write_schedule_file():
                logger.info("Witty Pi schedule generated and activated successfully")
            else:
                logger.error("Failed to generate Witty Pi schedule")
        except Exception as e:
            logger.error(f"Error generating Witty Pi schedule: {e}")


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
