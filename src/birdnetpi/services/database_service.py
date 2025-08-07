import contextlib
import os
from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from birdnetpi.models.database_models import Base


class DatabaseService:
    """Provides an interface for database operations, including initialization."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        # Configure SQLite engine with SD card optimizations
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            # Optimize connection pool for SQLite
            pool_pre_ping=True,
            pool_recycle=3600,  # Recycle connections every hour
        )

        # Apply SD card optimizations on every connection
        @event.listens_for(self.engine, "connect")
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

            # Optimize locking for single-process access
            cursor.execute("PRAGMA locking_mode = EXCLUSIVE")

            # Faster query planning (less CPU overhead)
            cursor.execute("PRAGMA optimize")

            cursor.close()

        Base.metadata.create_all(self.engine)
        self.session_local = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        # Initialize performance optimizations
        self._apply_startup_optimizations()

    @contextlib.contextmanager
    def get_db(self) -> Generator[Session, Any, None]:
        """Provide a database session for dependency injection."""
        db = self.session_local()
        try:
            yield db
        finally:
            db.close()

    def _apply_startup_optimizations(self) -> None:
        """Apply one-time startup optimizations for SD card longevity."""
        with self.get_db() as session:
            try:
                # Analyze tables for optimal query planning
                session.execute(text("ANALYZE"))

                # Update table statistics for better query optimization
                session.execute(text("PRAGMA optimize"))

                session.commit()
            except SQLAlchemyError as e:
                session.rollback()
                print(f"Warning: Failed to apply startup optimizations: {e}")

    def checkpoint_wal(self, mode: str = "RESTART") -> None:
        """Manually checkpoint WAL file to reduce its size.

        Args:
            mode: Checkpoint mode - "PASSIVE", "FULL", "RESTART", or "TRUNCATE"
                 RESTART is recommended for SD card longevity as it truncates WAL
        """
        with self.get_db() as session:
            try:
                result = session.execute(text(f"PRAGMA wal_checkpoint({mode})"))
                checkpoint_result = result.fetchone()
                if checkpoint_result:
                    busy_count, log_pages, checkpointed = checkpoint_result
                    if busy_count == 0:
                        print(f"WAL checkpoint successful: {checkpointed}/{log_pages} pages")
                    else:
                        print(f"WAL checkpoint partially blocked: {busy_count} busy")
                session.commit()
            except SQLAlchemyError as e:
                print(f"Warning: WAL checkpoint failed: {e}")

    def vacuum_database(self) -> None:
        """Vacuum database to reclaim space and optimize storage.

        Note: This operation requires significant free space (2x database size)
        and should be used sparingly on SD cards due to write amplification.
        """
        with self.get_db() as session:
            try:
                # Vacuum requires direct connection access
                session.execute(text("VACUUM"))
                session.commit()
                print("Database vacuum completed successfully.")
            except SQLAlchemyError as e:
                session.rollback()
                print(f"Error vacuuming database: {e}")
                raise

    def get_database_stats(self) -> dict[str, Any]:
        """Get database statistics useful for monitoring SD card usage.

        Returns:
            Dictionary containing database size, page count, and WAL status
        """
        stats = {}

        # Get file sizes
        if os.path.exists(self.db_path):
            stats["main_db_size"] = os.path.getsize(self.db_path)

            wal_path = f"{self.db_path}-wal"
            stats["wal_size"] = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0

            shm_path = f"{self.db_path}-shm"
            stats["shm_size"] = os.path.getsize(shm_path) if os.path.exists(shm_path) else 0

            stats["total_size"] = stats["main_db_size"] + stats["wal_size"] + stats["shm_size"]

        # Get SQLite internal stats
        with self.get_db() as session:
            try:
                # Page information
                page_count_result = session.execute(text("PRAGMA page_count")).fetchone()
                stats["page_count"] = page_count_result[0] if page_count_result else 0

                page_size_result = session.execute(text("PRAGMA page_size")).fetchone()
                stats["page_size"] = page_size_result[0] if page_size_result else 4096

                # WAL information
                wal_checkpoint_result = session.execute(text("PRAGMA wal_checkpoint")).fetchone()
                if wal_checkpoint_result:
                    stats["wal_busy_count"] = wal_checkpoint_result[0]
                    stats["wal_log_pages"] = wal_checkpoint_result[1]
                    stats["wal_checkpointed_pages"] = wal_checkpoint_result[2]

                # Journal mode
                journal_mode_result = session.execute(text("PRAGMA journal_mode")).fetchone()
                stats["journal_mode"] = journal_mode_result[0] if journal_mode_result else "unknown"

            except SQLAlchemyError as e:
                print(f"Warning: Could not retrieve all database stats: {e}")

        return stats

    def clear_database(self) -> None:
        """Clear all data from the database tables."""
        db = self.session_local()
        try:
            for table in Base.metadata.sorted_tables:
                db.execute(table.delete())
            db.commit()
            print("Database cleared successfully.")
        except SQLAlchemyError as e:
            db.rollback()
            print(f"Error clearing database: {e}")
            raise
        finally:
            db.close()
