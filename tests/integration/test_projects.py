import pytest

from toggl.api import Project
from toggl import exceptions

from . import factories


class TestProjects:
    def test_ls(self, cmd, fake):
        result = cmd('projects add --name \'{}\''.format(fake.word()))
        assert result.obj.exit_code == 0

        result = cmd('projects ls')
        parsed = result.parse_list()

        assert len(parsed) == 1

    def test_add_basic(self, cmd, fake):
        name = fake.word()
        result = cmd('projects add --name \'{}\''.format(name))
        assert result.obj.exit_code == 0

        # Duplicates not allowed
        with pytest.raises(exceptions.TogglApiException):
            cmd('projects add --name \'{}\''.format(name))

    def test_add_full_non_premium(self, cmd, fake):
        client = factories.ClientFactory()

        result = cmd('projects add --name \'{}\' --client \'{}\''.format(fake.word(), client.id))
        assert result.obj.exit_code == 0
        assert Project.objects.get(result.created_id()).client == client

        result = cmd('projects add --name \'{}\' --client \'{}\''.format(fake.word(), client.name))
        assert result.obj.exit_code == 0
        assert Project.objects.get(result.created_id()).client == client

        result = cmd('projects add --name \'{}\' --private --color 2'.format(fake.word()))
        assert result.obj.exit_code == 0

        prj = Project.objects.get(result.created_id())  # type: Project
        assert prj.is_private is True
        assert prj.color == 2

        with pytest.raises(exceptions.TogglPremiumException):
            cmd('projects add --name \'{}\' --billable'.format(fake.word()))

    @pytest.mark.premium
    def test_add_full_premium(self, cmd, fake):
        result = cmd('projects add --name \'{}\' --billable --rate 10.10  --auto_estimates'.format(fake.word()))
        assert result.obj.exit_code == 0

    def test_get(self, cmd, fake):
        name = fake.word()
        client = factories.ClientFactory()
        project = factories.ProjectFactory(name=name, is_private=False, color=2, client=client)

        result = cmd('projects get \'{}\''.format(project.id))
        id_parsed = result.parse_detail()

        assert id_parsed['name'] == name
        assert id_parsed['billable'] == 'False'
        assert id_parsed['auto_estimates'] == 'False'
        assert id_parsed['active'] == 'True'
        assert id_parsed['is_private'] == 'False'
        assert id_parsed['color'] == '2'
        assert str(client.id) in id_parsed['client']

        result = cmd('projects get \'{}\''.format(name))
        name_parsed = result.parse_detail()

        assert name_parsed['name'] == name
        assert name_parsed['billable'] == 'False'
        assert name_parsed['auto_estimates'] == 'False'
        assert name_parsed['active'] == 'True'
        assert name_parsed['is_private'] == 'False'
        assert name_parsed['color'] == '2'
        assert str(client.id) in name_parsed['client']

    def test_update(self, cmd, fake):
        name = fake.name()
        project = factories.ProjectFactory(name=name, is_private=False, color=2)

        new_name = fake.name()
        new_client = factories.ClientFactory()
        result = cmd('projects update --name \'{}\' --client \'{}\' --private --color 1 \'{}\''.format(new_name, new_client.name, name))
        assert result.obj.exit_code == 0

        project_obj = Project.objects.get(project.id)
        assert project_obj.name == new_name
        assert project_obj.client == new_client
        assert project_obj.color == 1
        assert project_obj.is_private is True

    @pytest.mark.premium
    def test_update_premium(self, cmd, fake):
        name = fake.name()
        project = factories.ProjectFactory(name=name, is_private=False, color=2)

        result = cmd('projects updates --billable --rate 10.10  --auto_estimates \'{}\''.format(name))
        assert result.obj.exit_code == 0

        project_obj = Project.objects.get(project.id)
        assert project_obj.rate == 10.10
        assert project_obj.billable is True
        assert project_obj.auto_estimates is True

    def test_delete(self, cmd):
        project = factories.ProjectFactory()

        result = cmd('projects rm --yes \'{}\''.format(project.id))
        assert result.obj.exit_code == 0

        result = cmd('projects rm  --yes \'{}\''.format(project.id))
        assert result.obj.exit_code == 44

        project = factories.ProjectFactory()
        result = cmd('projects rm --yes  \'{}\''.format(project.name))
        assert result.obj.exit_code == 0
