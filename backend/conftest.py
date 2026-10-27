# conftest.py
# Pytest configuration for the RouteGuard AI backend test suite.
# This file at the backend/ root ensures pytest can discover and import
# app modules correctly when running:
#   pytest tests/test_module7.py -v
#   pytest tests/test_snapshot_service.py -v

import pytest


def pytest_configure(config):
    """Enable asyncio_mode=auto for all async tests."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )


# Tell pytest-asyncio to auto-detect async test functions
# without requiring @pytest.mark.asyncio on every function.
def pytest_collection_modifyitems(items):
    import inspect
    for item in items:
        if isinstance(item, pytest.Function) and inspect.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)
