# Contributing

Any contribution are welcomed.

For submitting PRs, they need to have test coverage which pass the full run in Travis CI. 

## Developing

If you want to run the toggl CLI during development, I recommend you to use flow where you `pip install -e .`, which
symlinks locally the package and then you can simply use the CLI like `toggl ls`.

Also, if you find yourself with non-descriptive exception, you can set env. variable `export TOGGL_EXCEPTIONS=1` which
then will give you then the full stack trace. 

## Tests

For running integration tests you need dummy account on Toggl, where **you don't have any important data** as the data 
will be messed up with and eventually **deleted**! Get API token for this test account and set it as an environmental variable
`TOGGL_API_TOKEN`. Also figure out the Workspace ID of your account (`toggl workspace ls`) and set is as `TOGGL_WORKSPACE` 
environmental variable.

There are two sets of integration tests: normal and premium. To be able to run the premium set you have to have payed
workspace. As this is quiet unlikely you can leave the testing on Travis CI as it runs also the premium tests set.

Tests are written using `pytest` framework and are split into three categories (each having its own pytest mark):
 *  **unit** - unit tests testing mostly the framework around building the API wrappers
 *  **integration** - Integration tests which tests end to end coherence of API wrapper. Requires connectivity to Toggl API.
 *  **premium**: Subcategory of Integration tests that requires to have Premium/Paid workspace for the tests.

## Running tests

In order to run tests first you need to have required packages installed. You can install them using `pip install togglCli[test]`,
`python setup.py test` or `pip install -r test-requirements.txt`.

By default unit and integration tests are run without the one testing premium functionality, as most probably you don't have access to Premium workspace for testing purposes.
If you want to run just specific category you can do so using for example`pytest -m unit` for only unit tests.
