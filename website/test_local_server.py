import json
import shutil
import tempfile
import threading
import unittest
from datetime import timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server import LocalStudyStore, StudyError, create_server, iso_timestamp, utc_now


class LocalStudyStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.site_root = Path(__file__).resolve().parent
        self.data_dir = Path(self.temporary_directory.name) / "local_data"
        self.store = LocalStudyStore(self.site_root, self.data_dir)

    def test_assignment_progress_restore_and_submission(self):
        assignment = self.store.assign("participant-alpha")
        self.assertTrue(assignment["success"])
        self.assertEqual(assignment["test_group"], "test_group1.json")

        verification = self.store.verify_participant("participant-alpha")
        self.assertTrue(verification["has_assigned_url"])
        self.assertFalse(verification["has_saved_progress"])

        progress = {
            "session_id": assignment["session_id"],
            "participant_id": "participant-alpha",
            "test_group": assignment["test_group"],
            "currentProblem": 3,
            "timing": {"testStartTime": iso_timestamp()},
        }
        self.store.save_progress(progress)
        self.assertTrue(
            self.store.check_saved_progress({"participant_id": "participant-alpha"})[
                "has_saved_progress"
            ]
        )

        restarted_store = LocalStudyStore(self.site_root, self.data_dir)
        restored = restarted_store.load_progress({"participant_id": "participant-alpha"})
        self.assertEqual(restored["progress_data"]["currentProblem"], 3)
        self.assertEqual(
            restored["progress_data"]["assignmentFingerprint"],
            assignment["assignment_fingerprint"],
        )

        submission = restarted_store.save_results(
            {
                "session_id": assignment["session_id"],
                "participant_id": "participant-alpha",
                "test_group": assignment["test_group"],
                "problemAnswers": {"problem_0": {"answer": [[1]]}},
                "accuracy": "100.00%",
                "correct_answer": 1,
                "total_questions": 1,
            }
        )
        self.assertTrue((self.data_dir / "results" / submission["filename"]).is_file())
        self.assertFalse(
            restarted_store.check_saved_progress({"participant_id": "participant-alpha"})[
                "has_saved_progress"
            ]
        )
        self.assertEqual(
            restarted_store.get_assignment(assignment["session_id"])["assignment"]["status"],
            "completed",
        )
        admin_rows = restarted_store.admin_assignments(1, 20)
        self.assertEqual(admin_rows["assignments"][0]["accuracy"], "100.00%")
        downloaded_result, _ = restarted_store.admin_result(assignment["session_id"])
        self.assertEqual(downloaded_result["participant_id"], "participant-alpha")
        exported_results, _ = restarted_store.admin_export()
        self.assertEqual(len(exported_results), 1)
        with self.assertRaisesRegex(StudyError, "already been submitted"):
            restarted_store.save_results(
                {
                    "session_id": assignment["session_id"],
                    "participant_id": "participant-alpha",
                }
            )

    def test_round_robin_assignment_and_reuse(self):
        first = self.store.assign("participant-one")
        second = self.store.assign("participant-two")
        repeated = self.store.assign("participant-one")
        self.assertEqual(first["test_group"], "test_group1.json")
        self.assertEqual(second["test_group"], "test_group2.json")
        self.assertEqual(repeated["session_id"], first["session_id"])
        self.assertTrue(repeated["reused"])

    def test_attention_failure_locks_assignment(self):
        assignment = self.store.assign("participant-attention")
        result = self.store.record_attention_failure(
            {
                "session_id": assignment["session_id"],
                "participant_id": "participant-attention",
                "failure_data": {"attempts": 2},
            }
        )
        self.assertTrue(result["locked"])
        current = self.store.get_assignment(assignment["session_id"])["assignment"]
        self.assertEqual(current["status"], "attention_check_failed")
        with self.assertRaisesRegex(StudyError, "locked"):
            self.store.save_progress(
                {
                    "session_id": assignment["session_id"],
                    "participant_id": "participant-attention",
                }
            )

    def test_120_hour_timeout_archives_progress(self):
        assignment = self.store.assign("participant-timeout")
        self.store.save_progress(
            {
                "session_id": assignment["session_id"],
                "participant_id": "participant-timeout",
            }
        )
        state = json.loads(self.store.state_path.read_text(encoding="utf-8"))
        state["assignments"][assignment["session_id"]]["assigned_at"] = iso_timestamp(
            utc_now() - timedelta(hours=121)
        )
        self.store._write_json(self.store.state_path, state)

        current = self.store.get_assignment(assignment["session_id"])["assignment"]
        self.assertEqual(current["status"], "timeout")
        self.assertFalse(
            self.store.check_saved_progress({"participant_id": "participant-timeout"})[
                "has_saved_progress"
            ]
        )
        self.assertEqual(len(list((self.data_dir / "progress_archive").glob("*.json"))), 1)


class LocalStudyHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        source_root = Path(__file__).resolve().parent
        self.site_root = Path(self.temporary_directory.name) / "website"
        self.site_root.mkdir()
        shutil.copy2(source_root / "index.html", self.site_root / "index.html")
        shutil.copy2(source_root / "test.html", self.site_root / "test.html")
        shutil.copytree(source_root / "test", self.site_root / "test")
        shutil.copytree(source_root / "admin", self.site_root / "admin")
        self.server = create_server(
            "127.0.0.1",
            0,
            self.site_root,
            self.site_root / "local_data",
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self._stop_server)

    def _stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary_directory.cleanup()

    def _json_request(self, path, payload=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        with urlopen(Request(self.base_url + path, data=data, headers=headers), timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_participant_facing_http_flow(self):
        with urlopen(self.base_url + "/", timeout=5) as response:
            homepage = response.read().decode("utf-8")
        self.assertIn("Informed Consent", homepage)
        with self.assertRaises(HTTPError) as blocked:
            urlopen(self.base_url + "/local_data/state.json", timeout=5)
        self.assertEqual(blocked.exception.code, 404)

        status, verification = self._json_request(
            "/api/verify_participant_id", {"participant_id": "http-participant"}
        )
        self.assertEqual(status, 200)
        self.assertFalse(verification["has_assigned_url"])

        _, assignment = self._json_request(
            "/api/assign_url", {"participant_id": "http-participant"}
        )
        session_id = assignment["session_id"]
        _, assignment_lookup = self._json_request(
            f"/api/get_assignment?session_id={session_id}"
        )
        self.assertEqual(assignment_lookup["assignment"]["test_group"], "test_group1.json")

        _, group = self._json_request(
            "/api/load_remote_json", {"url": "/test/test_group1.json"}
        )
        self.assertEqual(group["tutorials_loaded"], 2)
        self.assertEqual(group["problems_loaded"], 20)

        _, saved = self._json_request(
            "/api/save_progress",
            {
                "session_id": session_id,
                "participant_id": "http-participant",
                "test_group": "test_group1.json",
                "currentProblem": 4,
            },
        )
        self.assertTrue(saved["success"])
        _, loaded = self._json_request(
            "/api/load_progress", {"participant_id": "http-participant"}
        )
        self.assertEqual(loaded["progress_data"]["currentProblem"], 4)

        with urlopen(self.base_url + "/admin/", timeout=5) as response:
            admin_page = response.read().decode("utf-8")
        self.assertIn("ARCANA 本地实验管理", admin_page)

        _, stats = self._json_request("/api/admin/stats")
        self.assertEqual(stats["total_assigned"], 1)
        self.assertEqual(stats["saved_progress"], 1)
        _, assignments = self._json_request("/api/admin/assignments?page=1&per_page=20")
        self.assertTrue(assignments["assignments"][0]["has_saved_progress"])
        _, admin_progress = self._json_request(f"/api/admin/progress/{session_id}")
        self.assertEqual(admin_progress["currentProblem"], 4)

        _, submitted = self._json_request(
            "/api/save_results",
            {
                "session_id": session_id,
                "participant_id": "http-participant",
                "test_group": "test_group1.json",
                "accuracy": "50.00%",
                "correct_answer": 1,
                "total_questions": 2,
            },
        )
        self.assertTrue(submitted["success"])
        _, admin_result = self._json_request(f"/api/admin/download/{session_id}")
        self.assertEqual(admin_result["accuracy"], "50.00%")
        _, exported = self._json_request("/api/admin/export")
        self.assertEqual(len(exported), 1)

        with self.assertRaises(HTTPError) as disabled_admin_write:
            self._json_request("/api/admin/cleanup", {})
        self.assertEqual(disabled_admin_write.exception.code, 405)


class ServerConfigurationTests(unittest.TestCase):
    def test_data_directory_cannot_contain_the_website(self):
        site_root = Path(__file__).resolve().parent
        with self.assertRaisesRegex(RuntimeError, "cannot be the website root"):
            create_server("127.0.0.1", 0, site_root, site_root)

    def test_welcome_page_show_paths_preserve_flex_centering(self):
        html = (Path(__file__).resolve().parent / "test.html").read_text(
            encoding="utf-8-sig"
        )
        self.assertNotIn("getElementById('startPage').style.display = 'block'", html)
        self.assertEqual(
            html.count("getElementById('startPage').style.display = 'flex'"),
            11,
        )
        self.assertIn(".start-content {", html)
        self.assertIn("margin: 0 auto;", html)


if __name__ == "__main__":
    unittest.main()
