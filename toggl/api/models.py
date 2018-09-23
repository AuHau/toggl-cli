import json
from copy import copy
from urllib.parse import urlencode

import pendulum

from . import base
from . import fields
from .. import utils
from .. import exceptions


# Workspace entity
class Workspace(base.TogglEntity):
    _can_create = False
    _can_delete = False

    name = fields.StringField(required=True)
    premium = fields.BooleanField()
    admin = fields.BooleanField()
    only_admins_may_create_projects = fields.BooleanField()
    only_admins_see_billable_rates = fields.BooleanField()
    rounding = fields.IntegerField()
    rounding_minutes = fields.IntegerField()
    default_hourly_rate = fields.FloatField()

    objects = base.TogglSet()


class WorkspaceEntity(base.TogglEntity):
    workspace = fields.MappingField(Workspace, 'wid', default=lambda config: config.default_workspace.id)


# Premium Entity
class PremiumEntity(WorkspaceEntity):
    """
    Abstract entity that enforces that linked Workspace is premium (paid).
    """
    def save(self, config=None):
        if not self.workspace.premium:
            raise exceptions.TogglPremiumException('The entity {} requires to be associated with Premium workspace!')

        super().save(config)


# ----------------------------------------------------------------------------
# Entities definitions
# ----------------------------------------------------------------------------
class Client(WorkspaceEntity):
    name = fields.StringField(required=True)
    notes = fields.StringField()


class Project(WorkspaceEntity):
    name = fields.StringField(required=True)
    customer = fields.MappingField(Client, 'cid')
    active = fields.BooleanField(default=True)
    is_private = fields.BooleanField(default=True)
    billable = fields.BooleanField(default=True)
    auto_estimates = fields.BooleanField(default=False)
    estimated_hours = fields.IntegerField()
    color = fields.IntegerField()
    rate = fields.FloatField()

    def validate(self):
        super(Project, self).validate()

        if self.customer is not None and not Client.objects.get(self.cid):
            raise exceptions.TogglValidationException("Client specified by ID does not exists!")


class UserSet(base.WorkspaceToggleSet):

    def current_user(self, config=None):
        fetched_entity = utils.toggl('/me', 'get', config=config)
        return self.entity_cls.deserialize(config=config, **fetched_entity['data'])


class User(WorkspaceEntity):
    _can_create = False
    _can_update = False
    _can_delete = False

    api_token = fields.StringField()
    send_timer_notifications = fields.BooleanField()
    openid_enabled = fields.BooleanField()
    default_workspace = fields.MappingField(Workspace, 'default_wid')
    email = fields.EmailField()
    fullname = fields.StringField()
    store_start_and_stop_time = fields.BooleanField()
    beginning_of_week = fields.ChoiceField({
        0: 'Sunday',
        1: 'Monday',
        2: 'Tuesday',
        3: 'Wednesday',
        4: 'Thursday',
        5: 'Friday',
        6: 'Saturday'
    })
    language = fields.StringField()
    image_url = fields.StringField()
    timezone = fields.StringField()

    objects = UserSet()

    @classmethod
    def signup(cls, email, password, timezone=None, created_with='TogglCLI', config=None):
        if config is None:
            config = utils.Config.factory()

        if timezone is None:
            timezone = config.timezone

        user_json = json.dumps({'user': {
            'email': email,
            'password': password,
            'timezone': timezone,
            'created_with': created_with
        }})
        data = utils.toggl("/signups", "post", user_json, config=config)
        return cls.deserialize(config=config, **data['data'])

    def is_admin(self, workspace):
        wid = workspace.id if isinstance(workspace, Workspace) else workspace

        workspace_user = WorkspaceUser.objects.get(wid=wid, uid=self.id)
        return workspace_user.admin


class WorkspaceUser(WorkspaceEntity):
    _can_get_detail = False
    _can_create = False

    email = fields.EmailField(is_read_only=True)
    active = fields.BooleanField()
    admin = fields.BooleanField(admin_only=True)
    user = fields.MappingField(User, 'uid', is_read_only=True)

    @classmethod
    def invite(cls, *emails, wid=None, config=None):
        config = config or utils.Config.factory()
        wid = wid or config.default_workspace.id

        emails_json = json.dumps({'emails': emails})
        data = utils.toggl("/workspaces/{}/invite".format(wid), "post", emails_json, config=config)

        if 'notifications' in data and data['notifications']:
            raise exceptions.TogglException(data['notifications'])


class Task(PremiumEntity):
    name = fields.StringField(required=True)
    project = fields.MappingField(Project, 'pid', required=True)
    user = fields.MappingField(User, 'uid')
    estimated_seconds = fields.IntegerField()
    active = fields.BooleanField(default=True)
    tracked_seconds = fields.IntegerField(is_read_only=True)


