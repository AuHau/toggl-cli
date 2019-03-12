# Toggl CLI

[![PyPI version](https://badge.fury.io/py/togglCli.svg)](https://badge.fury.io/py/togglCli) 
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/togglCli.svg)](https://pypi.org/project/togglCli)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/togglCli.svg)](https://pypi.org/project/togglCli/) 
[![codecov](https://codecov.io/gh/AuHau/toggl-cli/branch/master/graph/badge.svg)](https://codecov.io/gh/AuHau/toggl-cli) 
[![Build Status](https://travis-ci.org/AuHau/toggl-cli.svg?branch=master)](https://travis-ci.org/AuHau/toggl-cli)
[![Codacy Badge](https://api.codacy.com/project/badge/Grade/869d787a75dd4e259b824fb8754d3388)](https://app.codacy.com/app/AuHau/toggl-cli?utm_source=github.com&utm_medium=referral&utm_content=AuHau/toggl-cli&utm_campaign=Badge_Grade_Dashboard)
[![Updates](https://pyup.io/repos/github/AuHau/toggl-cli/shield.svg)](https://pyup.io/repos/github/AuHau/toggl-cli/)

> Command line tool and set of Python wrapper classes for interacting with toggl's API

## Install

Easiest way to install this package is through PyPi:

```shell
$ pip install togglCli
```

## Usage

For full overview of Toggl CLI capabilities please see [full documentation](https://toggl.uhlir.dev).

### CLI tool

With first run of the command you will be asked several questions to bootstrap default config file 
(only UNIX-like system are supported; for Window's users there is created dummy config file, which you have to setup manually).

To get overview of all commands and options please use `--help` option. Check out also help pages of the subcommands!

Several examples of commands:

```shell
# Starts tracking new time entry
$ toggl start

# Displays/enable modifications of currently running time entry
$ toggl now

# Lists all projects
$ toggl projects ls
```

### API wrappers

Toggl CLI comes with set of Python's class wrappers which follow similar pattern like Django ORM. 

The wrappers depends on config object which if not provided, the default config file (eq. `~/.togglrc`) is used. 

Toggl CLI uses `pendulum` for datetime management, but it is compatible with Python's native datetime, so you can use that if you want to.

```python
from toggl import api, utils
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

Feel free to dive in, contributions are welcomed! [Open an issue](https://github.com/auhau/toggl-cli/issues/new) or submit PRs.

For PRs please see [contribution guideline](https://github.com/AuHau/toggl-cli/blob/master/CONTRIBUTING.md).

## License

[MIT ©  Adam Uhlir & D. Robert Adams](https://github.com/AuHau/toggl-cli/blob/master/LICENSE)