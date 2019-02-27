import datetime
import logging
from builtins import int
from copy import copy
from enum import Enum
from collections.abc import MutableSequence, MutableSet
import typing

import pendulum
from validate_email import validate_email

from toggl import exceptions, utils
from toggl.api import base

logger = logging.getLogger('toggl.api.fields')

NOTSET = object()

T = typing.TypeVar('T')
Serializable = typing.TypeVar('Serializable', str, int, float, list, dict)


class TogglField(typing.Generic[T]):
    """
    Base descriptor for all Toggl's Fields implementation.

    Its main function is to set/get values from the Entity's instance, but it also perform's serialization, validation,
    parsing and many other features related to the Field and data it represents.

    Attributes common to all fields: name, verbose_name, required, default, admin_only, write.
    """

    # Represents Python's primitive type for easy implementation of basic Fields like String, Integer etc. using
    # Python builtins (eq. bool, str, etc.).
    _field_type = str

    name = None  # type: str
    """
    Attribute 'name' is a special attribute which is set by TogglEntityMeta and equals to the name of attribute under
    which is the field assigned to the Entity.
    """

    verbose_name = None  # type: str
    """
    Attribute 'verbose_name' is used for CLI interfaces for human-readable format, if omitted 'name' is used.
    """

    required = False  # type: str
    """
    Attribute 'required' defines if the field can be empty or not during creation of new instance.
    """

    default = None  # type: T
    """
    Attribute 'default' defines a default value to be used if no value is provided (None is valid default value).
    It can also be callable, which is evaluated everytime.
    """

    admin_only = False  # type: bool
    """
    Attribute 'admin_only' specifies that the field can be set only when the user has admin role in the related
    Workspace (meaningful for WorkspaceEntity and its subclasses).
    """

    write = True  # type: bool
    """
    Attribute 'write' specifies if user can set value to the field.
    """

    read = True  # type: bool
    """
    Attribute 'read' specifies if user can get value from the field.
    
    It represents fields that are not returned from server, but you can only pass value to them.
    It is allowed to read from the field once you set some value to it, but not before
    """

    premium = False  # type: bool
    """
    Attribute 'premium' specifies if the field can be used only for premium workspaces.
    """

    def __init__(self, verbose_name=None, required=False, default=NOTSET, admin_only=False,
                 write=True, read=True, premium=False):  # type: (str, bool, T, bool, bool, bool, bool) -> None
        self.name = None
        self.verbose_name = verbose_name
        self.required = required
        self.default = default
        self.admin_only = admin_only
        self.write = write
        self.read = read
        self.premium = premium

        if not write and not read:
            logger.warning('The field \'{}\' does not support write nor read mode, it is maybe useless?'.format(self))

    def validate(self, value, instance):  # type: (T, base.Entity) -> None
        """
        Validates if the passed value is valid from the perspective of the data type that the field represents.

        Basic implementation validate only 'required' and 'premium' attributes.

        :param instance: Instance of the TogglEntity which we are validating the value against
        :param value: Any value
        :raises exceptions.TogglValidationException: When the passed value is not valid.
        :raises exceptions.TogglPremiumException: If the associated Workspace is not premium workspace.
        """
        if self.required and self.default is NOTSET and not value:
            raise exceptions.TogglValidationException('The field \'{}\' is required!'.format(self.name))

        if self.premium:
            from .models import WorkspacedEntity, Workspace
            workspace = instance.workspace if isinstance(instance, WorkspacedEntity) else instance  # type: Workspace

            if getattr(instance, self.name, False) and not workspace.premium:
                raise exceptions.TogglPremiumException('You are trying to save object with premium field \'{}.{}\' in non-premium Workspace: {}'
                    .format(
                    instance.__class__.__name__,
                    self.name,
                    workspace
                ))

    def serialize(self, value):  # type: (T) -> typing.Optional[Serializable]
        """
        Returns value serialized into Python's primitives.
        """
        return value

    def parse(self, value, instance):  # type: (str, base.Entity) -> typing.Optional[T]
        """
        Parses value from string into value type of the field.

        Basic implementation uses Python's primitives for conversation specified in '_field_type' attribute.
        """
        if value is None:
            return None

        if self._field_type is not None:
            return self._field_type(value)

        return value

    def format(self, value, config=None):  # type: (typing.Optional[T], utils.Config) -> str
        """
        Formats the value into human-readable string, for CLI purpose.
        """
        if value is None:
            return ''

        return value

    def init(self, instance, value):  # type: (base.Entity, T) -> None
        """
        Method used to initialize the value in the instance.

        Used mainly for TogglEntity's __init__() and deserialize().
        """
        if self.name in instance.__dict__:
            raise exceptions.TogglException('Field \'{}.{}\' is already initiated!'
                                            .format(instance.__class__.__name__, self.name))

        try:
            value = self.parse(value, instance)
        except ValueError:
            raise TypeError(
                'Expected for field \'{}\' type {} got {}'.format(self.name, self._field_type, type(value)))

        instance.__dict__[self.name] = value

    def _set_value(self, instance, value):  # type: (base.Entity, T) -> None
        """
        Helper method for setting value into instance to correctly track changes.
        :raises RuntimeError: If the field does not have 'name' attribute set.
        """
        if not self.name:
            raise RuntimeError('Name of the field is not defined!')

        try:
            if instance.__dict__[self.name] == value:
                return
        except KeyError:
            pass

        instance.__change_dict__[self.name] = value
        instance.__dict__[self.name] = value

    def _get_value(self, instance):  # type: (base.Entity) -> T
        try:
            return instance.__dict__[self.name]
        except KeyError:
            if self.default is not NOTSET:
                # TODO: [Q/Design] Should be callable evaluated every time or only during the initialization?
                return self.default(getattr(instance, '_config', None)) if callable(self.default) else self.default

            raise AttributeError('Instance of {} has not set \'{}\''.format(instance.__class__.__name__, self.name))

    def _has_value(self, instance):
        return self.name in instance.__dict__

    def __get__(self, instance, owner):  # type: (typing.Optional['base.Entity'], typing.Any) -> T
        """
        Main TogglField's method that defines how the value of the field is retrieved from TogglEntity's instance.

        :raises RuntimeError: If the field does not have 'name' attribute set.
        :raises AttributeError: If the instance does not have set the corresponding attribute.
        :raises exceptions.TogglNotAllowedException: If read is not supported by the field
        """
        if not self.name:
            raise RuntimeError('Name of the field is not defined!')

        if not self.read and not self._has_value(instance):
            raise exceptions.TogglNotAllowedException('You are not allowed to read from \'{}\' attribute!'
                                                      .format(self.name))

        # When instance is None, then the descriptor as accessed directly from class and not its instance 
        # ==> return the descriptors instance.
        if instance is None:
            return self

        return self._get_value(instance)

    def __set__(self, instance, value):  # type: (base.Entity, T) -> None
        """
        Main TogglField's method that defines how the value of the field is stored in the TogglEntity's instance.

        :raises RuntimeError: If the field does not have 'name' attribute set.
        :raises exceptions.TogglNotAllowedException: If the field does not support write operation or is only available
                only for admin's and the user does not have admin role in the assigned Workspace.
        :raises TypeError: If the value to be set is of wrong type.
        """
        if not self.name:
            raise RuntimeError('Name of the field is not defined!')

        if not self.write:
            raise exceptions.TogglNotAllowedException('You are not allowed to write into \'{}\' attribute!'
                                                      .format(self.name))

        if self.admin_only or self.premium:
            from .models import WorkspacedEntity, Workspace
            workspace = instance.workspace if isinstance(instance, WorkspacedEntity) else instance

            if self.admin_only and not workspace.admin:
                raise exceptions.TogglNotAllowedException(
                    'You are trying edit field \'{}.{}\' which is admin only field, '
                    'but you are not an admin in workspace \'{}\'!'
                        .format(instance.__class__.__name__, self.name, workspace.name)
                )

            if self.premium and not workspace.premium:
                raise exceptions.TogglPremiumException(
                    'You are trying to edit field \'{}.{}\' which is premium only field, '
                    'but the associated workspace \'{}\' is not premium!'
                        .format(instance.__class__.__name__, self.name, workspace.name)
                )

        if value is None:
            if not self.required:
                self._set_value(instance, value)
                return
            else:
                raise TypeError('Field \'{}\' is required! None value is not allowed!'.format(self.name))

        try:
            value = self.parse(value, instance)
        except ValueError:
            raise TypeError(
                'Expected for field \'{}\' type {} got {}'.format(self.name, self._field_type, type(value)))

        self._set_value(instance, value)

    def __str__(self):
        return '{} - {}'.format(self.__class__.__name__, self.name)


