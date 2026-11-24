import json
from contextlib import closing
from http.client import HTTPConnection
from threading import Thread

from portbridge.__main__ import make_server
from portbridge.catalog import public_url
from portbridge.export import export
from portbridge.lab import build_lab, filter_lab

from test_portbridge import CatalogFixture


class LabTest(CatalogFixture):
    def test_tasks_pin_public_sources_and_track_evidence_separately(self):
        payload = build_lab()
        tasks = {task["id"]: task for task in payload["tasks"]}
        self.assertEqual([task["priority"] for task in tasks.values()], list(range(1, 6)))
        combined = tasks["pb-9-continued-first-frame"]
        self.assertEqual((combined["status"], combined["evidence_stage"], combined["adoption"]),
                         ("needs_revision", "reviewed_cpu", "pending"))
        self.assertEqual([row["sha"][:8] for row in combined["revisions"]], ["88658f1b", "21dc3889"])
        self.assertEqual(tasks["pb-9-reforge-present"]["evidence_stage"], "reviewed_gpu")
        self.assertEqual(tasks["xcl-1100-fma"]["evidence_stage"], "author_gpu")
        for task in tasks.values():
            self.assertEqual(task["adoption"], "pending")
            self.assertTrue(task["steps"] and task["expected"] and task["report"])
            self.assertTrue(task["translations"]["ru"]["why"])
            for field in ("source_url", "procedure_url", "result_url", "evidence_url"):
                self.assertTrue(public_url(task[field]), field)
            for row in task["revisions"]:
                self.assertRegex(row["sha"], r"^[0-9a-f]{40}$")
                self.assertTrue(public_url(row["url"]))
                self.assertTrue(row["url"].endswith(row["sha"]))

    def test_hardware_and_status_filters_combine(self):
        payload = build_lab()
        amd = filter_lab(payload, equipment="amd", status="needs_run")
        self.assertEqual([task["id"] for task in amd["tasks"]],
                         ["pb-5-xcl-wave64", "pb-9-reforge-present", "xcl-1100-fma"])
        self.assertEqual(amd, build_lab(equipment="amd", status="needs_run"))
        self.assertEqual(len(payload["tasks"]), 5)
        self.assertEqual(len(build_lab(equipment="nvidia", status="needs_revision")["tasks"]), 1)
        self.assertEqual(build_lab(equipment="cpu", status="needs_run")["tasks"], [])
        with self.assertRaises(ValueError):
            build_lab(status="merged")

    def test_static_and_local_api_share_the_queue(self):
        directory = export(self.catalog, self.workspace / "lab-site")
        self.assertEqual(export(self.catalog, directory), directory)
        data = json.loads((directory / "data/lab.json").read_bytes())
        with make_server(self.catalog, 0) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with closing(HTTPConnection("127.0.0.1", server.server_port, timeout=5)) as connection:
                    def fetch(path, method="GET"):
                        connection.request(method, path)
                        response = connection.getresponse()
                        return response.status, json.loads(response.read())

                    self.assertEqual(fetch("/api/v1/lab"), (200, data))
                    self.assertEqual(fetch("/api/v1/lab?equipment=cpu&status=awaiting_review"),
                                     (200, filter_lab(data, equipment="cpu", status="awaiting_review")))
                    self.assertEqual(fetch("/api/v1")[1]["routes"]["lab"], "/api/v1/lab")
                    self.assertEqual(fetch("/api/v1/lab?equipment=unknown")[0], 400)
                    self.assertEqual(fetch("/api/v1/lab?status=needs_run&status=awaiting_review")[0], 400)
                    self.assertEqual(fetch("/api/v1/lab", method="POST")[0], 405)
            finally:
                server.shutdown()
                thread.join()
