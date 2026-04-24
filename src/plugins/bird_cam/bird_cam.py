from plugins.base_plugin.base_plugin import BasePlugin
from utils.uptime_tracker import get_total_runtime, get_battery_uptime, read_witty_status, vin_to_percent
from PIL import Image
from io import BytesIO
import replicate
import requests
import logging
import base64
import time
import re
import os

logger = logging.getLogger(__name__)

THEMES = ['field_notes', 'night_watch', 'minimal', 'pokemon']

_MAX_AI_INPUT_SIZE = (768, 768)


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

        filter_mode = settings.get('filterMode', 'all')
        visitor_mode = settings.get('visitor_mode', 'highest_score')
        bird_filters = settings.get('bird_filter[]', [])
        if isinstance(bird_filters, str):
            bird_filters = [bird_filters] if bird_filters else []

        latest_bird = None
        bird_score = None
        img_b64 = None
        img_bytes = None
        img_bytes_raw = None
        filename = None

        specific_filename = settings.get('specific_filename', '').strip()
        if filter_mode == 'specific_photo' and specific_filename:
            filename = specific_filename
            # Parse bird name and score from img-BirdName_score_timestamp.ext
            base = filename.rsplit('.', 1)[0]
            if base.startswith('img-'):
                base = base[4:]
            parts = base.split('_')
            if len(parts) >= 2:
                raw_name = parts[0]
                try:
                    bird_score = int(parts[1])
                except ValueError:
                    pass
                latest_bird = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', raw_name)
            logger.info("BirdCam: specific photo filename=%s bird=%s score=%s", filename, latest_bird, bird_score)
            try:
                img_resp = requests.get(f"{base_url}/images/{filename}", timeout=10)
                if img_resp.status_code == 200:
                    img_bytes_raw = img_resp.content
                    img_bytes, mime = _resize_image_bytes(img_bytes_raw, dimensions)
                    img_b64 = f"data:{mime};base64,{base64.b64encode(img_bytes).decode()}"
            except requests.exceptions.RequestException as e:
                logger.error(f"Bird cam specific image fetch failed: {e}")
        else:
            try:
                params = [('birds[]', b) for b in bird_filters] if bird_filters else []
                image_endpoint = "/api/latest_image" if visitor_mode == 'most_recent' else "/api/best_image"
                latest_resp = requests.get(f"{base_url}{image_endpoint}", params=params, timeout=5)
                if latest_resp.status_code == 200:
                    latest_data = latest_resp.json()
                    filename = latest_data.get('filename')
                    latest_bird = latest_data.get('bird')
                    if filename:
                        parts = filename.rsplit('_', 2)
                        if len(parts) == 3:
                            try:
                                bird_score = int(parts[1])
                            except ValueError:
                                pass
                    logger.info("BirdCam: latest image filename=%s bird=%s score=%s", filename, latest_bird, bird_score)
                    if filename:
                        img_resp = requests.get(f"{base_url}/images/{filename}", timeout=10)
                        if img_resp.status_code == 200:
                            img_bytes_raw = img_resp.content
                            img_bytes, mime = _resize_image_bytes(img_bytes_raw, dimensions)
                            img_b64 = f"data:{mime};base64,{base64.b64encode(img_bytes).decode()}"
            except requests.exceptions.RequestException as e:
                logger.error(f"Bird cam image fetch failed: {e}")

        ai_style = settings.get('ai_style', 'colored pencil').strip() or 'colored pencil'
        ai_model = settings.get('ai_model', 'flux-2-pro')
        if ai_enhance and img_bytes_raw:
            api_key = device_config.load_env_key("REPLICATE_API_TOKEN")
            if api_key:
                try:
                    started_at = time.monotonic()
                    ai_prompt_suffix = settings.get('ai_prompt_suffix', '').strip()
                    pokemon_prompt = (
                        "Depict this bird as a pokemon sprite. "
                        "Keep its composition as much as possible but alter the colors to show high contrast. "
                        "Do not alter its position or features. "
                        "Remove the background and make it white."
                    ) if theme == 'pokemon' else None
                    img_bytes, mime = BirdCam.apply_ai_style(
                        api_key, img_bytes_raw, ai_style,
                        bird_name=latest_bird, output_size=dimensions,
                        ai_model=ai_model, prompt_suffix=ai_prompt_suffix,
                        base_prompt=pokemon_prompt,
                    )
                    logger.info("BirdCam: AI styling completed in %.2fs", time.monotonic() - started_at)
                    img_b64 = f"data:{mime};base64,{base64.b64encode(img_bytes).decode()}"
                except Exception as e:
                    logger.error(f"AI image enhancement failed: {e}")
            else:
                logger.warning("AI enhancement enabled but REPLICATE_API_TOKEN not configured.")

        witty_status = read_witty_status()
        vin = witty_status.get('vin')

        if theme not in THEMES:
            theme = 'field_notes'

        template_params = {
            "stats": stats,
            "bird_name": latest_bird,
            "bird_score": bird_score,
            "img_b64": img_b64,
            "filter_active": bool(bird_filters) or filter_mode == 'specific_photo',
            "bird_filters": bird_filters,
            "battery_percent": vin_to_percent(vin) if vin else 0,
            "battery_voltage": vin if vin else None,
            "total_uptime": get_total_runtime(),
            "battery_uptime": get_battery_uptime(),
            "filename": filename,
            "top_birds": top_birds,
            "theme": theme,
            "visitor_mode": visitor_mode,
            "plugin_settings": settings,
        }

        logger.info("BirdCam: rendering HTML image bird=%s has_img=%s theme=%s", latest_bird, bool(img_b64), theme)

        if theme == 'pokemon':
            template_params['bg_image_path'] = os.path.join(self.render_dir, 'pokemontemplate.png')
            return self.render_image(dimensions, "pokemon.html", None, template_params)

        return self.render_image(dimensions, "bird_cam.html", "bird_cam.css", template_params)

    @staticmethod
    def apply_ai_style(api_key, img_bytes, style, bird_name=None, output_size=None, ai_model="flux-2-pro", prompt_suffix="", base_prompt=None):
        logger.info("BirdCam AI: starting model=%s style=%s bird=%s input_bytes=%s", ai_model, style, bird_name, len(img_bytes))

        prepared_bytes, _ = _resize_image_bytes(img_bytes, _MAX_AI_INPUT_SIZE, output_format="JPEG", jpeg_quality=90)

        buf = BytesIO(prepared_bytes)
        buf.name = "bird.jpg"
        prompt = base_prompt or (
            f"Draw the bird exactly as is but in the style of {style}. "
            f"Change the background to blank white #FFFFFF while keeping the bird and the feeder perch in the exact same position. "
            f"The bird should be preserved exactly as is relative to its position in the image and feeder. "
            f"Preserve colors of the bird, its plumage should be accurate to the real life source image. "
            f"Use high detail, it should be a professional looking portrait."
        )
        if prompt_suffix:
            prompt = f"{prompt} {prompt_suffix}"
        client = replicate.Client(api_token=api_key)
        if ai_model == "flux-kontext-pro":
            target = output_size or _MAX_AI_INPUT_SIZE
            logger.info("BirdCam AI: sending request to flux-kontext-pro prompt=%r target=%s", prompt, target)
            output = client.run(
                "black-forest-labs/flux-kontext-pro",
                input={
                    "prompt": prompt,
                    "input_image": buf,
                    "aspect_ratio": "match_input_image",
                    "output_width": target[0],
                    "output_height": target[1],
                    "output_format": "jpg",
                    "safety_tolerance": 2,
                    "prompt_upsampling": False,
                },
            )
            logger.info("BirdCam AI: Replicate flux-kontext-pro completed")
        elif ai_model == "gpt-image-2":
            w, h = output_size if output_size else (1024, 1024)
            if w > 1024 or h > 1024:
                size = "1536x1024" if w >= h else "1024x1536"
            else:
                size = "1024x1024"
            logger.info("BirdCam AI: sending request to gpt-image-2 prompt=%r size=%s", prompt, size)
            output = client.run(
                "openai/gpt-image-2",
                input={
                    "prompt": prompt,
                    "input_images": [buf],
                    "size": size,
                    "output_format": "jpeg",
                    "output_compression": 90,
                    "quality": "medium",
                },
            )
            logger.info("BirdCam AI: Replicate gpt-image-2 completed")
        else:
            logger.info("BirdCam AI: sending request to flux-2-pro prompt=%r", prompt)
            output = client.run(
                "black-forest-labs/flux-2-pro",
                input={
                    "prompt": prompt,
                    "input_images": [buf],
                    "aspect_ratio": "match_input_image",
                    "resolution": "match_input_image",
                    "output_format": "jpg",
                    "output_quality": 90,
                    "safety_tolerance": 2,
                },
            )
            logger.info("BirdCam AI: Replicate flux-2-pro completed")
        result_url = str(output[0]) if isinstance(output, list) else str(output)
        styled_resp = requests.get(result_url, timeout=60)
        styled_resp.raise_for_status()
        styled_bytes = styled_resp.content
        logger.info("BirdCam AI: downloaded result bytes=%s", len(styled_bytes))
        if output_size:
            return _resize_image_bytes(styled_bytes, output_size, output_format="JPEG", flatten_alpha=True)
        return _resize_image_bytes(styled_bytes, _MAX_AI_INPUT_SIZE, output_format="JPEG", flatten_alpha=True)
