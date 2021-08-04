import pendulum
from toggl.api import TimeEntry


class TestTimeEntries:

    def test_ls(self, cmd, fake, factories):
        midpoint = pendulum.now(tz='utc') - pendulum.duration(days=2)

        start = fake.date_time_between(start_date="-5d", end_date=midpoint,)
        factories.TimeEntryFactory(start=start, stop=fake.date_time_between(start_date=start, end_date=midpoint,))
        start = fake.date_time_between(start_date="-5d", end_date=midpoint,)
        factories.TimeEntryFactory(start=start, stop=fake.date_time_between(start_date=start, end_date=midpoint,))
        start = fake.date_time_between(start_date="-5d", end_date=midpoint,)
        factories.TimeEntryFactory(start=start, stop=fake.date_time_between(start_date=start, end_date=midpoint,))

        start = fake.date_time_between(start_date=midpoint, end_date='now',)
        factories.TimeEntryFactory(start=start)
        start = fake.date_time_between(start_date=midpoint, end_date='now',)
        factories.TimeEntryFactory(start=start)
        start = fake.date_time_between(start_date=midpoint, end_date='now',)
        factories.TimeEntryFactory(start=start)
        start = fake.date_time_between(start_date=midpoint, end_date='now',)
        factories.TimeEntryFactory(start=start)

        result = cmd('ls')
        parsed = result.parse_list()
        assert len(parsed) == 7

        result = cmd('ls --start \'{}\''.format(midpoint.format('MMM D HH:mm:ss')))
        parsed = result.parse_list()
        assert len(parsed) == 4

        result = cmd('ls --stop \'{}\''.format(midpoint.format('MMM D HH:mm:ss')))
        parsed = result.parse_list()
        assert len(parsed) == 3

    def test_ls_filter(self, cmd, config, factories):
        project = factories.ProjectFactory()
        assert not TimeEntry.objects.filter(project=project, config=config)

        factories.TimeEntryFactory(project=project, tags={'a', 'b'})
        factories.TimeEntryFactory(project=project, tags={'a', })
        factories.TimeEntryFactory(project=project)

        result = cmd('ls --project {}'.format(project.id))
        parsed = result.parse_list()
        assert len(parsed) == 3

        result = cmd('ls --tags \'a,b\'')
        parsed = result.parse_list()
        assert len(parsed) == 1

        result = cmd('ls --tags \'a\'')
        parsed = result.parse_list()
        assert len(parsed) == 2

    def test_add_now(self, cmd, fake, config):
        result = cmd('add now 2m2s \'{}\''.format(fake.sentence()))
        assert result.obj.exit_code == 0
        entry = TimeEntry.objects.get(result.created_id(), config=config)  # type: TimeEntry
        assert (entry.stop - entry.start).seconds == 122

    def test_add_basic(self, cmd, fake, config):
        start = pendulum.instance(fake.past_datetime(start_date='-9d'))
        result = cmd('add \'{}\' 1h2m2s \'{}\''.format(start.format('MMM D YYYY HH:mm:ss'), fake.sentence()))
        assert result.obj.exit_code == 0

        entry = TimeEntry.objects.get(result.created_id(), config=config)  # type: TimeEntry
        assert entry.start == start
        assert (entry.stop - entry.start).seconds == 3722

    def test_add_tags(self, cmd, fake, config):
        start = pendulum.instance(fake.past_datetime(start_date='-9d'))
        end = start + pendulum.duration(hours=2)
        result = cmd('add \'{}\' \'{}\' \'{}\' --tags \'some tag,another tag\''.format(start.format('MMM D HH:mm:ss'),
                                                                                       end.format('MMM D HH:mm:ss'),
                                                                                       fake.sentence()))
        assert result.obj.exit_code == 0

        entry = TimeEntry.objects.get(result.created_id(), config=config)  # type: TimeEntry
        assert len(entry.tags) == 2
        assert 'some tag' in entry.tags
        assert 'another tag' in entry.tags

    def test_add_project(self, cmd, fake, config, factories):
        project = factories.ProjectFactory()
        start = pendulum.instance(fake.past_datetime(start_date='-9d'))
        end = start + pendulum.duration(hours=2)
        cmd('projects ls')
        result = cmd('add \'{}\' \'{}\' \'{}\' --project \'{}\''
                     .format(start.format('MMM D HH:mm:ss'), end.format('MMM D HH:mm:ss'), fake.sentence(), project.name))
        assert result.obj.exit_code == 0

        entry = TimeEntry.objects.get(result.created_id(), config=config)  # type: TimeEntry
        assert entry.project == project

        start = pendulum.instance(fake.past_datetime(start_date='-9d'))
        end = start + pendulum.duration(hours=2)
        result = cmd('add \'{}\' \'{}\' \'{}\' --project \'{}\''
                     .format(start.format('MMM D HH:mm:ss'), end.format('MMM D HH:mm:ss'), fake.sentence(), project.id))
        assert result.obj.exit_code == 0

        entry = TimeEntry.objects.get(result.created_id(), config=config)  # type: TimeEntry
        assert entry.project == project

    def test_rm(self, cmd, factories):
        obj = factories.TimeEntryFactory()
        result = cmd('rm {}'.format(obj.id))
        assert result.obj.exit_code == 0

        obj = factories.TimeEntryFactory()
        result = cmd('rm \'{}\''.format(obj.description))
        assert result.obj.exit_code == 0

    def test_start(self, cmd, fake, config, factories):
        project = factories.ProjectFactory()
        current = TimeEntry.objects.current(config=config)
        assert current is None

        descr = fake.sentence()
        result = cmd('start --tags \'a, b, c\' --project {} \'{}\''.format(project.id, descr))
        assert result.obj.exit_code == 0

        current = TimeEntry.objects.current(config=config)
        assert current is not None
        assert current.description == descr
        assert current.tags == {'a', 'b', 'c'}
        assert current.project == project

    def test_stop(self, cmd, fake, config):
        TimeEntry.start_and_save()

        result = cmd('stop')
        assert result.obj.exit_code == 0

        current = TimeEntry.objects.current(config=config)
        assert current is None

    def test_now(self, cmd, config, factories):
        project = factories.ProjectFactory()
        current = TimeEntry.start_and_save(project=project, config=config)

        result = cmd('now')
        assert result.obj.exit_code == 0
        parsed = result.parse_detail()
        assert str(project.id) in parsed['project']
        assert parsed['id'] == str(current.id)

        result = cmd('now --tags \'a,b,c\'')
        assert result.obj.exit_code == 0
        parsed = result.parse_detail()
        assert 'a' in parsed['tags']
        assert 'b' in parsed['tags']
        assert 'c' in parsed['tags']

        result = cmd('now --tags \'-b\'')
        assert result.obj.exit_code == 0
        parsed = result.parse_detail()
        assert 'b' not in parsed['tags']

    def test_continue(self, cmd, config, factories):
        some_entry = factories.TimeEntryFactory()

        start = pendulum.now('utc')
        stop = start + pendulum.duration(seconds=10)
        last_entry = factories.TimeEntryFactory(start=start, stop=stop)

        result = cmd('continue')
        assert result.obj.exit_code == 0
        continuing_entry = TimeEntry.objects.current(config=config)

        assert last_entry.description == continuing_entry.description
        assert last_entry.id != continuing_entry.id
        continuing_entry.stop_and_save()

        result = cmd('continue \'{}\''.format(some_entry.description))
        assert result.obj.exit_code == 0
        continuing_entry = TimeEntry.objects.current(config=config)
        assert continuing_entry.description == some_entry.description




