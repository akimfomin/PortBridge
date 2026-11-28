"""Exercise the patched fixture's control flow using mock render calls."""
import ast
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile


def main(path):
    source = path.read_text(encoding="utf-8")
    parsed = ast.parse(source)
    method, = [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name == "main"]
    targets = [((8, 4, 1), True), ((12, 1, 1), True)]
    visits = []

    def compile_pair(cli, sdk, work, group, wave32):
        for mode in ("implicit", "explicit"):
            yield group, mode

    def check(renderer, adapter, shader, reference):
        visits.append(shader)
        if shader == (targets[0][0], "implicit"):
            raise AssertionError("synthetic mismatch")

    mocks = dict(Path=Path, tempfile=tempfile, render=lambda *a: SimpleNamespace(returncode=0),
                 CASES=targets, write_reference=lambda *a: None, compile_pair=compile_pair,
                 check_readback=check, operation_cases=lambda: (), sys=sys)
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), "exec"), mocks)
    try:
        mocks["main"]("compiler", "sdk", "renderer", "adapter")
    except AssertionError as error:
        assert error.args == (["(8, 4, 1) wave32 implicit"],), error
    else:
        raise AssertionError("The injected mismatch must still fail the test")
    assert visits == [(group, mode) for group, _ in targets for mode in ("implicit", "explicit")], visits
    print("The explicit arm and later controls ran after the failed implicit arm; exit stays failing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
