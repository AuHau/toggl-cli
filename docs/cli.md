
### Environmental variables

It is possible to specify several options for the CLI commands through environmental variables. This can for example nicely
play out for directory specific settings (for example for projects) with [direnv](https://github.com/direnv/direnv) tool. 
Generally this mechanism is available for commands that create new entities. Values specified through this way have
priority over config values.

You can see which options can be specified in command's help where at the options help is
used `(ENV: <name of variable>)` syntax. Bellow you can see general overview of the variables:

 * **TOGGL_CONFIG** - Defines which config file should be used. Should be absolute path. By default ~/.togglrc is used.
 * **TOGGL_WORKSPACE** - Defines workspace to be used for the command, can be ID or Name of the Workspace.
 * **TOGGL_TASK** - Defines task to be used, can be ID or Name of the Task.
 * **TOGGL_PROJECT** - Defines project to be used, can be ID or Name of the Project.
 * **TOGGL_API_TOKEN** - Defines Toggl's account which will be used for the API calls.
 * **TOGGL_USERNAME** - Defines Toggl's account which will be used for the API calls.
 * **TOGGL_PASSWORD** - Defines Toggl's account which will be used for the API calls.