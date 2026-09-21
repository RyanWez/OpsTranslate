import pytest
from app import config

@pytest.fixture(autouse=True)
def reset_test_config(monkeypatch):
    monkeypatch.setattr(config, "IGNORE_DAILY_CAPS", False)
    monkeypatch.setattr(config, "WITHHOLD_ON_LEAK", True)
    monkeypatch.setattr(config, "DATABASE_URL", "")
    monkeypatch.setattr(config, "REDIS_URL", "")
