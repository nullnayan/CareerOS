import pytest

def pytest_configure(config):
    config.addinivalue_line("markers", "corpus: mark test as part of the corpus evaluation")
