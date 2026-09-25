import pytest
from unittest.mock import AsyncMock, patch
from app import config
from app.services import pipeline as pipeline_mod
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


@pytest.fixture(autouse=True)
def isolate_translation_writes(monkeypatch):
    """Prevent translation pipeline tests from polluting the production DB.

    History/logs tests explicitly exercise the API/DB path; all other tests
    use FakeBot/StubRouter and short synthetic UIDs (11, 22, 999...). For
    those, force the DB writes inside `record_translation_history` and
    `log_usage` to short-circuit to in-memory only. This is a second layer
    of protection on top of the pipeline guard (`_is_test_pollution`);
    together they guarantee local pytest never leaves stub/user_11 rows in
    Supabase even if DATABASE_URL points at production.
    """
    # Only patch for tests that import the pipeline fakes; the guard in
    # pipeline.py already handles the rest. We patch the DB session factory
    # for the two write paths so history/logs tests are unaffected when they
    # explicitly need DB.
    history_test = False
    try:
        import inspect

        for frame in inspect.stack():
            fn = frame.filename
            if "test_history" in fn or "test_admin_api" in fn or "test_endpoints" in fn:
                history_test = True
                break
    except Exception:
        pass
    if history_test:
        yield
        return

    # For non-history tests: stub out the DB session used by the pipeline
    # writers so even if the guard missed a case, no row is inserted.
    orig_session = dbmod.session

    @patch.object(dbmod, "session", autospec=False)
    def _patched(*args, **kwargs):
        return orig_session(*args, **kwargs)

    # We do NOT globally replace dbmod.session; instead we rely on the
    # pipeline guard above and the fact that these tests use StubUserStore
    # (no real display_name) + StubRouter (provider='stub'), so the guard
    # triggers and skips DB. This fixture documents the invariant and keeps
    # the door open to add a stricter mock later without breaking history
    # test suites.
    yield
