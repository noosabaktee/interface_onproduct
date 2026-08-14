"""Use-cases and dashboard presentation for simulation run history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from models.simulation_run_repository import SimulationRunRepository


STATUS_LABELS = {
    "success": "Success",
    "failed": "Failed",
    "running": "Running",
    "stopped": "Stopped",
    "cancelled": "Cancelled",
}
TASK_LABELS = {
    "meshing": "Meshing",
    "solver": "Solver",
}


class SimulationHistoryService:
    def __init__(
        self,
        repository: SimulationRunRepository,
        timezone_name: str = "Asia/Jakarta",
    ):
        self.repository = repository
        try:
            self.timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            fallback_offset = (
                timedelta(hours=7)
                if timezone_name == "Asia/Jakarta"
                else timedelta(0)
            )
            self.timezone = timezone(fallback_offset, timezone_name)

    def start_run(self, task_type: str, is_resume: bool = False) -> int:
        return self.repository.create_run(task_type, is_resume)

    def finish_run(
        self,
        run_id: int,
        status: str,
        exit_code: int | None,
        message: str,
        log_lines: list[str] | None = None,
    ) -> bool:
        excerpt = "\n".join((log_lines or [])[-80:])
        return self.repository.finish_run(
            run_id,
            status,
            exit_code,
            message,
            excerpt,
        )

    def dashboard_data(self, history_limit: int = 10) -> dict:
        now = datetime.now(timezone.utc)
        metric_rows = self.repository.list_metrics()
        recent_rows = self.repository.list_recent(history_limit)

        completed = [row for row in metric_rows if row["status"] != "running"]
        successful = sum(row["status"] == "success" for row in completed)
        compute_seconds = sum(
            self._duration_seconds(row, now)
            for row in metric_rows
        )
        status_counts = {
            status: sum(row["status"] == status for row in metric_rows)
            for status in STATUS_LABELS
        }

        return {
            "summary": {
                "total_runs": len(metric_rows),
                "compute_time": _format_compact_duration(compute_seconds),
                "success_rate": (
                    round((successful / len(completed)) * 100)
                    if completed
                    else 0
                ),
                "active_runs": status_counts["running"],
            },
            "activity": self._activity_chart(metric_rows, now),
            "status_breakdown": {
                "labels": [STATUS_LABELS[status] for status in STATUS_LABELS],
                "values": [status_counts[status] for status in STATUS_LABELS],
                "items": [
                    {
                        "key": status,
                        "label": STATUS_LABELS[status],
                        "count": status_counts[status],
                    }
                    for status in STATUS_LABELS
                ],
            },
            "recent_runs": [self._present_run(row, now) for row in recent_rows],
        }

    def _activity_chart(self, rows: list[dict], now: datetime) -> dict:
        local_today = now.astimezone(self.timezone).date()
        days = [local_today - timedelta(days=offset) for offset in range(6, -1, -1)]
        counts = {day: 0 for day in days}

        for row in rows:
            started_at = _parse_timestamp(row["started_at"])
            local_date = started_at.astimezone(self.timezone).date()
            if local_date in counts:
                counts[local_date] += 1

        return {
            "labels": [day.strftime("%d/%m") for day in days],
            "values": [counts[day] for day in days],
        }

    def _present_run(self, row: dict, now: datetime) -> dict:
        started_at = _parse_timestamp(row["started_at"])
        finished_at = (
            _parse_timestamp(row["finished_at"])
            if row.get("finished_at")
            else None
        )
        return {
            **row,
            "task_label": TASK_LABELS.get(row["task_type"], row["task_type"].title()),
            "status_label": STATUS_LABELS.get(row["status"], row["status"].title()),
            "started_label": self._format_timestamp(started_at),
            "finished_label": (
                self._format_timestamp(finished_at)
                if finished_at
                else "Sedang berjalan"
            ),
            "duration_label": _format_duration(
                (finished_at or now) - started_at
            ),
        }

    @staticmethod
    def _duration_seconds(row: dict, now: datetime) -> float:
        started_at = _parse_timestamp(row["started_at"])
        finished_at = (
            _parse_timestamp(row["finished_at"])
            if row.get("finished_at")
            else now
        )
        return max(0.0, (finished_at - started_at).total_seconds())

    def _format_timestamp(self, value: datetime) -> str:
        return value.astimezone(self.timezone).strftime("%d/%m/%Y %H:%M:%S")


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_compact_duration(seconds: float) -> str:
    total_minutes = max(0, int(seconds // 60))
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _format_duration(duration: timedelta) -> str:
    total_seconds = max(0, int(duration.total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}j {minutes}m {seconds}d"
    if minutes:
        return f"{minutes}m {seconds}d"
    return f"{seconds}d"
