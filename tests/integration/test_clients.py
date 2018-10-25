

class TestClients:

    def test_ls(self, cmd):
        result = cmd('clients ls')

        assert result.stdout.count('\n') == 2
