import json
import logging
import re
from abc import ABCMeta
from builtins import int
from collections import OrderedDict
from datetime import datetime
from enum import Enum
from inspect import Signature, Parameter

import dateutil
import pytz
from validate_email import validate_email

from .. import utils
from .. import exceptions

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


# TODO: Caching
class TogglSet(object):
    def __init__(self, entity_cls=None, url=None, can_get_detail=None, can_get_list=None):
        self.entity_cls = entity_cls
        self._url = url
        self._can_get_detail = can_get_detail
        self._can_get_list = can_get_list

    def bind_to_class(self, cls):
        if self.entity_cls is not None:
            raise exceptions.TogglException('The instance is already binded to a class {}!'.format(self.entity_cls))

        self.entity_cls = cls

    @property
    def url(self):
        return self._url or self.entity_cls.get_url()

    @property
    def can_get_detail(self):
        if self._can_get_detail is not None:
            return self._can_get_detail

        if self.entity_cls._can_get_detail is not None:
            return self._can_get_detail

        return True

    @property
    def can_get_list(self):
        if self._can_get_list is not None:
            return self._can_get_list

        if self.entity_cls._can_get_list is not None:
            return self._can_get_list

        return True

    def build_list_url(self, wid):
        return '/workspaces/{}/{}'.format(wid, self.url)

    def build_detail_url(self, id):
        return '/{}/{}'.format(self.url, id)

    def get(self, id=None, config=None, **conditions):
        if id is not None:
            if self.can_get_detail:
                try:
                    fetched_entity = utils.toggl(self.build_detail_url(id), 'get', config=config)
                    return self.entity_cls.deserialize(config=config, **fetched_entity['data'])
                except exceptions.TogglNotFoundException:
                    return None
            else:
                conditions['id'] = id

        entries = self.filter(config=config, **conditions)

        if len(entries) > 1:
            raise exceptions.TogglMultipleResultsException()

        if not entries:
            return None

        return entries[0]

    def filter(self, wid=None, config=None, **conditions):
        fetched_entities = self.all(wid, config)

        if fetched_entities is None:
            return []

        return [entity for entity in fetched_entities if evaluate_conditions(conditions, entity)]

    def all(self, wid=None, config=None):
        if not self.can_get_list:
            raise exceptions.TogglException('Entity {} is not allowed to fetch list from the API!'
                                            .format(self.entity_cls))

        config = config or utils.Config.factory()
        wid = wid or config.default_workspace.id
        fetched_entities = utils.toggl(self.build_list_url(wid), 'get', config=config)

        if fetched_entities is None:
            return []

        return [self.entity_cls.deserialize(config=config, **entity) for entity in fetched_entities]


class TogglField:
    _field_type = None

    def __init__(self, verbose_name=None, required=False, default=None, admin_only=False, is_read_only=False):
        self.name = None
        self.verbose_name = verbose_name
        self.required = required
        self.default = default
        self.admin_only = admin_only
        self.is_read_only = is_read_only

    def validate(self, value):
        if self.required and self.default is None and not value:
            raise exceptions.TogglValidationException('The field \'{}\' is required!'.format(self.name))

    def serialize(self, value):
        return value

    def parse(self, value, config=None):
        if self._field_type is not None:
            return self._field_type(value)

        return value

    def init(self, instance, value):
        if self.name in instance.__dict__:
            raise exceptions.TogglException('Field \'{}.{}\' is already initiated!'
                                            .format(instance.__class__.__name__, self.name))

        try:
            value = self.parse(value, instance._config)
        except ValueError:
            raise TypeError(
                'Expected for field \'{}\' type {} got {}'.format(self.name, self._field_type, type(value)))

        instance.__dict__[self.name] = value

    def _set_value(self, instance, value):
        try:
            if instance.__dict__[self.name] == value:
                return
        except KeyError:
            pass

        instance.__change_dict__[self.name] = value
        instance.__dict__[self.name] = value

    def __get__(self, instance, owner):
        try:
            return instance.__dict__[self.name]
        except KeyError:
            return self.default() if callable(self.default) else self.default

    def __set__(self, instance, value):
        if self.is_read_only:
            raise exceptions.TogglException('Attribute \'{}\' is read only!'.format(self.name))

        if self.admin_only:
            from .models import Workspace, WorkspaceEntity

            if (isinstance(instance, WorkspaceEntity) and not instance.workspace.admin) \
                    or (isinstance(instance, Workspace) and not instance.admin):
                raise exceptions.TogglAuthorizationException(
                    None, None,
                    'You are trying edit field \'{}.{}\' which is admin only field, but you are not an admin!'
                        .format(instance.__class__.__name__, self.name)
                )

        if value is None and not self.required:
            self._set_value(instance, value)
            return

        try:
            value = self.parse(value, instance._config)
        except ValueError:
            raise TypeError(
                'Expected for field \'{}\' type {} got {}'.format(self.name, self._field_type, type(value)))

        self._set_value(instance, value)

    def __str__(self):
        return '{} - {}'.format(self.__class__.__name__, self.name)


