from copy import copy

import pendulum

import pytest

from toggl.api import base, fields
from toggl import exceptions, utils

from ... import helpers


class RandomEntity(base.TogglEntity):
    some_field = fields.StringField()


class EntityWithDummySet(base.TogglEntity):
    objects = 'something'


class CustomSet(base.TogglSet):
    pass


class EntityWithCustomNotBindedSet(base.TogglEntity):
    objects = CustomSet()


class EntityWithCustomBindedSet(base.TogglEntity):
    objects = CustomSet(RandomEntity)


class TestMetaBase:

    def test_adding_toggl_set_as_objects(self):
        assert hasattr(RandomEntity, 'objects')
        assert isinstance(RandomEntity.objects, base.TogglSet)

    def test_not_overriding_objects(self):
        assert EntityWithDummySet.objects == 'something'

    def test_objects_class_binding(self):
        assert EntityWithCustomNotBindedSet.objects.entity_cls == EntityWithCustomNotBindedSet
        assert EntityWithCustomBindedSet.objects.entity_cls == RandomEntity


#######################################################################################################
## Evaluate Conditions


class EvaluateConditionsEntity(base.TogglEntity):
    string = fields.StringField()
    integer = fields.IntegerField()
    boolean = fields.BooleanField()
    set = fields.SetField()


class EvaluateConditionsEntityMapping(EvaluateConditionsEntity):
    mapping = fields.MappingField(RandomEntity, 'rid')


config = helpers.get_config()

evaluate_conditions_testset = (
    ({'string': 'asd'}, EvaluateConditionsEntity(config=config, string='asd'), True),
    ({'string': 'something'}, EvaluateConditionsEntity(config=config, string='else'), False),
    ({'string': 'asd', 'non-existing-field': 'value'}, EvaluateConditionsEntity(config=config, string='asd'), False),

    ({'string': 'asd', 'integer': 123, 'boolean': True},
     EvaluateConditionsEntity(config=config, string='asd', integer=123, boolean=True),
     True),

    ({'string': 'asd', 'integer': 123},
     EvaluateConditionsEntity(config=config, string='asd', integer=123, boolean=True),
     True),

    ({'integer': 123, 'boolean': True, 'set': {1, 2}},
     EvaluateConditionsEntity(config=config, string='asd', integer=123, boolean=True, set={1, 2, 3, 4}),
     True),

    ({'integer': 123, 'boolean': True, 'set': {1, 2, 3, 4}},
     EvaluateConditionsEntity(config=config, string='asd', integer=123, boolean=True, set={1, 2, 3, 4}),
     True),

    ({'integer': 123, 'boolean': True, 'set': {5, 6}},
     EvaluateConditionsEntity(config=config, string='asd', integer=123, boolean=True, set={1, 2, 3, 4}),
     False),
)

evaluate_conditions_contain_testset = (
    ({'string': 'asd'}, EvaluateConditionsEntity(config=config, string='asd'), True),
    ({'string': 'as'}, EvaluateConditionsEntity(config=config, string='asd'), True),
    ({'string': 'a'}, EvaluateConditionsEntity(config=config, string='asd'), True),
    ({'string': 'asdf'}, EvaluateConditionsEntity(config=config, string='asd'), False),
    ({'integer': 123}, EvaluateConditionsEntity(config=config, integer=123), True),
    ({'integer': 12}, EvaluateConditionsEntity(config=config, integer=123), False),
)


class TestEvaluateConditions:

    @pytest.mark.parametrize(('condition', 'entity', 'expected'), evaluate_conditions_testset)
    def test_equality(self, condition, entity, expected):
        assert base.evaluate_conditions(condition, entity) == expected

    @pytest.mark.parametrize(('condition', 'entity', 'expected'), evaluate_conditions_contain_testset)
    def test_contain(self, condition, entity, expected):
        assert base.evaluate_conditions(condition, entity, contain=True) == expected

    def test_mapping(self):
        mapped_obj = RandomEntity()
        mapped_obj.id = 111

        obj = EvaluateConditionsEntityMapping(integer=123, mapping=mapped_obj)

        assert base.evaluate_conditions({'integer': 123}, obj) is True
        assert base.evaluate_conditions({'mapping': mapped_obj}, obj) is True
        assert base.evaluate_conditions({'mapping': None}, obj) is False
        assert base.evaluate_conditions({'rid': 111}, obj) is True

        obj = EvaluateConditionsEntityMapping(integer=123)
        assert base.evaluate_conditions({'mapping': None}, obj) is True


