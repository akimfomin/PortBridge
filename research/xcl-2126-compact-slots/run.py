# SPDX-License-Identifier: GPL-2.0-only

import argparse
import hashlib, importlib.util, json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

parser = argparse.ArgumentParser(description="Replay the pinned XCL scratch implementation")
for argument in ("census", "rustc", "linker", "dxv"):
    parser.add_argument(f"--{argument}", type=Path, required=True)
args = parser.parse_args()
proof = Path(__file__).resolve().parent
census_dir = args.census.resolve(strict=True)
spec=importlib.util.spec_from_file_location("census", census_dir/"run.py")
census=importlib.util.module_from_spec(spec)
spec.loader.exec_module(census)
assert census.verified_sources()=="3283da481077c1962f13f1b4078841662f7a4ccb"
relative=Path("crates/xcl/src/gpu/dxil/module/split.rs")
fragment=(proof/"fragmentation.rs").read_text(encoding="utf-8")
rustc, linker, dxv = (path.resolve(strict=True) for path in (args.rustc,args.linker,args.dxv))
cases={}
def replace_once(haystack,old,new):
    assert haystack.count(old)==1,old
    return haystack.replace(old,new)

with TemporaryDirectory(prefix="pb-xcl-allocator-") as temp:
    dest=Path(temp)
    candidate = dest / "upstream"
    candidate_source = candidate / relative
    candidate_source.parent.mkdir(parents=True)
    candidate_source.write_bytes((census_dir / "upstream" / relative).read_bytes())
    subprocess.run(["git", "apply", str(proof / "xcl-2126-compact-slots.patch")], cwd=candidate, check=True, timeout=10)
    census.stage_sources(dest)
    target=dest/"gpu/dxil/module/split.rs"
    target.write_text(census.instrumented_emitter(candidate_source.read_text(encoding="utf-8")),encoding="utf-8")
    harness=target.with_name("census.rs")
    text=harness.read_text(encoding="utf-8")
    text=replace_once(text,"    assert_eq!(upstream.dwords_per_group, fixed.0 * 32);", """
    let compact = s.m.scratch_slots(plan).unwrap();
    assert!(peak <= compact.0 && compact.0 <= fixed.0);
    check_layout(&lives, &compact);
    assert_eq!(upstream.dwords_per_group, compact.0 * 32);
    println!("implementation,{name},{},{}", fixed.0 * 32, compact.0 * 32);
    """.strip("\n"))
    text=replace_once(text,"    for (stage, original) in upstream.pieces.into_iter().enumerate() {", """
    assert_eq!(events, emitted(name, "implementation", s, plan, &compact, out));
    for (stage, original) in upstream.pieces.into_iter().enumerate() {
        assert_eq!(original, std::fs::read(out.join(format!("{name}-implementation-{stage}.dxil"))).unwrap());
        if fixed.0 != compact.0 { continue; }""".strip("\n"))
    text=replace_once(text,"    assert_eq!(baseline.1, 0);", """
    assert_eq!(baseline.1, 0);
    assert_eq!(baseline, replay(&events, plan.blocks.len(), &compact, false));
    assert_eq!(baseline, replay(&events, plan.blocks.len(), &compact, true));
    println!("replayed,{name},{}", baseline.0);
    """.strip("\n"))
    text=replace_once(text,"    disjoint(out);","    disjoint(out);\n    fragmentation(out);\n    randomized();")
    text=replace_once(text,"fn strict(lives: &[Lifetime]) -> Layout {\n    let mut ordered = lives.to_vec();\n    ordered.sort_by_key(|l| (l.first, l.value));","""fn strict(lives: &[Lifetime]) -> Layout {
    ordered_strict(lives, false)
}

fn ordered_strict(lives: &[Lifetime], longer: bool) -> Layout {
    let mut ordered = lives.to_vec();
    ordered.sort_by_key(|l| (l.first, std::cmp::Reverse(if longer { l.last } else { 0 }), l.value));""")
    randomized="""
fn randomized() {
    let mut state = 0x5d31b776u32;
    let mut next = || { state ^= state << 13; state ^= state >> 17; state ^= state << 5; state };
    let mut checked = 0;
    for _ in 0..128 {
        let count = (next() % 90) + 6;
        let risks: Vec<_> = (0..count).map(|i| {
            let first = (next() as usize) % 36;
            let last = first + (next() as usize) % 14;
            Lifetime { value: Value::Inst(i), first, last, words: 1 + next() % 2 }
        }).collect();
        let compact = super::reuse_payload_slots(risks.iter().map(|r| super::PayloadLifetime {
            value: r.value, first: r.first, last: r.last, words: r.words,
        }).collect()).unwrap();
        check_layout(&risks, &compact);
        let reference = ordered_strict(&risks, true);
        assert_eq!(reference, compact);
        checked += count;
    }
    println!("randomized,128,{checked}");
}
"""
    harness.write_text(text+"\n"+fragment+"\n"+randomized,encoding="utf-8")
    exe=dest/"candidate.exe"
    subprocess.run([str(rustc),"--edition=2024","-D","warnings","-C",f"linker={linker}",str(dest/"main.rs"),"-o",str(exe)],
                   cwd=dest,check=True,timeout=40)
    assets=dest/"assets"
    assets.mkdir()
    proc=subprocess.run([str(exe),str(assets)],cwd=dest,capture_output=True,check=True,text=True,timeout=12)
    hashes={}
    for path in sorted(assets.glob("*.dxil")):
        validation=subprocess.run([str(dxv),str(path)],capture_output=True,text=True,check=True,timeout=10)
        assert "validation succeeded" in (validation.stdout+validation.stderr).casefold(),path
        hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    for line in proc.stdout.splitlines():
        fields=line.split(",")
        if fields[0]=="implementation": cases[fields[1]]=dict(zip(("before","after"),map(int,fields[2:])))
        if fields[0]=="replayed": cases[fields[1]]["scratch_words_per_order"]=int(fields[2])
        if fields[0]=="randomized": randomized_summary=list(map(int,fields[1:]))
    out={"revision":census.verified_sources(),"cases":cases,"validated_dxil":len(hashes),"randomized":randomized_summary,
         "sha256":hashes}
    print(json.dumps(out, indent=2))
