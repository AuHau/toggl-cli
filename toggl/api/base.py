import json
import logging
import re
from abc import ABCMeta
from builtins import int
from enum import Enum
from inspect import Signature, Parameter

from requests import HTTPError

from .. import utils
from ..exceptions import TogglValidationException, TogglException, TogglMultipleResults

logger = logging.getLogger('toggl.models.base')


def evaluate_conditions(conditions, entity):
    """
    Will compare conditions dict and entity.
    Condition's keys and values must match the entities attributes, but not the other way around.

    :param entity: TogglEntity
    :param conditions: dict
    :return:
    :rtype: bool
    """
    for key in conditions:
        if not getattr(entity, key, False):
            return False

        if str(getattr(entity, key)) != str(conditions[key]):
            return False

    return True


class OldUser(object):
    """
    utils.Singleton toggl user data.
    """

    __metaclass__ = utils.Singleton

    def __init__(self, config=None):
        """
        Fetches user data from toggl.
        """
        result_dict = utils.toggl("/me", 'get', config=config)

        # Results come back in two parts. 'since' is how long the user has
        # had their toggl account. 'data' is a dictionary of all the other
        # user data.
        self.data = result_dict['data']
        self.data['since'] = result_dict['since']

    def get(self, prop):
        """
        Return the given toggl user property. User properties are
        documented at https://github.com/toggl/toggl_api_docs/blob/master/chapters/users.md
        """
        return self.data[prop]


class TogglSet(object):
    def __init__(self, url, entity_cls, can_get_detail=True, can_get_list=True):
        self.url = url
        self.entity_cls = entity_cls
        self.can_get_detail = can_get_detail
        self.can_get_list = can_get_list

    def build_list_url(self, wid):
        return '/workspaces/{}/{}'.format(wid, self.url)

    def build_detail_url(self, id):
        return '/{}/{}'.format(self.url, id)

    def _convert_entity(self, raw_entity):
        entity_id = raw_entity.pop('id')
        raw_entity.pop('at')
        entity_object = self.entity_cls(**raw_entity)
        entity_object.id = entity_id

        return entity_object

    def get(self, id=None, config=None, **conditions):
        if id is not None:
            if self.can_get_detail:
                try:
                    fetched_entity = utils.toggl(self.build_detail_url(id), 'get', config=config)
                    return self._convert_entity(fetched_entity['data'])
                except HTTPError:
                    return None
            else:
                conditions['id'] = id

        entries = self.filter(config=config, **conditions)

        if len(entries) > 1:
            raise TogglMultipleResults()

        if not entries:
            return None

        return entries[0]

    def filter(self, wid=None, config=None, **conditions):
        fetched_entities = self.all(wid, config)

        if fetched_entities is None:
            return []

        return [entity for entity in fetched_entities if evaluate_conditions(conditions, entity)]

    def all(self, wid=None, config=None):
        wid = wid or OldUser(config).get('default_wid')
        fetched_entities = utils.toggl(self.build_list_url(wid), 'get', config=config)

        if fetched_entities is None:
            return []

        return [self._convert_entity(entity) for entity in fetched_entities]


class TogglField:
    field_type = object

    def __init__(self, verbose_name=None, required=False, default=None, is_premium=False):
        self.name = None
        self.verbose_name = verbose_name
        self.required = required
        self.default = default
        self.is_premium = is_premium

    def validate(self, value):
        if self.required and self.default is None and not value:
            raise TogglValidationException('The field \'{}\' is required!'.format(self.name))

    def __get__(self, instance, owner):
        try:
            return instance.__dict__[self.name]
        except KeyError:
            return self.default() if callable(self.default) else self.default

    def __set__(self, instance, value):
        if value is None and not self.required:
            instance.__dict__[self.name] = value
            return

        if not isinstance(value, self.field_type):
            # Before raising TypeError lets try to cast the value into correct type
            try:
                value = self.field_type(value)
            except ValueError:
                raise TypeError('Expected for field \'{}\' type {} got {}'.format(self.name, self.field_type, type(value)))

        instance.__dict__[self.name] = value

    def __str__(self):
        return '{} - {}'.format(self.__class__.__name__, self.name)


class StringField(TogglField):
    field_type = str


class IntegerField(TogglField):
    field_type = int


class FloatField(TogglField):
    field_type = float


class BooleanField(TogglField):
    field_type = bool


class MappingCardinality(Enum):
    ONE = 'one'
    MANY = 'many'


