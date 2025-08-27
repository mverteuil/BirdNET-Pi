import contextlib
import logging
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,  # type: ignore[attr-defined]
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlmodel import SQLModel

logger = logging.getLogger(__name__)


class DatabaseService:
    """Provides an interface for database operations, including initialization."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Store database URL for later use
        self.db_url = f"sqlite+aiosqlite:///{self.db_path}"

        # Configure async SQLite engine with SD card optimizations
        self.async_engine = create_async_engine(
            self.db_url,
            # Optimize connection pool for SQLite
            pool_pre_ping=True,
            pool_recycle=3600,  # Recycle connections every hour
        )

        self.async_session_local = async_sessionmaker(
            autocommit=False, autoflush=False, bind=self.async_engine, class_=AsyncSession
        )

        # Create sync engine and sessionmaker for backward compatibility with utilities
        # Note: aiosqlite doesn't have a sync_engine attribute, so we create one separately
        from sqlalchemy import create_engine, event

        if self.db_url.startswith("sqlite"):
            # For SQLite, create a separate sync engine
            sync_url = self.db_url.replace("+aiosqlite", "")
            self.sync_engine = create_engine(sync_url, echo=False)
        else:
            # For other databases that support both sync and async
            self.sync_engine = getattr(self.async_engine, "sync_engine", None)
            if self.sync_engine is None:
                # Create a sync version of the URL
                sync_url = self.db_url.replace("postgresql+asyncpg", "postgresql")
                self.sync_engine = create_engine(sync_url, echo=False)

        # Apply SD card optimizations on every connection to the sync engine
        @event.listens_for(self.sync_engine, "connect")
        def set_sqlite_pragma(
            dbapi_connection: Any,  # noqa: ANN401
            connection_record: Any,  # noqa: ANN401
        ) -> None:
            """Configure SQLite pragmas optimized for SD card longevity."""
            cursor = dbapi_connection.cursor()

            # WAL mode for better concurrency and reduced write amplification
            cursor.execute("PRAGMA journal_mode = WAL")

            # Reduce fsync calls (trade durability for SD card longevity)
            cursor.execute("PRAGMA synchronous = NORMAL")

            # Use memory for temporary storage (avoid SD card writes)
            cursor.execute("PRAGMA temp_store = MEMORY")

            # Set reasonable checkpoint interval (64MB)
            cursor.execute("PRAGMA wal_autocheckpoint = 16384")  # 16384 pages * 4KB = 64MB

            # Optimize page cache for SBC memory constraints
            cursor.execute("PRAGMA cache_size = -32000")  # 32MB cache

            # Enable memory-mapped I/O for better read performance
            cursor.execute("PRAGMA mmap_size = 268435456")  # 256MB

            # Don't use exclusive locking since we have both sync and async engines
            # cursor.execute("PRAGMA locking_mode = EXCLUSIVE")

            # Faster query planning (less CPU overhead)
            cursor.execute("PRAGMA optimize")

            cursor.close()

        self.session_local = sessionmaker(autocommit=False, autoflush=False, bind=self.sync_engine)

        # Provide alias for backward compatibility
        self.engine = self.sync_engine

        # For CLI utilities, initialize tables synchronously in constructor
        SQLModel.metadata.create_all(self.sync_engine)

    async def initialize(self) -> None:
        """Initialize the database asynchronously."""
        # Create tables using sync engine within async context
        async with self.async_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        # Apply startup optimizations
        await self._apply_startup_optimizations()

    @contextlib.asynccontextmanager
    async def get_async_db(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide an async database session for dependency injection."""
        async with self.async_session_local() as session:
            yield session

    @contextlib.contextmanager
    def get_db(self) -> Generator[Session, Any, None]:
        """Provide a sync database session for CLI utilities and backward compatibility."""
        db = self.session_local()
        try:
            yield db
        finally:
            db.close()

    async def _apply_startup_optimizations(self) -> None:
        """Apply one-time startup optimizations for SD card longevity."""
        async with self.get_async_db() as session:
            try:
                # Analyze tables for optimal query planning
                await session.execute(text("ANALYZE"))

                # Update table statistics for better query optimization
                await session.execute(text("PRAGMA optimize"))

                await session.commit()
            except SQLAlchemyError as e:
                await session.rollback()
                logger.warning("Failed to apply startup optimizations: %s", e)

    async def checkpoint_wal(self, mode: str = "RESTART") -> None:
        """Manually checkpoint WAL file to reduce its size.

        Args:
            mode: Checkpoint mode - "PASSIVE", "FULL", "RESTART", or "TRUNCATE"
                 RESTART is recommended for SD card longevity as it truncates WAL
        """
        async with self.get_async_db() as session:
            try:
                result = await session.execute(text(f"PRAGMA wal_checkpoint({mode})"))
                checkpoint_result = result.fetchone()
                if checkpoint_result:
                    busy_count, log_pages, checkpointed = checkpoint_result
                    if busy_count == 0:
                        logger.info(
                            "WAL checkpoint successful: %d/%d pages", checkpointed, log_pages
                        )
                    else:
                        logger.warning("WAL checkpoint partially blocked: %d busy", busy_count)
                await session.commit()
            except SQLAlchemyError as e:
                logger.warning("WAL checkpoint failed: %s", e)

    async def vacuum_database(self) -> None:
        """Vacuum database to reclaim space and optimize storage.

        Note: This operation requires significant free space (2x database size)
        and should be used sparingly on SD cards due to write amplification.
        """
        async with self.get_async_db() as session:
            try:
                # Vacuum requires direct connection access
                await session.execute(text("VACUUM"))
                await session.commit()
                logger.info("Database vacuum completed successfully")
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error("Error vacuuming database: %s", e)
                raise

    async def get_database_stats(self) -> dict[str, Any]:
        """Get database statistics useful for monitoring SD card usage.

        Returns:
            Dictionary containing database size, page count, and WAL status
        """
        stats = {}

        # Get file sizes
        if self.db_path.exists():
            stats["main_db_size"] = self.db_path.stat().st_size

            wal_path = Path(f"{self.db_path}-wal")
            stats["wal_size"] = wal_path.stat().st_size if wal_path.exists() else 0

            shm_path = Path(f"{self.db_path}-shm")
            stats["shm_size"] = shm_path.stat().st_size if shm_path.exists() else 0

            stats["total_size"] = stats["main_db_size"] + stats["wal_size"] + stats["shm_size"]

        # Get SQLite internal stats
        async with self.get_async_db() as session:
            try:
                # Page information
                page_count_result = await session.execute(text("PRAGMA page_count"))
                page_count_row = page_count_result.fetchone()
                stats["page_count"] = page_count_row[0] if page_count_row else 0

                page_size_result = await session.execute(text("PRAGMA page_size"))
                page_size_row = page_size_result.fetchone()
                stats["page_size"] = page_size_row[0] if page_size_row else 4096

                # WAL information
                wal_checkpoint_result = await session.execute(text("PRAGMA wal_checkpoint"))
                wal_checkpoint_row = wal_checkpoint_result.fetchone()
                if wal_checkpoint_row:
                    stats["wal_busy_count"] = wal_checkpoint_row[0]
                    stats["wal_log_pages"] = wal_checkpoint_row[1]
                    stats["wal_checkpointed_pages"] = wal_checkpoint_row[2]

                # Journal mode
                journal_mode_result = await session.execute(text("PRAGMA journal_mode"))
                journal_mode_row = journal_mode_result.fetchone()
                stats["journal_mode"] = journal_mode_row[0] if journal_mode_row else "unknown"

            except SQLAlchemyError as e:
                logger.warning("Could not retrieve all database stats: %s", e)

        return stats

    async def clear_database(self) -> None:
        """Clear all data from the database tables."""
        async with self.get_async_db() as session:
            try:
                for table in SQLModel.metadata.sorted_tables:
                    await session.execute(table.delete())
                await session.commit()
                logger.info("Database cleared successfully")
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error("Error clearing database: %s", e)
                raise

    async def dispose(self) -> None:
        """Dispose of database engines to release resources.

        This should be called when the DatabaseService is no longer needed,
        especially in tests, to prevent file descriptor leaks.
        """
        # Dispose async engine if it exists
        if hasattr(self, "async_engine") and self.async_engine:
            await self.async_engine.dispose()
            logger.debug("Async database engine disposed")

        # Dispose sync engine if it exists and is different from async
        if hasattr(self, "sync_engine") and self.sync_engine:
            # Only dispose if it's not the same as async_engine.sync_engine
            if (
                not hasattr(self.async_engine, "sync_engine")
                or self.sync_engine != self.async_engine.sync_engine
            ):
                self.sync_engine.dispose()
                logger.debug("Sync database engine disposed")

    def dispose_sync(self) -> None:
        """Dispose database engines synchronously for non-async contexts.

        Only disposes the sync engine. For full cleanup, use dispose() in an async context.
        """
        if hasattr(self, "sync_engine") and self.sync_engine:
            self.sync_engine.dispose()
            logger.debug("Sync database engine disposed")
