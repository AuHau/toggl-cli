

class TestClients:

    def test_ls(self, cmd):
        result = cmd('clients ls')
        parsed = result.parse_list()

        assert len(parsed) == 2
        assert parsed[1][0] == 'Testing Client'