#######################################################################################################
## TogglSet


class TestTogglSet:

    def test_rebind_class(self):
        tset = base.TogglSet()

        tset.bind_to_class(RandomEntity)

        with pytest.raises(exceptions.TogglException):
            tset.bind_to_class(RandomEntity)

    def test_unbound_set(self):
        tset = base.TogglSet()

        with pytest.raises(exceptions.TogglException):
            tset.get()

        with pytest.raises(exceptions.TogglException):
            tset.all()

        with pytest.raises(exceptions.TogglException):
            tset.filter()

        with pytest.raises(exceptions.TogglException):
            tset.base_url

    def test_url(self):
        tset = base.TogglSet(url='http://some-url.com')
        assert tset.base_url == 'http://some-url.com'

        tset = base.TogglSet(RandomEntity)
        assert tset.base_url == 'random_entitys'

    def test_can_get_detail(self):
        tset = base.TogglSet(can_get_detail=False)
        assert tset.can_get_detail is False

        RandomEntity._can_get_detail = False
        tset = base.TogglSet(RandomEntity)
        assert tset.can_get_detail is False
        RandomEntity._can_get_detail = True
        assert tset.can_get_detail is True

        tset = base.TogglSet()
        assert tset.can_get_detail is True

    def test_can_get_list(self):
        tset = base.TogglSet(can_get_list=False)
        assert tset.can_get_list is False

        RandomEntity._can_get_list = False
        tset = base.TogglSet(RandomEntity)
        assert tset.can_get_list is False
        RandomEntity._can_get_list = True
        assert tset.can_get_list is True

        tset = base.TogglSet()
        assert tset.can_get_list is True

    # Get()

    def test_get_detail_basic(self, mocker):
        mocker.patch.object(utils, 'toggl')
        utils.toggl.return_value = {
            'data': {
                'some_field': 'asdf'
            }
        }

        tset = base.TogglSet(RandomEntity)
        obj = tset.get(id=123)

        assert obj is not None
        assert obj.some_field == 'asdf'

    def test_get_detail_none(self, mocker):
        mocker.patch.object(utils, 'toggl')
        utils.toggl.return_value = {
            'data': None
        }

        tset = base.TogglSet(RandomEntity)
        obj = tset.get(id=123)

        assert obj is None

    def test_get_detail_none_exception(self, mocker):
        mocker.patch.object(utils, 'toggl')
        utils.toggl.side_effect = exceptions.TogglNotFoundException(404, 'Not found')

        tset = base.TogglSet(RandomEntity)
        obj = tset.get(id=123)

        assert obj is None

    def test_get_detail_filter_fallback(self, mocker):
        mocker.patch.object(utils, 'toggl')
        utils.toggl.return_value = [{
            'id': 123,
            'some_field': 'asdf'
        }]

        tset = base.TogglSet(RandomEntity, can_get_detail=False)
        obj = tset.get(id=123)

        assert obj is not None
        assert obj.some_field == 'asdf'

    def test_get_detail_filter_fallback_multiple_entries(self, mocker):
        mocker.patch.object(utils, 'toggl')
        utils.toggl.return_value = [{
            'id': 123,
            'some_field': 'asdf'
        }, {
            'id': 123,
            'some_field': 'asdf'
        }]

        tset = base.TogglSet(RandomEntity, can_get_detail=False)
        with pytest.raises(exceptions.TogglMultipleResultsException):
            tset.get(id=123)

    def test_get_detail_filter_fallback_no_entries(self, mocker):
        mocker.patch.object(utils, 'toggl')
        utils.toggl.return_value = [{
            'id': 321,
            'some_field': 'asdf'
        }, {
            'id': 321,
            'some_field': 'asdf'
        }]

        tset = base.TogglSet(RandomEntity, can_get_detail=False)
        assert tset.get(id=123) is None

    # Filter()

    def test_filter(self, mocker):
        mocker.patch.object(utils, 'toggl')
        utils.toggl.return_value = [
            {
                'id': 1,
                'some_field': 'asdf'
            },
            {
                'id': 2,
                'some_field': 'asdf'
            },
            {
                'id': 3,
                'some_field': 'mmm'
            },
        ]

        tset = base.TogglSet(RandomEntity, can_get_detail=False)
        objs = tset.filter(some_field='asdf')
        assert len(objs) == 2

    def test_filter_multiple_conditions(self, mocker):
        mocker.patch.object(utils, 'toggl')
        utils.toggl.return_value = [
            {
                'id': 3,
                'some_field': 'asdf'
            },
            {
                'id': 2,
                'some_field': 'asdf'
            },
            {
                'id': 3,
                'some_field': 'mmm'
            },
        ]

        tset = base.TogglSet(RandomEntity, can_get_detail=False)
        objs = tset.filter(some_field='asdf', id=2)
        assert len(objs) == 1

    def test_filter_contain(self, mocker):
        mocker.patch.object(utils, 'toggl')
        utils.toggl.return_value = [
            {
                'id': 1,
                'some_field': 'asdf'
            },
            {
                'id': 1,
                'some_field': 'asdf-aa'
            },
            {
                'id': 2,
                'some_field': 'asdf-bb'
            },
            {
                'id': 3,
                'some_field': 'mmm'
            },
        ]

        tset = base.TogglSet(RandomEntity, can_get_detail=False)
        objs = tset.filter(some_field='asdf', contain=True)
        assert len(objs) == 3

    def test_all(self, mocker):
        mocker.patch.object(utils, 'toggl')
        utils.toggl.return_value = [
            {
                'id': 4,
                'some_field': 'asdf'
            },
            {
                'id': 1,
                'some_field': 'asdf-aa'
            },
            {
                'id': 2,
                'some_field': 'asdf-bb'
            },
            {
                'id': 3,
                'some_field': 'mmm'
            },
        ]

        tset = base.TogglSet(RandomEntity)
        objs = tset.all()
        assert len(objs) == 4
        assert objs[0].some_field == 'asdf'

    def test_all_sort(self, mocker):
        mocker.patch.object(utils, 'toggl')
        utils.toggl.return_value = [
            {
                'id': 4,
                'some_field': 'asdf'
            },
            {
                'id': 1,
                'some_field': 'asdf-aa'
            },
            {
                'id': 2,
                'some_field': 'asdf-bb'
            },
            {
                'id': 3,
                'some_field': 'mmm'
            },
        ]

        tset = base.TogglSet(RandomEntity)
        objs = tset.filter(order='desc')
        assert len(objs) == 4
        assert objs[0].some_field == 'mmm'

    def test_all_can_get_list_false(self):
        tset = base.TogglSet(RandomEntity, can_get_list=False)

        with pytest.raises(exceptions.TogglException):
            tset.all()


