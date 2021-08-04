import re
import time
import typing
from pathlib import Path

from click.testing import Result
from click.testing import CliRunner

from toggl.cli.commands import cli
from toggl import utils, api


def inner_cmd(cmd, config=None, simple=True, *args):  # type: (str, str, bool, typing.List[str]) -> ParsingResult
    config = config or get_config()

    parsed = re.findall(r"([\"]([^\"]+)\")|([']([^']+)')|(\S+)",
                        cmd)  # Simulates quoting of strings with spaces (eq. filter -n "some important task")
    args = list(args) + [i[1] or i[3] or i[4] for i in parsed]

    if simple:
        args.insert(0, '--simple')

    result = CliRunner().invoke(cli, args, obj={'config': config})
    time.sleep(1)

    # Lets re-print it so pytest can catch it and show it on fails.
    print(result.stdout)

    if result.exception and not isinstance(result.exception, SystemExit):
        raise result.exception

    return ParsingResult(result)


def wrapper_inner_cmd(config=None):
    suggested_config = config

    def wrapper_func(cmd, config=None, *args, **kwargs):
        return inner_cmd(cmd, config or get_config(suggested_config), *args, **kwargs)

    return wrapper_func


def get_all_configs():
    config_path = Path(__file__).parent / 'configs'  # type: Path

    for config_file in config_path.iterdir():
        yield get_config(config_file.name)


def get_config(config='non-premium.config'):
    if isinstance(config, utils.Config):
        return config

    config_path = Path(__file__).parent / 'configs' / config

    if not config_path.exists():
        raise ValueError('Unknown config path: ' + str(config_path))

    return utils.Config.factory(str(config_path))


class ParsingResult:

    def __init__(self, result):  # type: (Result) -> None
        if result is None:
            raise TypeError('Result must not be None!')

        self.obj = result

    def created_id(self):
        regex = re.search(r'#(\d+)', self.obj.output)

        if not regex:
            raise RuntimeError('No ID found in the created message \'{}\'!'.format(self.obj.output))

        return regex.group(1)

    def parse_list(self):
        output = self.obj.output.strip()
        parsed = []

        for line in output.split('\n'):
            parsed.append(line.split('\t'))

        return parsed[1:]

    def parse_detail(self):
        output = self.obj.output.strip().split('\n')
        parsed = {}

        regex = re.search(r'(?P<name>[\w ]+)?#(?P<id>\d+)$', output[0])

        if not regex:
            raise RuntimeError('Unknown structure of detail string! >> ' + output[0])

        name = regex.group('name')
        parsed['name'] = name.strip() if name is not None else None
        parsed['id'] = regex.group('id')

        for line in output[1:]:
            regex = re.search(r'([\w ]+):(.*)', line)
            key = regex.group(1)
            value = regex.group(2)

            key = key.strip().replace(' ', '_')
            parsed[key.lower()] = value.strip()

        return parsed


class Cleanup:
    @staticmethod
    def _ids_cleanup(base, config=None, batch=False, *ids):
        config = config or get_config()

        if batch:
            utils.toggl('/{}/{}'.format(base, ','.join([str(eid) for eid in ids])), 'delete', config=config)
        else:
            for entity_id in ids:
                utils.toggl('/{}/{}'.format(base, entity_id), 'delete', config=config)

    @staticmethod
    def _all_cleanup(cls, config=None):
        config = config or get_config()
        entities = cls.objects.all(config=config)
        Cleanup.cleanup(entities)

    @staticmethod
    def cleanup(entities):
        """
        General cleanup for any TogglEntity instance
        """
        for instance in entities:
            instance.delete()

    @staticmethod
    def all_configs():
        for config in get_all_configs():
            Cleanup.all(config)

    @staticmethod
    def all(config=None):
        """
        Expensive operation as it goes over all resources in Toggl.
        """
        Cleanup.time_entries(config=config)
        Cleanup.project_users(config=config)
        Cleanup.workspace_users(config=config)
        Cleanup.tasks(config=config)
        Cleanup.tags(config=config)
        Cleanup.projects(config=config)
        Cleanup.clients(config=config)

    @staticmethod
    def clients(config=None, *ids):
        if not ids:
            Cleanup._all_cleanup(api.Client, config=config)
        else:
            Cleanup._ids_cleanup('clients', config, False, *ids)

    @staticmethod
    def tags(config=None, *ids):
        if not ids:
            Cleanup._all_cleanup(api.Tag, config=config)
        else:
            Cleanup._ids_cleanup('tags', config, False, *ids)

    @staticmethod
    def time_entries(config=None, *ids):
        if not ids:
            config = config or get_config()
            entities = api.TimeEntry.objects.all(config=config)
            ids = [entity.id for entity in entities]

        if not ids:
            return

        Cleanup._ids_cleanup('time_entries', config, True, *ids)

    @staticmethod
    def project_users(config=None, *ids):
        if not ids:
            Cleanup._all_cleanup(api.ProjectUser, config=config)
        else:
            Cleanup._ids_cleanup('project_users', config, False, *ids)

    @staticmethod
    def projects(config=None, *ids):
        if not ids:
            config = config or get_config()
            entities = api.Project.objects.all(config=config)
            ids = [entity.id for entity in entities]

        if not ids:
            return

        Cleanup._ids_cleanup('projects', config, True, *ids)

    @staticmethod
    def tasks(config=None, *ids):
        if not ids:
            Cleanup._all_cleanup(api.Task, config=config)
        else:
            Cleanup._ids_cleanup('tasks', config, False, *ids)

    @staticmethod
    def workspace_users(config=None, *ids):
        if not ids:
            config = config or get_config()
            # Making sure not to delete myself from the Workspace
            entities = filter(lambda wu: wu.__dict__.get('uid') != config.user.id,
                              api.WorkspaceUser.objects.all(config=config))
            Cleanup.cleanup(entities)
        else:
            Cleanup._ids_cleanup('workspace_users', config, False, *ids)
