"""Pytest configuration for bot tests."""


def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line("markers", "e2e: marks tests as end-to-end (requires backend API)")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
