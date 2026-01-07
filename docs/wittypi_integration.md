# Witty Pi Schedule Integration for InkyPi

## Overview

This implementation adds Witty Pi power cycling support to InkyPi, enabling the system to automatically manage Raspberry Pi power states based on defined schedules. When running in "oneshot" or "battery mode" (powered by Witty Pi), the InkyPi system will automatically generate a Witty Pi schedule file that coordinates with the active playlist's time window.

## Architecture

### Components

1. **`utils/wittypi_schedule.py`** - Core schedule generation utility
   - `WittyPiScheduleGenerator` class: Converts human-readable time windows and intervals into Witty Pi schedule format
   - `remove_schedule_file()` function: Cleans up schedule files when not in battery mode

2. **Model Updates (`src/model.py`)**
   - Extended `Playlist` class with Witty Pi configuration fields:
     - `wittypi_enabled`: Boolean to enable/disable for this playlist
     - `wittypi_start_time`: Daily power-on time (HH:MM)
     - `wittypi_end_time`: Daily power-off time (HH:MM)
     - `wittypi_cycle_minutes`: Interval between power cycles (minutes)
     - `wittypi_timezone`: Timezone for schedule calculations

3. **Flask Routes (`src/blueprints/playlist.py`)**
   - Updated `create_playlist()` and `update_playlist()` routes to accept and save Witty Pi settings
   - Settings persist in the device configuration file

4. **UI Updates (`src/templates/playlist.html`)**
   - New toggle to enable Witty Pi for each playlist
   - Time range pickers (separate from display window)
   - Cycle interval input (15-1440 minutes)
   - Timezone dropdown (supports 8 common zones, easily extensible)

5. **Boot Integration (`src/inkypi.py`)**
   - Detects oneshot/battery mode at startup
   - Auto-generates schedule for active playlist if enabled
   - Removes schedule when booting in normal mode

## Configuration

### How to Enable Witty Pi for a Playlist

1. Go to the Playlists page in InkyPi web UI
2. Create a new playlist or edit an existing one
3. Enable "Enable Witty Pi Power Cycling" checkbox
4. Set the desired power-on window (e.g., 6:00 AM - 10:00 PM)
5. Set cycle interval in minutes (e.g., 60 for hourly cycles)
6. Select your timezone
7. Save the playlist

### Configuration Example (in device.json)

```json
{
  "playlist_config": {
    "playlists": [
      {
        "name": "Day Display",
        "start_time": "06:00",
        "end_time": "22:00",
        "wittypi_enabled": true,
        "wittypi_start_time": "06:00",
        "wittypi_end_time": "22:00",
        "wittypi_cycle_minutes": 60,
        "wittypi_timezone": "America/New_York",
        "plugins": [...]
      }
    ]
  }
}
```

## How It Works

### Schedule Generation Algorithm

The generator performs the following calculations:

1. **Input Parameters**: Current time, daily power window (e.g., 6 AM - 10 PM), cycle duration (e.g., 60 minutes), timezone

2. **Cycle Calculation**:
   - If current time is before the window starts: Start cycle at window open time
   - If current time is after the window ends: Schedule cycle for window open next day
   - If within window: Calculate the next cycle boundary and start then

3. **Example Calculation**:
   ```
   Current time: 8:30 AM
   Window: 6:00 AM - 10:00 PM (16 hours)
   Cycle: 60 minutes
   
   Time in window: 2.5 hours = 150 minutes
   Cycles completed: 150 / 60 = 2 (with remainder)
   Next cycle boundary: (2 + 1) × 60 = 180 minutes from window start
   Next cycle start: 6:00 AM + 180 min = 9:00 AM
   ```

4. **Witty Pi Schedule Format**:
   ```
   BEGIN   2025-01-07 09:00:00
   END     2025-01-07 10:00:00
   
   ON M10 WAIT
   OFF M50
   ```
   - `ON M10 WAIT`: Powers on, runs for 10 minutes, then allows InkyPi to handle shutdown
   - `OFF M50`: Powers off for remaining 50 minutes of the cycle

### Boot Modes

**Oneshot/Battery Mode Detection**:
- Environment variable: `WITTYPI_ONESHOT=1`
- File presence: `/tmp/wittypi_oneshot`
- If detected, generate schedule for the active playlist (if Witty Pi enabled)

**Normal Mode**:
- Schedule file is removed to prevent power cycling

