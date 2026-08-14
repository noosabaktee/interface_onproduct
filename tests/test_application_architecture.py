import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app import create_app
from models.simulation_run_repository import SimulationRunRepository
from models.terminal_runner import get_command_state, start_command
from services import (
    CASE_FILE_MANAGER_KEY,
    DATABASE_SEEDER_KEY,
    GRAPH_SERVICE_KEY,
    PROCESSOR_SERVICE_KEY,
    SIMULATION_HISTORY_SERVICE_KEY,
)
from services.database_seeder import DatabaseSeeder
from services.processor_service import ProcessorService
from services.simulation_history_service import SimulationHistoryService


class ApplicationFactoryTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        case_root = root / "case"
        case_root.mkdir()
        graph_root = root / "graphs"
        report_root = root / "reports"
        graph_root.mkdir()
        report_root.mkdir()

        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "LOGIN_USERNAME": "engineer",
                "LOGIN_PASSWORD": "safe-password",
                "PROJECT_ROOT": root,
                "CASE_ROOT": case_root,
                "GRAPH_OUTPUT_PATH": graph_root,
                "GRAPH_SCRIPT_PATH": root / "plot.py",
                "GRAPH_LOG_PATH": case_root / "log.run",
                "REPORT_ROOT": report_root,
                "CASE_FILE_STATE_ROOT": root / "state",
                "DATABASE_PATH": root / "simulation_history.sqlite3",
                "DECOMPOSE_PAR_DICT": case_root / "system" / "decomposeParDict",
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_factory_registers_feature_controllers_and_services(self):
        self.assertIn(CASE_FILE_MANAGER_KEY, self.app.extensions)
        self.assertIn(DATABASE_SEEDER_KEY, self.app.extensions)
        self.assertIn(GRAPH_SERVICE_KEY, self.app.extensions)
        self.assertIn(PROCESSOR_SERVICE_KEY, self.app.extensions)
        self.assertIn(SIMULATION_HISTORY_SERVICE_KEY, self.app.extensions)
        self.assertEqual(
            self.app.view_functions["dashboard.case_file_manager"].__module__,
            "controllers.case_file_controller",
        )
        self.assertEqual(
            self.app.view_functions["dashboard.update_graph"].__module__,
            "controllers.graph_controller",
        )

    def test_authentication_guard_and_safe_redirect(self):
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login?next=/dashboard", response.location)

        response = self.client.post(
            "/login?next=https://example.com",
            data={"username": "engineer", "password": "safe-password"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/dashboard"))

    def test_paraview_keeps_model_controls_without_stream_tracer(self):
        case = {
            "case_root_name": "case",
            "foam_exists": True,
            "foam_name": "case.foam",
            "foam_path": "case/case.foam",
            "foam_size": "1 KB",
            "internal_mesh": {
                "available": True,
                "label": "internalMesh",
                "name": "internalMesh",
                "faces_label": "1",
            },
            "latest_fields": ["U", "p"],
            "latest_time": "1",
            "processors": [],
            "time_directories": ["0", "1"],
        }
        with self.client.session_transaction() as session:
            session.update(
                authenticated=True,
                username="engineer",
                csrf_token="test-token",
            )

        with (
            patch(
                "controllers.paraview_controller.get_paraview_case",
                return_value=case,
            ),
            patch(
                "controllers.paraview_controller.latest_report",
                return_value=None,
            ),
        ):
            response = self.client.get("/paraview")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<h4>Model</h4>", response.data)
        self.assertIn(b"data-opacity-slider", response.data)
        self.assertIn(b"data-coloring-control", response.data)
        self.assertNotIn(b"Stream Tracer", response.data)
        self.assertNotIn(b"data-stream-", response.data)

    def test_dashboard_renders_live_history_from_sqlite(self):
        history = self.app.extensions[SIMULATION_HISTORY_SERVICE_KEY]
        run_id = history.start_run("solver")
        history.finish_run(
            run_id,
            "failed",
            2,
            "Solver gagal karena konfigurasi tidak valid.",
        )
        with self.client.session_transaction() as session:
            session.update(
                authenticated=True,
                username="engineer",
                csrf_token="test-token",
            )

        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"SQLite Live Data", response.data)
        self.assertIn(b"Riwayat Meshing &amp; Solver", response.data)
        self.assertIn(b"Solver gagal karena konfigurasi tidak valid.", response.data)
        self.assertNotIn(b"1,248", response.data)
        self.assertNotIn(b"452h", response.data)

    def test_seed_cli_populates_database(self):
        result = self.app.test_cli_runner().invoke(args=["seed-db"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("12 dibuat", result.output)
        history = self.app.extensions[SIMULATION_HISTORY_SERVICE_KEY]
        dashboard = history.dashboard_data(history_limit=20)
        self.assertEqual(dashboard["summary"]["total_runs"], 12)
        self.assertEqual(len(dashboard["recent_runs"]), 12)

    def test_dashboard_history_can_be_filtered_by_task_type(self):
        self.app.test_cli_runner().invoke(args=["seed-db"])
        with self.client.session_transaction() as session:
            session.update(
                authenticated=True,
                username="engineer",
                csrf_token="test-token",
            )

        meshing_response = self.client.get("/dashboard?history_type=meshing")
        solver_response = self.client.get("/dashboard?history_type=solver")
        invalid_response = self.client.get("/dashboard?history_type=invalid")

        self.assertEqual(meshing_response.status_code, 200)
        self.assertIn(b'data-history-task="meshing"', meshing_response.data)
        self.assertNotIn(b'data-history-task="solver"', meshing_response.data)
        self.assertIn(
            b'href="/dashboard?history_type=meshing" class="active"',
            b" ".join(meshing_response.data.split()),
        )

        self.assertEqual(solver_response.status_code, 200)
        self.assertIn(b'data-history-task="solver"', solver_response.data)
        self.assertNotIn(b'data-history-task="meshing"', solver_response.data)

        self.assertEqual(invalid_response.status_code, 200)
        self.assertIn(b'data-history-task="meshing"', invalid_response.data)
        self.assertIn(b'data-history-task="solver"', invalid_response.data)


class ProcessorServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temporary_directory.name) / "decomposeParDict"
        self.config_path.write_text(
            "numberOfSubdomains 4;\n"
            "method scotch;\n"
            "scotchCoeffs\n"
            "{\n"
            "    processorWeight (1 1 1 1); //4\n"
            "}\n",
            encoding="utf-8",
        )
        self.service = ProcessorService(self.config_path, maximum_count=32)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_load_normalize_and_save(self):
        self.assertEqual(self.service.load(), 4)
        self.assertEqual(self.service.normalize(100), 32)

        saved_count = self.service.save("8")
        updated = self.config_path.read_text(encoding="utf-8")

        self.assertEqual(saved_count, 8)
        self.assertIn("numberOfSubdomains 8;", updated)
        self.assertIn("processorWeight (1 1 1 1 1 1 1 1); //8", updated)


class SimulationHistoryServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "history.sqlite3"
        self.repository = SimulationRunRepository(self.database_path)
        self.repository.initialize()
        self.service = SimulationHistoryService(self.repository, "Asia/Jakarta")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_run_lifecycle_and_dashboard_metrics_use_database(self):
        success_id = self.service.start_run("meshing")
        self.service.finish_run(
            success_id,
            "success",
            0,
            "Meshing selesai dengan sukses.",
            ["Meshing finished successfully."],
        )
        failed_id = self.service.start_run("solver")
        self.service.finish_run(
            failed_id,
            "failed",
            127,
            "Solver gagal: executable tidak ditemukan.",
            ["solver: command not found"],
        )
        running_id = self.service.start_run("meshing", is_resume=True)

        dashboard = self.service.dashboard_data()

        self.assertEqual(dashboard["summary"]["total_runs"], 3)
        self.assertEqual(dashboard["summary"]["active_runs"], 1)
        self.assertEqual(dashboard["summary"]["success_rate"], 50)
        self.assertEqual(
            dashboard["status_breakdown"]["values"],
            [1, 1, 1, 0, 0],
        )
        self.assertEqual(dashboard["recent_runs"][0]["id"], running_id)
        self.assertEqual(dashboard["recent_runs"][1]["status"], "failed")
        self.assertIn("executable", dashboard["recent_runs"][1]["message"])

        solver_history = self.service.dashboard_data(task_filter="solver")
        self.assertEqual(solver_history["history_filter"], "solver")
        self.assertEqual(len(solver_history["recent_runs"]), 1)
        self.assertTrue(
            all(run["task_type"] == "solver" for run in solver_history["recent_runs"])
        )
        self.assertEqual(solver_history["summary"]["total_runs"], 3)

    def test_abandoned_running_process_is_marked_failed(self):
        run_id = self.service.start_run("solver")

        changed = self.repository.mark_abandoned_runs()
        run = self.repository.get_run(run_id)

        self.assertEqual(changed, 1)
        self.assertEqual(run["status"], "failed")
        self.assertIsNotNone(run["finished_at"])
        self.assertIn("terputus", run["message"])

    def test_terminal_runner_persists_failed_meshing_reason(self):
        class FailedProcess:
            pid = 12345
            stdout = ["Synthetic fatal meshing error\n"]

            @staticmethod
            def poll():
                return 9

            @staticmethod
            def wait():
                return 9

        synthetic_steps = [("Synthetic step", "synthetic-command", 100)]
        with (
            patch("models.terminal_runner.MESHING_STEPS", synthetic_steps),
            patch("models.terminal_runner.subprocess.Popen", return_value=FailedProcess()),
            patch(
                "models.terminal_runner.CASE_ROOT",
                Path(self.temporary_directory.name),
            ),
        ):
            start_command("meshing", self.service)
            deadline = time.monotonic() + 3
            while True:
                state = get_command_state("meshing")
                latest_run = self.repository.list_recent(1)[0]
                if not state["running"] and latest_run["status"] != "running":
                    break
                if time.monotonic() >= deadline:
                    self.fail("Meshing test thread tidak selesai tepat waktu.")
                time.sleep(0.01)

        run = self.repository.list_recent(1)[0]
        self.assertEqual(run["task_type"], "meshing")
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["exit_code"], 9)
        self.assertIn("Synthetic step", run["message"])
        self.assertIn("fatal meshing error", run["log_excerpt"])

    def test_seeder_is_idempotent_and_preserves_real_history(self):
        seeder = DatabaseSeeder(self.repository)
        reference_time = datetime(2026, 8, 14, 5, 0, tzinfo=timezone.utc)

        first = seeder.seed(reference_time=reference_time)
        second = seeder.seed(reference_time=reference_time)

        self.assertEqual(first, {
            "created": 12,
            "updated": 0,
            "removed": 0,
            "total": 12,
        })
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["updated"], 12)
        self.assertEqual(len(self.repository.list_metrics()), 12)

        real_run_id = self.service.start_run("solver")
        self.service.finish_run(real_run_id, "success", 0, "History asli.")
        reset = seeder.seed(reset=True, reference_time=reference_time)

        self.assertEqual(reset["removed"], 12)
        self.assertEqual(reset["created"], 12)
        self.assertEqual(len(self.repository.list_metrics()), 13)
        self.assertEqual(seeder.remove(), 12)
        self.assertEqual(len(self.repository.list_metrics()), 1)
        self.assertEqual(self.repository.get_run(real_run_id)["message"], "History asli.")

    def test_schema_v2_partial_index_is_migrated_before_seeding(self):
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute("DROP INDEX idx_simulation_runs_seed_key")
            connection.execute(
                """
                CREATE UNIQUE INDEX idx_simulation_runs_seed_key
                ON simulation_runs(seed_key)
                WHERE seed_key IS NOT NULL
                """
            )
            connection.execute("PRAGMA user_version = 2")
            connection.commit()

        self.repository.initialize()
        result = DatabaseSeeder(self.repository).seed(
            reference_time=datetime(2026, 8, 14, 5, 0, tzinfo=timezone.utc)
        )

        with closing(sqlite3.connect(self.database_path)) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            index_sql = connection.execute(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type = 'index' AND name = 'idx_simulation_runs_seed_key'
                """
            ).fetchone()[0]

        self.assertEqual(version, 3)
        self.assertEqual(result["created"], 12)
        self.assertNotIn("WHERE", index_sql.upper())


if __name__ == "__main__":
    unittest.main()
