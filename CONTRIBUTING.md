# Contributing

Any contribution are welcomed.

For submitting PRs, they need to have test coverage. GitHub Actions runs the unit tests on every PR and they must pass. Integration tests run against the live Toggl API and are triggered manually via workflow dispatch.

## Developing

If you want to run the `tgl` CLI during development, set up the project with [uv](https://docs.astral.sh/uv/):

```shell
uv sync --extra test --extra docs
```

This creates a virtualenv at `.venv` with the package installed in editable mode plus all test and docs dependencies. Run the CLI via `uv run tgl ls`, or activate the venv (`source .venv/bin/activate`) and call `tgl` directly. If you have `tgl` installed globally (e.g. via `uv tool install tgl`), source your shell profile again to pick up the new symlinked version.

Also, if you find yourself with non-descriptive exception, you can set env. variable `export TGL_EXCEPTIONS=1` which
 will then give you the full stack trace.

## Tests

For running integration tests you need dummy account on Toggl, where **you don't have any important data** as the data
will be messed up with and eventually **deleted**! Get API token for this test account and set it as an environmental variable
`TOGGL_API_TOKEN`. Also figure out the Workspace ID of your account (`tgl workspaces ls`) and set it as `TOGGL_DEFAULT_WORKSPACE_ID`
environmental variable.

There are two sets of integration tests: normal and premium. To be able to run the premium set you have to have a paid
workspace; premium tests are skipped otherwise and are not run in CI.

Tests are written using `pytest` framework and are split into three categories (each having its own pytest mark):

* **unit** - unit tests testing mostly the framework around building the API wrappers
* **integration** - Integration tests which tests end to end coherence of API wrapper. Requires connectivity to Toggl API.
* **premium**: Subcategory of Integration tests that requires to have Premium/Paid workspace for the tests.

## Running tests

In order to run tests, install the test dependencies into the project's virtualenv with `uv sync --extra test`, then run the suite with `uv run pytest`.

By default unit and integration tests are run without the one testing premium functionality, as most probably you don't have access to Premium workspace for testing purposes.
If you want to run just specific category you can do so using for example`pytest -m unit` for only unit tests.
