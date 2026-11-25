"""Check the environment and dispatch only the six embedded synthetic modules."""

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent


class ProcessMemory(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        *((name, ctypes.c_size_t) for name in (
            "commit_total", "commit_limit", "commit_peak", "physical_total", "physical_available",
            "system_cache", "kernel_total", "kernel_paged", "kernel_nonpaged", "page_size"
        )),
        ("handle_count", wintypes.DWORD),
        ("process_count", wintypes.DWORD),
        ("thread_count", wintypes.DWORD),
    ]


def preflight():
    memory = ProcessMemory()
    memory.cb = ctypes.sizeof(memory)
    query = ctypes.WinDLL("psapi.dll", use_last_error=True).GetPerformanceInfo
    query.argtypes = (ctypes.POINTER(ProcessMemory), wintypes.DWORD)
    query.restype = wintypes.BOOL
    if not query(ctypes.byref(memory), ctypes.sizeof(memory)):
        raise ctypes.WinError(ctypes.get_last_error())
    commit = (memory.commit_limit - memory.commit_total) * memory.page_size
    physical = memory.physical_available * memory.page_size
    if commit < 4 << 30 or physical < 6 << 30:
        raise RuntimeError(f"admission refused: {commit / 2**30:.2f} GiB commit, {physical / 2**30:.2f} GiB RAM")
    return commit, physical


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def validation_layer(directory):
    manifest = directory / "VkLayer_khronos_validation.json"
    layer = json.loads(manifest.read_text(encoding="utf-8"))["layer"]
    if layer["name"] != "VK_LAYER_KHRONOS_validation":
        raise ValueError("validation manifest names a different layer")
    location = layer["library_path"]
    library = directory / location
    if not library.is_file() and Path(location).name == location:
        library = Path(shutil.which(location) or library)
    return digest(library), layer.get("api_version")


def run(exe, directory, output):
    layer_hash, version = validation_layer(directory)
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(("VK_", "VKD3D_", "MESA_VK_"))}
    env["VK_LAYER_PATH"] = str(directory)
    with output.open("x", encoding="utf-8", newline="\n") as log:
        try:
            commit, physical = preflight()
            log.write(json.dumps({"worker_sha256": digest(exe), "validation_sha256": layer_hash,
                                  "validation_api": version, "initial_commit_bytes": commit,
                                  "initial_physical_bytes": physical}) + "\n")
            log.flush()
            return subprocess.run([exe, "--run-six"], stdout=log, stderr=subprocess.STDOUT,
                                  env=env, cwd=exe.parent, timeout=25).returncode
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            log.write(json.dumps({"status": "stopped", "error": str(error)}) + "\n")
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layer-directory", required=True, type=Path)
    parser.add_argument("--worker", type=Path, default=HERE / "build" / "readback.exe")
    parser.add_argument("--output", type=Path, default=HERE / "native-readback-new.log")
    args = parser.parse_args()
    raise SystemExit(run(args.worker.resolve(strict=True), args.layer_directory.resolve(strict=True), args.output))
