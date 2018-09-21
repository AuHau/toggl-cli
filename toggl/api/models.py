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


class UserSet(base.TogglSet):

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
    # task = fields.MappingField(Task, 'tid') TODO: Tasks
    billable = fields.BooleanField(default=False, admin_only=True)
    start = TimeEntryDateTimeField(required=True)
    stop = TimeEntryDateTimeField()
    duration = fields.PropertyField(get_duration, set_duration, formater=format_duration)
    created_with = fields.StringField(required=True, default='TogglCLI')
    # tags = fields.ListField() TODO: Tags & ListField

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


# ----------------------------------------------------------------------------
# TimeEntry
# ----------------------------------------------------------------------------
# class TimeEntry(object):
#     """
#     Represents a single time entry.
#
#     NB: If duration is negative, it represents the amount of elapsed time
#     since the epoch. It's not well documented, but toggl expects this duration
#     to be in UTC.
#     """
#
#     def __init__(self, description=None, start_time=None, stop_time=None,
#                  duration=None, workspace_name=None, project_name=None,
#                  data_dict=None):
#         """
#         Constructor. None of the parameters are required at object creation,
#         but the object is validated before data is sent to toggl.
#         * description(str) is the optional time entry description.
#         * start_time(datetime) is the optional time this entry started.
#         * stop_time(datetime) is the optional time this entry ended.
#         * duration(int) is the optional duration, in seconds.
#         * project_name(str) is the optional name of the project without
#           the '@' prefix.
#         * data_dict is an optional dictionary created from a JSON-encoded time
#           entry from toggl. If this parameter is used to initialize the object,
#           its values will supercede any other constructor parameters.
#         """
#
#         # All toggl data is stored in the "data" dictionary.
#         self.data = {}
#
#         if description is not None:
#             self.data['description'] = description
#
#         if start_time is not None:
#             self.data['start'] = start_time.isoformat()
#
#         if stop_time is not None:
#             self.data['stop'] = stop_time.isoformat()
#
#         if workspace_name is not None:
#             workspace = WorkspaceList().find_by_name(workspace_name)
#             if workspace is None:
#                 raise RuntimeError("Workspace '{}' not found.".format(workspace_name))
#             self.data['wid'] = workspace['id']
#
#         if project_name is not None:
#             project = ProjectList(workspace_name).find_by_name(project_name)
#             if project is None:
#                 raise RuntimeError("Project '{}' not found.".format(project_name))
#             self.data['pid'] = project['id']
#
#         if duration is not None:
#             self.data['duration'] = duration
#
#         # If we have a dictionary of data, use it to initialize this.
#         if data_dict is not None:
#             self.data = data_dict
#
#         self.data['created_with'] = 'toggl-cli'
#
#     def add(self):
#         """
#         Adds this time entry as a completed entry.
#         """
#         self.validate()
#         utils.toggl("/time_entries", "post", self.json())
#
#     def continue_entry(self, continued_at=None):
#         """
#         Continues an existing entry.
#         """
#         create = utils.Config().get('options', 'continue_creates').lower() == 'true'
#
#         # Was the entry started today or earlier than today?
#         start_time = utils.DateAndTime().parse_iso_str(self.get('start'))
#
#         if create or start_time <= utils.DateAndTime().start_of_today():
#             # Entry was from a previous day. Create a new entry from this
#             # one, resetting any identifiers or time data.
#             new_entry = TimeEntry()
#             new_entry.data = self.data.copy()
#             new_entry.set('at', None)
#             new_entry.set('created_with', 'toggl-cli')
#             new_entry.set('duration', None)
#             new_entry.set('duronly', False)
#             new_entry.set('guid', None)
#             new_entry.set('id', None)
#             if continued_at:
#                 new_entry.set('start', continued_at.isoformat())
#             else:
#                 new_entry.set('start', None)
#             new_entry.set('stop', None)
#             new_entry.set('uid', None)
#             new_entry.start()
#         else:
#             # To continue an entry from today, set duration to
#             # 0 - (current_time - duration).
#             now = utils.DateAndTime().duration_since_epoch(utils.DateAndTime().now())
#             duration = ((continued_at or utils.DateAndTime().now()) - utils.DateAndTime().now()).total_seconds()
#             self.data['duration'] = 0 - (now - int(self.data['duration'])) - duration
#             self.data['duronly'] = True  # ignore start/stop times from now on
#
#             utils.toggl("/time_entries/{}".format(self.data['id']), 'put', data=self.json())
#
#             utils.Logger.debug('Continuing entry {}'.format(self.json()))
#
#     def delete(self):
#         """
#         Deletes this time entry from the server.
#         """
#         if not self.has('id'):
#             raise Exception("Time entry must have an id to be deleted.")
#
#         url = "/time_entries/{}".format(self.get('id'))
#         utils.toggl(url, 'delete')
#
#     def get(self, prop):
#         """
#         Returns the given toggl time entry property as documented at
#         https://github.com/toggl/toggl_api_docs/blob/master/chapters/time_entries.md
#         or None, if the property isn't set.
#         """
#         if prop in self.data:
#             return self.data[prop]
#         else:
#             return None
#
#     def has(self, prop):
#         """
#         Returns True if this time entry has the given property and it's not
#         None, False otherwise.
#         """
#         return prop in self.data and self.data[prop] is not None
#
#     def json(self):
#         """
#         Returns a JSON dump of this entire object as toggl payload.
#         """
#         return '{{"time_entry": {}}}'.format(json.dumps(self.data))
#
#     def normalized_duration(self):
#         """
#         Returns a "normalized" duration. If the native duration is positive,
#         it is simply returned. If negative, we return current_time + duration
#         (the actual amount of seconds this entry has been running). If no
#         duration is set, raises an exception.
#         """
#         if 'duration' not in self.data:
#             raise Exception('Time entry has no "duration" property')
#         if self.data['duration'] > 0:
#             return int(self.data['duration'])
#         else:
#             return time.time() + int(self.data['duration'])
#
#     def set(self, prop, value):
#         """
#         Sets the given toggl time entry property to the given value. If
#         value is None, the property is removed from this time entry.
#         Properties are documented at
#         https://github.com/toggl/toggl_api_docs/blob/master/chapters/time_entries.md
#         """
#         if value is not None:
#             self.data[prop] = value
#         elif prop in self.data:
#             self.data.pop(prop)
#
#     def start(self):
#         """
#         Starts this time entry by telling toggl. If this entry doesn't have
#         a start time yet, it is set to now. duration is set to
#         0-start_time.
#         """
#         if self.has('start'):
#             start_time = utils.DateAndTime().parse_iso_str(self.get('start'))
#             self.set('duration', 0 - utils.DateAndTime().duration_since_epoch(start_time))
#
#             self.validate()
#
#             utils.toggl("/time_entries", "post", self.json())
#         else:
#             data = utils.toggl("/time_entries/start", "post", self.json())
#
#             # We will get the start time from Toggl to keep consistency
#             self.data['start'] = data['data']['start']
#
#         utils.Logger.debug('Started time entry: {}'.format(self.json()))
#
#     def stop(self, stop_time=None):
#         """
#         Stops this entry. Sets the stop time at the datetime given, calculates
#         a duration, then updates toggl.
#         stop_time(datetime) is an optional datetime when this entry stopped. If
#         not given, then stops the time entry now.
#         """
#         utils.Logger.debug('Stopping entry {}'.format(self.json()))
#         self.validate(['description'])
#         if int(self.data['duration']) >= 0:
#             raise Exception("toggl: time entry is not currently running.")
#         if 'id' not in self.data:
#             raise Exception("toggl: time entry must have an id.")
#
#         if stop_time is None:
#             stop_time = utils.DateAndTime().now()
#         self.set('stop', stop_time.isoformat())
#         self.set('duration',
#                  utils.DateAndTime().duration_since_epoch(stop_time) + int(self.get('duration')))
#
#         utils.toggl("/time_entries/{}".format(self.get('id')), 'put', self.json())
#
#     def __str__(self):
#         """
#         Returns a human-friendly string representation of this time entry.
#         """
#         from .toggl import VERBOSE
#
#         if float(self.data['duration']) > 0:
#             is_running = '  '
#         else:
#             is_running = '* '
#
#         if 'pid' in self.data:
#             project = ProjectList().find_by_id(self.data['pid'])
#             if project is not None:
#                 project_name = " @{} ".format(project['name'])
#             elif 'wid' in self.data:
#                 ProjectList().fetch_by_wid(self.data['wid'])
#                 project_name = " @{} ".format(ProjectList().find_by_id(self.data['pid'])['name'])
#             else:
#                 project_name = " "
#
#         else:
#             project_name = " "
#
#         s = "{}{}{}{}".format(
#             is_running, self.data.get('description'), project_name,
#             utils.DateAndTime().elapsed_time(int(self.normalized_duration()))
#         )
#
#         if VERBOSE:
#             s += " [{}]".format(self.data['id'])
#
#         return s
#
#     def validate(self, exclude=None):
#         """
#         Ensure this time entry contains the minimum information required
#         by toggl, as well as passing some basic sanity checks. If not,
#         an exception is raised.
#
#         * toggl requires start, duration, and created_with.
#         * toggl doesn't require a description, but we do.
#         """
#         required = ['start', 'duration', 'description', 'created_with']
#
#         if exclude is None:
#             exclude = []
#
#         for prop in required:
#             if not self.has(prop) and prop not in exclude:
#                 utils.Logger.debug(self.json())
#                 raise Exception("toggl: time entries must have a '{}' property.".format(prop))
#         return True
#
#
# # ----------------------------------------------------------------------------
# # TimeEntryList
# # ----------------------------------------------------------------------------
# class TimeEntryList(six.Iterator):
#     """
#     A utils.Singleton list of recent TimeEntry objects.
#     """
#
#     __metaclass__ = utils.Singleton
#
#     def __init__(self):
#         """
#         Fetches time entry data from toggl.
#         """
#         self.time_entries = None
#         self.reload()
#
#     def __iter__(self):
#         """
#         Start iterating over the time entries.
#         """
#         self.iter_index = 0
#         return self
#
#     def find_by_description(self, description):
#         """
#         Searches the list of entries for the one matching the given
#         description, or return None. If more than one entry exists
#         with a matching description, the most recent one is
#         returned.
#         """
#         for entry in reversed(self.time_entries):
#             if entry.get('description') == description:
#                 return entry
#         return None
#
#     def get_latest(self):
#         """
#         Returns the latest entry
#         """
#         if len(self.time_entries) == 0:
#             return None
#         return self.time_entries[len(self.time_entries) - 1]
#
#     def __next__(self):
#         """
#         Returns the next time entry object.
#         """
#         if not self.time_entries or self.iter_index >= len(self.time_entries):
#             raise StopIteration
#         else:
#             self.iter_index += 1
#             return self.time_entries[self.iter_index - 1]
#
#     def now(self):
#         """
#         Returns the current time entry object or None.
#         """
#         for entry in self:
#             if int(entry.get('duration')) < 0:
#                 return entry
#         return None
#
#     def reload(self):
#         """
#         Force reloading time entry data from the server. Returns self for
#         method chaining.
#         """
#         # Fetch time entries from 00:00:00 yesterday to 23:59:59 today.
#         url = "/time_entries?start_date={}&end_date={}".format(
#             urllib.parse.quote(utils.DateAndTime().start_of_yesterday().isoformat('T')),
#             urllib.parse.quote(utils.DateAndTime().last_minute_today().isoformat('T'))
#         )
#         utils.Logger.debug(url)
#         entries = utils.toggl(url, 'get')
#
#         # Build a list of entries.
#         self.time_entries = []
#         for entry in entries:
#             te = TimeEntry(data_dict=entry)
#             utils.Logger.debug(te.json())
#             utils.Logger.debug('---')
#             self.time_entries.append(te)
#
#         # Sort the list by start time.
#         sorted(self.time_entries, key=lambda time_entry: time_entry.data['start'])
#         return self
#
#     def __str__(self):
#         """
#         Returns a human-friendly list of recent time entries.
#         """
#         # Sort the time entries into buckets based on "Month Day" of the entry.
#         days = {}
#         for entry in self.time_entries:
#             start_time = utils.DateAndTime().parse_iso_str(entry.get('start')).strftime("%Y-%m-%d")
#             if start_time not in days:
#                 days[start_time] = []
#             days[start_time].append(entry)
#
#         # For each day, print the entries, and sum the times.
#         s = ""
#         for date in sorted(days.keys()):
#             s += date + "\n"
#             duration = 0
#             for entry in days[date]:
#                 s += str(entry) + "\n"
#                 duration += entry.normalized_duration()
#             s += "  ({})\n".format(utils.DateAndTime().elapsed_time(int(duration)))
#         return s.rstrip()  # strip trailing \n
