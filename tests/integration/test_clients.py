import pytest

from toggl.api import Client
from toggl import exceptions


class TestClients:

    def test_add(self, cmd, fake):
        name = fake.name()
        result = cmd('clients add --name \'{}\' --notes \'{}\''.format(name, fake.sentence()))
        assert result.obj.exit_code == 0

        # Duplicated names not allowed
        with pytest.raises(exceptions.TogglApiException):
            cmd('clients add --name \'{}\''.format(name))

        result = cmd('clients add --name \'{}\' --notes \'{}\''.format(fake.name(), fake.sentence()))
        assert result.obj.exit_code == 0

    def test_ls(self, cmd):
        result = cmd('clients ls')
        parsed = result.parse_list()

        assert len(parsed) == 2

    def test_get(self, cmd, fake):
        name = fake.name()
        note = fake.sentence()
        result = cmd('clients add --name \'{}\' --notes \'{}\''.format(name, note))
        assert result.obj.exit_code == 0

        result = cmd('clients get \'{}\''.format(result.created_id()))
        id_parsed = result.parse_detail()

        assert id_parsed['notes'] == note
        assert id_parsed['name'] == name

        result = cmd('clients get \'{}\''.format(name))
        name_parsed = result.parse_detail()

        assert name_parsed['id'] == id_parsed['id']
        assert name_parsed['notes'] == note
        assert name_parsed['name'] == name

    def test_update(self, cmd, fake):
        name = fake.name()
        note = fake.sentence()
        result = cmd('clients add --name \'{}\' --notes \'{}\''.format(name, note))
        assert result.obj.exit_code == 0
        created_id = result.created_id()

        assert Client.objects.get(created_id).name == name

        new_name = fake.name()
        new_note = fake.sentence()
        result = cmd('clients update --name \'{}\' --notes \'{}\' \'{}\''.format(new_name, new_note, name))
        assert result.obj.exit_code == 0

        client_obj = Client.objects.get(created_id)
        assert client_obj.name == new_name
        assert client_obj.notes == new_note

    def test_delete(self, cmd, fake):
        result = cmd('clients add --name \'{}\' --notes \'{}\''.format(fake.name(), fake.sentence()))
        assert result.obj.exit_code == 0
        created_id = result.created_id()

        result = cmd('clients rm --yes \'{}\''.format(created_id))
        assert result.obj.exit_code == 0

        result = cmd('clients rm  --yes \'{}\''.format(created_id))
        assert result.obj.exit_code == 44

        name = fake.name()
        result = cmd('clients add --name \'{}\' --notes \'{}\''.format(name, fake.sentence()))
        assert result.obj.exit_code == 0

        result = cmd('clients rm --yes  \'{}\''.format(name))
        assert result.obj.exit_code == 0
