import concurrent.futures, json, os, re, subprocess, tempfile, traceback
from pathlib import Path
CONFIG = json.loads(Path(__file__).with_name("same-repository-input.json").read_text(encoding="utf-8"))
SHA = re.compile(r"[0-9a-f]{40}\Z")
ENV = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "SSH_"))}
ENV.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_ATTR_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
def inspect(config):
    repo = config["repo"]
    url = "https://github.com/" + repo
    report = dict(repo=repo, singles=[], pairs=[])
    try:
        with tempfile.TemporaryDirectory(prefix="pb-wave-bare-") as folder:
            def git(*args, limit=90):
                return subprocess.run(["git","-c","http.followRedirects=false","-c","protocol.allow=never","-c","protocol.https.allow=always",*args],env=ENV,cwd=folder,stdin=subprocess.DEVNULL,capture_output=True,timeout=limit)
            def ok(*args):
                p=git(*args)
                if p.returncode:
                    raise RuntimeError(p.stderr.decode("utf-8","replace").strip()[-1500:])
                return p.stdout.decode("utf-8","replace").strip()
            ok("init","--bare","--quiet","--template=")
            ok("remote","add","origin",url+".git")
            prs = {num: (branch, sha) for num,branch,sha in config["heads"]}
            numbers = set(prs) | {n for pair in config["pairs"] for n in pair}
            branches = {b for b,sha in prs.values()}
            refs = [f"refs/pull/{n}/head" for n in sorted(numbers)] + [f"refs/heads/{branch}" for branch in sorted(branches)]
            def ls():
                return dict((line.split()[1],line.split()[0]) for line in ok("ls-remote","--refs","origin",*refs).splitlines() if line)
            initial=ls()
            targets = {ref:f"refs/check/{ref.removeprefix('refs/')}" for ref in refs if ref in initial}
            ok("fetch","--quiet","--filter=blob:none","--no-tags","--no-recurse-submodules","origin",*[f"+{ref}:{dst}" for ref,dst in targets.items()])
            pins={ref:ok("rev-parse",dst) for ref,dst in targets.items()}
            final=ls()
            pins={ref:sha for ref,sha in pins.items() if sha == initial.get(ref) == final.get(ref) and SHA.fullmatch(sha)}
            report["targets"]={b:pins.get("refs/heads/"+b) for b in sorted(branches)}
            def head(n):
                sha=pins.get(f"refs/pull/{n}/head")
                return sha if n not in prs or sha == prs[n][1] else None
            def check(t,h):
                result=dict(target=t,head=h)
                if not t or not h:
                    return dict(result,status="unverified",reason="Pinned remote ref is unavailable or changed")
                mb=git("merge-base",t,h)
                if mb.returncode:
                    return dict(result,status="unverified",reason="No common ancestor")
                base=mb.stdout.decode().strip()
                result["merge_base"]=base
                d=git("diff","--no-ext-diff","--name-only","-z",base,h)
                result["changed_files"]=[p for p in d.stdout.decode("utf-8","replace").split("\0") if p]
                m=git("merge-tree","--write-tree","--name-only","--no-messages","-z",t,h)
                parts=m.stdout.decode("utf-8","replace").strip("\0\r\n").split("\0")
                if m.returncode not in (0,1) or not SHA.fullmatch(parts[0]):
                    return dict(result,status="unverified",reason=m.stderr.decode("utf-8","replace").strip()[-250:])
                if m.returncode==1:
                    return dict(result,status="conflict",paths=parts[1:])
                old=ok("rev-parse",t+"^{tree}")
                return dict(result,status="unchanged" if parts[0]==old else "clean",tree=parts[0])
            for number,(branch,_) in prs.items():
                report["singles"].append(dict(check(pins.get("refs/heads/"+branch),head(number)),pr=number,branch=branch))
            from itertools import combinations
            from collections import Counter
            overlaps = []
            active = [row for row in report["singles"] if row["status"] in {"clean","conflict"}]
            for a,b in combinations(active,2):
                if a["branch"] != b["branch"]:
                    continue
                shared = set(a.get("changed_files",[])) & set(b.get("changed_files",[]))
                meaningful = sorted(p for p in shared if p.endswith((".cpp",".c",".h",".rs",".inl",".py",".comp",".glsl",".hlsl",".ps1")))
                if meaningful:
                    overlaps.append((a,b,meaningful))
            overlaps.sort(key=lambda item: (-len(item[2]), item[0]["pr"], item[1]["pr"]))
            use = Counter()
            for a,b,paths in overlaps:
                first,second = a["pr"],b["pr"]
                if len(report["pairs"]) >= config["pair_limit"]:
                    break
                if use[first] >= 4 or use[second] >= 4:
                    continue
                use.update([first,second])
                report["pairs"].append(dict(check(head(first),head(second)),first=first,second=second,overlap=paths))
    except (OSError,RuntimeError,subprocess.TimeoutExpired) as exc:
        report["error"]=str(exc)
    return report
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
    out=list(workers.map(inspect,CONFIG))
Path(os.environ["PB_OPS_REPORT_FILE"]).write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
for r in out:
    from collections import Counter
    print(r["repo"],bool(r.get("error")),dict(Counter(x["status"] for x in r["singles"])),dict(Counter(x["status"] for x in r["pairs"])))
