"""
StartupManager handles startup playlist execution, mount detection, and Witty Pi scheduling.
Encapsulates complex initialization logic for better testability and maintainability.
"""

import os
import threading
import logging
import subprocess
from refresh_task import PlaylistRefresh
from utils.mount_detection import MountSelector, MCP23017NotAvailable
from utils.uptime_tracker import append_runtime, get_total_runtime
from utils.wittypi_schedule import WittyPiScheduleGenerator, remove_schedule_file


class StartupManager:
    """Manages startup playlist execution and related system initialization."""
    
    def __init__(self, device_config, refresh_task, logger=None):
        """
        Initialize the StartupManager.
        
        Args:
            device_config: Configuration object containing device settings
            refresh_task: RefreshTask instance for executing playlists
            logger: Logger instance (defaults to module logger)
        """
        self.device_config = device_config
        self.refresh_task = refresh_task
        self.logger = logger or logging.getLogger(__name__)
        self.bypass_file = os.path.expanduser("~/.inkypi_skip_startup")
    
    def should_skip_startup(self):
        """Check if startup should be skipped via bypass file."""
        if os.path.exists(self.bypass_file):
            self.logger.info("Bypass file '%s' found — skipping startup playlist.", self.bypass_file)
            remove_schedule_file()
            return True
        return False
    
    def detect_startup_playlist(self):
        """
        Detect which startup playlist to run.
        
        First tries mount detection if enabled, then falls back to static config.
        Returns dict with playlist_name, wait_seconds, and shutdown_after_refresh,
        or None if no playlist should run.
        """
        mount_selector_config = self.device_config.get_config("mount_startup_playlists", default=None)
        
        if mount_selector_config and mount_selector_config.get("enabled"):
            return self._detect_via_mount(mount_selector_config)
        else:
            return self.device_config.get_config("startup_playlist", default=None)
    
    def _detect_via_mount(self, mount_selector_config):
        """Detect startup playlist via reed switch mount selector."""
        try:
            selector = MountSelector.from_config(mount_selector_config, logger=self.logger)
            detection = selector.detect()
            
            if detection.all_open:
                return None
            elif detection.playlist_name:
                return {
                    "playlist_name": detection.playlist_name,
                    "wait_seconds": int(mount_selector_config.get("wait_seconds", 120)),
                    "shutdown_after_refresh": bool(mount_selector_config.get("shutdown_after_refresh", False)),
                }
        except MCP23017NotAvailable as exc:
            self.logger.warning("Mount selector disabled: %s", exc)
        except Exception:
            self.logger.exception("Mount selector failed; no startup playlist will run")
        
        return None
    
    def setup_wittypi_schedule(self, playlist):
        """Generate and write Witty Pi schedule if enabled for playlist."""
        if not playlist.wittypi_enabled:
            self.logger.info("Witty Pi is disabled for playlist '%s'", playlist.name)
            remove_schedule_file()
            return
        
        self.logger.info("Generating Witty Pi schedule for playlist '%s'", playlist.name)
        try:
            generator = WittyPiScheduleGenerator(
                start_time_str=playlist.wittypi_start_time,
                end_time_str=playlist.wittypi_end_time,
                cycle_minutes=playlist.wittypi_cycle_minutes,
                timezone_str=playlist.wittypi_timezone
            )
            if generator.write_schedule_file():
                self.logger.info("Witty Pi schedule generated and activated successfully")
            else:
                self.logger.error("Failed to generate Witty Pi schedule")
        except Exception as e:
            self.logger.error(f"Error generating Witty Pi schedule: {e}")
    
    def run_playlist(self, playlist, per_plugin_timeout):
        """Execute all plugins in a playlist."""
        self.logger.info("Running startup playlist: %s", playlist.name)
        
        for entry in playlist.plugins:
            pr = PlaylistRefresh(playlist, entry, force=True)
            
            done = threading.Event()
            try:
                self.refresh_task.manual_update(pr, completion_event=done)
                done.wait(timeout=per_plugin_timeout)
            except TypeError:
                # Fallback for older refresh_task API
                self.refresh_task.manual_update(pr)
                import time
                time.sleep(min(10, per_plugin_timeout))
    
    def shutdown_system(self):
        """Gracefully shutdown the system, recording uptime first."""
        self.logger.info("Startup playlist finished; preparing to shut down.")
        
        # Record uptime before shutdown
        self.logger.info("Recording uptime before shutdown")
        try:
            total_seconds = append_runtime()
            self.logger.info(f"Uptime recorded: {get_total_runtime()} ({total_seconds}s)")
        except Exception as e:
            self.logger.warning(f"Failed to record uptime: {e}")
        
        self.logger.info("Executing shutdown command")
        try:
            subprocess.run(["sudo", "shutdown", "-h", "now"], check=True)
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Shutdown command failed: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error during shutdown: {e}")
    
    def execute(self):
        """
        Execute startup logic: detect playlist, run it, optionally shutdown.
        
        This is the main entry point. Handles all error cases gracefully.
        """
        if self.should_skip_startup():
            return
        
        startup_config = self.detect_startup_playlist()
        
        if not startup_config:
            self.logger.info("No startup playlist configured")
            remove_schedule_file()
            return
        
        try:
            playlist_name = startup_config.get("playlist_name")
            per_plugin_timeout = int(startup_config.get("wait_seconds", 120))
            shutdown_after = bool(startup_config.get("shutdown_after_refresh", False))
            
            playlist_manager = self.device_config.get_playlist_manager()
            playlist = playlist_manager.get_playlist(playlist_name)
            
            if not playlist:
                self.logger.error("Startup playlist '%s' not found", playlist_name)
                return
            
            if not getattr(playlist, "plugins", None):
                self.logger.error("Startup playlist '%s' has no plugins", playlist_name)
                return
            
            # Setup Witty Pi if enabled
            self.setup_wittypi_schedule(playlist)
            
            # Run the playlist
            self.run_playlist(playlist, per_plugin_timeout)
            
            # Shutdown if configured
            if shutdown_after:
                self.shutdown_system()
        
        except Exception:
            self.logger.exception("Startup playlist execution failed")
