import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        if item.fspath is None:
            continue

        if 'integration' in str(item.fspath):
            item.add_marker(pytest.mark.integration)

        if 'unit' in str(item.fspath):
            item.add_marker(pytest.mark.unit)
