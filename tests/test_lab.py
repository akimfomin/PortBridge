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
        self.assertEqual([task["priority"] for task in tasks.values()], list(range(1, 13)))
        combined = tasks["pb-9-continued-first-frame"]
        self.assertEqual((combined["status"], combined["evidence_stage"], combined["adoption"]),
                         ("awaiting_review", "reviewed_gpu", "pending"))
        self.assertEqual([row["sha"][:8] for row in combined["revisions"]], ["88658f1b", "21dc3889", "b8572d92"])
        presenter = tasks["pb-9-reforge-present"]
        self.assertEqual((presenter["status"], presenter["evidence_stage"]), ("blocked", "reviewed_gpu"))
        self.assertEqual(presenter["result_url"], "https://github.com/akimfomin/PortBridge/issues/9")
        fma = tasks["xcl-1100-fma"]
        self.assertEqual((fma["status"], fma["evidence_stage"], fma["adoption"]),
                         ("awaiting_review", "reviewed_gpu", "pending"))
        self.assertEqual(fma["revisions"][0]["sha"], "1b3fbc4bc8c3088e69d78f85a2e73f1cccf4df51")
        self.assertEqual(fma["evidence_url"], "https://github.com/xcl-dev/xcl/pull/1100#issuecomment-7144197194")
        self.assertIn("PastiiJay", fma["evidence"])
        self.assertTrue(any("gpu_wave32_program_in_wave64_hardware" in step for step in fma["steps"]))
        xcl = next(solution for solution in self.catalog.problem("PB-0006")["solutions"] if solution["project"] == "xcl")
        report = next(evidence for evidence in xcl["evidence"] if evidence["url"] == fma["evidence_url"])
        self.assertEqual((report["kind"], report["revision"]), ("independent", fma["revisions"][0]["sha"]))
        native = tasks["anyxboxx-133-native-carry"]
        self.assertEqual((native["status"], native["evidence_stage"]), ("awaiting_review", "reviewed_gpu"))
        self.assertEqual(native["revisions"][0]["sha"], "9736508b0d201c641b119d2e4a18fb72f28bdde4")
        self.assertEqual(native["revisions"][1]["sha"], "9923c3bba74f4a7f3249e0c820f2e6821327c1f4")
        self.assertEqual(native["evidence_url"], "https://github.com/akimfomin/PortBridge/issues/19#issuecomment-7136020663")
        self.assertEqual(native["result_url"], "https://github.com/LooperSalty/AnyXboxX/pull/133#issuecomment-7136721736")
        native_fma = tasks["anyxboxx-133-native-fma"]
        self.assertEqual(native_fma["status"], "needs_run")
        self.assertEqual(native_fma["result_url"], "https://github.com/akimfomin/PortBridge/issues/58")
        self.assertEqual(native_fma["report_cases"], ["positive-down", "positive-up", "negative", "exact-tie"])
        addition = tasks["scarlett-commons-continued-add-basic"]
        self.assertEqual((addition["equipment"], addition["status"], addition["evidence_stage"]),
                         (["cpu"], "needs_run", "author_cpu"))
        self.assertEqual([row["sha"] for row in addition["revisions"]], [
            "5496f79f93c41f1134ce4c9e1d2674aa00c6bb55",
            "ba9549c254647b9f6ef3b4e47684e69a668b9ec1",
        ])
        self.assertEqual(addition["result_url"], "https://github.com/scarlett-commons/scarlett-commons/issues/32")
        gather = tasks["anyxboxx-147-native-wave64-gather"]
        self.assertEqual((gather["equipment"], gather["status"], gather["evidence_stage"]),
                         (["amd"], "needs_run", "assembled_offline"))
        self.assertEqual(gather["revisions"][0]["sha"], "28524547b9f0751581257279a329b8cae2f1dc1e")
        self.assertEqual(gather["result_url"], "https://github.com/LooperSalty/AnyXboxX/pull/147")
        handoff = tasks["framelab-12-vulkan-handoff"]
        self.assertEqual((handoff["equipment"], handoff["status"], handoff["evidence_stage"]),
                         (["amd"], "needs_run", "reviewed_gpu"))
        head = "82f069e82197e61b97f60bbcbcb7a3af7d3f8e77"
        repository = "https://github.com/5headsmartbtw/leonida-framelab"
        self.assertEqual(handoff["revisions"][0]["sha"], head)
        self.assertEqual(handoff["procedure_url"], f"{repository}/blob/{head}/tests/vulkan-handoff/README.md")
        self.assertEqual(handoff["result_url"], f"{repository}/issues/15")
        self.assertEqual(handoff["evidence_url"], f"{repository}/pull/12#issuecomment-7142089405")
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
                         ["continued-511-repeated-draw",
                          "anyxboxx-147-native-wave64-gather", "framelab-12-vulkan-handoff", "xcl-2126-scratch-coverage",
                          "anyxboxx-133-native-fma"])
        self.assertEqual(amd, build_lab(equipment="amd", status="needs_run"))
        self.assertEqual([task["id"] for task in build_lab(status="blocked")["tasks"]], ["pb-9-reforge-present"])
        self.assertEqual(len(payload["tasks"]), 12)
        self.assertEqual([task["id"] for task in build_lab(equipment="intel")["tasks"]],
                         ["xcl-2126-scratch-coverage"])
        self.assertEqual(len(build_lab(equipment="nvidia", status="awaiting_review")["tasks"]), 1)
        self.assertEqual([task["id"] for task in build_lab(equipment="cpu", status="needs_run")["tasks"]],
                         ["scarlett-commons-continued-add-basic"])
        with self.assertRaises(ValueError):
            build_lab(status="merged")

    def test_exact_task_selection_preserves_filters_and_rejects_invalid_ids(self):
        selected = build_lab(task="xcl-1100-fma", equipment="amd", status="awaiting_review")
        self.assertEqual([task["id"] for task in selected["tasks"]], ["xcl-1100-fma"])
        self.assertEqual(build_lab(task="xcl-1100-fma", equipment="amd", status="needs_run")["tasks"], [])
        self.assertEqual(build_lab(task="unknown-check")["tasks"], [])
        self.assertEqual(build_lab(task="xcl-1100-fma", equipment="cpu")["tasks"], [])
        self.assertEqual(build_lab(task="framelab-12-vulkan-handoff", equipment="nvidia")["tasks"], [])
        with self.assertRaises(ValueError):
            build_lab(task="../xcl-1100-fma")

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
                    self.assertEqual(fetch("/api/v1/lab?task=xcl-1100-fma"),
                                     (200, filter_lab(data, task="xcl-1100-fma")))
                    self.assertEqual(fetch("/api/v1/lab?task=xcl-1100-fma&task=pb-9-reforge-present")[0], 400)
                    self.assertEqual(fetch("/api/v1")[1]["routes"]["lab"], "/api/v1/lab")
                    self.assertEqual(fetch("/api/v1/lab?equipment=unknown")[0], 400)
                    self.assertEqual(fetch("/api/v1/lab?status=needs_run&status=awaiting_review")[0], 400)
                    self.assertEqual(fetch("/api/v1/lab", method="POST")[0], 405)
            finally:
                server.shutdown()
                thread.join()
