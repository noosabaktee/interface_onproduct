import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from werkzeug.datastructures import FileStorage

from app import app
from models.case_file_manager import CaseFileError, CaseFileManager
from services import CASE_FILE_MANAGER_KEY


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
        (self.case_root / "postProcessing").mkdir(exist_ok=True)
        self.report_root.mkdir()
        self.graph_root.mkdir(parents=True)
        (self.case_root / "system" / "controlDict").write_text("application solver;\n", encoding="utf-8")
        (self.case_root / "constant" / "triSurface" / "dryer.stl").write_bytes(b"solid dryer\nendsolid\n")
        (self.case_root / "log.run").write_text("solver output\n", encoding="utf-8")
        (self.case_root / "scripts").mkdir()
        (self.case_root / "scripts" / "Allrun").write_text("./solver\n", encoding="utf-8")
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
        def collect_folders(nodes):
            collected = set()
            for node in nodes:
                if node["is_folder"]:
                    collected.add(node["path"])
                    collected.update(collect_folders(node["children"]))
            return collected

        folders = collect_folders(listing["tree"])

        self.assertEqual(listing["stats"]["all"], 4)
        self.assertTrue(records["system/controlDict"]["editable"])
        self.assertFalse(records["constant/triSurface/dryer.stl"]["editable"])
        self.assertFalse(records["log.run"]["editable"])
        self.assertEqual(records["log.run"]["kind"], "log")
        self.assertEqual(folders, {"0", "constant", "constant/triSurface", "postProcessing", "system"})
        self.assertFalse(any(node.get("path") == "log.run" for node in listing["tree"]))

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

    def test_post_processing_is_visible_and_writable(self):
        listing = self.manager.list_files()
        root_paths = {node["path"] for node in listing["tree"] if node["is_folder"]}
        self.assertIn("postProcessing", root_paths)

        self.manager.upload_files(
            [self.upload("summary.dat", b"time value\n0 12\n")],
            target_folder="postProcessing",
        )
        self.manager.save_text("postProcessing/summary.dat", "time value\n0 14\n")

        self.assertEqual(
            (self.case_root / "postProcessing" / "summary.dat").read_text(encoding="utf-8"),
            "time value\n0 14\n",
        )

    def test_upload_allows_more_than_one_hundred_files(self):
        uploads = [
            self.upload(f"batch_{index:03}.txt", f"file {index}\n".encode("utf-8"))
            for index in range(125)
        ]

        result = self.manager.upload_files(uploads, target_folder="system")

        self.assertEqual(result["added"], 125)
        self.assertTrue((self.case_root / "system" / "batch_124.txt").exists())

    def test_folder_upload_requires_matching_allowed_root(self):
        result = self.manager.upload_files(
            [
                self.upload("constant/transportProperties", b"nu 1e-05;\n"),
                self.upload("constant/sub/model", b"model\n"),
            ],
            target_folder="constant",
            folder_upload=True,
        )

        self.assertEqual(result["added"], 2)
        self.assertTrue((self.case_root / "constant" / "transportProperties").exists())
        self.assertTrue((self.case_root / "constant" / "sub" / "model").exists())

        with self.assertRaises(CaseFileError):
            self.manager.upload_files(
                [self.upload("system/fvSchemes", b"schemes\n")],
                target_folder="constant",
                folder_upload=True,
            )

    def test_writes_are_restricted_to_core_case_folders(self):
        with self.assertRaises(CaseFileError):
            self.manager.save_text("scripts/Allrun", "./other\n")
        with self.assertRaises(CaseFileError):
            self.manager.replace_file("scripts/Allrun", self.upload("Allrun", b"./other\n"))
        with self.assertRaises(CaseFileError):
            self.manager.delete_file("scripts/Allrun")
        with self.assertRaises(CaseFileError):
            self.manager.upload_files([self.upload("notes.txt", b"notes\n")], target_folder="scripts")

        self.assertEqual((self.case_root / "scripts" / "Allrun").read_text(encoding="utf-8"), "./solver\n")

    def test_replace_file_keeps_target_name_and_can_restore_original(self):
        target = self.case_root / "system" / "controlDict"
        original = target.read_bytes()

        result = self.manager.replace_file(
            "system/controlDict",
            self.upload("replacement.cfg", b"application replacement;\n"),
        )

        self.assertEqual(result["path"], "system/controlDict")
        self.assertEqual(target.read_bytes(), b"application replacement;\n")
        self.assertFalse((target.parent / "replacement.cfg").exists())

        cleared = self.manager.clear("uploads")
        self.assertEqual(cleared["restored"], 1)
        self.assertEqual(target.read_bytes(), original)

    def test_replace_folder_syncs_target_and_can_restore_original_files(self):
        original = (self.case_root / "constant" / "triSurface" / "dryer.stl").read_bytes()

        result = self.manager.replace_folder(
            "constant/triSurface",
            [
                self.upload("freshGeometry/inlet.stl", b"solid inlet\nendsolid\n"),
                self.upload("freshGeometry/walls.stl", b"solid walls\nendsolid\n"),
            ],
        )

        self.assertEqual(result["path"], "constant/triSurface")
        self.assertEqual(result["added"], 2)
        self.assertEqual(result["removed"], 1)
        self.assertFalse((self.case_root / "constant" / "triSurface" / "dryer.stl").exists())
        self.assertTrue((self.case_root / "constant" / "triSurface" / "inlet.stl").exists())
        self.assertTrue((self.case_root / "constant" / "triSurface" / "walls.stl").exists())

        cleared = self.manager.clear("uploads")
        self.assertEqual(cleared["files"], 2)
        self.assertEqual(cleared["restored"], 1)
        self.assertEqual((self.case_root / "constant" / "triSurface" / "dryer.stl").read_bytes(), original)
        self.assertFalse((self.case_root / "constant" / "triSurface" / "inlet.stl").exists())
        self.assertFalse((self.case_root / "constant" / "triSurface" / "walls.stl").exists())

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
        (self.case_root / "postProcessing").mkdir(exist_ok=True)
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
        (case_root / "0").mkdir(parents=True)
        (case_root / "constant").mkdir()
        (case_root / "system").mkdir()
        (case_root / "postProcessing").mkdir()
        (case_root / "log.run").write_text("solver log;\n", encoding="utf-8")
        (case_root / "system" / "controlDict").write_text("application solver;\n", encoding="utf-8")
        self.manager = CaseFileManager(case_root, base / "state")
        self.original_manager = app.extensions[CASE_FILE_MANAGER_KEY]
        app.extensions[CASE_FILE_MANAGER_KEY] = self.manager
        app.config.update(TESTING=True)
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["authenticated"] = True
            session["username"] = "tester"
            session["csrf_token"] = "csrf-test"

    def tearDown(self):
        app.extensions[CASE_FILE_MANAGER_KEY] = self.original_manager
        self.temporary_directory.cleanup()

    def test_manager_page_renders_and_write_routes_require_csrf(self):
        response = self.client.get("/case-files")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Case File Manager", response.data)
        self.assertIn(b"controlDict", response.data)
        self.assertIn(b'data-case-explorer', response.data)
        self.assertIn(b'data-inline-content', response.data)
        self.assertIn(b'data-case-replace-trigger', response.data)
        self.assertIn(b'data-case-replacement-folder-input', response.data)
        self.assertIn(b'id="replaceCaseFileModal"', response.data)
        self.assertIn(b"data-replace-file", response.data)
        self.assertIn(b"postProcessing", response.data)

        response = self.client.post(
            "/case-files/upload",
            data={"target_folder": "", "files": (io.BytesIO(b"data"), "new.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)

    def test_legacy_upload_page_is_removed(self):
        response = self.client.get("/upload")
        self.assertEqual(response.status_code, 404)

        dashboard_response = self.client.get("/dashboard")
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertNotIn(b'href="/upload"', dashboard_response.data)
        self.assertIn(b'href="/case-files"', dashboard_response.data)

    def test_replace_route_overwrites_selected_path_without_renaming_it(self):
        response = self.client.post(
            "/case-files/replace/system/controlDict",
            data={
                "csrf_token": "csrf-test",
                "file": (io.BytesIO(b"application replaced;\n"), "local-name.txt"),
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            (self.manager.case_root / "system" / "controlDict").read_bytes(),
            b"application replaced;\n",
        )
        self.assertFalse((self.manager.case_root / "system" / "local-name.txt").exists())

    def test_replace_folder_route_syncs_selected_folder(self):
        response = self.client.post(
            "/case-files/replace-folder/system",
            data={
                "csrf_token": "csrf-test",
                "files": [
                    (io.BytesIO(b"application replaced;\n"), "fresh/controlDict"),
                    (io.BytesIO(b"new file\n"), "fresh/fvSchemes"),
                ],
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            (self.manager.case_root / "system" / "controlDict").read_bytes(),
            b"application replaced;\n",
        )
        self.assertEqual(
            (self.manager.case_root / "system" / "fvSchemes").read_bytes(),
            b"new file\n",
        )

    def test_upload_edit_download_and_delete_routes(self):
        response = self.client.post(
            "/case-files/upload",
            data={
                "csrf_token": "csrf-test",
                "target_folder": "system",
                "files": (io.BytesIO(b"hello\n"), "notes.txt"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue((self.manager.case_root / "system" / "notes.txt").exists())

        response = self.client.get("/case-files/text/system/notes.txt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["content"], "hello\n")

        response = self.client.post(
            "/case-files/save/system/notes.txt",
            data={"csrf_token": "csrf-test", "content": "updated\n"},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["message"], "Perubahan berhasil disimpan.")
        self.assertEqual((self.manager.case_root / "system" / "notes.txt").read_text(), "updated\n")

        response = self.client.get("/case-files/download/system/notes.txt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"updated\n")
        response.close()

        response = self.client.post(
            "/case-files/delete/system/notes.txt",
            data={"csrf_token": "csrf-test"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse((self.manager.case_root / "system" / "notes.txt").exists())

        response = self.client.post(
            "/case-files/upload",
            data={
                "csrf_token": "csrf-test",
                "target_folder": "postProcessing",
                "files": (io.BytesIO(b"time value\n0 1\n"), "summary.dat"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue((self.manager.case_root / "postProcessing" / "summary.dat").exists())

    def test_folder_upload_route_and_read_only_save_rejection(self):
        response = self.client.post(
            "/case-files/upload",
            data={
                "csrf_token": "csrf-test",
                "upload_mode": "folder",
                "target_folder": "constant",
                "files": (io.BytesIO(b"nu 1e-05;\n"), "constant/transportProperties"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue((self.manager.case_root / "constant" / "transportProperties").exists())

        response = self.client.post(
            "/case-files/upload",
            data={
                "csrf_token": "csrf-test",
                "upload_mode": "folder",
                "target_folder": "constant",
                "files": (io.BytesIO(b"schemes\n"), "system/fvSchemes"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse((self.manager.case_root / "system" / "fvSchemes").exists())

        response = self.client.post(
            "/case-files/save/log.run",
            data={"csrf_token": "csrf-test", "content": "changed\n"},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Perubahan hanya diizinkan", response.get_json()["error"])
        self.assertEqual((self.manager.case_root / "log.run").read_text(encoding="utf-8"), "solver log;\n")


if __name__ == "__main__":
    unittest.main()
