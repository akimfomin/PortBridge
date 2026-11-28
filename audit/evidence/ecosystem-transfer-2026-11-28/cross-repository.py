import concurrent.futures
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

TARGETS = {
 "whoalin1/victory-altracing": ("95e1ca80b56865b3bf2654f27c7550b05a8d54a9", [("trustno1-coder/VIctory-NVIDIA", [1015,1017,1018,1019,999,1003,1005,1006,1007,1008]),("TaynanGT/Vice-Tay",[390,392,395,403])]),
 "XaviFortes/VIctory-RDNA": ("4e3a4d2a2c8b47c1c7355d7847def528a506af28", [("TaynanGT/Vice-Tay",[388,389,390,392,393,395,403]),("trustno1-coder/VIctory-NVIDIA",[1017,1018,1019])]),
 "TaynanGT/Vice-Tay": ("fe7c6e52198f2070805ffafc4e55a7163291bad0", [("XaviFortes/VIctory-RDNA",[4]),("trustno1-coder/VIctory-NVIDIA",[1015,1017,1018,1019,994]),("fxceless/victory-fork",[1496,1506,1507])]),
 "LooperSalty/AnyXboxX": ("66b92fbe48c82ecbb334eba19c872f0c538ff1fb", [("TaynanGT/Vice-Tay",[388,390,392,395,403]),("trustno1-coder/VIctory-NVIDIA",[1015,1017,1018,1019])]),
 "PastiiJay/klbf-lab": ("87e5f7bc8d2fc7bbb8b8b3a0b5c6858bccc10174", [("TaynanGT/Vice-Tay",[388,392,395,403]),("trustno1-coder/VIctory-NVIDIA",[1017,1018,1019])]),
}
ENV={k:v for k,v in os.environ.items() if not k.startswith(("GIT_","SSH_"))}
ENV.update(GIT_CONFIG_NOSYSTEM="1",GIT_CONFIG_GLOBAL=os.devnull,GIT_ATTR_NOSYSTEM="1",GIT_TERMINAL_PROMPT="0")
def inspect(target):
    receiving, sources = TARGETS[target]
    output = []
    with tempfile.TemporaryDirectory(prefix="pb-cross-tree-") as folder:
        def git(*args, data=None):
            return subprocess.run(["git","-c","http.followRedirects=false","-c","protocol.allow=never","-c","protocol.https.allow=always",*args],cwd=folder,env=ENV,input=data,capture_output=True,timeout=100)
        def text(p):
            return p.stdout.decode(errors="replace").strip()
        def checked(*args):
            p=git(*args)
            if p.returncode:
                raise RuntimeError(args[0]+": "+p.stderr.decode(errors="replace").strip()[-200:])
            return text(p)
        def fetch(repo,*refs):
            checked("fetch","--quiet","--filter=blob:none","--no-tags","--no-recurse-submodules",f"https://github.com/{repo}.git",*refs)
        checked("init","--quiet","--bare","--template=")
        fetch(target,"refs/heads/main:refs/audit/target")
        if checked("rev-parse","refs/audit/target")!=receiving:
            raise RuntimeError("Receiving main moved")
        for source,numbers in sources:
            pins={p["number"]:p for p in PULLS[source]["pulls"]}
            refs={t[1]:t[0] for line in checked("ls-remote","--refs",f"https://github.com/{source}.git",*[f"refs/pull/{n}/head" for n in numbers]).splitlines() if len(t:=line.split())==2}
            selected=[n for n in numbers if n in pins and pins[n]["head"]==refs.get(f"refs/pull/{n}/head")]
            local=lambda n:f"refs/audit/{source.split('/')[0]}/p{n}"
            if selected:
                fetch(source,*[f"refs/pull/{n}/head:{local(n)}" for n in selected])
            for n in numbers:
                row=dict(target=target,receiving=receiving,source=f"https://github.com/{source}/pull/{n}")
                output.append(row)
                if n not in selected or checked("rev-parse",local(n))!=pins[n]["head"]:
                    row.update(status="skip",reason="Missing from frozen metadata or PR moved")
                    continue
                head=pins[n]["head"]
                original_base=text(git("merge-base",pins[n]["base"],head))
                if not re.fullmatch("[0-9a-f]{40}",original_base):
                    row.update(status="skip",reason="No source merge base")
                    continue
                row.update(head=head,base=original_base)
                diff=git("diff","--binary","--no-ext-diff","--no-renames",original_base,head,"--","crates","scripts")
                if diff.returncode or not diff.stdout:
                    row.update(status="skip",reason="No delta in selected source scope")
                    continue
                checked("read-tree",receiving)
                args=["--directory=third_party/victory"] if target=="LooperSalty/AnyXboxX" else []
                direct=git("apply","--cached","--check",*args,data=diff.stdout)
                reverse=git("apply","--cached","--check","--reverse",*args,data=diff.stdout)
                if direct.returncode==0:
                    row["status"]="source-patch-clean"
                elif reverse.returncode==0:
                    row["status"]="source-patch-present"
                elif args:
                    row["status"]="source-context-mismatch"
                    row["paths"]=[line.partition("patch failed: ")[2] for line in direct.stderr.decode(errors="replace").splitlines() if line.startswith("error: patch failed: ")]
                else:
                    merged=git("merge-tree","--write-tree","--no-messages","--name-only","-z","--merge-base",original_base,receiving,head)
                    fields=merged.stdout.decode(errors="replace").strip("\0\r\n").split("\0")
                    row["status"]={0:"full-pr-three-way-clean",1:"full-pr-three-way-conflict"}.get(merged.returncode,"skip")
                    if merged.returncode==1:
                        row["paths"]=fields[1:]
                    elif merged.returncode==0 and fields[0]==checked("rev-parse",receiving+"^{tree}"):
                        row["status"]="full-pr-tree-unchanged"
    return output
if __name__=="__main__":
    from collections import Counter
    import sys
    PULLS=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs={target:pool.submit(inspect,target) for target in TARGETS}
        result={}
        for target,job in jobs.items():
            try:
                result[target]=job.result()
            except (OSError,RuntimeError,subprocess.TimeoutExpired) as e:
                result[target]=[{"status":"skip","reason":str(e)}]
            print(target,dict(Counter(row["status"] for row in result[target])))
    Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")

