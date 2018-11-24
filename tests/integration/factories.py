import factory
import faker

from toggl import api
from tests import helpers


class TogglFactory(factory.Factory):

    @classmethod
    def _build(cls, model_class, config=None, *args, **kwargs):
        config = config or helpers.get_config()
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
    # client = factory.SubFactory(ClientFactory)
    active = True
    is_private = True


class TaskFactory(TogglFactory):
    class Meta:
        model = api.Task

    name = factory.Faker('sentace')
    project = factory.SubFactory(ProjectFactory)
    estimated_seconds = factory.Faker('pydecimal', positive=True)


class TimeEntryFactory(TogglFactory):
    class Meta:
        model = api.TimeEntry

    description = factory.Faker('sentence')
    # project = factory.SubFactory(ProjectFactory)
    start = factory.Faker('past_datetime', start_date='-9d')

    @factory.lazy_attribute
    def stop(self):
        fake = faker.Faker()
        return fake.past_datetime(start_date=self.start)


class PremiumTimeEntryFactory(TogglFactory):
    billable = factory.Faker('pybool')
    task = factory.SubFactory(TaskFactory)
