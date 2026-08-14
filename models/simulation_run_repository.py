"""SQLite persistence for Meshing and Solver execution history."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


TASK_TYPES = {"meshing", "solver"}
RUN_STATUSES = {"running", "success", "failed", "stopped", "cancelled"}
DATABASE_VERSION = 1


class SimulationRunRepository:
    """Store simulation lifecycle records using short-lived connections."""

    def __init__(self, database_path: Path | str):
        self.database_path = Path(database_path)

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version < 1:
                self._create_initial_schema(connection)
            connection.execute(f"PRAGMA user_version = {DATABASE_VERSION}")

    def mark_abandoned_runs(self) -> int:
        """Close records left running after an application restart."""

        finished_at = _utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE simulation_runs
                SET status = 'failed',
                    finished_at = ?,
                    exit_code = -1,
                    message = ?
                WHERE status = 'running' AND finished_at IS NULL
                """,
                (
                    finished_at,
                    "Proses terputus karena aplikasi berhenti atau dijalankan ulang.",
                ),
            )
            return cursor.rowcount

    def create_run(self, task_type: str, is_resume: bool = False) -> int:
        _validate_value(task_type, TASK_TYPES, "task type")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO simulation_runs (
                    task_type,
                    started_at,
                    status,
                    message,
                    is_resume
                ) VALUES (?, ?, 'running', ?, ?)
                """,
                (
                    task_type,
                    _utc_now(),
                    "Proses sedang berjalan.",
                    int(is_resume),
                ),
            )
            return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        status: str,
        exit_code: int | None,
        message: str,
        log_excerpt: str = "",
    ) -> bool:
        _validate_value(status, RUN_STATUSES - {"running"}, "status")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE simulation_runs
                SET finished_at = ?,
                    status = ?,
                    exit_code = ?,
                    message = ?,
                    log_excerpt = ?
                WHERE id = ? AND status = 'running' AND finished_at IS NULL
                """,
                (
                    _utc_now(),
                    status,
                    exit_code,
                    _clean_text(message, 2000),
                    _clean_text(log_excerpt, 12000),
                    run_id,
                ),
            )
            return cursor.rowcount == 1

    def get_run(self, run_id: int) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM simulation_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_recent(self, limit: int = 10) -> list[dict]:
        safe_limit = max(1, min(int(limit), 100))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM simulation_runs
                ORDER BY started_at DESC, id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_started_since(self, started_at: str) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM simulation_runs
                WHERE started_at >= ?
                ORDER BY started_at ASC, id ASC
                """,
                (started_at,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_metrics(self) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, task_type, started_at, finished_at, status
                FROM simulation_runs
                ORDER BY id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _create_initial_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS simulation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL
                    CHECK (task_type IN ('meshing', 'solver')),
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL
                    CHECK (
                        status IN (
                            'running',
                            'success',
                            'failed',
                            'stopped',
                            'cancelled'
                        )
                    ),
                exit_code INTEGER,
                message TEXT NOT NULL DEFAULT '',
                log_excerpt TEXT NOT NULL DEFAULT '',
                is_resume INTEGER NOT NULL DEFAULT 0
                    CHECK (is_resume IN (0, 1))
            );

            CREATE INDEX IF NOT EXISTS idx_simulation_runs_started_at
                ON simulation_runs(started_at DESC);

            CREATE INDEX IF NOT EXISTS idx_simulation_runs_status
                ON simulation_runs(status);

            CREATE INDEX IF NOT EXISTS idx_simulation_runs_task_type
                ON simulation_runs(task_type);
            """
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_value(value: str, allowed: set[str], label: str) -> None:
    if value not in allowed:
        raise ValueError(f"Unsupported {label}: {value}")


def _clean_text(value: str, maximum_length: int) -> str:
    return (value or "").strip()[:maximum_length]