class StringField(TogglField):
    _field_type = str


class IntegerField(TogglField):
    _field_type = int


class FloatField(TogglField):
    _field_type = float


class BooleanField(TogglField):
    _field_type = bool


class DateTimeField(StringField):

    @staticmethod
    def _is_naive(value):
        return value.utcoffset() is None

    def parse(self, value, config=None):
        config = config or utils.Config.factory()

        if isinstance(value, datetime):
            if self._is_naive(value):
                return value.astimezone(config.timezone)

            return value

        try:
            date = dateutil.parser.parse(value, dayfirst=config.day_first, yearfirst=config.year_first)
            return config.timezone.localize(date)
        except AttributeError:
            date = dateutil.parser.parse(value)
            return config.timezone.localize(date)

    def serialize(self, value):
        if not isinstance(value, datetime):
            raise ValueError('DateTimeField needs for serialization datetime object!')

        if self._is_naive(value):
            return value.isoformat()

        return value.astimezone(pytz.utc).replace(tzinfo=None).isoformat()


class EmailField(StringField):

    def validate(self, value):
        super(EmailField, self).validate(value)

        if not validate_email(value):
            raise exceptions.TogglValidationException('Email \'{}\' is not valid email address!'.format(value))


class PropertyField(TogglField):

    def __init__(self, getter, setter=None, verbose_name=None, admin_only=False):
        self.getter = getter
        self.setter = setter or self.default_setter

        super().__init__(verbose_name=verbose_name, admin_only=admin_only, is_read_only=setter is None)

    @staticmethod
    def default_setter(name, instance, value, init=False):
        """
        Default setter which behaves like normal ToggleField, that stores the value inside of the instance's dict under
        the field's name.

        :param name: Field's name
        :param instance: Instance of the entity
        :param value: Value to be set
        :param init: Boolean that describe if the value is being set during creation of the entity's instance
        :return: None
        """
        instance.__dict__[name] = value

    @staticmethod
    def default_getter(name, instance, serializing=False):
        """
        Default getter which retrieves the value from instance's dict.

        :param name: Field's name
        :param instance: Instance of the entity
        :param serializing: Whether the function is called during serialization of the instance into JSON
        :return: Value of the field
        """
        return instance.__dict__[name]

    def init(self, instance, value):
        self.setter(self.name, instance, value, init=True)

    def __get__(self, instance, owner):
        return self.getter(self.name, instance, serializing=False)

    def __set__(self, instance, value):
        if self.is_read_only:
            raise exceptions.TogglException('Attribute \'{}\' is read only!'.format(self.name))

        if self.admin_only:
            from .models import Workspace, WorkspaceEntity

            if (isinstance(instance, WorkspaceEntity) and not instance.workspace.admin) \
                    or (isinstance(instance, Workspace) and not instance.admin):
                raise exceptions.TogglAuthorizationException(
                    None, None,
                    'You are trying edit field \'{}.{}\' which is admin only field, but you are not an admin!'
                        .format(instance.__class__.__name__, self.name)
                )

        return self.setter(self.name, instance, value, init=False)


