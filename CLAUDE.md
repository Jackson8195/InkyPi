# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

InkyPi is a Raspberry Pi-based E-Ink display system with a Flask web UI. It renders customizable content (weather, calendars, AI images, etc.) onto e-paper displays via a plugin architecture. Development can be done without hardware using a mock display mode.

## Commands

**Development setup (no hardware required):**
```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r install/requirements-dev.txt
bash install/update_vendors.sh    # Fetches Waveshare drivers and vendor assets
python src/inkypi.py --dev        # Runs on port 8080 with mock display
```

**Run tests:**
```bash
pytest                            # All tests
pytest tests/test_model.py        # Single file
pytest tests/test_model.py::TestClass::test_method  # Single test
```

**Production (on Raspberry Pi):**
```bash
sudo bash install/install.sh                   # Inky displays
sudo bash install/install.sh -W epd7in3f       # Waveshare (specify model)
sudo systemctl start inkypi.service            # Start production service (port 80)
```

**Update production install:**
```bash
git pull && sudo bash install/update.sh
```

## Architecture

### Startup Flow (`src/inkypi.py`)

The entry point initializes three core singletons stored in `app.config`:
- `DEVICE_CONFIG` — `Config` instance reading `src/config/device_dev.json` (dev) or `device.json` (prod)
- `DISPLAY_MANAGER` — routes rendering to `InkyDisplay`, `WaveshareDisplay`, or `MockDisplay` (dev)
- `REFRESH_TASK` — background thread that periodically calls the active plugin and pushes images to the display

These are passed into Flask blueprints via `current_app.config`.

### Plugin System (`src/plugins/`)

Plugins are self-contained directories. Each must contain:
- `{plugin_id}.py` — class inheriting `BasePlugin`, implementing `generate_image(settings, device_config) -> PIL.Image`
- `plugin-info.json` — metadata: `display_name`, `id`, `class`
- `icon.png`
- Optional: `settings.html` (user config form), `render/` (HTML/CSS templates for image generation)

The `PluginRegistry` (`src/plugins/plugin_registry.py`) dynamically discovers and loads plugins at startup. Plugins render images either directly with Pillow or by rendering HTML/CSS to PNG via `src/utils/image_utils.py`.

### Playlist & Scheduling (`src/model.py`, `src/refresh_task.py`)

- `PlaylistManager` holds multiple `Playlist` objects, each with a time window (start/end time)
- The active playlist is resolved each refresh cycle based on current time
- `PluginInstance` stores a plugin ID and user settings; a playlist cycles through its instances
- `RefreshTask` runs as a daemon thread; it compares image hashes to skip redundant display updates and tracks metadata in `RefreshInfo`

### Configuration (`src/config.py`, `src/config/`)

- Config is stored as JSON; merges user values over defaults so new keys are backward-compatible
- Device settings include: display type/resolution, timezone, refresh interval, image enhancement values (brightness, contrast, saturation)
- Dev config lives at `src/config/device_dev.json`; production at `src/config/device.json`

### Display Layer (`src/display/`)

- `DisplayManager` selects the driver based on config
- `MockDisplay` (dev) saves rendered output to `mock_display_output/latest.png` — useful for visually testing plugin output without hardware
- Display drivers handle image resizing, color mode conversion, and hardware-specific rendering

### Power Management (`src/startup_manager.py`, `src/utils/wittypi_schedule.py`)

Witty Pi integration allows scheduled power on/off. `StartupManager` detects mount-based triggers and can execute a designated startup playlist before normal operation resumes. This path is only active on production hardware.

### Web Interface (`src/blueprints/`)

Four Flask blueprints handle the UI:
- `main.py` — dashboard and current image endpoint (`/api/current_image`)
- `plugin.py` — plugin configuration, immediate display trigger (`/display_plugin_instance`)
- `playlist.py` — playlist CRUD
- `settings.py` — device-wide settings

Templates use Jinja2 (`src/templates/`); static assets in `src/static/`.

## Key Files

| File | Role |
|------|------|
| `src/inkypi.py` | App entry point |
| `src/model.py` | `PlaylistManager`, `Playlist`, `PluginInstance`, `RefreshInfo` |
| `src/refresh_task.py` | Background refresh thread |
| `src/config.py` | Config load/save logic |
| `src/plugins/base_plugin/base_plugin.py` | Plugin base class |
| `src/plugins/plugin_registry.py` | Dynamic plugin loader |
| `src/display/mock_display.py` | Dev-mode display (no hardware needed) |
| `src/utils/image_utils.py` | HTML→PNG rendering, image helpers |
| `tests/test_model.py` | Playlist timing & priority tests |

## Building Plugins

See `docs/building_plugins.md` for the full guide. Key points:
- Implement `generate_image(settings, device_config)` returning a `PIL.Image` at the device's native resolution
- Access plugin settings via the `settings` dict (matches keys in `settings.html`)
- Use `self.render_html_template(template, context, device_config)` in `BasePlugin` for HTML-based rendering
- Register is automatic — no manual registry edits needed

## API Keys

Plugins that call external APIs (OpenAI, OpenWeatherMap, Google Calendar, Unsplash, etc.) require keys configured via the web UI Settings page. See `docs/api_keys.md` for per-plugin requirements.
