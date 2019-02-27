import pytest

from toggl.api import Tag
from toggl import exceptions


class TestTags:
    def test_ls(self, cmd, factories):
        factories.TagFactory.create_batch(2)
        result = cmd('tags ls')
        parsed = result.parse_list()

        assert len(parsed) == 2

    def test_add(self, cmd, fake):
        name = fake.name()
        result = cmd('tags add --name \'{}\''.format(name))
        assert result.obj.exit_code == 0

        # Duplicated names not allowed
        with pytest.raises(exceptions.TogglApiException):
            cmd('tags add --name \'{}\''.format(name))

    def test_update(self, cmd, fake, config):
        name = fake.name()
        result = cmd('tags add --name \'{}\''.format(name))
        assert result.obj.exit_code == 0
        created_id = result.created_id()

        assert Tag.objects.get(created_id, config=config).name == name

        new_name = fake.name()
        result = cmd('tags update --name \'{}\' \'{}\''.format(new_name, name))
        assert result.obj.exit_code == 0

        assert Tag.objects.get(created_id, config=config).name == new_name

    def test_delete(self, cmd, fake):
        result = cmd('tags add --name \'{}\''.format(fake.name()))
        assert result.obj.exit_code == 0
        created_id = result.created_id()

        result = cmd('tags rm --yes \'{}\''.format(created_id))
        assert result.obj.exit_code == 0

        result = cmd('tags rm  --yes \'{}\''.format(created_id))
        assert result.obj.exit_code == 44
