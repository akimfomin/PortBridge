import argparse
from pathlib import Path
import subprocess


PIN = "f176c4774680f5813461cc5bd4e3ccfda1f55dd3"
HOST = "crates/victory-gpu/src/host.rs"
folder = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=("baseline", "candidate"))
parser.add_argument("--repo", type=Path, default=Path.cwd())
parser.add_argument("--out", type=Path, default=folder / "generated")
args = parser.parse_args()
repo = args.repo.resolve()
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
assert head == PIN, head
host = (subprocess.check_output(["git", "show", f"{PIN}:{HOST}"], cwd=repo, text=True, encoding="utf-8")
        if args.mode == "baseline" else (repo / HOST).read_text(encoding="utf-8"))


def between(source, start, end):
    fragment = source[source.index(start):]
    return fragment[:fragment.index(end)]


states = between(host, "#[derive(Default)]\nstruct BufferStates", "/// A host command list and its allocator")
submit = between(host, "    fn submit<'a>", "    /// With `VICTORY_D3D12_DRED`: the faulting address")
setup = between(submit, "        let mut lists: Vec<Option<ID3D12CommandList>>", "        // The time a settle")
append_run = between(submit, "        for list in runs {\n            list.run_deferred", "        batch.flush();")
append_card = between(submit, "        if let Some(check) = card.as_ref().and_then", "        let prepared")
late = between(submit, "        if late {\n            *submitted += 1;", "            self.card_sent();")
sync = between(submit, "        // Diagnostics: each list on its own", "            // With timing on each group")
execute = between(host, "    fn execute_command_groups(", "    fn submit<'a>") if args.mode == "candidate" else ""
card = between(host, "        if plan.ranges.iter().any(|r| r.compared)", "        work.out += 1;")
assert "D3D12_RESOURCE_BARRIER_TYPE_UAV" in card
assert "SetComputeRootShaderResourceView(1, r.shadow.buffer.GetGPUVirtualAddress())" in card

text = (folder / "state_fixture.rs.in").read_text(encoding="utf-8")
for key, value in {
    "STATES": states, "SETUP": setup, "APPEND_RUN": append_run, "APPEND_CARD": append_card,
    "LATE": late, "SYNC": sync, "EXECUTE": execute, "MODE": args.mode,
}.items():
    marker = f"@{key}@"
    assert text.count(marker) == 1
    text = text.replace(marker, value)
args.out.mkdir(parents=True, exist_ok=True)
(args.out / f"state.{args.mode}.rs").write_text(text, encoding="utf-8")