class ChoiceField(TogglField):
    choices = {}

    def __init__(self, choices, *args, **kwargs):
        super(ChoiceField, self).__init__(*args, **kwargs)

        self.choices = choices

    def __set__(self, instance, value):
        # User entered the choice's label and not the key, let's remap it
        if value not in self.choices:
            for key, choice_value in self.choices.items():
                if value == choice_value:
                    value = key
                    break

        super(ChoiceField, self).__set__(instance, value)

    def validate(self, value):
        super(ChoiceField, self).validate(value)

        if value not in self.choices and value not in self.choices.values():
            raise exceptions.TogglValidationException('Value \'{}\' is not valid choice!'.format(value))

    def get_label(self, value):
        return self.choices[value]


class MappingCardinality(Enum):
    ONE = 'one'
    MANY = 'many'


class MappingField(TogglField):

    def __init__(self, mapped_cls, mapped_field, cardinality=MappingCardinality.ONE, *args, **kwargs):
        super(MappingField, self).__init__(*args, **kwargs)

        if not issubclass(mapped_cls, TogglEntity):
            raise TypeError('Mapped class has to be TogglEntity subclass!')

        self.mapped_cls = mapped_cls
        self.mapped_field = mapped_field
        self.cardinality = cardinality

    def init(self, instance, value):
        if self.cardinality == MappingCardinality.ONE:
            try:
                if not isinstance(value, self.mapped_cls):
                    logger.warning('Assigning class {} to MappedField with class {}.'.format(type(value),
                                                                                             self.mapped_cls))

                instance.__dict__[self.mapped_field] = value.id
            except AttributeError:
                if not isinstance(value, int):
                    logger.warning('Assigning as ID to mapped field value which is not integer!')

                instance.__dict__[self.mapped_field] = value
        else:
            raise NotImplementedError('Field with MANY cardinality is not supported for attribute assignment')

    def _set_value(self, instance, value):
        try:
            if instance.__dict__[self.mapped_field] == value:
                return
        except KeyError:
            pass

        instance.__change_dict__[self.mapped_field] = value
        instance.__dict__[self.mapped_field] = value

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
            raise exceptions.TogglException('{}: Unknown cardinality \'{}\''.format(self.name, self.cardinality))

    def __set__(self, instance, value):
        if self.cardinality == MappingCardinality.ONE:
            try:
                if not isinstance(value, self.mapped_cls):
                    logger.warning('Assigning class {} to MappedField with class {}.'.format(type(value),
                                                                                             self.mapped_cls))

                self._set_value(instance, value.id)
            except AttributeError:
                if not isinstance(value, int):
                    logger.warning('Assigning as ID to mapped field value which is not integer!')

                self._set_value(instance, value)
        else:
            raise NotImplementedError('Field with MANY cardinality is not supported for attribute assignment')


class TogglEntityMeta(ABCMeta):

    def _make_signature(fields):
        non_default_parameters = [Parameter(field.name, Parameter.POSITIONAL_OR_KEYWORD) for field in fields.values()
                                  if field.name != 'id' and field.required]
        default_parameters = [Parameter(field.name, Parameter.POSITIONAL_OR_KEYWORD, default=field.default) for field in
                              fields.values()
                              if field.name != 'id' and not field.required]

        return Signature(non_default_parameters + default_parameters)

    def _make_fields(attrs, parents):
        fields = OrderedDict()
        for parent in parents:
            fields.update(parent.__fields__)

        for key, field in attrs.items():
            if isinstance(field, TogglField):
                field.name = key
                fields[key] = field

        return fields

    def _make_mapped_fields(fields):
        return {field.mapped_field: field for field in fields.values() if isinstance(field, MappingField)}

    def __new__(mcs, name, bases, attrs, **kwargs):
        new_class = super().__new__(mcs, name, bases, attrs, **kwargs)

        fields = mcs._make_fields(attrs, bases)
        setattr(new_class, '__fields__', fields)
        setattr(new_class, '__mapped_fields__', mcs._make_mapped_fields(fields))
        setattr(new_class, '__signature__', mcs._make_signature(fields))

        # Add objects only if they are not defined to allow custom ToggleSet implementations
        if not hasattr(new_class, 'objects'):
            setattr(new_class, 'objects', TogglSet(new_class))
        else:
            try:
                new_class.objects.bind_to_class(new_class)
            except (exceptions.TogglException, AttributeError):
                pass

        return new_class


