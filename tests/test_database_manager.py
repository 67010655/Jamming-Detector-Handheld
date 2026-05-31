import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database_manager


class FailingPragmaConnection:
    def __init__(self):
        self.execute_calls = 0
        self.closed = False

    def execute(self, _sql):
        self.execute_calls += 1
        if self.execute_calls == 2:
            raise RuntimeError("pragma setup failed")

    def close(self):
        self.closed = True


def test_get_connection_closes_when_pragma_setup_fails(monkeypatch):
    conn = FailingPragmaConnection()
    monkeypatch.setattr(database_manager.sqlite3, "connect", lambda _db_name: conn)

    with pytest.raises(RuntimeError, match="pragma setup failed"):
        database_manager._get_connection()

    assert conn.closed is True
