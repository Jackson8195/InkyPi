#!/usr/bin/env python3

# set up logging
import os, logging.config

from pi_heif import register_heif_opener

logging.config.fileConfig(os.path.join(os.path.dirname(__file__), 'config', 'logging.conf'))

# suppress warning from inky library https://github.com/pimoroni/inky/issues/205
import warnings
warnings.filterwarnings("ignore", message=".*Busy Wait: Held high.*")

import time
from refresh_task import PlaylistRefresh
from plugins.plugin_registry import load_plugins, get_plugin_instance
import os
import random
import time
import sys
import json
import logging
import threading
import argparse
import subprocess
from datetime import datetime
from utils.app_utils import generate_startup_image
from utils.mount_detection import MountSelector, MCP23017NotAvailable
from utils.uptime_tracker import append_runtime, get_total_runtime
from utils.wittypi_schedule import WittyPiScheduleGenerator, remove_schedule_file
from flask import Flask, request
from werkzeug.serving import is_running_from_reloader
from config import Config
from display.display_manager import DisplayManager
from refresh_task import RefreshTask
from blueprints.main import main_bp
from blueprints.settings import settings_bp
from blueprints.plugin import plugin_bp
from blueprints.playlist import playlist_bp
from jinja2 import ChoiceLoader, FileSystemLoader
from plugins.plugin_registry import load_plugins
from waitress import serve


logger = logging.getLogger(__name__)


def _is_oneshot_mode():
    """Return True when booted in oneshot/battery mode controlled by Witty Pi."""
    return os.getenv('WITTYPI_ONESHOT') == '1' or os.path.exists('/tmp/wittypi_oneshot')

# Parse command line arguments
parser = argparse.ArgumentParser(description='InkyPi Display Server')
parser.add_argument('--dev', action='store_true', help='Run in development mode')
args = parser.parse_args()

# Set development mode settings
if args.dev:
    Config.config_file = os.path.join(Config.BASE_DIR, "config", "device_dev.json")
    DEV_MODE = True
    PORT = 8080
    logger.info("Starting InkyPi in DEVELOPMENT mode on port 8080")
else:
    DEV_MODE = False
    PORT = 80
    logger.info("Starting InkyPi in PRODUCTION mode on port 80")
logging.getLogger('waitress.queue').setLevel(logging.ERROR)
app = Flask(__name__)
template_dirs = [
   os.path.join(os.path.dirname(__file__), "templates"),    # Default template folder
   os.path.join(os.path.dirname(__file__), "plugins"),      # Plugin templates
]
app.jinja_loader = ChoiceLoader([FileSystemLoader(directory) for directory in template_dirs])

device_config = Config()
display_manager = DisplayManager(device_config)
refresh_task = RefreshTask(device_config, display_manager)

load_plugins(device_config.get_plugins())

# Store dependencies
app.config['DEVICE_CONFIG'] = device_config
app.config['DISPLAY_MANAGER'] = display_manager
app.config['REFRESH_TASK'] = refresh_task

# Set additional parameters
app.config['MAX_FORM_PARTS'] = 10_000

