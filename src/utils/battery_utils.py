"""
Battery monitoring utilities for InkyPi.

This module provides battery power metrics monitoring for Raspberry Pi devices
with various battery HATs, UPS modules, or power management systems.

Supported battery monitoring methods:
1. I2C-based battery monitors (common in UPS HATs)
2. INA219 power monitor
3. System power supply interface (/sys/class/power_supply/)
4. Custom voltage monitoring via ADC

The module gracefully handles cases where no battery monitoring is available.
"""

import logging
import os
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class BatteryMonitor:
    """
    Battery monitoring interface that supports multiple backend implementations.
    
    This class attempts to detect and use available battery monitoring hardware
    on the Raspberry Pi. It tries multiple methods in order of preference and
    falls back gracefully if no battery monitoring is available.
    """
    
    def __init__(self):
        """Initialize the battery monitor with auto-detection."""
        self.backend = None
        self.backend_name = "none"
        self._initialize_backend()
    
    def _initialize_backend(self):
        """
        Attempt to initialize battery monitoring backend.
        
        Tries multiple detection methods in order:
        1. System power supply interface (most common)
        2. INA219 power monitor
        3. I2C-based battery monitors
        """
        # Try system power supply interface first
        if self._try_power_supply_backend():
            return
        
        # Try INA219 power monitor
        if self._try_ina219_backend():
            return
        
        # Try generic I2C battery monitors
        if self._try_i2c_backend():
            return
        
        logger.info("No battery monitoring hardware detected. Battery metrics will not be available.")
    
    def _try_power_supply_backend(self) -> bool:
        """
        Try to initialize using Linux power supply interface.
        
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            power_supply_path = "/sys/class/power_supply"
            if not os.path.exists(power_supply_path):
                return False
            
            # Look for battery devices
            devices = os.listdir(power_supply_path)
            battery_devices = [d for d in devices if 'battery' in d.lower() or 'bat' in d.lower()]
            
            if not battery_devices:
                return False
            
            # Use the first battery device found
            battery_device = battery_devices[0]
            battery_path = os.path.join(power_supply_path, battery_device)
            
            # Verify we can read basic battery info
            capacity_file = os.path.join(battery_path, "capacity")
            if os.path.exists(capacity_file):
                with open(capacity_file, 'r') as f:
                    f.read()  # Test read
                
                self.backend = PowerSupplyBackend(battery_path)
                self.backend_name = f"power_supply({battery_device})"
                logger.info(f"Initialized battery monitoring using power supply interface: {battery_device}")
                return True
        except Exception as e:
            logger.debug(f"Failed to initialize power supply backend: {e}")
        
        return False
    
    def _try_ina219_backend(self) -> bool:
        """
        Try to initialize INA219 power monitoring chip.
        
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            # Try to import INA219 library
            from ina219 import INA219
            from ina219 import DeviceRangeError
            
            # Try to initialize INA219 on default I2C address (0x40)
            ina = INA219(shunt_ohms=0.1, address=0x40)
            ina.configure()
            
            # Test read to verify device is present
            ina.voltage()
            
            self.backend = INA219Backend(ina)
            self.backend_name = "ina219"
            logger.info("Initialized battery monitoring using INA219 power monitor")
            return True
        except ImportError:
            logger.debug("INA219 library not installed")
        except Exception as e:
            logger.debug(f"Failed to initialize INA219 backend: {e}")
        
        return False
    
    def _try_i2c_backend(self) -> bool:
        """
        Try to initialize generic I2C battery monitor.
        
        Returns:
            bool: True if successful, False otherwise.
        """
        try:
            # This is a placeholder for custom I2C battery monitors
            # Users can extend this to support their specific hardware
            pass
        except Exception as e:
            logger.debug(f"Failed to initialize I2C backend: {e}")
        
        return False
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current battery metrics.
        
        Returns:
            Dict containing battery metrics with the following keys:
            - available (bool): Whether battery monitoring is available
            - backend (str): Name of the monitoring backend used
            - percentage (float): Battery percentage (0-100), if available
            - voltage (float): Battery voltage in volts, if available
            - current (float): Current draw in mA (negative for discharge), if available
            - power (float): Power in watts, if available
            - status (str): Battery status (Charging/Discharging/Full/Unknown), if available
            - temperature (float): Battery temperature in Celsius, if available
        """
        if not self.backend:
            return {
                "available": False,
                "backend": self.backend_name
            }
        
        try:
            metrics = self.backend.get_metrics()
            metrics["available"] = True
            metrics["backend"] = self.backend_name
            return metrics
        except Exception as e:
            logger.warning(f"Failed to read battery metrics: {e}")
            return {
                "available": False,
                "backend": self.backend_name,
                "error": str(e)
            }
    
    def is_available(self) -> bool:
        """
        Check if battery monitoring is available.
        
        Returns:
            bool: True if battery monitoring is available, False otherwise.
        """
        return self.backend is not None


class PowerSupplyBackend:
    """Backend for reading battery info from Linux power supply interface."""
    
    def __init__(self, device_path: str):
        """
        Initialize power supply backend.
        
        Args:
            device_path: Path to the power supply device (e.g., /sys/class/power_supply/BAT0)
        """
        self.device_path = device_path
    
    def _read_sysfs_file(self, filename: str) -> Optional[str]:
        """
        Read a value from a sysfs file.
        
        Args:
            filename: Name of the file to read
            
        Returns:
            File contents as string, or None if file doesn't exist or can't be read
        """
        filepath = os.path.join(self.device_path, filename)
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    return f.read().strip()
        except Exception as e:
            logger.debug(f"Failed to read {filepath}: {e}")
        return None
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get battery metrics from power supply interface."""
        metrics = {}
        
        # Read capacity (percentage)
        capacity = self._read_sysfs_file("capacity")
        if capacity:
            try:
                metrics["percentage"] = float(capacity)
            except ValueError:
                pass
        
        # Read voltage (usually in microvolts)
        voltage_now = self._read_sysfs_file("voltage_now")
        if voltage_now:
            try:
                metrics["voltage"] = float(voltage_now) / 1_000_000  # Convert µV to V
            except ValueError:
                pass
        
        # Read current (usually in microamps)
        current_now = self._read_sysfs_file("current_now")
        if current_now:
            try:
                metrics["current"] = float(current_now) / 1_000  # Convert µA to mA
            except ValueError:
                pass
        
        # Read power (usually in microwatts)
        power_now = self._read_sysfs_file("power_now")
        if power_now:
            try:
                metrics["power"] = float(power_now) / 1_000_000  # Convert µW to W
            except ValueError:
                pass
        
        # Read status
        status = self._read_sysfs_file("status")
        if status:
            metrics["status"] = status
        
        # Read temperature (usually in tenths of degree Celsius)
        temp = self._read_sysfs_file("temp")
        if temp:
            try:
                metrics["temperature"] = float(temp) / 10
            except ValueError:
                pass
        
        # Calculate power if we have voltage and current but not power
        if "power" not in metrics and "voltage" in metrics and "current" in metrics:
            metrics["power"] = (metrics["voltage"] * metrics["current"]) / 1000  # V * mA / 1000 = W
        
        return metrics


