# Witty Pi Quick Start Guide

## What is Witty Pi Integration?

Witty Pi is a hardware power controller for Raspberry Pi. This integration allows InkyPi to automatically manage power cycles when running on battery/solar power through Witty Pi.

## Quick Setup

### 1. Enable for Your Playlist

- Navigate to **Playlists** in InkyPi
- Click edit on your playlist (or create a new one)
- Check **"Enable Witty Pi Power Cycling"**
- Set your preferred **Power On Time** (when the system should turn on)
- Set your **Power Off Time** (when the system should turn off)
- Choose a **Cycle Interval** (how often to power on/off)
  - Recommended: 60 minutes for normal displays
  - Use 30 minutes for frequent updates
  - Use 120 minutes for minimal power consumption
- Select your **Timezone**
- Save

### 2. What Happens Next

When your Pi powers up with Witty Pi:

1. ✅ InkyPi detects battery mode
2. ✅ Finds your active playlist
3. ✅ Generates a power schedule for the next cycle
4. ✅ Runs for about 10 minutes
5. ✅ Shuts down cleanly (InkyPi handles it)
6. ✅ Witty Pi powers down for the rest of the cycle
7. ✅ Cycle repeats at your set interval

## Examples

### Example 1: Daytime Weather Display

- **Power Window**: 6:00 AM - 10:00 PM
- **Cycle**: 60 minutes
- **Effect**: Powers on every hour during the day
- **Use**: Weather station, calendar, info display
- **Battery Life**: ~8 days on typical battery (10 min/hour usage)

### Example 2: Battery-Saver Dashboard

- **Power Window**: 6:00 AM - 10:00 PM  
- **Cycle**: 120 minutes
- **Effect**: Powers on every 2 hours
- **Use**: Low-priority status display
- **Battery Life**: ~15 days on typical battery

### Example 3: 24/7 Solar Display

- **Power Window**: 24:00 (all day, adjusted for sunlight)
- **Cycle**: 30 minutes
- **Effect**: Powers on every 30 minutes
- **Use**: Real-time monitoring
- **Battery Life**: Depends on solar input

## Settings Explained

| Setting | Purpose | Typical Values |
|---------|---------|---|
| Power Window | Limit cycles to certain hours | 6:00-22:00 (daytime) |
| Cycle Interval | Time between power-ons | 60 (hourly) |
| Timezone | Correct time calculations | Your local timezone |

## Testing Your Configuration

1. Boot your Pi with Witty Pi in battery mode
2. Check if InkyPi displays normally
3. Wait for the configured cycle time minus 5 minutes
4. System should shut down automatically
5. Witty Pi will power it back on at the next cycle

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Schedule not working | Verify battery mode detection / Check timezone |
| Powers off too early/late | Check system time / Review cycle math |
| Battery drains quickly | Reduce cycle frequency / Extend power window limits |
| Schedule file not found | Check `/home/pi/wittypi/` exists / Check permissions |

## Commands

### Check if running in battery mode
```bash
echo $WITTYPI_ONESHOT
# or
ls -la /tmp/wittypi_oneshot
```

### View generated schedule
```bash
cat /home/pi/wittypi/schedule.wpi
```

### Check InkyPi logs
```bash
journalctl -u inkypi -f
```

## Power Calculation

To estimate battery life:

1. **Duty Cycle** = (ON time) / (Cycle time)
   - Example: 10 min ON / 60 min cycle = 16.7%

2. **Battery Hours** = (Capacity mAh) / (Average Current mA)
   - Example: 5000 mAh / 500 mA = 10 hours max

3. **Estimated Days** = (Battery Hours × 24) × (1 - Duty Cycle)
   - Example: (10 × 24) × (1 - 0.167) = 200 hours ≈ 8 days

## Tips for Maximum Battery Life

1. ✅ Use longer cycle intervals (120 min instead of 60)
2. ✅ Limit power window to daylight hours
3. ✅ Use low-power plugins (avoid video/animation)
4. ✅ Disable refresh during off-window hours
5. ✅ Use e-ink displays (ultra low power)
6. ✅ Place solar panel in direct sunlight

## Support

For issues or questions:
- Check [wittypi_integration.md](wittypi_integration.md) for detailed documentation
- Review logs: `/var/log/inkypi/` or `journalctl -u inkypi`
- Visit Witty Pi documentation: http://www.geeekpi.com/wittypi/

---

**Version**: 1.0  
**Last Updated**: January 2025
