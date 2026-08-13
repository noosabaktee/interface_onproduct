import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from werkzeug.datastructures import FileStorage

from app import app
from controllers import dashboard_controller
from models.case_file_manager import CaseFileError, CaseFileManager


class CaseFileManagerTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        base = Path(self.temporary_directory.name)
        self.case_root = base / "demoCase"
        self.state_root = base / "state"
        self.report_root = base / "report"
        self.graph_root = base / "grafik" / "output"
        (self.case_root / "0").mkdir(parents=True)
        (self.case_root / "system").mkdir()
        (self.case_root / "constant" / "triSurface").mkdir(parents=True)
        self.report_root.mkdir()
        self.graph_root.mkdir(parents=True)
        (self.case_root / "system" / "controlDict").write_text("application solver;\n", encoding="utf-8")
        (self.case_root / "constant" / "triSurface" / "dryer.stl").write_bytes(b"solid dryer\nendsolid\n")
        (self.case_root / "log.run").write_text("solver output\n", encoding="utf-8")
        (self.report_root / "summary.txt").write_text("report\n", encoding="utf-8")
        (self.graph_root / "residual.png").write_bytes(b"png-data")
        (self.graph_root.parent / "log_all").write_text("graph log\n", encoding="utf-8")
        self.manager = CaseFileManager(
            self.case_root,
            self.state_root,
            report_root=self.report_root,
            graph_root=self.graph_root,
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    @staticmethod
    def upload(name, content):
        return FileStorage(stream=io.BytesIO(content), filename=name)

    def test_recursive_listing_classifies_text_stl_and_logs(self):
        listing = self.manager.list_files()
        records = {record["path"]: record for record in listing["files"]}

        self.assertEqual(listing["stats"]["all"], 3)
        self.assertTrue(records["system/controlDict"]["editable"])
        self.assertFalse(records["constant/triSurface/dryer.stl"]["editable"])
        self.assertEqual(records["log.run"]["kind"], "log")

    def test_path_traversal_is_rejected(self):
        with self.assertRaises(CaseFileError):
            self.manager.resolve_path("../outside.txt", must_exist=False)

    def test_upload_clear_removes_new_file_and_restores_replacement(self):
        original = (self.case_root / "system" / "controlDict").read_bytes()
        result = self.manager.upload_files(
            [self.upload("notes.custom", b"hello"), self.upload("controlDict", b"changed\n")],
            target_folder="system",
            replace=True,
        )

        self.assertEqual(result["added"], 1)
        self.assertEqual(result["replaced"], 1)
        self.assertEqual((self.case_root / "system" / "controlDict").read_bytes(), b"changed\n")
        self.assertTrue((self.case_root / "system" / "notes.custom").exists())

        cleared = self.manager.clear("uploads")
        self.assertEqual(cleared["files"], 1)
        self.assertEqual(cleared["restored"], 1)
        self.assertEqual((self.case_root / "system" / "controlDict").read_bytes(), original)
        self.assertFalse((self.case_root / "system" / "notes.custom").exists())

    def test_text_edit_and_binary_rejection(self):
        self.manager.save_text("system/controlDict", "application changedSolver;\n")
        self.assertIn("changedSolver", self.manager.read_text("system/controlDict")["content"])

        with self.assertRaises(CaseFileError):
            self.manager.read_text("constant/triSurface/dryer.stl")

    def test_case_and_log_archives_include_expected_sources(self):
        case_archive, _ = self.manager.build_case_archive()
        log_archive, _ = self.manager.build_logs_archive()
        try:
            with zipfile.ZipFile(case_archive) as archive:
                names = set(archive.namelist())
            self.assertIn("demoCase/system/controlDict", names)
            self.assertIn("reports/summary.txt", names)
            self.assertIn("graphs/residual.png", names)

            with zipfile.ZipFile(log_archive) as archive:
                log_names = set(archive.namelist())
            self.assertIn("case_logs/log.run", log_names)
            self.assertIn("graph_logs/log_all", log_names)
        finally:
            case_archive.unlink(missing_ok=True)
            log_archive.unlink(missing_ok=True)

    def test_clear_results_preserves_core_inputs(self):
        (self.case_root / "1.5" / "U").parent.mkdir()
        (self.case_root / "1.5" / "U").write_text("result", encoding="utf-8")
        (self.case_root / "processor0").mkdir()
        (self.case_root / "processor0" / "p").write_text("result", encoding="utf-8")
        (self.case_root / "postProcessing").mkdir()
        (self.case_root / "constant" / "polyMesh").mkdir()
        (self.case_root / "constant" / "polyMesh" / "points").write_text("mesh", encoding="utf-8")

        self.manager.clear("results")

        self.assertFalse((self.case_root / "1.5").exists())
        self.assertFalse((self.case_root / "processor0").exists())
        self.assertFalse((self.case_root / "postProcessing").exists())
        self.assertFalse((self.case_root / "constant" / "polyMesh").exists())
        self.assertFalse((self.case_root / "log.run").exists())
        self.assertTrue((self.case_root / "0").is_dir())
        self.assertTrue((self.case_root / "system" / "controlDict").is_file())


class CaseFileRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        base = Path(self.temporary_directory.name)
        case_root = base / "case"
        case_root.mkdir()
        (case_root / "controlDict").write_text("application solver;\n", encoding="utf-8")
        self.manager = CaseFileManager(case_root, base / "state")
        self.original_manager = dashboard_controller.CASE_FILES
        dashboard_controller.CASE_FILES = self.manager
        app.config.update(TESTING=True)
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["authenticated"] = True
            session["username"] = "tester"
            session["csrf_token"] = "csrf-test"

    def tearDown(self):
        dashboard_controller.CASE_FILES = self.original_manager
        self.temporary_directory.cleanup()

    def test_manager_page_renders_and_write_routes_require_csrf(self):
        response = self.client.get("/case-files")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Case File Manager", response.data)
        self.assertIn(b"controlDict", response.data)
        self.assertIn(b'id="editCaseFileModal"', response.data)
        self.assertIn(b"data-edit-file", response.data)
        self.assertLess(response.data.index(b"</main>"), response.data.index(b'id="editCaseFileModal"'))

        response = self.client.post(
            "/case-files/upload",
            data={"target_folder": "", "files": (io.BytesIO(b"data"), "new.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)

    def test_upload_edit_download_and_delete_routes(self):
        response = self.client.post(
            "/case-files/upload",
            data={
                "csrf_token": "csrf-test",
                "target_folder": "custom",
                "files": (io.BytesIO(b"hello\n"), "notes.txt"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue((self.manager.case_root / "custom" / "notes.txt").exists())

        response = self.client.get("/case-files/text/custom/notes.txt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["content"], "hello\n")

        response = self.client.post(
            "/case-files/save/custom/notes.txt",
            data={"csrf_token": "csrf-test", "content": "updated\n"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual((self.manager.case_root / "custom" / "notes.txt").read_text(), "updated\n")

        response = self.client.get("/case-files/download/custom/notes.txt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"updated\n")
        response.close()

        response = self.client.post(
            "/case-files/delete/custom/notes.txt",
            data={"csrf_token": "csrf-test"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse((self.manager.case_root / "custom" / "notes.txt").exists())


if __name__ == "__main__":
    unittest.main()
