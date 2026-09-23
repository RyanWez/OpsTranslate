import pytest
from app import config
from app.store import db as dbmod


@pytest.fixture(autouse=True)
def reset_test_config(monkeypatch):
    monkeypatch.setattr(config, "IGNORE_DAILY_CAPS", False)
    monkeypatch.setattr(config, "WITHHOLD_ON_LEAK", True)
    monkeypatch.setattr(config, "REDIS_URL", "")
    # NOTE: DATABASE_URL is deliberately NOT cleared here. Provider CRUD
    # tests are DB-only by design (Admin Panel is the source of truth, no
    # env/file fallback) and need the real DATABASE_URL from local .env.
    # Tests needing DB-less mode must monkeypatch DATABASE_URL="" themselves
    # AND reset dbmod's cached engine (dbmod._engine = None).
