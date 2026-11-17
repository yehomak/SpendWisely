"""Test setup: point the app at a throwaway DuckDB file BEFORE app.config is imported,
so tests never open the real ./db/spendwisely.duckdb."""
import os
import tempfile

_tmpdir = tempfile.mkdtemp(prefix="spendwisely-test-")
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.duckdb")
os.environ.setdefault("OTP_EMAIL_TO", "owner@example.test")
