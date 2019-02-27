import logging
import json
from pprint import pformat
from time import sleep

import click
import requests

from toggl.utils.config import Config
from toggl import exceptions

logger = logging.getLogger('toggl.utils')


class SubCommandsGroup(click.Group):
    """
    Group extension which distinguish between direct commands and groups. Groups
    are then displayed in help as 'Sub-Commands'.
    """

    SUB_COMMANDS_SECTION_TITLE = 'Sub-Commands'

    def __init__(self, *args, **kwargs):
        self.subcommands = {}
        super().__init__(*args, **kwargs)

    def group(self, *args, **kwargs):
        def decorator(f):
            cmd = super(SubCommandsGroup, self).group(*args, **kwargs)(f)
            self.subcommands[cmd.name] = cmd
            return cmd

        return decorator

    def format_subcommands(self, ctx, formatter):
        # Format Sub-Commands
        rows = []
        for subcommand in self.list_subcommands(ctx):
            cmd = self.get_command(ctx, subcommand)
            # What is this, the tool lied about a command.  Ignore it
            if cmd is None:
                continue

            subcommand_help = cmd.short_help or ''
            rows.append((subcommand, subcommand_help))

        if rows:
            with formatter.section(self.SUB_COMMANDS_SECTION_TITLE):
                formatter.write_dl(rows)

    def format_commands(self, ctx, formatter):
        self.format_subcommands(ctx, formatter)
        super().format_commands(ctx, formatter)

    def list_subcommands(self, _):
        return sorted(self.subcommands)

    def list_commands(self, ctx):
        return sorted(
            {k: v for k, v in self.commands.items() if k not in self.subcommands}
        )


# ----------------------------------------------------------------------------
# toggl
# ----------------------------------------------------------------------------
def are_credentials_valid(api_token=None, username=None, password=None):
    config = Config.factory(None)

    if api_token is not None:
        config.api_token = api_token
    else:
        config.username = username
        config.password = password

    try:
        toggl("/me", "get", config=config)
        return True
    except exceptions.TogglAuthenticationException as e:
        logger.debug(e)
        return False


def convert_credentials_to_api_token(username, password):
    config = Config.factory(None)
    config.username = username
    config.password = password

    data = toggl("/me", "get", config=config)
    return data['data']['api_token']


def handle_error(response):
    if response.status_code == 402:
        raise exceptions.TogglPremiumException(
            "Request tried to utilized Premium functionality on workspace which is not Premium!"
        )

    if response.status_code == 403:
        raise exceptions.TogglAuthenticationException(
            response.status_code, response.text,
            "Authentication credentials are not correct."
        )

    if response.status_code == 429:
        raise exceptions.TogglThrottlingException(
            response.status_code, response.text,
            "Toggl's API refused your request for throttling reasons."
        )

    if response.status_code == 404:
        raise exceptions.TogglNotFoundException(
            response.status_code, response.text,
            "Requested resource not found."
        )

    if 500 <= response.status_code < 600:
        raise exceptions.TogglServerException(response.status_code, response.text,
                                              'Toggl\'s API is currently unavailable!')

    raise exceptions.TogglApiException(
        response.status_code, response.text,
        "Toggl's API server returned {} code with message: {}"
            .format(response.status_code, response.text)
    )


def _toggl_request(url, method, data, headers, auth):
    logger.info('Sending {} to \'{}\' data: {}'.format(method.upper(), url, json.dumps(data)))
    if method == 'delete':
        response = requests.delete(url, auth=auth, data=data, headers=headers)
    elif method == 'get':
        response = requests.get(url, auth=auth, data=data, headers=headers)
    elif method == 'post':
        response = requests.post(url, auth=auth, data=data, headers=headers)
    elif method == 'put':
        response = requests.put(url, auth=auth, data=data, headers=headers)
    else:
        raise NotImplementedError('HTTP method "{}" not implemented.'.format(method))

    if response.status_code >= 300:
        handle_error(response)

    return response


def toggl(url, method, data=None, headers=None, config=None, address=None):
    """
    Makes an HTTP request to toggl.com. Returns the parsed JSON as dict.
    """
    from ..toggl import TOGGL_URL

    if headers is None:
        headers = {'content-type': 'application/json'}

    if config is None:
        config = Config.factory()

    url = "{}{}".format(address or TOGGL_URL, url)

    tries = config.retries if config.retries and config.retries > 1 else 1  # There needs to be at least one try!

    exception = None
    for _ in range(tries):
        try:
            logger.debug('Default workspace: {}'.format(config._default_workspace))
            response = _toggl_request(url, method, data, headers, config.get_auth())
            response_json = response.json()
            logger.debug('Response {}:\n{}'.format(response.status_code, pformat(response_json)))
            return response_json
        except (exceptions.TogglThrottlingException, requests.exceptions.ConnectionError) as e:
            sleep(0.1)  # Lets give Toggl API some time to recover
            exception = e
            # TODO: Make it exponential

    # If retries failed then 'e' contains the last Exception/Error, lets re-raise it!
    raise exception
