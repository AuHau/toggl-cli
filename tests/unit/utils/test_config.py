from toggl.utils import config


class TestIniConfigMixin:
    def test_basic(self):
        ini = config.IniConfigMixin(None)

        assert ini.is_loaded is False
        assert ini._config_path is None

