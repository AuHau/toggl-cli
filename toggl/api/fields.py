import datetime
import logging
from builtins import int
from enum import Enum

import pendulum
from validate_email import validate_email

from .. import exceptions
from .. import utils
from . import base

logger = logging.getLogger('toggl.models.fields')


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

    def format(self, value, config=None):
        return value

    def init(self, instance, value):
        if self.name in instance.__dict__:
            raise exceptions.TogglException('Field \'{}.{}\' is already initiated!'
                                            .format(instance.__class__.__name__, self.name))

        try:
            value = self.parse(value, instance._config)
        except ValueError as e:
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
    def _is_naive(value):  # type: (datetime.datetime) -> bool
        return value.utcoffset() is None

    def __set__(self, instance, value):
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

    def parse(self, value, config=None):
        config = config or utils.Config.factory()

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

    def format(self, value, config=None):
        if value is None:
            return None

        if not isinstance(value, pendulum.DateTime):
            raise TypeError('DateTimeField needs for formatting pendulum.DateTime object')

        config = config or utils.Config.factory()

        return value.in_timezone(config.timezone).format(config.datetime_format)

    def serialize(self, value):
        if value is None:
            return None

        if not isinstance(value, pendulum.DateTime):
            raise TypeError('DateTimeField needs for serialization pendulum.DateTime object!')

        return value.in_timezone('UTC').to_iso8601_string()


class EmailField(StringField):

    def validate(self, value):
        super(EmailField, self).validate(value)

        if not validate_email(value):
            raise exceptions.TogglValidationException('Email \'{}\' is not valid email address!'.format(value))


class PropertyField(TogglField):

    def __init__(self, getter, setter=None, serializer=None, formater=None, verbose_name=None, admin_only=False):
        self.getter = getter
        self.serializer = serializer
        self.formater = formater
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

    def format(self, value, config=None):
        return self.formater(value, config) if self.formater else super().format(value, config)

    def serialize(self, value):
        return self.serializer(value) if self.serializer else super().serialize(value)

    def __get__(self, instance, owner):
        return self.getter(self.name, instance)

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

    def format(self, value, config=None):
        return self.get_label(value)

    def get_label(self, value):
        return self.choices[value]


class MappingCardinality(Enum):
    ONE = 'one'
    MANY = 'many'


class MappingField(TogglField):

    def __init__(self, mapped_cls, mapped_field, cardinality=MappingCardinality.ONE, *args, **kwargs):
        super(MappingField, self).__init__(*args, **kwargs)

        if not issubclass(mapped_cls, base.TogglEntity):
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

                if isinstance(default, base.TogglEntity):
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
