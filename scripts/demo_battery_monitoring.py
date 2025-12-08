#!/usr/bin/env python3
"""
Battery monitoring demonstration script for InkyPi.

This script demonstrates the battery monitoring capabilities by displaying
current battery metrics in a human-readable format.

Usage:
    python3 demo_battery_monitoring.py
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils.battery_utils import get_battery_metrics


def format_battery_status(metrics):
    """Format battery metrics in a human-readable format."""
    print("\n" + "="*60)
    print("InkyPi Battery Monitoring Status")
    print("="*60)
    
    if not metrics.get('available'):
        print("\n❌ Battery monitoring is NOT available")
        print(f"Backend: {metrics.get('backend', 'unknown')}")
        if 'error' in metrics:
            print(f"Error: {metrics['error']}")
        print("\nNo battery monitoring hardware detected.")
        print("For setup instructions, see: docs/battery_monitoring.md")
        return
    
    print("\n✅ Battery monitoring is AVAILABLE")
    print(f"Backend: {metrics.get('backend', 'unknown')}")
    print()
    
    # Display percentage with visual indicator
    if 'percentage' in metrics:
        percentage = metrics['percentage']
        print(f"Battery Level: {percentage:.1f}%")
        
        # Create a simple text-based battery indicator
        filled = int(percentage / 10)
        empty = 10 - filled
        bar = "█" * filled + "░" * empty
        print(f"[{bar}]")
        print()
    
    # Display status
    if 'status' in metrics:
        status = metrics['status']
        status_icon = {
            'Charging': '🔌',
            'Discharging': '🔋',
            'Full': '✅',
            'Idle': '💤'
        }.get(status, '❓')
        print(f"Status: {status_icon} {status}")
    
    # Display voltage
    if 'voltage' in metrics:
        voltage = metrics['voltage']
        print(f"Voltage: {voltage:.2f}V")
    
    # Display current
    if 'current' in metrics:
        current = metrics['current']
        direction = "charging" if current > 0 else "discharging"
        print(f"Current: {abs(current):.1f}mA ({direction})")
    
    # Display power
    if 'power' in metrics:
        power = metrics['power']
        print(f"Power: {abs(power):.2f}W")
    
    # Display temperature
    if 'temperature' in metrics:
        temp = metrics['temperature']
        print(f"Temperature: {temp:.1f}°C")
    
    print("\n" + "="*60)
    
    # Provide recommendations based on metrics
    if 'percentage' in metrics:
        percentage = metrics['percentage']
        if percentage < 10:
            print("\n⚠️  WARNING: Battery critically low! Consider charging soon.")
        elif percentage < 20:
            print("\n⚠️  Battery low. You may want to charge soon.")
        elif percentage > 90:
            print("\n✅ Battery is well charged.")
    
    print()


def main():
    """Main function to demonstrate battery monitoring."""
    try:
        print("\nRetrieving battery metrics...")
        metrics = get_battery_metrics()
        format_battery_status(metrics)
        
        # Show additional information for users
        print("\nTo integrate battery monitoring with InkyPi:")
        print("  1. Enable 'Log System Stats' in the Settings page")
        print("  2. View logs with: journalctl -u inkypi -f")
        print("  3. Query status via API: curl http://localhost/battery-status")
        print("\nFor more information, see: docs/battery_monitoring.md\n")
        
    except Exception as e:
        print(f"\n❌ Error getting battery metrics: {e}")
        print("This may be expected if running on a system without battery hardware.")
        sys.exit(1)


if __name__ == '__main__':
    main()
