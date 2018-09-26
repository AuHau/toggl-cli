import logging
import os
import typing

import click
import inquirer
import pendulum

from .. import exceptions

logger = logging.getLogger('toggl.utils.bootstrap')


class ConfigBootstrap:
    """
    Create config based on the input from the User
    """

    KEEP_TOGGLS_DEFAULT_WORKSPACE = '-- Keep Toggl\'s default --'
    SYSTEM_TIMEZONE = '-- Use system\'s timezone --'
    API_TOKEN_OPTION = 'API token'
    CREDENTIALS_OPTION = 'Credentials'

    def __init__(self):
        self.workspaces = None

    def _build_tmp_config(self, api_token=None, username=None, password=None):
        from .config import Config
        config = Config.factory(None)

        if api_token is not None:
            config.api_token = api_token
        else:
            config.username = username
            config.password = password

        return config

    def _get_workspaces(self, api_token):
        from ..api import Workspace
        config = self._build_tmp_config(api_token=api_token)

        if self.workspaces is None:
            self.workspaces = [self.KEEP_TOGGLS_DEFAULT_WORKSPACE]
            for workspace in Workspace.objects.all(config=config):
                self.workspaces.append(workspace.name)

        return self.workspaces

    def _map_answers(self, **answers):
        output = {
            'api_token': answers['api_token'],

            'file_logging': answers['file_logging'],
        }

        if answers['timezone'] == self.SYSTEM_TIMEZONE:
            output['timezone'] = 'local'

        if output['file_logging']:
            output['file_logging_path'] = os.path.expanduser(answers.get('file_logging_path'))

        if answers['default workspace'] != self.KEEP_TOGGLS_DEFAULT_WORKSPACE:
            from ..api import Workspace
            config = self._build_tmp_config(api_token=answers['api_token'])
            output['default_wid'] = str(Workspace.objects.get(name=answers['default workspace'], config=config).id)

        return output

    def _get_api_token(self):  # type: () -> typing.Union[str, None]
        from .others import are_credentials_valid

        type_auth = inquirer.shortcuts.list_input(message="Type of authentication you want to use",
                                                  choices=[self.API_TOKEN_OPTION, self.CREDENTIALS_OPTION])

        if type_auth is None:
            return None

        if type_auth == self.API_TOKEN_OPTION:
            return inquirer.shortcuts.password(message="Your API token",
                                               validate=lambda answers, current: are_credentials_valid(api_token=current))

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

    def _exit(self):
        click.secho("We were not able to setup the needed configuration and we are unfortunately not able to "
                    "proceed without it.", bg="white", fg="red")
        exit(-1)

    def start(self):
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

        api_token = self._get_api_token()

        if api_token is None:
            self._exit()

        questions = [
            inquirer.List('default workspace', message="Should TogglCli use different default workspace from Toggl's "
                                                       "setting?",
                          choices=lambda answers: self._get_workspaces(api_token)),

            inquirer.Text('timezone', 'Used timezone', default=self.SYSTEM_TIMEZONE,
                          validate=lambda answers, current: current in pendulum.timezones
                                                            or current == self.SYSTEM_TIMEZONE),

            inquirer.Confirm('file_logging', message="Enable logging of togglCli actions into file?", default=False),
            inquirer.Path('file_logging_path', message="Path to the log file", ignore=lambda x: not x['file_logging'],
                          default='~/.toggl_log'),
        ]

        answers = inquirer.prompt(questions)

        if answers is None:
            self._exit()

        click.echo("\nConfiguration successfully finished!\nNow continuing with your command:\n\n")

        return self._map_answers(api_token=api_token, **answers)

