from datetime import timedelta

import factory
import faker

from toggl import api
from tests import helpers

# TODO: Do more clean way how to pass config into the Factory
module_config = None


class TogglFactory(factory.Factory):

    @classmethod
    def _build(cls, model_class, config=None, *args, **kwargs):
        config = module_config or config or helpers.get_config()
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
    billable = False


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
        return fake.date_time_between_dates(self.start, self.start + timedelta(hours=12))


class PremiumTimeEntryFactory(TogglFactory):
    task = factory.SubFactory(TaskFactory)


class TagFactory(TogglFactory):
    class Meta:
        model = api.Tag

    name = factory.Faker('name')
