"""Run only the new cache regression against the exact before/after files."""
import ast
import importlib.util
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


root = Path(sys.argv[1])
source = root / "any-patched/tests/test_shader_cache.py"
syntax = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
test = next(node for node in syntax.body
            if isinstance(node, ast.FunctionDef) and node.name == "test_corrupted_locked_entry_is_a_miss")
for tag in ("any", "any-patched"):
    cache_path = root / tag / "PrototypeScarlett/emu/shader_cache.py"
    names = {"shader_cache": load(cache_path, f"shadercache_{tag}")}
    exec(compile(ast.Module(body=[test], type_ignores=[]), str(source), "exec"), names)
    with tempfile.TemporaryDirectory() as tmp:
        patches = []
        class Fixture:
            @staticmethod
            def setattr(obj, name, value):
                change = patch.object(obj, name, value)
                change.start()
                patches.append(change)
        try:
            names[test.name](Path(tmp), Fixture())
        except PermissionError:
            assert tag == "any"
            print("Baseline: PermissionError reproduced")
        else:
            assert tag == "any-patched"
            print("Candidate: corrupted locked entry is a miss; no bytes cached")
        finally:
            for change in reversed(patches):
                change.stop()