#######################################################################################################
## TogglEntityMeta


class MetaTestEntity(metaclass=base.TogglEntityMeta):
    id = fields.IntegerField()
    string = fields.StringField()
    boolean = fields.BooleanField()
    mapped = fields.MappingField(RandomEntity, 'mapping_field')


class ExtendedMetaTestEntity(MetaTestEntity):
    another_string = fields.StringField()
    another_mapped = fields.MappingField(RandomEntity, 'another_mapping_field')


class TestTogglEntityMeta:
    @staticmethod
    def set_fields_names(fields):
        for name, field in fields.items():
            field.name = name

    def test_make_signature(self):
        fields_set = {
            'id': fields.IntegerField(),
            'str': fields.StringField(default='asd'),
            'req_str': fields.StringField(required=True),
        }

        self.set_fields_names(fields_set)

        sig = base.TogglEntityMeta._make_signature(fields_set)
        sig_params = sig.parameters

        assert len(sig_params) == 2
        assert sig_params['str'].default == 'asd'
        assert 'id' not in sig_params

    def test_make_fields(self):
        fields_set = {
            'id': fields.IntegerField(),
            'str': fields.StringField(default='asd'),
            'req_str': fields.StringField(required=True),
            'something_random': 'asdf'
        }

        result = base.TogglEntityMeta._make_fields(fields_set, [RandomEntity])

        # Four because there is one Field taken from RandomEntity and 'something_random' is ignored
        assert len(result) == 4
        assert result['id'].name == 'id'

    def test_make_mapped_fields(self):
        mapping_field_instance = fields.MappingField(RandomEntity, 'mapped_field')

        fields_set = {
            'id': fields.IntegerField(),
            'str': fields.StringField(),
            'mapping': mapping_field_instance,
            'something_random': 'asdf'
        }

        result = base.TogglEntityMeta._make_mapped_fields(fields_set)

        # Four because there is one Field taken from RandomEntity and 'something_random' is ignored
        assert len(result) == 1
        assert result['mapped_field'] is mapping_field_instance

    def test_whole_class(self):
        assert len(MetaTestEntity.__fields__) == 4
        assert len(MetaTestEntity.__mapped_fields__) == 1
        assert hasattr(MetaTestEntity, 'objects')
        assert hasattr(MetaTestEntity, '__signature__')
        assert isinstance(MetaTestEntity.objects, base.TogglSet)

    def test_extended_class(self):
        assert len(ExtendedMetaTestEntity.__fields__) == 6
        assert len(ExtendedMetaTestEntity.__mapped_fields__) == 2

    def test_mapping_fields_conflict(self):
        with pytest.raises(TypeError):
            class ExtendedMetaTestEntityWithConflicts(MetaTestEntity):
                some_other_mapped_field = fields.MappingField(RandomEntity, 'mapping_field')


