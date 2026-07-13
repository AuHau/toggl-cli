from tests import helpers


def test_get_config_uses_default_workspace_from_environment(monkeypatch):
    monkeypatch.delenv("TOGGL_TEST_WORKSPACE_ID", raising=False)
    monkeypatch.setenv("TOGGL_DEFAULT_WORKSPACE_ID", "12345")

    config = helpers.get_config()

    assert config.default_wid == 12345
