import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from tests.integration.helpers import ParsingResult
from toggl.cli.commands import cli
from toggl import utils


@pytest.fixture()
def cmd():
    def inner_cmd(cmd, config='default.config', simple=True, *args):
        config_path = Path(__file__).parent
        config_path = config_path.joinpath('configs/' + config)

        if not config_path.exists():
            raise ValueError('Unknown config path: ' + str(config_path))

        config = utils.Config.factory(str(config_path))

        parsed = re.findall(r"([\"]([^\"]+)\")|([']([^']+)')|(\S+)", cmd)  # Simulates quoting of strings with spaces (eq. filter -n "some important task")
        args = list(args) + [i[1] or i[3] or i[4] for i in parsed]

        if simple:
            args.insert(0, '--simple')

        result = CliRunner().invoke(cli, args, obj={'config': config})

        return ParsingResult(result)

    return inner_cmd
