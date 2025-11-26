"""Конфигурация pytest для тестов бота."""


def pytest_configure(config):
    """Регистрирует кастомные маркеры pytest."""
    config.addinivalue_line("markers", "e2e: marks tests as end-to-end (requires backend API)")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