class INA219Backend:
    """Backend for reading battery info from INA219 power monitor."""
    
    def __init__(self, ina219):
        """
        Initialize INA219 backend.
        
        Args:
            ina219: Configured INA219 instance
        """
        self.ina = ina219
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get battery metrics from INA219."""
        metrics = {}
        
        try:
            # Read voltage in volts
            metrics["voltage"] = self.ina.voltage()
            
            # Read current in mA (negative means discharging)
            metrics["current"] = self.ina.current()
            
            # Read power in mW and convert to W
            metrics["power"] = self.ina.power() / 1000
            
            # Determine status based on current direction
            if metrics["current"] > 10:  # Threshold to avoid noise
                metrics["status"] = "Charging"
            elif metrics["current"] < -10:
                metrics["status"] = "Discharging"
            else:
                metrics["status"] = "Idle"
        
        except Exception as e:
            logger.warning(f"Error reading from INA219: {e}")
        
        return metrics


# Global battery monitor instance
_battery_monitor = None


def get_battery_monitor() -> BatteryMonitor:
    """
    Get the global battery monitor instance.
    
    Returns:
        BatteryMonitor: The global battery monitor instance
    """
    global _battery_monitor
    if _battery_monitor is None:
        _battery_monitor = BatteryMonitor()
    return _battery_monitor


def get_battery_metrics() -> Dict[str, Any]:
    """
    Get current battery metrics (convenience function).
    
    Returns:
        Dict containing battery metrics
    """
    monitor = get_battery_monitor()
    return monitor.get_metrics()
