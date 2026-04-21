from plugins.base_plugin.base_plugin import BasePlugin
from utils.uptime_tracker import get_total_runtime, get_battery_uptime, read_witty_status, vin_to_percent
from openai import OpenAI
from PIL import Image
from io import BytesIO
import onnxruntime as ort
import numpy as np
import requests
import logging
import base64
import os

logger = logging.getLogger(__name__)

THEMES = ['field_notes', 'night_watch', 'minimal']

_U2NETP_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx"
_U2NETP_PATH = os.path.expanduser("~/.u2net/u2netp.onnx")
_ort_session = None


def _get_ort_session():
    global _ort_session
    if _ort_session is None:
        if not os.path.exists(_U2NETP_PATH):
            os.makedirs(os.path.dirname(_U2NETP_PATH), exist_ok=True)
            logger.info("Downloading u2netp background removal model (~4MB)...")
            r = requests.get(_U2NETP_URL, stream=True, timeout=60)
            r.raise_for_status()
            with open(_U2NETP_PATH, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info("u2netp model downloaded.")
        _ort_session = ort.InferenceSession(_U2NETP_PATH)
    return _ort_session


def _remove_background(img_bytes):
    session = _get_ort_session()
    img = Image.open(BytesIO(img_bytes)).convert("RGB")
    orig_size = img.size

    resized = img.resize((320, 320), Image.LANCZOS)
    inp = np.array(resized, dtype=np.float32) / 255.0
    inp = (inp - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
    inp = inp.transpose(2, 0, 1)[np.newaxis].astype(np.float32)

    input_name = session.get_inputs()[0].name
    raw = session.run(None, {input_name: inp})[0]
    mask = raw[0, 0]
    mask = 1.0 / (1.0 + np.exp(-mask))
    mask = (mask * 255).astype(np.uint8)
    mask_img = Image.fromarray(mask).resize(orig_size, Image.LANCZOS)

    img_rgba = img.convert("RGBA")
    img_rgba.putalpha(mask_img)
    buf = BytesIO()
    img_rgba.save(buf, format="PNG")
    return buf.getvalue()


class BirdCam(BasePlugin):

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        template_params['themes'] = THEMES
        template_params['api_key'] = {
            "required": False,
            "service": "OpenAI",
            "expected_key": "OPEN_AI_SECRET"
        }
        return template_params

    def generate_image(self, settings, device_config):
        host = settings.get('host', '').strip()
        port = settings.get('port', '5000').strip() or '5000'

        if not host:
            raise RuntimeError("Bird cam host IP is required.")

        base_url = f"http://{host}:{port}"

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        try:
            stats_resp = requests.get(f"{base_url}/api/stats", timeout=5)
            stats_resp.raise_for_status()
            stats = stats_resp.json()
        except requests.exceptions.ConnectionError:
            raise RuntimeError(f"Cannot reach bird cam at {host}:{port}. Check host and network.")
        except requests.exceptions.Timeout:
            raise RuntimeError("Bird cam request timed out. Check host and network.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Bird cam /api/stats failed: {e}")
            raise RuntimeError("Failed to fetch bird cam stats, please check logs.")

        top_birds = []
        try:
            counts_resp = requests.get(f"{base_url}/api/bird_counts_raw", timeout=5)
            if counts_resp.status_code == 200:
                counts = counts_resp.json()
                top_birds = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5]
        except requests.exceptions.RequestException as e:
            logger.error(f"Bird cam /api/bird_counts_raw failed: {e}")

        bird_filters = settings.get('bird_filter[]', [])
        if isinstance(bird_filters, str):
            bird_filters = [bird_filters] if bird_filters else []

        latest_bird = None
        img_b64 = None
        img_bytes = None
        filename = None
        try:
            params = [('birds[]', b) for b in bird_filters] if bird_filters else []
            latest_resp = requests.get(f"{base_url}/api/latest_image", params=params, timeout=5)
            if latest_resp.status_code == 200:
                latest_data = latest_resp.json()
                filename = latest_data.get('filename')
                latest_bird = latest_data.get('bird')
                if filename:
                    img_resp = requests.get(f"{base_url}/images/{filename}", timeout=10)
                    if img_resp.status_code == 200:
                        img_bytes = img_resp.content
                        ext = filename.rsplit('.', 1)[-1].lower()
                        mime = 'image/jpeg' if ext in ('jpg', 'jpeg') else 'image/png'
                        img_b64 = f"data:{mime};base64,{base64.b64encode(img_bytes).decode()}"
        except requests.exceptions.RequestException as e:
            logger.error(f"Bird cam image fetch failed: {e}")

        ai_enhance = settings.get('ai_enhance') == 'true'
        ai_style = settings.get('ai_style', 'colored pencil').strip() or 'colored pencil'
        if ai_enhance and img_bytes:
            api_key = device_config.load_env_key("OPEN_AI_SECRET")
            if api_key:
                try:
                    img_bytes = BirdCam.apply_ai_style(api_key, img_bytes, ai_style, bird_name=latest_bird)
                    img_b64 = f"data:image/png;base64,{base64.b64encode(img_bytes).decode()}"
                except Exception as e:
                    logger.error(f"AI image enhancement failed: {e}")
            else:
                logger.warning("AI enhancement enabled but OPEN_AI_SECRET not configured.")

        witty_status = read_witty_status()
        vin = witty_status.get('vin')

        theme = settings.get('theme', 'field_notes')
        if theme not in THEMES:
            theme = 'field_notes'

        template_params = {
            "stats": stats,
            "bird_name": latest_bird,
            "img_b64": img_b64,
            "filter_active": bool(bird_filters),
            "bird_filters": bird_filters,
            "battery_percent": vin_to_percent(vin) if vin else 0,
            "battery_voltage": vin if vin else None,
            "total_uptime": get_total_runtime(),
            "battery_uptime": get_battery_uptime(),
            "filename": filename,
            "top_birds": top_birds,
            "theme": theme,
            "plugin_settings": settings,
        }

        return self.render_image(dimensions, "bird_cam.html", "bird_cam.css", template_params)

    @staticmethod
    def apply_ai_style(api_key, img_bytes, style, bird_name=None):
        client = OpenAI(api_key=api_key)

        isolated = _remove_background(img_bytes)

        buf = BytesIO(isolated)
        buf.name = "bird.png"
        prompt = f"Detailed {style} portrait of this {bird_name or 'bird'} on a dark vignette background."
        response = client.images.edit(
            model="gpt-image-1",
            image=buf,
            prompt=prompt,
        )
        return base64.b64decode(response.data[0].b64_json)