### Generated Schedule Location

- Default: `/home/pi/wittypi/schedule.wpi`
- Regenerated on each boot in battery mode
- Single cycle per boot (only covers the next ON/OFF interval)

## Integration Points

### At Startup (inkypi.py)

```python
# Detect boot mode
is_oneshot_mode = os.getenv('WITTYPI_ONESHOT') == '1' or os.path.exists('/tmp/wittypi_oneshot')

if is_oneshot_mode:
    # Find active playlist
    active_playlist = playlist_manager.determine_active_playlist(datetime.now())
    
    if active_playlist and active_playlist.wittypi_enabled:
        # Generate schedule for this cycle
        generator = WittyPiScheduleGenerator(...)
        generator.write_schedule_file()
else:
    # Normal mode - clean up any existing schedule
    remove_schedule_file()
```

### On Playlist Update

When a user modifies playlist settings via the web UI, the changes are immediately saved to `device.json`. The schedule is regenerated on the next boot in battery mode.

## Timezone Support

Built-in timezones (easily extensible in `playlist.html`):
- UTC
- US/Eastern
- US/Central
- US/Mountain
- US/Pacific
- Europe/London
- Europe/Paris
- Asia/Tokyo
- Australia/Sydney

Uses `pytz` library for timezone handling.

## Error Handling

- Invalid timezones default to UTC
- Missing playlists are logged and skipped
- File write errors are logged and reported
- Graceful fallback if Witty Pi module unavailable

## Testing

A test script is provided: `test_wittypi_schedule.py`

Run with:
```bash
cd /path/to/InkyPi
python test_wittypi_schedule.py
```

Tests several scenarios:
1. Current time at start of window
2. Current time mid-cycle
3. Current time before window
4. Current time after window
5. Wrapping windows (e.g., 21:00 - 03:00)

## Example Use Case

**Setup**: Battery-powered InkyPi displaying weather during daylight hours

**Configuration**:
- Active Playlist: "Day Display"
- Display Window: 6 AM - 10 PM
- Witty Pi Enabled: Yes
- Power Window: 6 AM - 10 PM
- Cycle: 60 minutes
- Timezone: America/New_York

**Behavior**:
- System boots at random time (Witty Pi powered it on)
- Schedule for next power cycle is created
- InkyPi displays current weather plugin
- After 10 minutes, displays will refresh
- After 60 minutes total, system powers down
- Witty Pi powers back on next cycle hour
- Process repeats

**Power Consumption**:
- 10 minutes per hour active (≈17% duty cycle)
- 50 minutes per hour powered down
- Ideal for battery/solar-powered displays

## Extending the Implementation

### Adding More Timezones

Edit `src/templates/playlist.html` in the wittypi_timezone select:

```html
<option value="Asia/Mumbai">Asia/Mumbai</option>
<option value="Africa/Cairo">Africa/Cairo</option>
```

### Customizing ON Duration

Edit `src/utils/wittypi_schedule.py`, `generate_schedule_content()` method:

```python
# Currently: 10 minutes reserved for ON/WAIT
on_duration = 10  # Adjust as needed
off_duration = self.cycle_minutes - on_duration
```

### Boot Mode Detection Enhancement

If your Witty Pi setup uses different signals, modify `src/inkypi.py`:

```python
is_oneshot_mode = (
    os.getenv('WITTYPI_ONESHOT') == '1' or
    os.path.exists('/tmp/wittypi_oneshot') or
    check_custom_indicator()  # Your function
)
```

## Troubleshooting

### Schedule not generating
1. Verify boot mode detection: Check for `WITTYPI_ONESHOT` env var or `/tmp/wittypi_oneshot` file
2. Check logs: `journalctl -u inkypi` or app logs
3. Verify playlist has Witty Pi enabled
4. Ensure `/home/pi/wittypi/` directory exists with proper permissions

### Wrong power-off time
1. Check timezone setting matches your location
2. Verify current system time is correct
3. Review calculation: `(cycles_completed + 1) × cycle_minutes`

### File not written
1. Check permissions on `/home/pi/wittypi/`
2. Verify disk space available
3. Review error logs for write failures

## Future Enhancements

- Multiple cycles per boot (extended schedules)
- Manual schedule file editing UI
- Schedule preview before save
- Power consumption calculator
- Temperature-based cycle adjustments
- Integration with system uptime tracking
