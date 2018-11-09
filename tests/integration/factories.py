import factory

from toggl import api
from . import helpers


class TogglFactory(factory.Factory):

    @classmethod
    def _build(cls, model_class, config='default.config', *args, **kwargs):
        config = helpers.get_config(config)
        return model_class(config=config, *args, **kwargs)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        obj = cls._build(model_class, *args, **kwargs)
        obj.save()

        return obj


class ClientFactory(TogglFactory):
    class Meta:
        model = api.Client

    name = factory.Faker('name')
    notes = factory.Faker('sentence')


class ProjectFactory(TogglFactory):
    class Meta:
        model = api.Project

    name = factory.Faker('name')
    client = factory.SubFactory(ClientFactory)
    active = True
    is_private = True

