"""SQLite persistence for Meshing and Solver execution history."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


TASK_TYPES = {"meshing", "solver"}
RUN_STATUSES = {"running", "success", "failed", "stopped", "cancelled"}
DATABASE_VERSION = 3


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
            if version > DATABASE_VERSION:
                raise RuntimeError(
                    f"Database version {version} lebih baru dari aplikasi."
                )
            if version < 1:
                self._create_initial_schema(connection)
                version = 1
            if version < 2:
                self._add_seed_support(connection)
                version = 2
            if version < 3:
                self._rebuild_seed_key_index(connection)
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

    def list_recent(
        self,
        limit: int = 10,
        task_type: str | None = None,
    ) -> list[dict]:
        safe_limit = max(1, min(int(limit), 100))
        if task_type is not None:
            _validate_value(task_type, TASK_TYPES, "task type")

        where_clause = "WHERE task_type = ?" if task_type else ""
        parameters = (task_type, safe_limit) if task_type else (safe_limit,)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM simulation_runs
                {where_clause}
                ORDER BY started_at DESC, id DESC
                LIMIT ?
                """,
                parameters,
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

    def upsert_seed_runs(
        self,
        records: list[dict],
        reset: bool = False,
    ) -> dict:
        """Insert deterministic demo records without duplicating real history."""

        created = 0
        updated = 0
        removed = 0
        with self._connect() as connection:
            if reset:
                removed = connection.execute(
                    "DELETE FROM simulation_runs WHERE is_seed = 1"
                ).rowcount

            for record in records:
                self._validate_seed_record(record)
                already_exists = connection.execute(
                    "SELECT 1 FROM simulation_runs WHERE seed_key = ?",
                    (record["seed_key"],),
                ).fetchone()
                connection.execute(
                    """
                    INSERT INTO simulation_runs (
                        task_type,
                        started_at,
                        finished_at,
                        status,
                        exit_code,
                        message,
                        log_excerpt,
                        is_resume,
                        is_seed,
                        seed_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    ON CONFLICT(seed_key) DO UPDATE SET
                        task_type = excluded.task_type,
                        started_at = excluded.started_at,
                        finished_at = excluded.finished_at,
                        status = excluded.status,
                        exit_code = excluded.exit_code,
                        message = excluded.message,
                        log_excerpt = excluded.log_excerpt,
                        is_resume = excluded.is_resume,
                        is_seed = 1
                    """,
                    (
                        record["task_type"],
                        record["started_at"],
                        record.get("finished_at"),
                        record["status"],
                        record.get("exit_code"),
                        _clean_text(record.get("message", ""), 2000),
                        _clean_text(record.get("log_excerpt", ""), 12000),
                        int(bool(record.get("is_resume"))),
                        record["seed_key"],
                    ),
                )
                if already_exists:
                    updated += 1
                else:
                    created += 1

        return {
            "created": created,
            "updated": updated,
            "removed": removed,
            "total": len(records),
        }

    def delete_seed_runs(self) -> int:
        with self._connect() as connection:
            return connection.execute(
                "DELETE FROM simulation_runs WHERE is_seed = 1"
            ).rowcount

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

    @staticmethod
    def _add_seed_support(connection: sqlite3.Connection) -> None:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(simulation_runs)")
        }
        if "is_seed" not in columns:
            connection.execute(
                """
                ALTER TABLE simulation_runs
                ADD COLUMN is_seed INTEGER NOT NULL DEFAULT 0
                    CHECK (is_seed IN (0, 1))
                """
            )
        if "seed_key" not in columns:
            connection.execute(
                "ALTER TABLE simulation_runs ADD COLUMN seed_key TEXT"
            )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_simulation_runs_seed_key
            ON simulation_runs(seed_key)
            """
        )

    @staticmethod
    def _rebuild_seed_key_index(connection: sqlite3.Connection) -> None:
        connection.execute("DROP INDEX IF EXISTS idx_simulation_runs_seed_key")
        connection.execute(
            """
            CREATE UNIQUE INDEX idx_simulation_runs_seed_key
            ON simulation_runs(seed_key)
            """
        )

    @staticmethod
    def _validate_seed_record(record: dict) -> None:
        _validate_value(record.get("task_type"), TASK_TYPES, "task type")
        _validate_value(record.get("status"), RUN_STATUSES, "status")
        if not record.get("seed_key"):
            raise ValueError("Seed record harus memiliki seed_key.")
        if not record.get("started_at"):
            raise ValueError("Seed record harus memiliki started_at.")
        if record["status"] == "running" and record.get("finished_at"):
            raise ValueError("Seed berstatus running tidak boleh memiliki finished_at.")
        if record["status"] != "running" and not record.get("finished_at"):
            raise ValueError("Seed yang sudah selesai harus memiliki finished_at.")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_value(value: str, allowed: set[str], label: str) -> None:
    if value not in allowed:
        raise ValueError(f"Unsupported {label}: {value}")


def _clean_text(value: str, maximum_length: int) -> str:
    return (value or "").strip()[:maximum_length]