class TimeEntryDateTimeField(fields.DateTimeField):

    def format(self, value, config=None, instance=None, display_running=False, only_time_for_same_day=False):
        if not display_running and not only_time_for_same_day:
            return super().format(value, config)

        if value is None and display_running:
            return 'running'

        if instance is not None \
            and only_time_for_same_day \
            and (value - instance.start).in_days() == 0:

            config = config or utils.Config.factory()

            return value.in_timezone(config.timezone).format('LTS')

        return super().format(value, config)


def get_duration(name, instance, serializing=False):
    if instance.is_running:
        return instance.start.int_timestamp * -1

    return int((instance.stop - instance.start).in_seconds())


def set_duration(name, instance, value, init=False):
    if value is None:
        return

    if value > 0:
        instance.is_running = False
        instance.stop = instance.start + pendulum.duration(seconds=value)
    else:
        instance.is_running = True
        instance.stop = None


def format_duration(value, config=None):
    if value < 0:
        value = pendulum.now().int_timestamp + value

    hours = value // 3600
    minutes = (value - hours * 3600) // 60
    seconds = (value - hours * 3600 - minutes * 60) % 60

    return '{}:{:02d}:{:02d}'.format(hours, minutes, seconds)


class TimeEntrySet(base.TogglSet):

    def build_list_url(self, wid=None):
        return '/{}'.format(self.url)

    def current(self, config=None):
        config = config or utils.Config.factory()
        fetched_entity = utils.toggl('/time_entries/current', 'get', config=config)

        if fetched_entity.get('data') is None:
            return None

        return self.entity_cls.deserialize(config=config, **fetched_entity['data'])

    def filter(self, order='desc', start=None, stop=None, config=None, contain=False, **conditions):
        if start is None and stop is None:
            return super().filter(order=order, config=config, contain=contain, **conditions)

        config = config or utils.Config.factory()
        url = self.build_list_url() + '?'

        if start is not None:
            url += 'start_date={}&'.format(urlencode(start.isoformat()))

        if stop is not None:
            url += 'stop_date={}&'.format(urlencode(stop.isoformat()))

        fetched_entities = utils.toggl(url, 'get', config=config)

        if fetched_entities is None:
            return []

        output = []
        i = 0 if order == 'asc' else len(fetched_entities) - 1
        while 0 <= i < len(fetched_entities):
            entity = self.entity_cls.deserialize(config=config, **fetched_entities[i])

            if base.evaluate_conditions(conditions, entity, contain):
                output.append(entity)

            if order == 'asc':
                i += 1
            else:
                i -= 1

        return output

    def all(self, order='desc', wid=None, config=None):
        return super().all(order=order, config=config)


class TimeEntry(WorkspaceEntity):
    description = fields.StringField()
    project = fields.MappingField(Project, 'pid')
    task = fields.MappingField(Task, 'tid')
    billable = fields.BooleanField(default=False, admin_only=True)
    start = TimeEntryDateTimeField(required=True)
    stop = TimeEntryDateTimeField()
    duration = fields.PropertyField(get_duration, set_duration, formater=format_duration)
    created_with = fields.StringField(required=True, default='TogglCLI')
    tags = fields.ListField()

    objects = TimeEntrySet()

    def __init__(self, start, stop=None, duration=None, **kwargs):
        if stop is None and duration is None:
            raise ValueError(
                'You can create only finished time entries through this way! '
                'You must supply either \'stop\' or \'duration\' parameter!'
            )

        self.is_running = False

        super().__init__(start=start, stop=stop, duration=duration, **kwargs)

    @classmethod
    def get_url(cls):
        return 'time_entries'

    def to_dict(self, serialized=False, changes_only=False):
        # Enforcing serialize duration when start or stop changes
        if changes_only and (self.__change_dict__.get('start') or self.__change_dict__.get('stop')):
            self.__change_dict__['duration'] = None

        return super().to_dict(serialized=serialized, changes_only=changes_only)

    @classmethod
    def start_and_save(cls, start=None, config=None, **kwargs):
        config = config or utils.Config.factory()

        if start is None:
            start = pendulum.now(config.timezone)

        if 'stop' in kwargs or 'duration' in kwargs:
            raise RuntimeError('With start() method you can not create finished entries!')

        instance = cls.__new__(cls)
        instance.is_running = True
        instance._config = config
        instance.start = start

        for key, value in kwargs.items():
            setattr(instance, key, value)

        instance.save()

        return instance

    def stop_and_save(self, stop=None):
        if not self.is_running:
            raise exceptions.TogglValidationException('You can\'t stop not running entry!')

        config = self._config or utils.Config.factory()

        if stop is None:
            stop = pendulum.now(config.timezone)

        self.stop = stop
        self.is_running = False
        self.save(config=config)

        return self

    def continue_and_save(self, start=None):
        config = self._config or utils.Config.factory()

        if start is None:
            start = pendulum.now(config.timezone)

        new_entry = copy(self)
        new_entry.start = start
        new_entry.stop = None
        new_entry.is_running = True

        new_entry.save(config=config)

        return new_entry
