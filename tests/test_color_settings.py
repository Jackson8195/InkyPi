import pytest
from unittest.mock import MagicMock
from werkzeug.datastructures import ImmutableMultiDict, FileStorage
from io import BytesIO
from jinja2 import Environment, DictLoader

from src.utils.app_utils import parse_form, handle_request_files


class TestParseForm:
    """Tests for parse_form utility, focused on color settings."""

    def test_single_color_values_extracted(self):
        form_data = ImmutableMultiDict([
            ('backgroundColor', '#ff0000'),
            ('textColor', '#ffffff'),
            ('backgroundOption', 'color'),
            ('plugin_id', 'countdown'),
        ])
        result = parse_form(form_data)
        assert result['backgroundColor'] == '#ff0000'
        assert result['textColor'] == '#ffffff'
        assert result['backgroundOption'] == 'color'

    def test_array_color_values_extracted(self):
        form_data = ImmutableMultiDict([
            ('contributionColor[]', '#ebedf0'),
            ('contributionColor[]', '#9be9a8'),
            ('contributionColor[]', '#40c463'),
        ])
        result = parse_form(form_data)
        assert result['contributionColor[]'] == ['#ebedf0', '#9be9a8', '#40c463']

    def test_background_option_image(self):
        form_data = ImmutableMultiDict([
            ('backgroundOption', 'image'),
            ('backgroundColor', '#ffffff'),
        ])
        result = parse_form(form_data)
        assert result['backgroundOption'] == 'image'

    def test_default_color_values_preserved(self):
        form_data = ImmutableMultiDict([
            ('backgroundColor', '#ffffff'),
            ('textColor', '#000000'),
            ('backgroundOption', 'color'),
        ])
        result = parse_form(form_data)
        assert result['backgroundColor'] == '#ffffff'
        assert result['textColor'] == '#000000'

    def test_non_color_fields_unaffected(self):
        form_data = ImmutableMultiDict([
            ('title', 'My Title'),
            ('feedUrl', 'http://example.com/rss'),
            ('backgroundColor', '#ff0000'),
        ])
        result = parse_form(form_data)
        assert result['title'] == 'My Title'
        assert result['feedUrl'] == 'http://example.com/rss'
        assert result['backgroundColor'] == '#ff0000'


class TestHandleRequestFiles:
    """Tests for handle_request_files, focused on preserving existing file paths."""

    def _make_empty_file_storage(self, field_name):
        """Create a FileStorage object with no file (empty upload)."""
        return FileStorage(stream=BytesIO(b''), filename='', name=field_name)

    def _make_file_storage(self, field_name, filename, content=b'data'):
        """Create a FileStorage object with file content."""
        return FileStorage(stream=BytesIO(content), filename=filename, name=field_name)

    def test_no_files_uploaded_returns_empty(self):
        from werkzeug.datastructures import FileMultiDict
        files = FileMultiDict([('backgroundImageFile', self._make_empty_file_storage('backgroundImageFile'))])
        result = handle_request_files(files)
        assert result == {}

    def test_existing_file_path_preserved_when_form_data_passed(self):
        """When form_data contains an existing file path (from hidden input), it should be preserved."""
        from werkzeug.datastructures import FileMultiDict
        # Simulate empty file input (no new upload)
        files = FileMultiDict([
            ('backgroundImageFile', self._make_empty_file_storage('backgroundImageFile'))
        ])
        # Simulate hidden input with existing file path
        form_data = ImmutableMultiDict([
            ('backgroundImageFile', '/path/to/existing/image.png'),
        ])
        result = handle_request_files(files, form_data)
        assert result.get('backgroundImageFile') == '/path/to/existing/image.png'

    def test_existing_file_path_lost_when_form_data_not_passed(self):
        """Without form_data, existing file path from hidden input is NOT preserved via handle_request_files."""
        from werkzeug.datastructures import FileMultiDict
        files = FileMultiDict([
            ('backgroundImageFile', self._make_empty_file_storage('backgroundImageFile'))
        ])
        # Without form_data, the function returns empty dict for empty uploads
        result = handle_request_files(files)
        assert result == {}


class TestBaseRenderTemplate:
    """Tests for the base plugin render template color application."""

    BASE_TEMPLATE = '''
<body style="
    {%- if plugin_settings.backgroundOption == 'image' %}
        background-image: url('{{ plugin_settings.backgroundImageFile }}');
        background-size: cover;
        background-position: center;
    {%- else %}
        background-color: {{ plugin_settings.backgroundColor or '#ffffff' }};
    {%- endif %}
    color: {{ plugin_settings.textColor or '#000000' }};
">content</body>
'''

    def _render(self, plugin_settings):
        env = Environment(loader=DictLoader({'plugin.html': self.BASE_TEMPLATE}))
        template = env.get_template('plugin.html')
        return template.render(plugin_settings=plugin_settings)

    def test_background_color_applied_when_option_is_color(self):
        output = self._render({'backgroundOption': 'color', 'backgroundColor': '#ff0000', 'textColor': '#000000'})
        assert 'background-color: #ff0000' in output
        assert 'background-image' not in output

    def test_background_color_applied_when_option_missing(self):
        """When backgroundOption is not set (e.g., old saved settings), color should still apply."""
        output = self._render({'backgroundColor': '#ff0000', 'textColor': '#000000'})
        assert 'background-color: #ff0000' in output

    def test_background_image_applied_when_option_is_image(self):
        output = self._render({
            'backgroundOption': 'image',
            'backgroundImageFile': '/path/to/image.png',
            'textColor': '#000000'
        })
        assert 'background-image' in output
        assert '/path/to/image.png' in output
        assert 'background-color' not in output

    def test_text_color_applied(self):
        output = self._render({'backgroundOption': 'color', 'backgroundColor': '#ffffff', 'textColor': '#ff0000'})
        assert 'color: #ff0000' in output

    def test_text_color_defaults_to_black_when_missing(self):
        """When textColor is missing, it should default to #000000."""
        output = self._render({'backgroundOption': 'color', 'backgroundColor': '#ffffff'})
        assert 'color: #000000' in output

    def test_background_color_defaults_to_white_when_missing(self):
        """When backgroundColor is missing, it should default to #ffffff."""
        output = self._render({'backgroundOption': 'color', 'textColor': '#000000'})
        assert 'background-color: #ffffff' in output

    def test_all_defaults_when_settings_empty(self):
        """When plugin_settings is empty dict, defaults should be used."""
        output = self._render({})
        assert 'background-color: #ffffff' in output
        assert 'color: #000000' in output
