import json
import logging
import typing
from copy import copy
from urllib.parse import quote_plus
from validate_email import validate_email

import datetime
import pendulum

from toggl.api import base, fields
from toggl import utils, exceptions

logger = logging.getLogger('toggl.api.models')


# Workspace entity
class Workspace(base.TogglEntity):
    _can_create = False
    _can_delete = False

    name = fields.StringField(required=True)
    """
    Name of the workspace
    """

    premium = fields.BooleanField()
    """
    If it's a pro workspace or not. Shows if someone is paying for the workspace or not
    """

    admin = fields.BooleanField()
    """
    Shows whether currently requesting user has admin access to the workspace
    """

    only_admins_may_create_projects = fields.BooleanField()
    """
    Whether only the admins can create projects or everybody
    """

    only_admins_see_billable_rates = fields.BooleanField()
    """
    Whether only the admins can see billable rates or everybody
    """

    rounding = fields.IntegerField()
    """
    Type of rounding:
    
    * round down: -1
    * nearest: 0
    * round up: 1
    """

    rounding_minutes = fields.IntegerField()
    """
    Round up to nearest minute
    """

    default_hourly_rate = fields.FloatField()
    """
    Default hourly rate for workspace, won't be shown to non-admins 
    if the only_admins_see_billable_rates flag is set to true
    """

    default_currency = fields.StringField()
    """
    Default currency for workspace
    """

    # As TogglEntityMeta is by default adding WorkspaceTogglSet to TogglEntity,
    # but we want vanilla TogglSet so defining it here explicitly.
    objects = base.TogglSet()

    def invite(self, *emails):  # type: (str) -> None
        """
        Invites users defined by email addresses. The users does not have to have account in Toggl, in that case after
        accepting the invitation, they will go through process of creating the account in the Toggl web.

        :param emails: List of emails to invite.
        :return: None
        """
        for email in emails:
            if not validate_email(email):
                raise exceptions.TogglValidationException('Supplied email \'{}\' is not valid email!'.format(email))

        emails_json = json.dumps({'emails': emails})
        data = utils.toggl("/workspaces/{}/invite".format(self.id), "post", emails_json, config=self._config)

        if 'notifications' in data and data['notifications']:
            raise exceptions.TogglException(data['notifications'])


class WorkspacedEntity(base.TogglEntity):
    """
    Abstract entity which has linked Workspace
    """

    workspace = fields.MappingField(Workspace, 'wid', write=False,
                                               default=lambda config: config.default_workspace)
    """
    Workspace to which the resource is linked to.
    """


# Premium Entity
class PremiumEntity(WorkspacedEntity):
    """
    Abstract entity that enforces that linked Workspace is premium (paid).
    """

    def save(self, config=None):  # type: (utils.Config) -> None
        if not self.workspace.premium:
            raise exceptions.TogglPremiumException('The entity {} requires to be associated with Premium workspace!')

        super().save(config)


# ----------------------------------------------------------------------------
# Entities definitions
# ----------------------------------------------------------------------------
class Client(WorkspacedEntity):
    """
    Client entity
    """

    name = fields.StringField(required=True)
    """
    Name of client (Required)
    """

    notes = fields.StringField()
    """
    Notes about the client
    """


