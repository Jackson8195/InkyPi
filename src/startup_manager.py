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
from utils.wittypi_schedule import WittyPiScheduleGenerator


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
        self.schedule_metadata_file = os.path.expanduser("~/.inkypi_schedule_playlist")
    
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
    
    def _get_last_scheduled_playlist(self):
        """Read which playlist the current schedule was generated for."""
        try:
            if os.path.exists(self.schedule_metadata_file):
                with open(self.schedule_metadata_file, 'r') as f:
                    return f.read().strip()
        except Exception as e:
            self.logger.debug(f"Failed to read schedule metadata: {e}")
        return None
    
    def _save_scheduled_playlist(self, playlist_name):
        """Record which playlist the schedule was generated for."""
        try:
            with open(self.schedule_metadata_file, 'w') as f:
                f.write(playlist_name)
        except Exception as e:
            self.logger.warning(f"Failed to save schedule metadata: {e}")
    
    def _clear_scheduled_playlist_metadata(self):
        """Clear the schedule metadata when removing the schedule."""
        try:
            if os.path.exists(self.schedule_metadata_file):
                os.remove(self.schedule_metadata_file)
        except Exception as e:
            self.logger.debug(f"Failed to clear schedule metadata: {e}")
    
    def _check_and_update_wittypi_schedule(self, current_playlist):
        """
        Check if Witty Pi schedule needs to be regenerated or removed.
        
        Args:
            current_playlist: The playlist that is currently active (or None if no mount)
        """
        last_scheduled = self._get_last_scheduled_playlist()
        current_playlist_name = current_playlist.name if current_playlist else None
        
        # If no current playlist, remove schedule and metadata
        if not current_playlist:
            if last_scheduled:
                self.logger.info("No playlist mounted; removing Witty Pi schedule")
                WittyPiScheduleGenerator.remove_schedule()
                self._clear_scheduled_playlist_metadata()
            return
        
        # If Witty Pi is disabled, remove schedule if it exists
        if not current_playlist.wittypi_enabled:
            if last_scheduled:
                self.logger.info("Witty Pi disabled for current playlist; removing schedule")
                WittyPiScheduleGenerator.remove_schedule()
                self._clear_scheduled_playlist_metadata()
            return
        
        # Witty Pi is enabled for current playlist
        # Regenerate if: mount changed OR schedule doesn't exist
        if last_scheduled != current_playlist_name:
            self.logger.info(
                f"Witty Pi schedule needs update (was: {last_scheduled}, now: {current_playlist_name})"
            )
            WittyPiScheduleGenerator.generate_for_playlist(
                wittypi_enabled=True,
                wittypi_start_time=current_playlist.wittypi_start_time,
                wittypi_end_time=current_playlist.wittypi_end_time,
                wittypi_cycle_minutes=current_playlist.wittypi_cycle_minutes,
                wittypi_timezone=current_playlist.wittypi_timezone
            )
            self._save_scheduled_playlist(current_playlist_name)
        else:
            self.logger.info(f"Witty Pi schedule still valid for {current_playlist_name}")
    

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
        """
        Check and update Witty Pi schedule if needed based on current mount.
        
        Only regenerates if the mount changed or settings differ from last boot.
        """
        self._check_and_update_wittypi_schedule(playlist)
    
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
            WittyPiScheduleGenerator.remove_schedule()
            self._clear_scheduled_playlist_metadata()
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
