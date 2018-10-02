import datetime

import pendulum

from toggl.api import base, fields, models
from toggl import exceptions
import pytest

#########################################################################################
# PropertyField


class Entity(base.TogglEntity):
    string = fields.StringField()
    integer = fields.IntegerField()
    boolean = fields.BooleanField()
    float = fields.FloatField()


class TestTogglField:

    def test_validate(self):
        field = fields.TogglField()

        try:
            field.validate(None)
            field.validate('asd')
        except exceptions.TogglValidationException:
            pytest.fail('Validation exception raised!')

        field = fields.TogglField(required=True)
        with pytest.raises(exceptions.TogglValidationException):
            field.validate(None)

        field = fields.TogglField(required=True, default=None)
        try:
            field.validate(None)
        except exceptions.TogglValidationException:
            pytest.fail('Validation exception raised!')

    def test_init(self):
        obj = Entity(string='asdf')

        with pytest.raises(exceptions.TogglException):
            obj.__fields__['string'].init(obj, 'ggg')

        try:
            obj.__fields__['integer'].init(obj, '123')
        except exceptions.TogglException:
            pytest.fail('Exception raised!')

        assert obj.integer == 123

    def test_parse(self):
        obj = Entity()

        obj.integer = 123
        assert obj.integer == 123
        obj.integer = '123'
        assert obj.integer == 123
        with pytest.raises(TypeError):
            obj.integer = 'asd'

        obj.float = 123.123
        assert obj.float == 123.123
        obj.float = '123.123'
        assert obj.float == 123.123
        with pytest.raises(TypeError):
            obj.float = 'asd'

        obj.boolean = 'True'
        assert obj.boolean is True
        obj.boolean = 0
        assert obj.boolean is False
        obj.boolean = 'asdasd'
        assert obj.boolean is True

    def test_get(self):
        obj = Entity()
        obj.__dict__ = {'field': 123}

        field = fields.StringField()
        with pytest.raises(RuntimeError):
            field.__get__(obj, None)

        field.name = 'field'
        assert field.__get__(obj, None) == 123

        field.name = 'non-existing=field'
        with pytest.raises(AttributeError):
            field.__get__(obj, None)

    def test_get_default(self):
        obj = Entity()
        obj.__dict__ = {}

        field = fields.StringField(default='asd')
        field.name = 'field'
        assert field.__get__(obj, None) == 'asd'

    def test_get_callable_default(self):
        obj = Entity()
        obj.__dict__ = {}

        field = fields.StringField(default=lambda: '123')
        field.name = 'field'
        assert field.__get__(obj, None) == '123'

    def test_set(self):
        obj = Entity()

        field = fields.StringField()
        with pytest.raises(RuntimeError):
            field.__set__(obj, 'asd')

        field.name = 'field'
        field.__set__(obj, 'asd')
        assert obj.__dict__['field'] == 'asd'
        assert obj.__change_dict__['field'] == 'asd'

        field.__set__(obj, None)
        assert obj.__dict__['field'] is None

    def test_set_required(self):
        obj = Entity()

        field = fields.StringField(required=True)
        field.name = 'field'

        with pytest.raises(TypeError):
            field.__set__(obj, None)

    def test_set_read_only(self):
        obj = Entity()

        field = fields.StringField(is_read_only=True)
        field.name = 'field'

        with pytest.raises(exceptions.TogglException):
            field.__set__(obj, 'asd')

    def test_set_admin(self):
        class WorkspaceMock:
            admin = True

        class WorkspaceEntityMock(models.WorkspaceEntity):
            workspace = WorkspaceMock

        obj = WorkspaceEntityMock()

        field = fields.StringField(admin_only=True)
        field.name = 'field'

        field.__set__(obj, 'asd')
        assert obj.__dict__['field'] == 'asd'

        WorkspaceMock.admin = False
        with pytest.raises(exceptions.TogglAuthorizationException):
            field.__set__(obj, 'asd')


#########################################################################################
# MappingField

class TestMappingField:
    def test_basic(self):
        class A:
            pass

        with pytest.raises(TypeError):
            fields.MappingField(A, 'a')


#########################################################################################
# PropertyField


class PropertyFieldStore:
    value = None


def getter(name, instance, serializing=False):
    assert name == 'field'

    return PropertyFieldStore.value


def setter(name, instance, value, init=False):
    PropertyFieldStore.value = value


class PropertyEntity(base.TogglEntity):
        field = fields.PropertyField(getter, setter)


class ReadOnlyPropertyEntity(base.TogglEntity):
        field = fields.PropertyField(fields.PropertyField.default_getter)


class TestPropertyField:

    def test_init(self):
        PropertyFieldStore.value = None
        PropertyEntity()
        assert PropertyFieldStore.value is None

        PropertyFieldStore.value = None
        PropertyEntity(field='some value')
        assert PropertyFieldStore.value == 'some value'

    def test_set_and_get(self):
        PropertyFieldStore.value = None
        instance = PropertyEntity()

        instance.field = 'some value'
        assert PropertyFieldStore.value == 'some value'
        assert instance.field == 'some value'

    def test_deserialization(self):
        PropertyFieldStore.value = None
        instance = PropertyEntity.deserialize()

        assert PropertyFieldStore.value is None
        assert instance.field is None

        PropertyFieldStore.value = None
        instance = PropertyEntity.deserialize(field='some value')

        assert PropertyFieldStore.value == 'some value'
        assert instance.field == 'some value'

    def test_read_only(self):
        PropertyFieldStore.value = None
        instance = ReadOnlyPropertyEntity()

        with pytest.raises(exceptions.TogglException):
            instance.field = 'some value'

        PropertyFieldStore.value = None
        instance = ReadOnlyPropertyEntity(field='some value')
        assert instance.field == 'some value'
        assert instance.__fields__['field'].is_read_only == True
        with pytest.raises(exceptions.TogglException):
            instance.field = 'some value'


#########################################################################################
# DateTimeField

class DateTimeEntity(base.TogglEntity):
    field = fields.DateTimeField()


class TestDateTimeField:

    def test_type_check(self):
        instance = DateTimeEntity()

        with pytest.raises(TypeError):
            instance.field = 'some value not datetime'

        try:
            instance.field = datetime.datetime.now()
        except TypeError:
            pytest.fail('DateTimeField does not accept valid datetime.datetime object!')

        try:
            instance.field = pendulum.now()
        except TypeError:
            pytest.fail('DateTimeField does not accept valid pendulum.DateTime object!')


#########################################################################################
# ListField

class ListEntity(base.TogglEntity):
    field = fields.ListField()


class TestListField:

    def test_type_check(self):
        instance = ListEntity()

        with pytest.raises(TypeError):
            instance.field = 'some value not list'

        try:
            instance.field = ['some', 'list']
        except TypeError:
            pytest.fail('ListField does not accept valid list object!')

    def test_format(self):
        instance = ListEntity()

        value = ['some', 'list']
        formatted_value = instance.__fields__['field'].format(value)
        assert len(value) == len(formatted_value.split(','))

        value = ['some']
        formatted_value = instance.__fields__['field'].format(value)
        assert ',' not in formatted_value

        value = None
        formatted_value = instance.__fields__['field'].format(value)
        assert formatted_value == ''