Field = typing.TypeVar('Field', bound=TogglField)


#########################################################################
# Primitive fields implementation using _field_type


class StringField(TogglField[str]):
    _field_type = str


class IntegerField(TogglField[int]):
    _field_type = int


class FloatField(TogglField[float]):
    _field_type = float


class BooleanField(TogglField[bool]):
    _field_type = bool


#########################################################################
# Advanced fields


class DateTimeField(TogglField[typing.Union[datetime.datetime, pendulum.DateTime]]):
    """
    Field that represents DateTime.

    It mainly utilizes the pendulum.DateTime object.
    For serialization the ISO 8601 format is used.
    For parsing it uses best-guess method which tries to guess the format using dateutil.parse().
    """

    @staticmethod
    def _is_naive(value: datetime.datetime) -> bool:
        return value.utcoffset() is None

    def __set__(self, instance, value):  # type: (typing.Optional['base.Entity'], typing.Union[datetime.datetime, pendulum.DateTime]) -> None
        if value is None:
            return super().__set__(instance, value)

        config = instance._config or utils.Config.factory()

        if isinstance(value, datetime.datetime):
            if self._is_naive(value):
                value = pendulum.instance(value, config.timezone)
            else:
                value = pendulum.instance(value)
        elif isinstance(value, pendulum.DateTime):
            pass
        else:
            raise TypeError('Value which is being set to DateTimeField have to be either '
                            'datetime.datetime or pendulum.DateTime object!')

        super().__set__(instance, value)

    def parse(self, value, instance):  # type: (str, base.Entity) -> pendulum.DateTime
        config = getattr(instance, '_config', None) or utils.Config.factory()

        if isinstance(value, datetime.datetime):
            if self._is_naive(value):
                return pendulum.instance(value, config.timezone)

            return pendulum.instance(value)
        elif isinstance(value, pendulum.DateTime):
            return value

        try:
            return pendulum.parse(value, strict=False, dayfirst=config.day_first,
                                  yearfirst=config.year_first)
        except AttributeError:
            return pendulum.parse(value, strict=False)

    def format(self, value, config=None):  # type: (pendulum.DateTime, utils.Config) -> str
        if value is None:
            return ''

        if not isinstance(value, pendulum.DateTime):
            raise TypeError('DateTimeField needs for formatting pendulum.DateTime object')

        config = config or utils.Config.factory()

        return value.in_timezone(config.timezone).format(config.datetime_format)

    def serialize(self, value):  # type: (pendulum.DateTime) -> typing.Optional[Serializable]
        if value is None:
            return None

        if not isinstance(value, pendulum.DateTime):
            raise TypeError('DateTimeField needs for serialization pendulum.DateTime object!')

        return value.in_timezone('UTC').to_iso8601_string()