class Project(WorkspacedEntity):
    """
    Project entity
    """

    name = fields.StringField(required=True)
    """
    Name of the project. (Required)
    """

    client = fields.MappingField(Client, 'cid')
    """
    Client associated to the project.
    """

    active = fields.BooleanField(default=True)
    """
    Whether the project is archived or not. (Default: True)
    """

    is_private = fields.BooleanField(default=True)
    """
    Whether project is accessible for only project users or for all workspace users. (Default: True)
    """

    billable = fields.BooleanField(premium=True)
    """
    Whether the project is billable or not. 
    
    (Available only for Premium workspaces)
    """

    auto_estimates = fields.BooleanField(default=False, premium=True)
    """
    Whether the estimated hours are automatically calculated based on task estimations or manually 
    fixed based on the value of 'estimated_hours'. 
    
    (Available only for Premium workspaces)
    """

    estimated_hours = fields.IntegerField(premium=True)
    """
    If auto_estimates is true then the sum of task estimations is returned, otherwise user inserted hours.
    
    (Available only for Premium workspaces)
    """

    color = fields.IntegerField()
    """
    Id of the color selected for the project
    """

    rate = fields.FloatField(premium=True)
    """
    Hourly rate of the project.
    
    (Available only for Premium workspaces)
    """

    def add_user(self, user, manager=False, rate=None) :  # type: (User, bool, typing.Optional[float]) -> ProjectUser
        """
        Add new user to a project.

        :param user: User to be added
        :param manager: Specifies if the user should have manager's rights
        :param rate: Rate for billing
        :return: ProjectUser instance.
        """
        project_user = ProjectUser(project=self, user=user, workspace=self.workspace, manager=manager, rate=rate)
        project_user.save()

        return project_user


class UserSet(base.WorkspaceTogglSet):

    def current_user(self, config=None):  # type: (utils.Config) -> 'User'
        """
        Fetches details about the current user.
        """
        fetched_entity = utils.toggl('/me', 'get', config=config)
        return self.entity_cls.deserialize(config=config, **fetched_entity['data'])


class User(WorkspacedEntity):
    """
    User entity.
    """

    _can_create = False
    _can_update = False
    _can_delete = False
    _can_get_detail = False

    api_token = fields.StringField()
    """
    API token to use for API calls.
    
    (Returned only for User.objects.current_user() call.)
    """

    send_timer_notifications = fields.BooleanField()

    default_workspace = fields.MappingField(Workspace, 'default_wid')  # type: Workspace
    """
    Default workspace for calls that does not specify Workspace.
    
    (Returned only for User.objects.current_user() call.)
    """

    email = fields.EmailField()
    """
    Email address of user.
    """

    fullname = fields.StringField()
    """
    Full name of the user.
    """

    beginning_of_week = fields.ChoiceField({
        '0': 'Sunday',
        '1': 'Monday',
        '2': 'Tuesday',
        '3': 'Wednesday',
        '4': 'Thursday',
        '5': 'Friday',
        '6': 'Saturday'
    })
    """
    Defines which day is the first day of week for the user.
    """

    language = fields.StringField()
    """
    Stores language used for the user.
    """

    image_url = fields.StringField()
    """
    URL of the profile image of the user.
    """

    timezone = fields.StringField()
    """
    Timezone which is used to convert the times into. 
    
    May differ from one used in this tool, see toggl.utils.Config().
    """

    # TODO: Add possibility to use this value in Config.time_format
    timeofday_format = fields.ChoiceField({
        'H:mm': '24-hour',
        'h:mm A': '12-hour'
    })
    """
    Format of time used to display time.
    """

    # TODO: Add possibility to use this value in Config.datetime_format
    date_format = fields.ChoiceField(
        ["YYYY-MM-DD", "DD.MM.YYYY", "DD-MM-YYYY", "MM/DD/YYYY", "DD/MM/YYYY", "MM-DD-YYYY"]
    )
    """
    Format of date used to display dates.
    """

    objects = UserSet()

    @classmethod
    def signup(cls, email, password, timezone=None, created_with='TogglCLI',
               config=None):  # type: (str, str, str, str, utils.Config) -> User
        """
        Creates brand new user. After creation confirmation email is sent to him.

        :param email: Valid email of the new user.
        :param password: Password of the new user.
        :param timezone: Timezone to be associated with the user. If empty, than timezone from config is used.
        :param created_with: Name of application that created the user.
        :param config:
        :return:
        """
        if config is None:
            config = utils.Config.factory()

        if timezone is None:
            timezone = config.timezone

        if not validate_email(email):
            raise exceptions.TogglValidationException('Supplied email \'{}\' is not valid email!'.format(email))

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

    def __str__(self):
        return '{} (#{})'.format(self.fullname, self.id)


