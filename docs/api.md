# API wrapper classes

In addition to the command-line interface, `tgl` provides wrapper classes for the Toggl Track API.
The wrappers are available in the `tgl.api` package. There are these classes available:

* Client
* Workspace
* Project
* User
* WorkspaceUser
* ProjectUser
* TimeEntry
* Task
* Tag

There is currently no generated API reference. See the documented [model source](https://github.com/sekR4/tgl/blob/master/tgl/api/models.py) for details.

## Configuration

As described at [Configuration section](index.md#configuration) `tgl` heavily depends on configuration, which is also
true for the API wrappers.

You can specify the config object to be used for the API calls passing the object to TogglSet's methods and entities's constructor using
`config=<config object>` (examples bellow). If no config object is passed, the default config is parsed from config
file at `~/.tglrc`.

If you want to use some config object across whole application, you can replace the default config object using call
`utils.Config.set_default(<config_obj>)` (example bellow). It is recommended to put this step as part of bootstraping
of your application.


## Examples

The API wrapper classes follow similar design pattern like Django's ORM classes. Here are some examples of the API calls.

```python
from tgl import api, utils

# All clients from default config which is placed under ~/.tglrc
all_clients = api.Client.objects.all()
for client in all_clients:
    print(client.name)

specific_client = api.Client.objects.get(123)

project = api.Project(name='New project!')
project.client = specific_client
project.save() # Creating new instance does not automatically save the entity, you have to call save() to do that.

update_project = api.Project()


# Loads config from different place then ~/.tglrc
loaded_config = utils.Config.factory('/some/path/to/config')

new_task_with_different_config = api.Task(name='some name', config=loaded_config)
new_task_with_different_config.save()

# Creates empty config without any file loading, at least API token/User credentials needs to be set afterwards
empty_config = utils.Config.factory(None)
empty_config.api_token = 'users token'

# Lets update a Task
some_task = api.Task.objects.get(123, config=empty_config)

# Raises TogglNotAllowedException as tracked_seconds is read-only
some_task.tracked_seconds = 123

some_task.name = 'new task name'
some_task.save() # Again entity needs to be saved to propagate the changes to server

# Getting default config object
default_config = utils.Config.factory()

# Set new default config
utils.Config.set_default(empty_config)
assert utils.Config.factory() is empty_config  # ==> True

```




