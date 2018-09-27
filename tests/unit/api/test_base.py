from toggl.api import base, fields
from toggl import exceptions


class RandomEntity(base.TogglEntity):
    some_field = fields.StringField()


class EntityWithDummySet(base.TogglEntity):
    objects = 'something'


class CustomSet(base.TogglSet):
    pass


class EntityWithCustomNotBindedSet(base.TogglEntity):
    objects = CustomSet('some_url')


class EntityWithCustomBindedSet(base.TogglEntity):
    objects = CustomSet('some_url', RandomEntity)


class TestMetaBase:

    def test_adding_toggl_set_as_objects(self):
        assert hasattr(RandomEntity, 'objects')
        assert isinstance(RandomEntity.objects, base.TogglSet)

    def test_not_overriding_objects(self):
        assert EntityWithDummySet.objects == 'something'

    def test_objects_class_binding(self):
        assert EntityWithCustomNotBindedSet.objects.entity_cls == EntityWithCustomNotBindedSet
        assert EntityWithCustomBindedSet.objects.entity_cls == RandomEntity