class WorkspaceUser(WorkspacedEntity):
    """
    Workspace User entity.

    This entity represents assignment of specific User into Workspace.
    It additionally configures access rights and several other things.
    """

    _can_get_detail = False
    _can_create = False

    email = fields.EmailField(write=False)
    """
    Email of the user.
    """

    active = fields.BooleanField()
    """
    If user is active in Workspace.
    """

    admin = fields.BooleanField(admin_only=True)
    """
    Weather user has admin privilege in the Workspace. 
    """

    user = fields.MappingField(User, 'uid', write=False)
    """
    User's instance
    """

    def __str__(self):
        return '{} (#{})'.format(self.email, self.id)


class ProjectUser(WorkspacedEntity):
    """
    Project User entity.

    Similarly to WorkspaceUser, it is entity which represents assignment of specific User into Project.
    It additionally configures access rights and several other things.
    """
    _can_get_detail = False

    rate = fields.FloatField(admin_only=True)
    """
    Hourly rate for the project user in the currency of the project's client or in workspace default currency.
    
    (Available only for Premium workspaces)
    """

    manager = fields.BooleanField(default=False)
    """
    Admin rights for this project    
    """

    project = fields.MappingField(Project, 'pid', write=False)
    """
    Project to which the User is assigned.
    """

    user = fields.MappingField(User, 'uid', write=False)
    """
    User which is linked to Project.
    """

    def __str__(self):
        return '{}/{} (#{})'.format(self.project.name, self.user.email, self.id)


class Task(PremiumEntity):
    """
    Task entity.

    This entity is available only for Premium workspaces.
    """

    name = fields.StringField(required=True)
    """
    Name of task
    """

    project = fields.MappingField(Project, 'pid', required=True)
    """
    Project to which the Task is linked to.
    """

    user = fields.MappingField(User, 'uid')
    """
    User to which the Task is assigned to.
    """

    estimated_seconds = fields.IntegerField()
    """
    Estimated duration of task in seconds.
    """

    active = fields.BooleanField(default=True)
    """
    Whether the task is done or not.
    """

    tracked_seconds = fields.IntegerField(write=False)
    """
    Total time tracked (in seconds) for the task.
    """


class Tag(WorkspacedEntity):
    """
    Tag entity
    """

    _can_get_detail = False

    name = fields.StringField(required=True)
    """
    Name of tag (Required)
    """


# Time Entry entity


class TimeEntryDateTimeField(fields.DateTimeField):
    """
    Special extension of DateTimeField which handles better way of formatting the datetime for CLI use-case.
    """

    def format(self, value, config=None, instance=None, display_running=False,
               only_time_for_same_day=None):
        if not display_running and not only_time_for_same_day:
            return super().format(value, config)

        if value is None and display_running:
            return 'running'

        if instance is not None and only_time_for_same_day:
            config = config or utils.Config.factory()

            if value.in_timezone(config.timezone).to_date_string() == only_time_for_same_day.in_timezone(
                config.timezone).to_date_string():
                return value.in_timezone(config.timezone).format(config.time_format)

        return super().format(value, config)


def get_duration(name, instance):  # type: (str, base.Entity) -> int
    """
    Getter for Duration Property field.

    Handles correctly the conversion of of negative running duration (for more refer to the Toggl API doc).
    """
    if instance.is_running:
        return instance.start.int_timestamp * -1

    return int((instance.stop - instance.start).in_seconds())


def set_duration(name, instance, value, init=False):  # type: (str, base.Entity, typing.Optional[int], bool) -> typing.Optional[bool]
    """
    Setter for Duration Property field.
    """
    if init is True:
        instance.is_running = False

    if value is None:
        return

    if value > 0:
        instance.is_running = False
        instance.stop = instance.start + pendulum.duration(seconds=value)
    else:
        instance.is_running = True
        instance.stop = None

    return True  # Any change will result in updated instance's state.


