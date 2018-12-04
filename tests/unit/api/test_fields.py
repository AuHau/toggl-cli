import datetime

import pendulum

from toggl.api import base, fields, models
from toggl import exceptions, utils
import pytest


class Entity(base.TogglEntity):
    string = fields.StringField()
    integer = fields.IntegerField()
    boolean = fields.BooleanField()
    float = fields.FloatField()


class TestTogglField:

    def test_validate(self):
        field = fields.TogglField()
        instance = object()

        try:
            field.validate(None, instance)
            field.validate('asd', instance)
        except exceptions.TogglValidationException:
            pytest.fail('Validation exception raised!')

        field = fields.TogglField(required=True)
        with pytest.raises(exceptions.TogglValidationException):
            field.validate(None, instance)

        field = fields.TogglField(required=True, default=None)
        try:
            field.validate(None, instance)
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

        field = fields.StringField(default=lambda _: '123')
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
            name = 'WorkspaceMock'

        class WorkspacedEntityMock(models.WorkspacedEntity):
            workspace = WorkspaceMock

        obj = WorkspacedEntityMock()

        field = fields.StringField(admin_only=True)
        field.name = 'field'

        field.__set__(obj, 'asd')
        assert obj.__dict__['field'] == 'asd'

        WorkspaceMock.admin = False
        with pytest.raises(exceptions.TogglNotAllowedException):
            field.__set__(obj, 'asd')

    def test_premium(self):
        class WorkspaceMock:
            premium = False
            name = 'WorkspaceMock'

        class WorkspacedEntityMock(models.WorkspacedEntity):
            workspace = WorkspaceMock
            premium_field = fields.StringField(premium=True)

        with pytest.raises(exceptions.TogglPremiumException):
            obj = WorkspacedEntityMock(premium_field='something')
            obj.save()

        obj = WorkspacedEntityMock()

        field = fields.StringField(premium=True)
        field.name = 'field'

        with pytest.raises(exceptions.TogglPremiumException):
            field.__set__(obj, 'asd')

        WorkspaceMock.premium = True
        field.__set__(obj, 'asd')
        assert obj.__dict__['field'] == 'asd'


#########################################################################################
# MappingField

class TestMappingField:
    def test_basic(self):
        class A:
            pass

        with pytest.raises(TypeError):
            fields.MappingField(A, 'a')

    def test_default(self, mocker):
        config = utils.Config.factory(None)
        a = Entity(config=config)
        b = Entity()
        c = Entity()

        field = fields.MappingField(Entity, 'a', default=b)
        assert field.__get__(a, None) is b

        mocker.patch.object(base.TogglSet, 'get')
        base.TogglSet.get.return_value = c

        field = fields.MappingField(Entity, 'a', default=123)
        assert field.__get__(a, None) is c
        base.TogglSet.get.assert_called_with(123)
        base.TogglSet.get.reset_mock()

        field = fields.MappingField(Entity, 'a', default=lambda _: 321)
        assert field.__get__(a, None) is c
        base.TogglSet.get.assert_called_with(321)

        stub = mocker.stub()
        stub.return_value = c
        field = fields.MappingField(Entity, 'a', default=stub)
        field.__get__(a, None)
        stub.assert_called_once_with(config)


#########################################################################################
# PropertyField


class PropertyFieldStore:
    value = None


class PropertyFieldStateChanged:
    value = True


def getter(name, instance, serializing=False):
    assert name == 'field'

    return PropertyFieldStore.value


def setter(name, instance, value, init=False):
    PropertyFieldStore.value = value
    return PropertyFieldStateChanged.value


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

    def test_changes(self):
        PropertyFieldStore.value = None
        obj = PropertyEntity(field='some value')
        assert len(obj.__change_dict__) == 0

        # Simulating that setting the value does not change the instance's state
        PropertyFieldStateChanged.value = False
        obj.field = 'some other value'
        assert len(obj.__change_dict__) == 0

        # Simulating that the value changed the state
        PropertyFieldStateChanged.value = True
        obj.field = 'some other value'
        assert len(obj.__change_dict__) == 1


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
    field = fields.ListField()  # type: list


class RequiredListEntity(base.TogglEntity):
    field = fields.ListField(required=True)  # type: list


class TestListField:

    def test_type_check(self):
        instance = ListEntity()
        required_instance = RequiredListEntity(field=[1, 2, 3])

        with pytest.raises(TypeError):
            instance.field = 'some value not list'

        with pytest.raises(TypeError):
            required_instance.field = None

        try:
            instance.field = None
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

    def test_init(self):
        instance = ListEntity(field=[1, 2, 3])

        assert len(instance.field) == 3
        assert isinstance(instance.field, fields.ListContainer)

    def test_update(self):
        instance = ListEntity(field=[1, 2, 3])

        assert len(instance.field) == 3
        instance.field.append(4)
        assert len(instance.field) == 4

    def test_change_detection(self):
        instance = ListEntity(field=[1, 2, 3])
        instance.field.append(4)

        assert len(instance.__change_dict__) == 1


#########################################################################################
# SetField

class SetEntity(base.TogglEntity):
    field = fields.SetField()  # type: set


class SetListEntity(base.TogglEntity):
    field = fields.SetField(required=True)  # type: set


class TestSetField:

    def test_type_check(self):
        instance = SetEntity()
        required_instance = SetListEntity(field=[1, 2, 3])

        with pytest.raises(TypeError):
            instance.field = 'some value not list'

        with pytest.raises(TypeError):
            required_instance.field = None

        try:
            instance.field = None
            instance.field = ['some', 'list']
            instance.field = {'some', 'list'}
        except TypeError:
            pytest.fail('ListField does not accept valid list object!')

    def test_format(self):
        instance = SetEntity()

        value = {'some', 'list'}
        formatted_value = instance.__fields__['field'].format(value)
        assert len(value) == len(formatted_value.split(','))

        value = {'some'}
        formatted_value = instance.__fields__['field'].format(value)
        assert ',' not in formatted_value

        value = None
        formatted_value = instance.__fields__['field'].format(value)
        assert formatted_value == ''

    def test_init(self):
        instance = SetEntity(field=[1, 2, 3, 3])

        assert len(instance.field) == 3
        assert isinstance(instance.field, fields.SetContainer)

    def test_update(self):
        instance = SetEntity(field=[1, 2, 3])

        assert len(instance.field) == 3
        instance.field.add(4)
        assert len(instance.field) == 4
        instance.field.add(4)
        assert len(instance.field) == 4

    def test_change_detection(self):
        instance = SetEntity(field=[1, 2, 3])
        assert len(instance.__change_dict__) == 0

        instance.field.add(4)
        assert 'field' in instance.__change_dict__

        instance.__change_dict__ = {}
        instance.field.remove(4)
        assert 'field' in instance.__change_dict__

