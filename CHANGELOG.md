# Changelog 

Earlier changes were not versioned. Therefore dates of change are used instead there.

For new releases see [Github Release page](https://github.com/AuHau/toggl-cli)

## [3.0.1](https://github.com/AuHau/toggl-cli/compare/v3.0.0...v3.0.1) (2024-06-16)


### Bug Fixes

* bootstrap timezone ([#325](https://github.com/AuHau/toggl-cli/issues/325)) ([cd81170](https://github.com/AuHau/toggl-cli/commit/cd81170fb4281c1ea7afb52736808bc5d99071d6))

## [3.0.0](https://github.com/AuHau/toggl-cli/compare/v2.4.4...v3.0.0) (2024-06-03)


### ⚠ BREAKING CHANGES

* migration to v9 api version ([#303](https://github.com/AuHau/toggl-cli/issues/303))

### Features

* add limit option to ls ([#314](https://github.com/AuHau/toggl-cli/issues/314)) ([c1d5ede](https://github.com/AuHau/toggl-cli/commit/c1d5edef5c8dbc94c5d55d11bcb863a6af29b237))
* migration to v9 api version ([#303](https://github.com/AuHau/toggl-cli/issues/303)) ([b9aff61](https://github.com/AuHau/toggl-cli/commit/b9aff6190217e886d166f6036262c82e2114a6a9))
* print description for toggl start ([#316](https://github.com/AuHau/toggl-cli/issues/316)) ([6693dfe](https://github.com/AuHau/toggl-cli/commit/6693dfe2af72fed7af481cabd0d7527307c2a841))
* respect XDG spec for configuration files ([#300](https://github.com/AuHau/toggl-cli/issues/300)) ([5086039](https://github.com/AuHau/toggl-cli/commit/5086039e6392523fad5ef3de2326eca7bf8b6832))


### Bug Fixes

* Set default color to toggl's default 1 ([#302](https://github.com/AuHau/toggl-cli/issues/302)) ([7ee7aa8](https://github.com/AuHau/toggl-cli/commit/7ee7aa8ace000a88035c00a0de7842dbbf83d293))

## [2.4.4](https://github.com/AuHau/toggl-cli/compare/v2.4.3...v2.4.4) (2023-02-14)


### Reverts

* pbr removal ([4829a62](https://github.com/AuHau/toggl-cli/commit/4829a629e11d77975a8cf1fe3c3638c1a73c0765))


### Miscellaneous Chores

* release trigger commit ([#287](https://github.com/AuHau/toggl-cli/issues/287)) ([6b4b8fa](https://github.com/AuHau/toggl-cli/commit/6b4b8fae50195d398b5a7241dc2bb0fa432dcdc6))


### Documentation

* cleanup badges ([#290](https://github.com/AuHau/toggl-cli/issues/290)) ([fe99cc0](https://github.com/AuHau/toggl-cli/commit/fe99cc0d1ca4801e8043a1e72a66d19a1fb53519))

## v2.2.0

Features:
 * Python 3.8 support
 * new `toggl sum` command that displays sums of time grouped by days
 * new `toggl goal` command that waits until you reach your defined goal for the day and the send notification
 * new theming support
 * `--today` flag for `ls` and `sum` command  

## v2.1.0

Features:
 * New Tag model with CLI commands
 * 'me' command to display current user's info
 
Fixes:
 * Correct retrieval of package's version 
 * Properly working Premium/Non-premium tests

## v2.0.2

Fixes for python_required and calculation of duration

## v2.0.1

Fix for required python version

## v2.0.0

Full rewrite of the tool by [AuHau](https://github.com/AuHau), which implements most of the toggl's API capabilities. 
Entities which is now possible to fully manage (eq. CRUD operations):
 *  Time entries
 *  Clients
 *  Projects
 *  Project users
 *  Tasks (only for premium workspaces)
 *  Workspaces
 *  Workspace users
 
Main new features of the tool:
 *  Possibility to use environment variables to specify some of the input parameters
 *  Possibility to specify different config to be used for the command's execution
 *  Django ORM's like API Classes

## v2.0.0.0b3

 * Fixing bootstrap failures
 * Dropping relative imports
 * Minor improvements

## v2.0.0.0b2

 * Adding support for Time entries Report API which enables fetching all time entries ( `api.TimeEntry.objects.all_from_reports()` / `toggl ls --use-reports`)
 * Adding support to register specific Config object as default one

## v2.0.0.0b1

First Beta release of full rewrite

## 15 Dec 2014 
Thanks to [FedericoVaga](https://github.com/FedericoVaga)
`.togglrc` now supports API token authentication. You will need to add
`api_token` to the `auth` section, and `prefer_token` to the `options` section.

## 11 Nov 2014
Major refactoring into a more MVC OO structure.

## 30 Oct 2014
Added a feature that starting, stopping, and continuing an
entry prints out the time it started or stopped. This requires a new option in
~/.togglrc: `time_format = %I:%M%p` is the default.  See
[strftime()](https://docs.python.org/2/library/datetime.html#strftime-and-strptime-behavior)
for more options.