def format_duration(value, config=None):  # type: (int, utils.Config) -> str
    """
    Formatting the duration into HOURS:MINUTES:SECOND format.
    """
    if value < 0:
        config = config or utils.Config.factory()
        value = pendulum.now(tz=config.tz).int_timestamp + value

    hours = value // 3600
    minutes = (value - hours * 3600) // 60
    seconds = (value - hours * 3600 - minutes * 60) % 60

    return '{}:{:02d}:{:02d}'.format(hours, minutes, seconds)


datetime_type = typing.Union[datetime.datetime, pendulum.DateTime]


class TimeEntrySet(base.TogglSet):
    """
    TogglSet which is extended by current() method which returns the currently running TimeEntry.
    Moreover it extends the filtrating mechanism by native filtering according start and/or stop time.
    """

    def build_list_url(self, caller, config, conditions):  # type: (str, utils.Config, typing.Dict) -> str
        url = '/{}'.format(self.base_url)

        if caller == 'filter':
            start = conditions.pop('start', None)
            stop = conditions.pop('stop', None)

            if start is not None or stop is not None:
                url += '?'

            if start is not None:
                url += 'start_date={}&'.format(quote_plus(start.isoformat()))

            if stop is not None:
                url += 'end_date={}&'.format(quote_plus(stop.isoformat()))

        return url

    def current(self, config=None):  # type: (utils.Config) -> TimeEntry
        """
        Method that returns currently running TimeEntry or None if there is no currently running time entry.

        :param config:
        :return:
        """
        config = config or utils.Config.factory()
        fetched_entity = utils.toggl('/time_entries/current', 'get', config=config)

        if fetched_entity.get('data') is None:
            return None

        return self.entity_cls.deserialize(config=config, **fetched_entity['data'])

    def _build_reports_url(self, start, stop, page, wid):
        url = '/details?user_agent=toggl_cli&workspace_id={}&page={}'.format(wid, page)

        if start is not None:
            url += '&since={}'.format(quote_plus(start.isoformat()))

        if stop is not None:
            url += '&until={}'.format(quote_plus(stop.isoformat()))

        return url

    def _should_fetch_more(self, page, returned):  # type: (int, typing.Dict) -> bool
        return page * returned['per_page'] < returned['total_count']

    def _deserialize_from_reports(self, config, entity_dict):
        entity = {
            'id': entity_dict['id'],
            'start': entity_dict['start'],
            'stop': entity_dict['end'],
            'duration': entity_dict['dur'] / 1000,
            'description': entity_dict['description'],
            'tags': entity_dict['tags'],
            'pid': entity_dict['pid'],
            'tid': entity_dict['tid'],
            'billable': entity_dict['billable'],
        }

        return self.entity_cls.deserialize(config=config, **entity)

    def all_from_reports(self, start=None, stop=None, workspace=None, config=None):  # type: (typing.Optional[datetime_type], typing.Optional[datetime_type], typing.Union[str, int, Workspace], typing.Optional[utils.Config]) -> typing.Generator[TimeEntry, None, None]
        """
        Method that implements fetching of all time entries through Report API.
        No limitation on number of time entries.

        :param start: From when time entries should be fetched. Defaults to today - 6 days.
        :param stop: Until when time entries should be fetched. Defaults to today, unless since is in future or more than year ago, in this case until is since + 6 days.
        :param workspace: Workspace from where should be the time entries fetched from. Defaults to Config.default_workspace.
        :param config:
        :return: Generator that yields TimeEntry
        """
        from .. import toggl
        config = config or utils.Config.factory()
        page = 1

        try:
            wid = workspace.id
        except AttributeError:
            try:
                wid = int(workspace)
            except (ValueError, TypeError):
                wid = config.default_workspace.id

        while True:
            url = self._build_reports_url(start, stop, page, wid)
            returned = utils.toggl(url, 'get', config=config, address=toggl.REPORTS_URL)

            if not returned.get('data'):
                return

            for entity in returned.get('data'):
                yield self._deserialize_from_reports(config, entity)

            if not self._should_fetch_more(page, returned):
                return

            page += 1


