from toggl.api import base
from toggl import exceptions


class RandomEntity(base.TogglEntity):
    some_field = base.StringField()


class EntityWithCustomObjects(base.TogglEntity):
    objects = 'something'


class TestMetaBase:

    def test_adding_toggl_set_as_objects(self):
        assert hasattr(RandomEntity, 'objects')
        assert isinstance(RandomEntity.objects, base.TogglSet)

    def test_not_overriding_objects(self):
        assert EntityWithCustomObjects.objects == 'something'
