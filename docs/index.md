# Welcome to Toggl CLI

Toggl CLI is a Python utility which consists of Command-Line-Interface and Python's API Wrappers to interact with Toggl API.
Each part is discussed in detail in corresponding section.   

Originally written by [D. Robert Adams](https://github.com/drobertadams), currently maintained by [Adam Uhlir](https://github.com/AuHau).

## Installation

To install Toggl CLI the easiest way is to use pip:

```shell
$ pip install togglCli
```

To use edge master you can also clone the repo and install it directly:
```shell
$ git clone https://github.com/AuHau/toggl-cli
$ cd toggl-cli
$ pip install .
```

Master branch should contain mostly working version, but it is not guaranteed.

## Configuration

Toggl CLI heavily depends on user's configuration. Upon first usage of the CLI the user is taken through bootstrap
process where he is asked questions regarding the desired settings and authentication credentials. The final configuration is
stored as configuration file at `~/.togglrc`.

If user select's to enter username & password, then the bootstrap process will convert it into API token which is then
stored.

!!! info "Bootstrap on Windows"
    Currently the bootstrap process is not available for Windows users. Upon the first usage of the CLI, Toggl CLI will
    create dummy config file and exit in order for user to configure it before next run. Use the bellow explanations
    to see available options. 

!!! danger "Plaintext credentials"
    By default the authentication credentials are stored in plain text in your configuration file! Be aware of that!

### Migrations

If you have used original version of Toggl CLI and have proper config file, upon the first run of the new version, Toggl
CLI will try to migrate it into new format.

### Possible settings

| Name | Type | Default | Description |
| --------------|---------- |---------- | ------- |
| `date_format` | string | `L` | Setting which specifies the format in which all the dates will be printed. For syntax see [Pendulum's doc](https://pendulum.eustace.io/docs/#tokens). |
| `datetime_format` | string | `LTS L` | Setting which specifies the format in which all the datetimes will be printed. For syntax see [Pendulum's doc](https://pendulum.eustace.io/docs/#tokens). |
| `time_format` | string | `LTS` | Setting which specifies the format in which all the times will be printed. For syntax see [Pendulum's doc](https://pendulum.eustace.io/docs/#tokens). |
| `day_first` | bool | `False` | Setting which specifies behaviour for dateutils.parse() behaviour. Whether to interpret the first value in an ambiguous 3-integer date (e.g. 01/05/09) as the day (True) or month (False). |
| `year_first` | bool | `False` | Setting which specifies behaviour for dateutils.parse() behaviour. Whether to interpret the first value in an ambiguous 3-integer date (e.g. 01/05/09) as the year. If True, the first number is taken to be the year, otherwise the last number is taken to be the year. |
| `file_logging` | bool | `False` | Turns on/off logging into file specified by file_logging_path variable. |
| `file_logging_path` | string | `''` | Specifies path where the logs will be stored. |
| `retries` | integer | `2` | In case when the HTTP API call is interrupted or the API rejects it because of throttling reasons, the tool will use exponential back-off with number of retries specified by this value. |
| `tz` | string | `None` | Timezone setting. If 'local' value is used then timezone from system's settings is used. If None, then timezone from Toggl's setting is used. |
| `theme` | string | `None` | Define theme to be used in the CLI. See [Themes section](cli.md#themes) for possible values.
| `default_wid` | integer | `None` | ID of default workspace to be used. If left empty then Toggl's configuration is used. |




