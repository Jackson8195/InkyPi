import pytest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils.battery_utils import BatteryMonitor, PowerSupplyBackend, get_battery_metrics


class TestBatteryMonitor:
    """Test the BatteryMonitor class."""
    
    def test_initialization(self):
        """Test that BatteryMonitor can be initialized."""
        monitor = BatteryMonitor()
        assert monitor is not None
        assert monitor.backend_name is not None
    
    def test_get_metrics_returns_dict(self):
        """Test that get_metrics returns a dictionary."""
        monitor = BatteryMonitor()
        metrics = monitor.get_metrics()
        assert isinstance(metrics, dict)
        assert 'available' in metrics
        assert 'backend' in metrics
    
    def test_is_available_returns_bool(self):
        """Test that is_available returns a boolean."""
        monitor = BatteryMonitor()
        result = monitor.is_available()
        assert isinstance(result, bool)
    
    def test_no_backend_returns_unavailable(self):
        """Test that when no backend is available, metrics indicate unavailability."""
        monitor = BatteryMonitor()
        if not monitor.is_available():
            metrics = monitor.get_metrics()
            assert metrics['available'] is False
            assert metrics['backend'] == 'none'


class TestPowerSupplyBackend:
    """Test the PowerSupplyBackend class."""
    
    def test_read_sysfs_nonexistent_file(self):
        """Test reading a non-existent sysfs file returns None."""
        backend = PowerSupplyBackend("/nonexistent/path")
        result = backend._read_sysfs_file("capacity")
        assert result is None
    
    def test_get_metrics_returns_dict(self):
        """Test that get_metrics returns a dictionary even for non-existent device."""
        backend = PowerSupplyBackend("/nonexistent/path")
        metrics = backend.get_metrics()
        assert isinstance(metrics, dict)


class TestBatteryMetricsFunction:
    """Test the convenience function for getting battery metrics."""
    
    def test_get_battery_metrics_returns_dict(self):
        """Test that get_battery_metrics returns a dictionary."""
        metrics = get_battery_metrics()
        assert isinstance(metrics, dict)
        assert 'available' in metrics
        assert 'backend' in metrics
    
    def test_get_battery_metrics_structure(self):
        """Test that metrics have expected structure when available."""
        metrics = get_battery_metrics()
        
        # These keys should always be present
        assert 'available' in metrics
        assert 'backend' in metrics
        
        # If battery is available, check for optional metrics
        if metrics['available']:
            # At least one metric should be present if available
            optional_keys = ['percentage', 'voltage', 'current', 'power', 'status', 'temperature']
            has_metrics = any(key in metrics for key in optional_keys)
            assert has_metrics, "Available battery should have at least one metric"
