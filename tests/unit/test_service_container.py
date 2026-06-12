"""
Tests for ServiceContainer initialization and shutdown.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from misaka.config import SettingKeys
from misaka.db.database import DatabaseBackend
from misaka.main import ServiceContainer


class TestServiceContainer:

    def test_initializes_all_services(self, db: DatabaseBackend) -> None:
        container = ServiceContainer(db)
        assert container.db is db
        assert container.permission_service is not None
        assert container.settings_service is not None
        assert container.session_service is not None
        assert container.message_service is not None
        assert container.router_config_service is not None
        assert container.task_service is not None
        assert container.mcp_service is not None
        assert container.claude_service is not None

    async def test_close_closes_database(self, db: DatabaseBackend) -> None:
        container = ServiceContainer(db)
        # Monkey-patch db.close to track calls
        original_close = db.close
        close_called = []
        def track_close():
            close_called.append(True)
            original_close()
        db.close = track_close

        await container.close()
        assert len(close_called) == 1

    async def test_close_handles_db_error(self, db: DatabaseBackend) -> None:
        container = ServiceContainer(db)
        original_close = db.close
        db.close = MagicMock(side_effect=RuntimeError("close failed"))
        try:
            await container.close()  # Should not raise
        finally:
            # Restore original close so conftest teardown works
            db.close = original_close

    async def test_close_aborts_streaming(self, db: DatabaseBackend) -> None:
        container = ServiceContainer(db)
        container.claude_service._is_streaming = True
        container.claude_service.abort = AsyncMock()
        container.mcp_service.stop_all = AsyncMock()

        await container.close()

    def test_services_share_db(self, db: DatabaseBackend) -> None:
        container = ServiceContainer(db)
        assert container.session_service._db is db
        assert container.message_service._db is db
        assert container.settings_service._db is db
        assert container.router_config_service._db is db
        assert container.task_service._db is db
        assert container.claude_service._db is db

    def test_claude_service_uses_permission_service(self, db: DatabaseBackend) -> None:
        container = ServiceContainer(db)
        assert container.claude_service._permission_service is container.permission_service

    def test_configure_remote_vector_backend_rebuilds_services(
        self,
        db: DatabaseBackend,
    ) -> None:
        container = ServiceContainer(db)
        old_orchestrator = container.rag_orchestrator

        changed = container.configure_vector_backend(
            "seekdb_remote",
            {
                "host": "seekdb.example.com",
                "port": 2881,
                "user": "root",
                "password": "secret",
                "database_name": "misaka_kb",
            },
        )

        assert changed is True
        assert db.get_setting(SettingKeys.VECTOR_BACKEND) == "seekdb_remote"
        assert db.get_seekdb_config()["host"] == "seekdb.example.com"
        assert container.rag_orchestrator is not old_orchestrator
        assert container.kb_service._orchestrator is container.rag_orchestrator
        assert container.document_service._orchestrator is container.rag_orchestrator
        assert container.rag_orchestrator._factory._backend == "seekdb"
        assert container.rag_orchestrator._factory._seekdb_mode == "seekdb_remote"
