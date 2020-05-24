import logging
import os
import platform
import typing

import click
import inquirer
import pendulum

from toggl import exceptions, __version__, utils
from toggl.cli.themes import themes

logger = logging.getLogger('toggl.utils.bootstrap')


class ConfigBootstrap:
    """
    Class for facilitation of bootstraping the TogglCLI application with user's configuration.
    """

    KEEP_TOGGLS_DEFAULT_WORKSPACE = '-- Keep Toggl\'s default --'
    SYSTEM_TIMEZONE = '-- Use system\'s timezone --'
    TOGGL_TIMEZONE = 'toggl'
    API_TOKEN_OPTION = 'API token'
    CREDENTIALS_OPTION = 'Credentials'

    def __init__(self):
        self.workspaces = None

    def _build_tmp_config(self, api_token=None, username=None, password=None):  # type: (str, str, str) -> utils.Config
        """
        Method for creating temporary Config with specified credentials (eq. either api token or username/password)
        """
        from .config import Config
        config = Config.factory(None)

        if api_token is not None:
            config.api_token = api_token
        else:
            config.username = username
            config.password = password

        return config

    def _get_workspaces(self, api_token):  # type: (str) -> list
        """
        Retrieve all workspaces for user defined by api token.
        """
        from ..api import Workspace
        config = self._build_tmp_config(api_token=api_token)

        if self.workspaces is None:
            self.workspaces = [self.KEEP_TOGGLS_DEFAULT_WORKSPACE]
            for workspace in Workspace.objects.all(config=config):
                self.workspaces.append(workspace.name)

        return self.workspaces

    def _map_answers(self, **answers):  # type: (**str) -> dict
        """
        Creates dict which follows the ConfigParser convention from the provided user's answers.
        """
        output = {
            'version': __version__,
            'api_token': answers['api_token'],
            'file_logging': answers['file_logging'],
        }

        for theme in themes.values():
            if theme.name == answers['theme']:
                output['theme'] = theme.code
                break

        if answers['timezone'] == self.SYSTEM_TIMEZONE:
            output['tz'] = 'local'
        elif answers['timezone'] == self.TOGGL_TIMEZONE:
            pass
        else:
            output['tz'] = answers['timezone']

        if output['file_logging']:
            output['file_logging_path'] = os.path.expanduser(answers.get('file_logging_path'))

        if answers['default workspace'] != self.KEEP_TOGGLS_DEFAULT_WORKSPACE:
            from ..api import Workspace
            config = self._build_tmp_config(api_token=answers['api_token'])
            output['default_wid'] = str(Workspace.objects.get(name=answers['default workspace'], config=config).id)

        return output

    @classmethod
    def get_api_token(cls):  # type: () -> typing.Optional[str]
        """
        Method guide the user through first phase of the bootstrap: credentials gathering.
        It supports two ways of authentication: api token or credentials.
        But in case of user's credentials, they are converted into API token for security reason as the secret is
        stored in plain-text configuration file.
        """
        from .others import are_credentials_valid

        type_auth = inquirer.shortcuts.list_input(message="Type of authentication you want to use",
                                                  choices=[cls.API_TOKEN_OPTION, cls.CREDENTIALS_OPTION])

        if type_auth is None:
            return None

        if type_auth == cls.API_TOKEN_OPTION:
            return inquirer.shortcuts.password(message="Your API token",
                                               validate=lambda _, current: are_credentials_valid(api_token=current))

        questions = [
            inquirer.Text('username', message="Your Username"),
            inquirer.Password('password', message="Your Password"),
        ]

        while True:
            credentials = inquirer.prompt(questions)

            if credentials is None:
                return None

            try:
                from .others import convert_credentials_to_api_token
                return convert_credentials_to_api_token(username=credentials['username'],
                                                        password=credentials['password'])
            except exceptions.TogglAuthenticationException:
                click.echo('The provided credentials are not valid! Please try again.')

    def _exit(self):  # type: () -> None
        click.secho("We were not able to setup the needed configuration and we are unfortunately not able to "
                    "proceed without it.", bg="white", fg="red")
        exit(-1)

    def _bootstrap_windows(self):
        click.secho(""" _____                 _   _____  _     _____
|_   _|               | | /  __ \| |   |_   _|
  | | ___   __ _  __ _| | | /  \/| |     | |
  | |/ _ \ / _` |/ _` | | | |    | |     | |
  | | (_) | (_| | (_| | | | \__/\| |_____| |_
  \_/\___/ \__, |\__, |_|  \____/\_____/\___/
            __/ | __/ |
           |___/ |___/
""", fg="red")

        click.echo("Welcome to Toggl CLI!\n"
                   "Unfortunately for Windows users we don't have interactive initialization of TogglCLI. "
                   "We have created dummy configuration file which you should configure before using this tool.\n")

        return {
            'version': __version__,
            'api_token': 'YOUR API KEY',
        }

    def start(self):  # type: () -> dict
        """
        Entry point for the bootstrap process.
        The process will gather required information for configuration and then return those information in dict which
        follows the utils.config.Config attribute's naming.
        """
        if platform.system() == 'Windows':
            return self._bootstrap_windows()

        click.secho(""" _____                 _   _____  _     _____
|_   _|               | | /  __ \| |   |_   _|
  | | ___   __ _  __ _| | | /  \/| |     | |
  | |/ _ \ / _` |/ _` | | | |    | |     | |
  | | (_) | (_| | (_| | | | \__/\| |_____| |_
  \_/\___/ \__, |\__, |_|  \____/\_____/\___/
            __/ | __/ |
           |___/ |___/
""", fg="red")

        click.echo("Welcome to Toggl CLI!\n"
                   "We need to setup some configuration before you start using this awesome tool!\n")

        click.echo("{} Your credentials will be stored in plain-text inside of the configuration!\n".format(
            click.style("Warning!", fg="yellow", bold=True)
        ))

        api_token = self.get_api_token()

        if api_token is None:
            self._exit()

        questions = [
            inquirer.List('default workspace', message="Should TogglCli use different default workspace from Toggl's "
                                                       "setting?",
                          choices=lambda answers: self._get_workspaces(api_token)),

            inquirer.Text('timezone', 'Timezone to use (value \'{}\', will keep Toggl\'s setting)'.format(self.TOGGL_TIMEZONE),
                          default=self.SYSTEM_TIMEZONE,
                          validate=lambda answers, current: current in pendulum.timezones
                                                            or current == self.SYSTEM_TIMEZONE
                                                            or current == self.TOGGL_TIMEZONE),
            inquirer.List('theme', message='What theme should be used for the CLI interface?',
                          choices=lambda answers: [theme.name for theme in themes.values()]),
            inquirer.Confirm('file_logging', message="Enable logging of togglCli actions into file?", default=False),
            inquirer.Path('file_logging_path', message="Path to the log file", ignore=lambda x: not x['file_logging'],
                          default='~/.toggl_log'),
        ]

        answers = inquirer.prompt(questions)

        if answers is None:
            self._exit()

        click.echo("""
        Configuration successfully finished!

        If you want to enable command completion run: toggl config completion install

        Now continuing with your command:

        """)

        return self._map_answers(api_token=api_token, **answers)

    def start_windows(self):
        pass