class EmailField(StringField):
    """
    Field that performs validation for valid email address.
    """

    def validate(self, value, instance):
        super().validate(value, instance)

        if not validate_email(value):
            raise exceptions.TogglValidationException('Email \'{}\' is not valid email address!'.format(value))


class PropertyField(TogglField):
    """
    Advanced field that is inspired by @property decorator.

    It allows you to write easily custom fields by defining getter, setter, serializer and formatter.

    For more info about getter and setter see default_getter() and default_setter() methods which shows the signature
    and default behaviour.

    Serializer is a function that has to serialize given value into Python primitive, so it can be converted into JSON.

    Formatter is a function that has to return string in human-readable format.
    """

    def __init__(self, getter=None, setter=None, serializer=None, formatter=None, verbose_name=None, admin_only=False):
        self.getter = getter or self.default_getter
        self.serializer = serializer
        self.formatter = formatter
        self.setter = setter or self.default_setter

        super().__init__(verbose_name=verbose_name, admin_only=admin_only,
                         write=setter is not None, read=getter is not None)

    @staticmethod
    def default_setter(name, instance, value, init=False):
        """
        Default setter which behaves like normal TogglField, that stores the value inside of the instance's dict under
        the field's name.

        :param name: Field's name
        :param instance: Instance of the entity
        :param value: Value to be set
        :param init: Boolean that describe if the value is being set during creation of the entity's instance
        :return: Boolean which indicates whether the value resulted in updated state of the instance
                (for tracking changes for correct PUT behavior). True if state was changed.
        """
        org_value = instance.__dict__.get(name)
        instance.__dict__[name] = value

        return org_value != value

    @staticmethod
    def default_getter(name, instance):
        """
        Default getter which retrieves the value from instance's dict.

        :param name: Field's name
        :param instance: Instance of the entity
        :return: Value of the field
        """
        return instance.__dict__.get(name)

    def init(self, instance, value):
        if not self.name:
            raise RuntimeError('Name of the field is not defined!')

        self.setter(self.name, instance, value, init=True)

    def format(self, value, config=None):
        return self.formatter(value, config) if self.formatter else super().format(value, config)

    def serialize(self, value):
        return self.serializer(value) if self.serializer else super().serialize(value)

    def _get_value(self, instance):
        return self.getter(self.name, instance)

    def __set__(self, instance, value):
        if not self.name:
            raise RuntimeError('Name of the field is not defined!')

        if not self.write:
            raise exceptions.TogglException('You are not allowed to write into \'{}\' attribute!'.format(self.name))

        if self.admin_only:
            from .models import WorkspacedEntity, Workspace
            workspace = instance.workspace if isinstance(instance, WorkspacedEntity) else instance  # type: Workspace
            if not workspace.admin:
                raise exceptions.TogglNotAllowedException(
                    'You are trying edit field \'{}.{}\' which is admin only field, '
                    'but you are not an admin in workspace \'{}\'!'
                        .format(instance.__class__.__name__, self.name, workspace.name)
                )

        has_updated_state = self.setter(self.name, instance, value, init=False)

        if not isinstance(has_updated_state, bool):
            raise TypeError('Setter must return bool!')

        if has_updated_state is True:
            instance.__change_dict__[self.name] = value