class TimeEntry(WorkspacedEntity):
    description = fields.StringField()
    """
    Description of the entry.
    """

    project = fields.MappingField(Project, 'pid')
    """
    Project to which the Time entry is linked to.
    """

    task = fields.MappingField(Task, 'tid', premium=True)
    """
    Task to which the Time entry is linked to.

    (Available only for Premium workspaces)
    """

    billable = fields.BooleanField(default=False, premium=True)
    """
    If available to be billed. (Default: False)
    
    (Available only for Premium workspaces)
    """

    start = TimeEntryDateTimeField(required=True)
    """
    DateTime of start of the time entry. (Required)
    """

    stop = TimeEntryDateTimeField()
    """
    DateTime of end of the time entry.
    """

    duration = fields.PropertyField(get_duration, set_duration, formatter=format_duration)
    """
    Dynamic field of entry's duration in seconds. 
    
    If the time entry is currently running, the duration attribute contains a negative value, 
    denoting the start of the time entry in seconds since epoch (Jan 1 1970). The correct duration can be 
    calculated as current_time + duration, where current_time is the current time in seconds since epoch.
    """

    created_with = fields.StringField(required=True, default='TogglCLI', read=False)
    """
    Information who created the time entry.
    """

    tags = fields.SetField()
    """
    Set of tags associated with the time entry.
    """

    objects = TimeEntrySet()

    def __init__(self, start, stop=None, duration=None, **kwargs):
        if stop is None and duration is None:
            raise ValueError(
                'You can create only finished time entries through this way! '
                'You must supply either \'stop\' or \'duration\' parameter!'
            )

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
    def start_and_save(cls, start=None, config=None, **kwargs):  # type: (pendulum.DateTime, utils.Config, **typing.Any) -> TimeEntry
        """
        Creates a new running entry.

        If there is another running time entry in the time of calling this method, then the running entry is stopped.
        This is handled by Toggl's backend.

        :param start: The DateTime object representing start of the new TimeEntry. If None than current time is used.
        :param config:
        :param kwargs: Other parameters for creating the new TimeEntry
        :return: New running TimeEntry
        """
        config = config or utils.Config.factory()

        if start is None:
            start = pendulum.now(config.timezone)

        if 'stop' in kwargs or 'duration' in kwargs:
            raise RuntimeError('With start_and_save() method you can not create finished entries!')

        instance = cls.__new__(cls)
        instance.__change_dict__ = {}
        instance.is_running = True
        instance._config = config
        instance.start = start

        for key, value in kwargs.items():
            setattr(instance, key, value)

        instance.save()

        return instance

    def stop_and_save(self=None, stop=None):
        """
        Stops running the entry. It has to be running entry.

        :param stop: DateTime which should be set as stop time. If None, then current time is used.
        :return: Self
        """
        if self is None:
            # noinspection PyMethodFirstArgAssignment
            self = TimeEntry.objects.current()
            if self is None:
                raise exceptions.TogglValidationException('There is no running entry to be stoped!')

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
        """
        Creates new time entry with same description as the self entry and starts running it.

        :param start: The DateTime object representing start of the new TimeEntry. If None than current time is used.
        :return: The new TimeEntry.
        """
        if self.is_running:
            logger.warning('Trying to continue time entry {} which is already running!'.format(self))

        config = self._config or utils.Config.factory()

        if start is None:
            start = pendulum.now(config.timezone)

        new_entry = copy(self)
        new_entry.start = start
        new_entry.stop = None
        new_entry.is_running = True

        new_entry.save(config=config)

        return new_entry

    def __str__(self):
        return '{} (#{})'.format(getattr(self, 'description', ''), self.id)
