# Battery Power Monitoring

InkyPi now includes comprehensive battery power monitoring capabilities for Raspberry Pi systems with battery HATs, UPS modules, or power management systems. This guide explains how to set up and use battery monitoring.

## Overview

The battery monitoring system automatically detects and supports multiple types of battery monitoring hardware:

1. **Linux Power Supply Interface** - Standard interface used by most UPS HATs and battery systems
2. **INA219 Power Monitor** - High-precision current/voltage sensor chip
3. **Custom I2C Battery Monitors** - Extensible support for custom hardware

## Supported Hardware

### UPS HATs with Power Supply Interface

Most modern UPS HATs for Raspberry Pi expose battery information through the Linux power supply interface. These include:

- **Waveshare UPS HAT** (multiple models)
- **Geekworm X728 UPS** 
- **PiJuice HAT**
- **52Pi UPS Plus**
- **Other battery HATs** that implement the standard power supply interface

No additional configuration is needed for these devices - InkyPi will automatically detect them.

### INA219-based Power Monitors

The INA219 is a popular current/voltage monitoring chip used in many DIY power monitoring solutions. To use it with InkyPi:

1. **Install the INA219 Python library:**
   ```bash
   source /usr/local/inkypi/venv_inkypi/bin/activate
   pip install pi-ina219
   deactivate
   ```

2. **Connect your INA219:**
   - VCC to 3.3V
   - GND to Ground
   - SDA to GPIO 2 (SDA)
   - SCL to GPIO 3 (SCL)
   - V- to battery negative
   - V+ to battery positive

3. **Enable I2C** (if not already enabled):
   ```bash
   sudo raspi-config
   # Navigate to: Interface Options > I2C > Enable
   ```

4. **Restart InkyPi:**
   ```bash
   sudo systemctl restart inkypi.service
   ```

## Features

### System Stats Logging

When "Log System Stats" is enabled in the Settings page, battery metrics are automatically included in the periodic system stats logging. This includes:

- **Battery Percentage**: Remaining battery capacity (0-100%)
- **Voltage**: Current battery voltage in volts
- **Current**: Current draw in milliamps (negative = discharging, positive = charging)
- **Power**: Power consumption/generation in watts
- **Status**: Battery status (Charging, Discharging, Full, Idle)
- **Temperature**: Battery temperature in Celsius (if available)

To enable system stats logging:
1. Go to Settings in the web UI
2. Check "Log System Stats"
3. Save settings

View the logs to see battery metrics:
```bash
journalctl -u inkypi -f
```

Example log entry:
```
System Stats: {
  'cpu_percent': 15.2,
  'memory_percent': 42.3,
  'disk_percent': 35.1,
  'cpu_temperature': 47.5,
  'battery': {
    'available': True,
    'backend': 'power_supply(BAT0)',
    'percentage': 85.0,
    'voltage': 4.15,
    'current': -450.0,
    'power': 1.87,
    'status': 'Discharging'
  }
}
```

### Battery Status API

Query the current battery status via the REST API:

```bash
curl http://your-inkypi-ip/battery-status
```

Response format:
```json
{
  "available": true,
  "backend": "power_supply(BAT0)",
  "percentage": 85.0,
  "voltage": 4.15,
  "current": -450.0,
  "power": 1.87,
  "status": "Discharging",
  "temperature": 32.5
}
```

If no battery monitoring is available:
```json
{
  "available": false,
  "backend": "none"
}
```

## Troubleshooting

### No Battery Detected

If InkyPi reports no battery monitoring available, check:

1. **Verify hardware is connected properly**
   - Check physical connections
   - Ensure UPS HAT is properly seated on GPIO pins

2. **Check if your UPS HAT is recognized by the system:**
   ```bash
   ls /sys/class/power_supply/
   ```
   You should see entries like `BAT0`, `BAT1`, or similar.

3. **For INA219:**
   - Verify I2C is enabled: `sudo i2cdetect -y 1`
   - You should see address `40` (or configured address) in the output
   - Check that the pi-ina219 library is installed

4. **Check InkyPi logs for detection messages:**
   ```bash
   journalctl -u inkypi -n 100 | grep -i battery
   ```

### Inaccurate Readings

For INA219-based monitors:

1. **Calibrate the shunt resistor value** in `/home/runner/work/InkyPi/InkyPi/src/utils/battery_utils.py`:
   ```python
   # In _try_ina219_backend method, adjust shunt_ohms:
   ina = INA219(shunt_ohms=0.1, address=0x40)  # Change 0.1 to your actual value
   ```

2. **Check the I2C address** - default is 0x40, but some boards use different addresses:
   ```bash
   sudo i2cdetect -y 1
   ```

3. **Restart InkyPi after changes:**
   ```bash
   sudo systemctl restart inkypi.service
   ```

## Custom Battery Monitor Integration

To integrate a custom battery monitoring solution:

1. **Edit** `/home/runner/work/InkyPi/InkyPi/src/utils/battery_utils.py`

2. **Implement a custom backend class** following the pattern of existing backends:
   ```python
   class CustomBackend:
       def __init__(self, config):
           # Initialize your hardware
           pass
       
       def get_metrics(self) -> Dict[str, Any]:
           # Read and return battery metrics
           return {
               "percentage": 85.0,
               "voltage": 4.15,
               "current": -450.0,
               "status": "Discharging"
           }
   ```

3. **Add detection logic** in `BatteryMonitor._initialize_backend()`:
   ```python
   def _initialize_backend(self):
       # ... existing detection methods ...
       
       # Try custom backend
       if self._try_custom_backend():
           return
   ```

4. **Restart InkyPi** to load the new backend

## Best Practices

### Power Efficiency

- InkyPi is already optimized for low power consumption with E-Ink displays
- Battery monitoring adds minimal overhead
- Consider increasing the plugin cycle interval for battery-powered setups
- E-Ink displays maintain their image without power, perfect for battery operation

### Monitoring and Alerts

To set up battery level alerts, you can:

1. **Create a script** that queries the battery status API:
   ```bash
   #!/bin/bash
   BATTERY_LEVEL=$(curl -s http://localhost/battery-status | jq -r '.percentage')
   if (( $(echo "$BATTERY_LEVEL < 20" | bc -l) )); then
       echo "Low battery: ${BATTERY_LEVEL}%"
       # Add notification logic here
   fi
   ```

2. **Schedule with cron:**
   ```bash
   crontab -e
   # Add: */30 * * * * /path/to/battery-check.sh
   ```

### Recommended Settings for Battery Operation

For extended battery life:
- Increase plugin cycle interval to 1-2 hours or more
- Disable unnecessary plugins
- Use scheduled playlists to reduce update frequency during certain hours
- Enable "Log System Stats" only when needed for diagnostics

## Hardware Recommendations

For reliable battery monitoring, we recommend:

1. **Waveshare UPS HAT Series** - Good balance of features and price
2. **PiJuice HAT** - Advanced power management with software support
3. **Geekworm X728 V2.3** - High capacity UPS with display
4. **DIY INA219 Solution** - Budget-friendly option for makers

All of these work out-of-the-box with InkyPi's battery monitoring system.

## Further Reading

- [Raspberry Pi Power Supply Documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#power-supply)
- [INA219 Datasheet](https://www.ti.com/product/INA219)
- [Linux Power Supply Class](https://www.kernel.org/doc/html/latest/power/power_supply_class.html)
