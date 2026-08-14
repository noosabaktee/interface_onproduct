import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from services import (
    CASE_FILE_MANAGER_KEY,
    GRAPH_SERVICE_KEY,
    PROCESSOR_SERVICE_KEY,
)
from services.processor_service import ProcessorService


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
                "DECOMPOSE_PAR_DICT": case_root / "system" / "decomposeParDict",
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_factory_registers_feature_controllers_and_services(self):
        self.assertIn(CASE_FILE_MANAGER_KEY, self.app.extensions)
        self.assertIn(GRAPH_SERVICE_KEY, self.app.extensions)
        self.assertIn(PROCESSOR_SERVICE_KEY, self.app.extensions)
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


if __name__ == "__main__":
    unittest.main()