class ChoiceField(StringField):
    """
    Field that limits the range of possible values.

    The choices can defined either as dict where keys are values of the field and the dict's values are
    labels for these values, or as list which contains the set of possible values.
    """

    choices = {}

    def __init__(self, choices, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.choices = choices

    def __set__(self, instance, value):  # type: (typing.Optional['base.Entity'], str) -> ChoiceField
        # User entered the choice's label and not the key, let's remap it
        if value not in self.choices and isinstance(self.choices, dict):
            for key, choice_value in self.choices.items():
                if value == choice_value:
                    value = key
                    break

        super().__set__(instance, value)

    def validate(self, value, instance):  # type: (str, typing.Optional['base.Entity']) -> None
        super().validate(value, instance)

        if value not in self.choices:
            raise exceptions.TogglValidationException('Value \'{}\' is not valid choice!'.format(value))

    def format(self, value, config=None):  # type: (str, utils.Config) -> str
        return self.get_label(value)

    def get_label(self, value):  # type: (str) -> str
        if not isinstance(self.choices, dict):
            return value

        return self.choices[value]


class ListContainer(MutableSequence):
    def __init__(self, entity_instance, field_name, existing_list=None):
        if existing_list is not None:
            self._inner_list = copy(existing_list)
        else:
            self._inner_list = list()

        self._instance = entity_instance
        self._field_name = field_name

    def __len__(self):
        return len(self._inner_list)

    def __delitem__(self, index):
        self._instance.__change_dict__[self._field_name] = self
        self._inner_list.__delitem__(index)

    def insert(self, index, value):
        self._instance.__change_dict__[self._field_name] = self
        self._inner_list.insert(index, value)

    def __setitem__(self, index, value):
        self._instance.__change_dict__[self._field_name] = self
        self._inner_list.__setitem__(index, value)

    def __getitem__(self, index):
        return self._inner_list.__getitem__(index)

    def append(self, value):
        self._instance.__change_dict__[self._field_name] = self
        self._inner_list.append(value)


ListType = typing.Union[ListContainer, typing.List, None]


class ListField(TogglField[ListType]):
    """
    Field that represents list of values.

    It only accept list value's. As list is mutable object the in-place operators can be used to modify the object.
    """

    def format(self, value, config=None):  # type: (ListType, utils.Config) -> str
        if value is None:
            return ''

        return ', '.join(value)

    def parse(self, value, instance):  # type: (typing.List, typing.Optional['base.Entity']) -> ListContainer
        return ListContainer(instance, self.name, value)

    def serialize(self, value):  # type: (ListContainer) -> typing.Optional[typing.List]
        if value is None:
            return None

        if not isinstance(value, ListContainer):
            raise TypeError('Serialized value is not ListContainer!')

        return value._inner_list

    def __set__(self, instance, value):  # type: (typing.Optional['base.Entity'], ListType) -> None
        if value is None:
            super().__set__(instance, None)
            return

        if not isinstance(value, list) and not isinstance(value, ListContainer):
            raise TypeError('ListField expects list instance when setting a value to the field.')

        if isinstance(value, list):
            value = ListContainer(instance, self.name, value)

        super().__set__(instance, value)


class SetContainer(MutableSet):
    def __init__(self, entity_instance, field_name, existing_set=None):
        if existing_set is not None:
            if isinstance(existing_set, list):
                self._inner_set = set(existing_set)
            else:
                self._inner_set = copy(existing_set)
        else:
            self._inner_set = set()

        self._instance = entity_instance
        self._field_name = field_name

    def add(self, value):
        self._instance.__change_dict__[self._field_name] = self
        self._inner_set.add(value)

    def discard(self, value):
        self._instance.__change_dict__[self._field_name] = self
        self._inner_set.discard(value)

    def __contains__(self, x):
        return x in self._inner_set

    def __iter__(self):
        return self._inner_set.__iter__()

    def __len__(self):
        return len(self._inner_set)

    def __or__(self, other):
        return self._inner_set | other

    def __sub__(self, other):
        return self._inner_set - other


SetType = typing.Union[SetContainer, set, None]


class SetField(TogglField[SetType]):
    """
    Field that represents set of values.

    It only accept list (list is converted to set)/set value's. As set is mutable object the in-place operators can be
    used to modify the object.
    """

    def format(self, value, config=None):  # type: (typing.Optional['base.Entity'], utils.Config) -> str
        if value is None:
            return ''

        return ', '.join(value)

    def parse(self, value, instance):
        if value is None:
            return SetContainer(instance, self.name)

        if not isinstance(value, list) and not isinstance(value, SetContainer) and not isinstance(value, set):
            raise TypeError('ListField expects list/set/SetContainer instance when setting a value to the field.')

        return SetContainer(instance, self.name, value)

    def serialize(self, value):
        if value is None:
            return None

        if not isinstance(value, SetContainer):
            raise TypeError('Serialized value is not SetContainer!')

        return list(value._inner_set)

    def __set__(self, instance, value):
        if value is None:
            super().__set__(instance, None)
            return

        if not isinstance(value, list) and not isinstance(value, SetContainer) and not isinstance(value, set):
            raise TypeError('ListField expects list/set/SetContainer instance when setting a value to the field.')

        if not isinstance(value, SetContainer):
            value = SetContainer(instance, self.name, value)

        super().__set__(instance, value)


class MappingCardinality(Enum):
    ONE = 'one'
    MANY = 'many'


M = typing.TypeVar('M')
MappedM = typing.Union[M, int, None]


# TODO: [Feature/Low] Finish MappingCardinality.MANY implementation
class MappingField(TogglField[M]):
    """
    Special Field which behaves similarly to ForeignKey in Django ORM. It lets user to map attribute to different
    TogglEntity.

    It needs 'mapped_cls' which represents another TogglEntity that this field is mapped to. Also it needs information
    about 'mapped_field' where it stores the actual ID of the mapped entity.
    To better explain the mapping let us assume code:

    >>> class A(base.TogglEntity):
    >>>     pass
    >>>
    >>> class B(base.TogglEntity):
    >>>     field = MappingField(mapped_cls=A, mapped_field='field_id')
    >>>
    >>> object_a = A()
    >>> object_a.id = 123
    >>> b = B(field=object_a)

    Then b.field will return object_a while b.field_id (eq. the mapped field) will return the object_a's ID: 123.

    The objects are retrieved using the mapped_cls's TogglSet.

    The 'default' attribute has bit different behaviour then with other fields. If it is callable then it is called
    as expected, but then the returned value is submitted to following checks as it would be if the value would not be
    callable.
    If it is TogglEntity than it is returned as expected.
    But if it anything else then the value is used as ID of the Mapped entity and fetched.
    """

    def __init__(self, mapped_cls, mapped_field, cardinality=MappingCardinality.ONE,
                 *args, **kwargs):  # type: (typing.Type[M], str, str, *typing.Any, **typing.Any) -> None
        super().__init__(*args, **kwargs)

        if not issubclass(mapped_cls, base.TogglEntity):
            raise TypeError('Mapped class has to be TogglEntity\'s subclass!')

        self.mapped_cls = mapped_cls
        self.mapped_field = mapped_field
        self.cardinality = cardinality

    def init(self, instance, value):  # type: (base.Entity, MappedM) -> None
        if self.cardinality == MappingCardinality.ONE:
            if value is None:
                instance.__dict__[self.mapped_field] = None
                return

            try:
                if value.id is None:
                    raise RuntimeError(
                        'You are trying to assign mapped entity which was yet not saved! (Does not have ID)')

                instance.__dict__[self.mapped_field] = value.id

                if not isinstance(value, self.mapped_cls):
                    logger.warning('Assigning instance of class {} to MappedField with class {}.'
                        .format(
                            type(value),
                            self.mapped_cls
                        ))
            except AttributeError:  # It is probably not TogglEntity ==> lets try if it is ID/integer
                try:
                    instance.__dict__[self.mapped_field] = int(value)
                except ValueError:  # Don't have any clue what it is, let just save the value and log warning
                    logger.warning('Assigning as ID to mapped field value which is not integer!')
                    instance.__dict__[self.mapped_field] = value

        else:
            raise NotImplementedError('Field with MANY cardinality is not supported for attribute assignment')

    def validate(self, value, instance):  # type: (M, base.Entity) -> None
        try:
            super().validate(value, instance)
        except AttributeError:
            pass  # Ignoring because of caused by the getattr(self.name) in TogglField.validate()

        if self.premium:
            from .models import WorkspacedEntity, Workspace
            workspace = instance.workspace if isinstance(instance, WorkspacedEntity) else instance

            if getattr(instance, self.mapped_field, False) and not workspace.premium:
                raise exceptions.TogglPremiumException(
                    'You are trying to save object with premium field \'{}.{}\''.format(
                        instance.__class__.__name__,
                        self.name
                    ))

        ## Commented out because of it is expensive validation, which should be ignored until introducing caching.
        # if value is not None:
        #     obj = self.mapped_cls.objects.get(value)
        #
        #     if obj is None:
        #         raise exceptions.TogglValidationException('Mapped object does not exist!')

    def serialize(self, value):  # type: (typing.Optional[M]) -> typing.Optional[Serializable]
        if value is None:
            return None

        return value.id

    def _set_value(self, instance, value):
        try:
            if instance.__dict__[self.mapped_field] == value:
                return
        except KeyError:
            pass

        instance.__change_dict__[self.mapped_field] = value
        instance.__dict__[self.mapped_field] = value

    def _get_value(self, instance):  # type: (base.Entity) -> M
        if self.cardinality == MappingCardinality.ONE:
            try:
                id = instance.__dict__[self.mapped_field]

                # Hack to resolve default if the ID is defined but None
                if id is None:
                    raise KeyError
            except KeyError:
                default = self.default

                # No default, no point of continuing
                if default is NOTSET:
                    raise AttributeError(
                        'Instance {} has not set mapping field \'{}\'/\'{}\''.format(instance, self.name,
                                                                                     self.mapped_field))

                if callable(default):
                    default = default(getattr(instance, '_config', None))

                if isinstance(default, base.TogglEntity):
                    return default

                id = default

            return self.mapped_cls.objects.get(id, config=getattr(instance, '_config', None))

        elif self.cardinality == MappingCardinality.MANY:
            raise NotImplementedError("Not implemented yet")
        else:
            raise exceptions.TogglException('{}: Unknown cardinality \'{}\''.format(self.name, self.cardinality))

    def __set__(self, instance, value):  # type: (base.Entity, MappedM) -> None
        if self.cardinality == MappingCardinality.ONE:
            try:
                if value.id is None:
                    raise RuntimeError(
                        'You are trying to assign mapped entity which was yet not saved! (Does not have ID)')

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
