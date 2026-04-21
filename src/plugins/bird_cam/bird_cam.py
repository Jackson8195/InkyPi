from plugins.base_plugin.base_plugin import BasePlugin
from utils.uptime_tracker import get_total_runtime, get_battery_uptime, read_witty_status, vin_to_percent
from openai import OpenAI
from PIL import Image
from io import BytesIO
import requests
import logging
import base64
import time

logger = logging.getLogger(__name__)

THEMES = ['field_notes', 'night_watch', 'minimal']

_MAX_AI_INPUT_SIZE = (1024, 1024)


def _resize_image_bytes(img_bytes, max_size, output_format=None, flatten_alpha=False, jpeg_quality=85):
    with Image.open(BytesIO(img_bytes)) as img:
        image = img.copy()

    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

    image.thumbnail(max_size, Image.LANCZOS)

    if flatten_alpha and "A" in image.getbands():
        flattened = Image.new("RGB", image.size, "white")
        flattened.paste(image, mask=image.getchannel("A"))
        image = flattened
    elif image.mode == "RGBA" and output_format != "PNG":
        image = image.convert("RGB")

    image_format = output_format or ("PNG" if "A" in image.getbands() else "JPEG")
    mime = "image/png" if image_format == "PNG" else "image/jpeg"

    buffer = BytesIO()
    save_kwargs = {"format": image_format}
    if image_format == "JPEG":
        save_kwargs.update({"quality": jpeg_quality, "subsampling": 0})
    image.save(buffer, **save_kwargs)
    return buffer.getvalue(), mime


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
        ai_enhance = settings.get('ai_enhance') == 'true'
        theme = settings.get('theme', 'field_notes')

        if not host:
            raise RuntimeError("Bird cam host IP is required.")

        base_url = f"http://{host}:{port}"
        logger.info(
            "BirdCam: starting generate_image host=%s port=%s theme=%s ai_enhance=%s",
            host, port, theme, ai_enhance,
        )

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
                logger.info("BirdCam: latest image filename=%s bird=%s", filename, latest_bird)
                if filename:
                    img_resp = requests.get(f"{base_url}/images/{filename}", timeout=10)
                    if img_resp.status_code == 200:
                        img_bytes = img_resp.content
                        img_bytes, mime = _resize_image_bytes(img_bytes, dimensions)
                        img_b64 = f"data:{mime};base64,{base64.b64encode(img_bytes).decode()}"
        except requests.exceptions.RequestException as e:
            logger.error(f"Bird cam image fetch failed: {e}")

        ai_style = settings.get('ai_style', 'colored pencil').strip() or 'colored pencil'
        if ai_enhance and img_bytes:
            api_key = device_config.load_env_key("OPEN_AI_SECRET")
            if api_key:
                try:
                    started_at = time.monotonic()
                    img_bytes, mime = BirdCam.apply_ai_style(
                        api_key, img_bytes, ai_style,
                        bird_name=latest_bird, output_size=dimensions,
                    )
                    logger.info("BirdCam: AI styling completed in %.2fs", time.monotonic() - started_at)
                    img_b64 = f"data:{mime};base64,{base64.b64encode(img_bytes).decode()}"
                except Exception as e:
                    logger.error(f"AI image enhancement failed: {e}")
            else:
                logger.warning("AI enhancement enabled but OPEN_AI_SECRET not configured.")

        witty_status = read_witty_status()
        vin = witty_status.get('vin')

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

        logger.info("BirdCam: rendering HTML image bird=%s has_img=%s", latest_bird, bool(img_b64))
        return self.render_image(dimensions, "bird_cam.html", "bird_cam.css", template_params)

    @staticmethod
    def apply_ai_style(api_key, img_bytes, style, bird_name=None, output_size=None):
        client = OpenAI(api_key=api_key)
        logger.info("BirdCam AI: starting style=%s bird=%s input_bytes=%s", style, bird_name, len(img_bytes))

        prepared_bytes, _ = _resize_image_bytes(img_bytes, _MAX_AI_INPUT_SIZE, output_format="PNG")

        buf = BytesIO(prepared_bytes)
        buf.name = "bird.png"
        prompt = (
            f"Redraw this entire image as a detailed {style} illustration. "
            f"Preserve the exact {bird_name or 'bird'} pose, colors, and markings faithfully. "
            f"Replace the background with a dark vignette gradient. "
            f"Visible {style} strokes throughout."
        )
        logger.info("BirdCam AI: sending request to OpenAI prompt=%r", prompt)
        response = client.images.edit(
            model="gpt-image-1",
            image=buf,
            prompt=prompt,
        )
        logger.info("BirdCam AI: OpenAI image edit completed")
        styled_bytes = base64.b64decode(response.data[0].b64_json)
        logger.info("BirdCam AI: decoded response bytes=%s", len(styled_bytes))
        if output_size:
            return _resize_image_bytes(styled_bytes, output_size, output_format="JPEG", flatten_alpha=True)
        return _resize_image_bytes(styled_bytes, _MAX_AI_INPUT_SIZE, output_format="JPEG", flatten_alpha=True)