# Register Blueprints
app.register_blueprint(main_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(plugin_bp)
app.register_blueprint(playlist_bp)

# Register opener for HEIF/HEIC images
register_heif_opener()

if __name__ == '__main__':

    is_oneshot_mode = _is_oneshot_mode()

    # start the background refresh task
    refresh_task.start()

    # --- STARTUP PLAYLIST ONE-SHOT RUN (with bypass file) ---
    # Persistent bypass file: create ~/.inkypi_skip_startup to skip startup playlist
    bypass_file = os.path.expanduser("~/.inkypi_skip_startup")

    # If bypass is present, skip mount detection entirely
    if not os.path.exists(bypass_file):
        mount_selector_config = device_config.get_config("mount_startup_playlists", default=None)
        if mount_selector_config and mount_selector_config.get("enabled"):
            # Mount detection replaces startup_playlist config entirely
            startup_playlist_config = None
            try:
                selector = MountSelector.from_config(mount_selector_config, logger=logger)
                detection = selector.detect()

                if detection.all_open:
                    startup_playlist_config = None
                elif detection.playlist_name:
                    startup_playlist_config = {
                        "playlist_name": detection.playlist_name,
                        "wait_seconds": int(mount_selector_config.get("wait_seconds", 120)),
                        "shutdown_after_refresh": bool(mount_selector_config.get("shutdown_after_refresh", False)),
                    }
            except MCP23017NotAvailable as exc:
                logger.warning("Mount selector disabled: %s", exc)
                startup_playlist_config = None
            except Exception:
                logger.exception("Mount selector failed; no startup playlist will run")
                startup_playlist_config = None
        else:
            # Fall back to static startup_playlist config if mount detection not enabled
            startup_playlist_config = device_config.get_config("startup_playlist", default=None)
    else:
        startup_playlist_config = None

    if os.path.exists(bypass_file):
        logger.info("Bypass file '%s' found — skipping startup playlist.", bypass_file)
        # Do NOT remove the file — it persists across boots
        if not is_oneshot_mode:
            logger.info("Normal boot mode - removing any existing Witty Pi schedule")
            remove_schedule_file()
    elif startup_playlist_config:
        try:
            playlist_name = startup_playlist_config.get("playlist_name")
            per_plugin_timeout = int(startup_playlist_config.get("wait_seconds", 120))
            shutdown_after = bool(startup_playlist_config.get("shutdown_after_refresh", False))

            playlist_manager = device_config.get_playlist_manager()
            playlist = playlist_manager.get_playlist(playlist_name)

            if not playlist:
                logger.error("Startup playlist '%s' not found", playlist_name)
            elif not getattr(playlist, "plugins", None):
                logger.error("Startup playlist '%s' has no plugins", playlist_name)
            else:
                if is_oneshot_mode:
                    if playlist.wittypi_enabled:
                        logger.info("Detected oneshot/battery mode - generating Witty Pi schedule for '%s'", playlist.name)
                        try:
                            generator = WittyPiScheduleGenerator(
                                start_time_str=playlist.wittypi_start_time,
                                end_time_str=playlist.wittypi_end_time,
                                cycle_minutes=playlist.wittypi_cycle_minutes,
                                timezone_str=playlist.wittypi_timezone
                            )
                            if generator.write_schedule_file():
                                logger.info("Witty Pi schedule generated successfully")
                            else:
                                logger.error("Failed to generate Witty Pi schedule")
                        except Exception as e:
                            logger.error(f"Error generating Witty Pi schedule: {e}")
                    else:
                        logger.info("Witty Pi is disabled for playlist '%s'", playlist.name)
                else:
                    logger.info("Normal boot mode - removing any existing Witty Pi schedule")
                    remove_schedule_file()

                logger.info("Running startup playlist once: %s", playlist_name)

                for entry in playlist.plugins:
                    pr = PlaylistRefresh(playlist, entry, force=True)

                    done = threading.Event()
                    try:
                        refresh_task.manual_update(pr, completion_event=done)
                        done.wait(timeout=per_plugin_timeout)
                    except TypeError:
                        refresh_task.manual_update(pr)
                        time.sleep(min(10, per_plugin_timeout))

                if shutdown_after:
                    logger.info("Startup one-shot finished; preparing to shut down.")

                    # Record uptime directly before shutdown
                    logger.info("Recording uptime before shutdown")
                    try:
                        total_seconds = append_runtime()
                        logger.info(f"Uptime recorded: {get_total_runtime()} ({total_seconds}s)")
                    except Exception as e:
                        logger.warning(f"Failed to record uptime: {e}")

                    logger.info("Executing shutdown command")
                    try:
                        subprocess.run(["sudo", "shutdown", "-h", "now"], check=True)
                    except subprocess.CalledProcessError as e:
                        logger.error(f"Shutdown command failed: {e}")
                    except Exception as e:
                        logger.error(f"Unexpected error during shutdown: {e}")
        except Exception:
            logger.exception("Startup playlist one-shot failed")
    else:
        # No startup playlist configured; ensure normal mode cleans up any leftover schedule
        if not is_oneshot_mode:
            logger.info("Normal boot mode - removing any existing Witty Pi schedule")
            remove_schedule_file()
    # --- END STARTUP PLAYLIST ONE-SHOT RUN ---

    # display default inkypi image on startup
    if device_config.get_config("startup") is True:
        logger.info("Startup flag is set, displaying startup image")
        img = generate_startup_image(device_config.get_resolution())
        display_manager.display_image(img)
        device_config.update_value("startup", False, write=True)

    try:
        # Run the Flask app
        app.secret_key = str(random.randint(100000,999999))
        
        # Get local IP address for display (only in dev mode when running on non-Pi)
        if DEV_MODE:
            import socket
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
                logger.info(f"Serving on http://{local_ip}:{PORT}")
            except:
                pass  # Ignore if we can't get the IP
            
        serve(app, host="0.0.0.0", port=PORT, threads=1)
    finally:
        refresh_task.stop()