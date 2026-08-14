"""Deterministic demo data seeder for the simulation history database."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from models.simulation_run_repository import SimulationRunRepository


@dataclass(frozen=True)
class SeedScenario:
    key: str
    task_type: str
    started_ago: timedelta
    duration: timedelta
    status: str
    exit_code: int
    message: str
    log_excerpt: str
    is_resume: bool = False


SCENARIOS = (
    SeedScenario(
        "demo-meshing-01",
        "meshing",
        timedelta(days=6, hours=8),
        timedelta(minutes=18),
        "success",
        0,
        "Meshing selesai dengan sukses.",
        "blockMesh completed.\nsnappyHexMesh completed.\ncheckMesh completed.",
    ),
    SeedScenario(
        "demo-solver-01",
        "solver",
        timedelta(days=6, hours=4),
        timedelta(hours=1, minutes=36),
        "success",
        0,
        "Solver selesai dan mencapai endTime.",
        "Courant Number mean: 0.04 max: 0.61\nEnd\nSolver finished successfully.",
    ),
    SeedScenario(
        "demo-meshing-02",
        "meshing",
        timedelta(days=5, hours=9),
        timedelta(minutes=7),
        "failed",
        2,
        "Meshing gagal pada tahap blockMesh: geometri boundary tidak valid.",
        "FOAM FATAL ERROR: Cannot find patchField entry for outletMilk.",
    ),
    SeedScenario(
        "demo-meshing-03",
        "meshing",
        timedelta(days=5, hours=6),
        timedelta(minutes=15),
        "success",
        0,
        "Meshing resume selesai dengan sukses setelah konfigurasi diperbaiki.",
        "Resuming meshing from step 2/6.\ncheckMesh completed.\nProcess completed successfully.",
        True,
    ),
    SeedScenario(
        "demo-solver-02",
        "solver",
        timedelta(days=4, hours=7),
        timedelta(minutes=34),
        "failed",
        1,
        "Solver gagal karena Courant number melewati batas dan solusi divergen.",
        "Courant Number mean: 0.91 max: 4.82\nFOAM FATAL ERROR: Floating point exception.",
    ),
    SeedScenario(
        "demo-meshing-04",
        "meshing",
        timedelta(days=3, hours=9),
        timedelta(minutes=21),
        "success",
        0,
        "Meshing selesai dengan sukses.",
        "snappyHexMesh completed.\nMesh OK.\ndecomposePar completed.",
    ),
    SeedScenario(
        "demo-solver-03",
        "solver",
        timedelta(days=3, hours=5),
        timedelta(minutes=47),
        "stopped",
        -15,
        "Solver dihentikan oleh pengguna untuk penyesuaian boundary condition.",
        "Stop requested.\nSolver stopped at latest writeTime.",
    ),
    SeedScenario(
        "demo-solver-04",
        "solver",
        timedelta(days=2, hours=8),
        timedelta(hours=2, minutes=10),
        "success",
        0,
        "Solver resume selesai dengan sukses.",
        "Resuming from latest checkpoint.\nEnd\nProcess completed successfully.",
        True,
    ),
    SeedScenario(
        "demo-meshing-05",
        "meshing",
        timedelta(days=2, hours=4),
        timedelta(minutes=5),
        "cancelled",
        -15,
        "Meshing dibatalkan oleh pengguna sebelum snappyHexMesh.",
        "Cancel requested.\nProcess cancelled.",
    ),
    SeedScenario(
        "demo-meshing-06",
        "meshing",
        timedelta(days=1, hours=9),
        timedelta(minutes=17),
        "success",
        0,
        "Meshing selesai dengan sukses dan mesh dinyatakan valid.",
        "checkMesh completed.\nMesh OK.\nProcess completed successfully.",
    ),
    SeedScenario(
        "demo-solver-05",
        "solver",
        timedelta(days=1, hours=5),
        timedelta(hours=1, minutes=52),
        "success",
        0,
        "Solver selesai dengan residual dalam batas aman.",
        "Final residual = 8.4e-07\nCourant Number mean: 0.03 max: 0.54\nEnd",
    ),
    SeedScenario(
        "demo-meshing-07",
        "meshing",
        timedelta(hours=6),
        timedelta(minutes=19),
        "success",
        0,
        "Meshing terbaru selesai dengan sukses.",
        "surfaceFeatureExtract completed.\nsnappyHexMesh completed.\nMesh OK.",
    ),
)


class DatabaseSeeder:
    def __init__(self, repository: SimulationRunRepository):
        self.repository = repository

    def seed(
        self,
        reset: bool = False,
        reference_time: datetime | None = None,
    ) -> dict:
        anchor = reference_time or datetime.now(timezone.utc)
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=timezone.utc)
        anchor = anchor.astimezone(timezone.utc).replace(microsecond=0)

        records = [self._build_record(scenario, anchor) for scenario in SCENARIOS]
        return self.repository.upsert_seed_runs(records, reset=reset)

    def remove(self) -> int:
        return self.repository.delete_seed_runs()

    @staticmethod
    def _build_record(scenario: SeedScenario, anchor: datetime) -> dict:
        started_at = anchor - scenario.started_ago
        finished_at = started_at + scenario.duration
        return {
            "seed_key": scenario.key,
            "task_type": scenario.task_type,
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": finished_at.isoformat(timespec="seconds"),
            "status": scenario.status,
            "exit_code": scenario.exit_code,
            "message": scenario.message,
            "log_excerpt": scenario.log_excerpt,
            "is_resume": scenario.is_resume,
        }

