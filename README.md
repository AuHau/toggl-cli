# tgl

An independent command-line client and Python library for Toggl Track.

> [!IMPORTANT]
> `tgl` is an unofficial project and is not affiliated with, endorsed by, or sponsored by Toggl. Toggl and Toggl Track are trademarks of Toggl OÜ.

> [!NOTE]
> This project is a fork of [AuHau/toggl-cli](https://github.com/AuHau/toggl-cli), maintained by Sebastian Kwon.

[![Tests](https://github.com/sekR4/tgl/actions/workflows/tests.yaml/badge.svg)](https://github.com/sekR4/tgl/actions/workflows/tests.yaml)

## Install

`tgl` is not yet published on PyPI. Install it straight from GitHub using [uv](https://docs.astral.sh/uv/):

```shell
$ uv tool install git+https://github.com/sekR4/tgl
```

Or run it without installing:

```shell
$ uvx --from git+https://github.com/sekR4/tgl tgl
```

## Usage

For a full overview of `tgl` capabilities, see the [documentation](docs/index.md).

### CLI tool

With first run of the command you will be asked several questions to bootstrap default config file
(only UNIX-like system are supported; for Window's users there is created dummy config file, which you have to setup manually).

To get overview of all commands and options please use `--help` option. Check out also help pages of the subcommands!

Several examples of commands:

```shell
# Starts tracking new time entry
$ tgl start

# Displays/enables modifications of the currently running time entry
$ tgl now

# Lists all projects
$ tgl projects ls
```

### API wrappers

`tgl` includes Python class wrappers that follow a pattern similar to Django's ORM.

The wrappers depend on a config object. When none is provided, the default config file (`~/.tglrc`, or `$XDG_CONFIG_HOME/.tglrc` if set) is used.

`tgl` uses `pendulum` for datetime management but also accepts Python's native datetime objects.

```python
from tgl import api, utils
import pendulum

new_entry = api.TimeEntry(description='Some new time entry', start=pendulum.now() - pendulum.duration(minutes=15), stop=pendulum.now())
new_entry.save()

list_of_all_entries = api.TimeEntry.objects.all()

current_time_entry = api.TimeEntry.objects.current()

# Custom config from existing file
config = utils.Config.factory('./some.config')

# Custom config without relying on any existing config file
config = utils.Config.factory(None)  # Without None it will load the default config file
config.api_token = 'your token'
config.timezone = 'utc'  # Custom timezone

project = api.Project.object.get(123, config=config)
project.name = 'Some new name'
project.save()
```

## Contributing

Contributions are welcome. [Open an issue](https://github.com/sekR4/tgl/issues/new), submit a pull request, or read the [contribution guidelines](CONTRIBUTING.md).

## License

[MIT © Sebastian Kwon, Adam Uhlir, and D. Robert Adams](LICENSE)