#######################################################################################################
## TogglEntity

class Entity(base.TogglEntity):
    string = fields.StringField()
    integer = fields.IntegerField()
    boolean = fields.BooleanField()
    datetime = fields.DateTimeField()


class EntityWithRequired(Entity):
    required = fields.StringField(required=True)


class EntityWithDefault(Entity):
    default = fields.StringField(default='asd')
    callable_default = fields.StringField(default=lambda _: 'aaa')


class EntityWithMapping(Entity):
    mapping = fields.MappingField(RandomEntity, 'eid')


class EntityWithRequiredMapping(Entity):
    mapping = fields.MappingField(Entity, 'eid', required=True)


class TestTogglEntity:

    def test_init(self):
        obj = Entity(string='asd', integer=123)

        assert obj.string == 'asd'
        assert obj.integer == 123

        with pytest.raises(AttributeError):
            obj.boolean

        # Test that not-present required field raise TypeError
        with pytest.raises(TypeError):
            EntityWithRequired(string='asd')

    def test_init_ignore_id(self):
        obj_no_id = Entity(id=111, string='asd', integer=123)
        assert obj_no_id.id is None

    def test_init_mapping(self):
        obj = Entity(string='asd', integer=123)
        obj.id = 123
        mapped_obj = EntityWithMapping(mapping=obj)
        assert mapped_obj.__dict__['eid'] == 123
        mapped_obj = EntityWithMapping(eid=123)
        assert mapped_obj.__dict__['eid'] == 123
        with pytest.raises(TypeError):
            EntityWithRequiredMapping(string='asd')

    def test_to_dict(self):
        obj = Entity(string='asd', integer=123)
        obj_dict = obj.to_dict()

        assert obj_dict['string'] == 'asd'
        assert obj_dict['integer'] == 123

    def test_to_dict_default(self):
        obj = EntityWithDefault(string='asd', integer=123)
        obj_dict = obj.to_dict()

        assert obj_dict['string'] == 'asd'
        assert obj_dict['integer'] == 123
        assert obj_dict['default'] == 'asd'
        assert obj_dict['callable_default'] == 'aaa'

    def test_to_dict_mapping_default(self):
        a = RandomEntity()

        class EntityWithDefaultMapping(Entity):
            default = fields.MappingField(RandomEntity, 'eid', default=a)

        obj = EntityWithDefaultMapping()
        obj_dict = obj.to_dict()
        assert obj_dict['default'] is a

    def test_to_dict_mapping(self, mocker):
        obj = Entity(integer=321)
        obj.id = 123

        different_obj = Entity(integer=321)
        different_obj.id = 124

        mapped_obj = EntityWithMapping(string='asd', mapping=obj)

        mocker.patch.object(base.TogglSet, 'get')
        base.TogglSet.get.return_value = obj

        obj_dict = mapped_obj.to_dict()
        assert obj_dict['string'] == 'asd'
        assert obj_dict['mapping'] is obj
        base.TogglSet.get.assert_called_with(123, config=mocker.ANY)
        base.TogglSet.get.reset_mock()

        obj_dict = mapped_obj.to_dict(serialized=True)
        assert obj_dict['string'] == 'asd'
        assert obj_dict['eid'] == 123

        base.TogglSet.get.return_value = different_obj
        mapped_obj.mapping = different_obj
        change_obj_dict = mapped_obj.to_dict(changes_only=True)
        assert 'string' not in change_obj_dict
        assert change_obj_dict['mapping'] is different_obj
        base.TogglSet.get.assert_called_with(124, config=mocker.ANY)

    def test_to_dict_changes(self):
        obj = Entity(string='asd', integer=123, boolean=True)
        obj.boolean = False
        obj.integer = 321
        obj_dict = obj.to_dict(changes_only=True)

        assert 'string' not in obj_dict
        assert obj_dict['integer'] == 321
        assert obj_dict['boolean'] is False

    def test_to_dict_serialization(self):
        date = pendulum.now(tz='UTC')
        obj = Entity(string='asd', integer=123, datetime=date)
        obj_dict = obj.to_dict(serialized=True)

        assert obj_dict['string'] == 'asd'
        assert obj_dict['integer'] == 123
        assert obj_dict['datetime'] == date.to_iso8601_string()

    def test_copy(self):
        obj = Entity(string='asd', integer=123)
        obj.id = 123
        new_obj = copy(obj)

        assert not obj is new_obj
        assert obj.string == new_obj.string
        assert obj.integer == new_obj.integer
        assert new_obj.id is None

    def test_save_create(self, mocker):
        mocker.patch.object(utils, 'toggl')
        utils.toggl.return_value = {
            'data': {
                'id': 333
            }
        }

        obj = Entity(string='asd', integer=123)
        obj.save()

        assert obj.id == 333
        assert utils.toggl.called is True

        obj = Entity(string='asd', integer=123)
        obj._can_create = False
        with pytest.raises(exceptions.TogglException):
            obj.save()

    def test_save_update(self, mocker):
        mocker.patch.object(utils, 'toggl')
        utils.toggl.return_value = {
            'data': {
                'id': 333
            }
        }

        obj = Entity(string='asd', integer=123)
        obj.id = 333
        obj.save()

        assert obj.id == 333
        assert utils.toggl.called is True

        obj = Entity(string='asd', integer=123)
        obj.id = 333
        obj._can_update = False
        with pytest.raises(exceptions.TogglException):
            obj.save()

    def test_delete(self, mocker):
        mocker.patch.object(utils, 'toggl')
        utils.toggl.return_value = {
            'data': {
                'id': 333
            }
        }

        obj = Entity(string='asd', integer=123)
        obj.id = 333
        obj.save()

        assert obj.id == 333
        assert utils.toggl.called is True

        obj = Entity(string='asd', integer=123)
        obj.id = 333
        obj._can_update = False
        with pytest.raises(exceptions.TogglException):
            obj.save()