class MappingField(TogglField):

    def __init__(self, mapped_cls, mapped_field, cardinality=MappingCardinality.ONE, read_only=False, *args, **kwargs):
        super(MappingField, self).__init__(*args, **kwargs)

        if not issubclass(mapped_cls, TogglEntity):
            raise TypeError('Mapped class has to be TogglEntity subclass!')

        self.mapped_cls = mapped_cls
        self.mapped_field = mapped_field
        self.cardinality = cardinality
        self.read_only = read_only

    def __get__(self, instance, owner):
        if self.cardinality == MappingCardinality.ONE:
            try:
                id = instance.__dict__[self.mapped_field]

                # Hack to resolve default if the ID is defined but None
                if id is None:
                    raise KeyError
            except KeyError:
                default = self.default

                # No default, no point of continuing
                if default is None:
                    return None

                if callable(default):
                    default = default(instance._config)

                if isinstance(default, TogglEntity):
                    return default

                id = default

            return self.mapped_cls.objects.get(id)

        elif self.cardinality == MappingCardinality.MANY:
            raise NotImplementedError("Not implemented yet")
        else:
            raise TogglException('{}: Unknown cardinality \'{}\''.format(self.name, self.cardinality))

    def __set__(self, instance, value):
        if self.read_only:
            raise AttributeError('Field is read only!')

        if self.cardinality == MappingCardinality.ONE:
            try:
                if not isinstance(value, self.mapped_cls):
                    logger.warning('Assigning class \'{}\' to MappedField with class \'{}\'.'.format(type(value),
                                                                                                     self.mapped_cls))

                instance.__dict__[self.mapped_field] = value.id
            except AttributeError:
                if not isinstance(value, int):
                    logger.warning('Assigning as ID to mapped field value which is not integer!')

                instance.__dict__[self.mapped_field] = value.id
        else:
            raise NotImplementedError('Field with MANY cardinality is not supported for attribute assignment')


def _make_signature(fields):
    non_default_parameters = [Parameter(field.name, Parameter.POSITIONAL_OR_KEYWORD) for field in fields
                              if field.name != 'id' and field.required]
    default_parameters = [Parameter(field.name, Parameter.POSITIONAL_OR_KEYWORD, default=field.default) for field in fields
                          if field.name != 'id' and not field.required]

    return Signature(non_default_parameters + default_parameters)


def _make_fields(attrs, parents):
    fields = []
    for parent in parents:
        fields += parent.__fields__

    for key, field in attrs.items():
        if isinstance(field, TogglField):
            field.name = key
            fields.append(field)

    return fields


class TogglEntityBase(ABCMeta):

    def __new__(mcs, name, bases, attrs, **kwargs):
        new_class = super().__new__(mcs, name, bases, attrs, **kwargs)

        fields = _make_fields(attrs, bases)
        setattr(new_class, '__fields__', fields)
        setattr(new_class, '__signature__', _make_signature(fields))
        setattr(new_class, 'objects', TogglSet(new_class.get_url(), new_class, new_class._can_get_detail))

        return new_class


# TODO: Premium fields and check for current Workspace to be Premium
class TogglEntity(metaclass=TogglEntityBase):
    __signature__ = _make_signature({})
    __fields__ = []

    _validate_workspace = True
    _can_create = True
    _can_update = True
    _can_delete = True
    _can_get_detail = True

    id = IntegerField(required=False)

    def __init__(self, config=None, **kwargs):
        self._config = config

        for field in self.__fields__:
            if field.name in {'id'}:
                continue

            if isinstance(field, MappingField):
                # User supplied most probably the whole mapped object
                if field.name in kwargs:
                    setattr(self, field.name, kwargs.get(field.name))
                    continue

                # Most probably converting API call with direct ID of the object
                if field.mapped_field in kwargs:
                    setattr(self, field.mapped_field, kwargs.get(field.mapped_field))
                    continue

                if field.default is None and field.required:
                    raise TypeError('We need "{}" attribute!'.format(field.mapped_field))
                continue

            if field.name not in kwargs:
                if field.default is None and field.required:
                    raise TypeError('We need "{}" attribute!'.format(field.name))
            else: # Set the attribute only when there is some value to set, so default values could work properly
                setattr(self, field.name, kwargs[field.name])

    def save(self):
        if not self._can_update and self.id is not None:
            raise TogglException("Updating this entity is not allowed!")

        if not self._can_create and self.id is None:
            raise TogglException("Creating this entity is not allowed!")

        self.validate()

        if self.id is not None:  # Update
            utils.toggl("/{}/{}".format(self.get_url(), self.id), "put", self.json(), config=self._config)
        else:  # Create
            data = utils.toggl("/{}".format(self.get_url()), "post", self.json(), config=self._config)
            self.id = data['data']['id']  # Store the returned ID

    def delete(self):
        if not self._can_delete:
            raise TogglException("Deleting this entity is not allowed!")

        utils.toggl("/{}/{}".format(self.get_url(), self.id), "delete")
        self.id = None  # Invalidate the object, so when save() is called after delete a new object is created

    def __cmp__(self, other):
        if not isinstance(other, self.__class__):
            raise TogglException("You are trying to compare instances of different classes!")

        return self.id == other.id

    def json(self):
        return json.dumps({self.get_name(): self.to_dict()})

    @classmethod
    def get_name(cls, verbose=False):
        name = cls.__name__
        name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()

        if verbose:
            return name.replace('_', ' ').capitalize()

        return name

    @classmethod
    def get_url(cls):
        return cls.get_name() + 's'

    def validate(self):
        for field in self.__fields__:
            field.validate(getattr(self, field.name, None))

    def to_dict(self):
        entity_dict = {}
        for field in self.__fields__:
            try:
                entity_dict[field.mapped_field] = getattr(self, field.name).id
            except AttributeError:
                entity_dict[field.name] = getattr(self, field.name, None)

        return entity_dict

    def __str__(self):
        return "{} (#{})".format(getattr(self, 'name'), self.id)