# TODO: Premium fields and check for current Workspace to be Premium
class TogglEntity(metaclass=TogglEntityMeta):
    __signature__ = Signature()
    __fields__ = OrderedDict()
    __change_dict__ = {}

    _validate_workspace = True
    _can_create = True
    _can_update = True
    _can_delete = True
    _can_get_detail = True
    _can_get_list = True

    id = IntegerField(required=False)

    def __init__(self, config=None, **kwargs):
        self._config = config

        for field in self.__fields__.values():
            if field.name in {'id'}:
                continue

            if isinstance(field, MappingField):
                # User supplied most probably the whole mapped object
                if field.name in kwargs:
                    field.init(self, kwargs.get(field.name))
                    continue

                # Most probably converting API call with direct ID of the object
                if field.mapped_field in kwargs:
                    field.init(self, kwargs.get(field.mapped_field))
                    continue

                if field.default is None and field.required:
                    raise TypeError('We need "{}" attribute!'.format(field.mapped_field))
                continue

            if field.name not in kwargs:
                if field.default is None and field.required:
                    raise TypeError('We need "{}" attribute!'.format(field.name))
            else:  # Set the attribute only when there is some value to set, so default values could work properly
                field.init(self, kwargs[field.name])

    def save(self, config=None):
        if not self._can_update and self.id is not None:
            raise exceptions.TogglException("Updating this entity is not allowed!")

        if not self._can_create and self.id is None:
            raise exceptions.TogglException("Creating this entity is not allowed!")

        config = config or self._config

        self.validate()

        if self.id is not None:  # Update
            utils.toggl("/{}/{}".format(self.get_url(), self.id), "put", self.json(update=True), config=config)
            self.__change_dict__ = {}  # Reset tracking changes
        else:  # Create
            data = utils.toggl("/{}".format(self.get_url()), "post", self.json(), config=config)
            self.id = data['data']['id']  # Store the returned ID

    def delete(self, config=None):
        if not self._can_delete:
            raise exceptions.TogglException("Deleting this entity is not allowed!")

        utils.toggl("/{}/{}".format(self.get_url(), self.id), "delete", config=config or self._config)
        self.id = None  # Invalidate the object, so when save() is called after delete a new object is created

    def __cmp__(self, other):
        if not isinstance(other, self.__class__):
            raise exceptions.TogglException("You are trying to compare instances of different classes!")

        return self.id == other.id

    def json(self, update=False):
        if update:
            change_dict = self.__change_dict__
            del change_dict['id']

            return json.dumps({self.get_name(): change_dict})

        return json.dumps({self.get_name(): self.to_dict()})

    def validate(self):
        for field in self.__fields__.values():
            field.validate(getattr(self, field.name, None))

    def to_dict(self, serialized=False):
        entity_dict = {}
        for field in self.__fields__.values():
            try:
                entity_dict[field.mapped_field] = getattr(self, field.name).id
            except AttributeError:
                value = getattr(self, field.name, None)
                entity_dict[field.name] = field.serialize(value) if serialized else value

        return entity_dict

    def __str__(self):
        return "{} (#{})".format(getattr(self, 'name'), self.id)

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

    @classmethod
    def deserialize(cls, config=None, **kwargs):
        try:
            kwargs.pop('at')
        except KeyError:
            pass

        instance = cls.__new__(cls)
        instance._config = config

        for key, value in kwargs.items():
            try:
                field = instance.__fields__[key]
            except KeyError:
                try:
                    field = instance.__mapped_fields__[key]
                except KeyError:
                    continue

            value = field.parse(value, config=config)
            field.init(instance, value)

        return instance
