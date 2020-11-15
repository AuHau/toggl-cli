from toggl.cli.helpers import format_duration


class TestDuration:

    def test_duration_format_seconds(self):
        assert format_duration(9) == '0:0:9'
        assert format_duration(11) == '0:0:11'

    def test_duration_format_minutes(self):
        assert format_duration(60 + 11) == '0:1:11'
        assert format_duration(20 * 60 + 11) == '0:20:11'

    def test_duration_format_hours(self):
        assert format_duration(1 * 3600 + 20 * 60 + 11) == '1:20:11'
        assert format_duration(22 * 3600 + 20 * 60 + 11) == '22:20:11'
