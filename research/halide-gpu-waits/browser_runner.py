import csv
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
import io
import json
import queue
import subprocess
import time
from urllib.parse import urlsplit

MAX_RESULT = 262_144



class Handler(BaseHTTPRequestHandler):
    """Only serve the generated benchmark and accept its single local result."""

    def __init__(self, *args, assets, token, results, **kwargs):
        self.assets = assets
        self.result_path = "/result/" + token
        self.results = results
        super().__init__(*args, **kwargs)

    def setup(self):
        self.request.settimeout(3)
        super().setup()

    def log_message(self, format_string, *args):
        pass

    def do_GET(self):
        name = urlsplit(self.path).path
        asset = self.assets.get(name)
        if asset is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime, content = asset
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src 'self'; connect-src 'self'; "
                         "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        same_origin = "http://127.0.0.1:" + str(self.server.server_port)
        if self.path != self.result_path or self.headers.get("Origin") != same_origin:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if self.headers.get_content_type() != "application/json":
            self.send_error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
            if not 0 < length <= MAX_RESULT:
                raise ValueError("Invalid result length")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Expected a result object")
            self.results.put_nowait(payload)
        except (ValueError, UnicodeError, queue.Full) as error:
            self.send_error(HTTPStatus.BAD_REQUEST, str(error))
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()


def adapter_reference(expected_name):
    command = ["nvidia-smi", "--query-gpu=name,pci.device_id,driver_version", "--format=csv,noheader"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=True,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    cards = [dict(zip(("name", "pci", "driver"), (item.strip() for item in row)))
             for row in csv.reader(io.StringIO(result.stdout)) if len(row) == 3]
    candidates = [card for card in cards if expected_name.casefold() in card["name"].casefold()]
    if len(candidates) != 1:
        raise ValueError("NVIDIA inventory did not identify exactly one requested card")
    return cards, candidates[0]


def attest_adapter(report, inventory, reference):
    info = report.get("adapter", {})
    name = str(info.get("description") or "").casefold()
    vendor = str(info.get("vendor") or "").casefold()
    architecture = str(info.get("architecture") or "").casefold()
    device = str(info.get("device") or "").casefold().removeprefix("0x")
    reference_device = reference["pci"].casefold().removeprefix("0x")[:4]
    exact_name = bool(name and reference["name"].casefold() in name)
    exact_id = bool(device and reference_device and device == reference_device)
    adapter_is_ada = architecture in {"ada", "lovelace", "ada-lovelace", "ada lovelace"}
    inventory_is_ada = "rtx 40" in reference["name"].casefold()
    single_matching_architecture = len(inventory) == 1 and adapter_is_ada and inventory_is_ada
    if info.get("isFallbackAdapter") is not False or vendor not in {"nvidia", "0x10de", "10de"}:
        raise ValueError(f"Chrome did not report a non-fallback NVIDIA adapter: {info}")
    if not (exact_name or exact_id or single_matching_architecture):
        raise ValueError(f"Chrome's adapter could not be associated with the requested physical card: {info}")
    return {"inventory_reference": reference, "browser": info,
            "evidence": "exact device" if exact_name or exact_id else "single NVIDIA card and matching Ada architecture"}


def stop_launched_browser(process):
    if process.poll() is not None:
        return
    # The launched process belongs exclusively to the new benchmark profile.
    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                   creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True, timeout=8)
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def read_browser_result(process, results, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return results.get(timeout=0.2)
        except queue.Empty:
            if process.poll() is not None:
                raise RuntimeError(f"Isolated Chrome exited with code {process.returncode}")
    raise TimeoutError("Isolated Chrome did not complete in the available time")
