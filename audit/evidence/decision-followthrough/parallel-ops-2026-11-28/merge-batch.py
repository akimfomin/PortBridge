import concurrent.futures, json, os, re, subprocess, tempfile, traceback
from pathlib import Path
CONFIG = json.loads(r'''[{"repo":"TaynanGT/Vice-Tay","pairs":[[263,290],[290,254],[357,290],[263,389],[382,379],[389,379]],"heads":[[389,"main","d7e5183b6b619d1976ef1b0dce798c7fd042fa82"],[290,"main","315c946d8d1b7c2b2fcc32b0a0d75444e41bcc4f"],[357,"main","6d20a254f9a6a25ecc3f826ef8242eb7aa1952ee"],[263,"main","4f5de4ecdd613867bb8af4b548957174139b321f"],[254,"main","971deec05027bf51d13729866e4e8f28ffb77855"],[382,"main","ea557975ff2e8bef5cd206e452de0420c1cfd650"],[193,"main","1a34e9ca637a4e46aeace956d0ab7d7e9d257302"]]},{"repo":"LooperSalty/AnyXboxX","pairs":[[521,528],[528,526],[511,521],[570,571],[568,519],[566,571]],"heads":[[521,"main","ebb6f09858f3bc96a1e7bc72e5030b71d0e500d4"],[528,"main","28814de19064a8ab9bb6b068acc057225907006e"],[526,"main","47f2505aa23a2aaf8e47ac325d36e7238112b728"],[511,"main","33d3018ea4450201a05173873e2dc1da811b2636"],[571,"main","c129c8b7175f1cb9fe6a83bea9e11fdaa65f907e"],[570,"main","6245785d1e807d051b69bbb16fc57a1a80e2a802"],[568,"main","2e1939d5d020f7df83a522994744caa2d049fc2d"],[566,"main","9acac901053093014cbae7a508d51fe9b311cb39"]]},{"repo":"ProjectLeonida/mandy","pairs":[[2518,2517],[2518,2516],[2511,2517],[2501,2513],[2516,2517]],"heads":[[2518,"main","f2b6d4a1dafcabd261af217a06b4040383184f5e"],[2511,"main","4a497c8f1bebda53091413442a76d31ff3411c97"],[2517,"main","b3db0f3659d2deb51b086fc93e767182b2ac0dad"],[2501,"main","660f609d95f821b6698984f305bca0fe38b57653"],[2516,"main","c05dc2ff523524183cb78df75055ddee7e4c186a"],[2513,"main","c6f39028a6b293edb2c413b8229b6480fd0c5204"],[2515,"main","6e5e82e4003ae9971afc36fa79d051d23d3255cd"]]},{"repo":"Marvisak/VIctory","pairs":[[3630,3608],[3630,3612],[3608,3609],[3623,3246],[3586,3623]],"heads":[[3630,"main","7dfc01a60a93ee7a084f027d261a70f9ddb38e1d"],[3608,"main","d06df15fe1c618a775490070ec24bf791941e60a"],[3612,"main","aa6305357c3b90c6d64309c6c94bab3895df0547"],[3609,"main","d54570166a81247966e596487b050b93bc548415"],[3623,"main","8f5927edcbc97261c3bb491da687bd4efc299857"],[3246,"main","c2e4507ce40ccdf1056ccf9c40e39f27bb8721ef"],[3586,"main","1960fa53e7759e8cfae8e254b66826af668e7d38"]]},{"repo":"xcl-dev/xcl","pairs":[[3036,2902],[3036,2975],[3008,2987],[2975,2902]],"heads":[[2793,"main","1f106b3f93ffeb19b7fa999fe695f9abb1f18f88"],[2902,"nvidia-dev","96dfa767b927190f0d57eba22f9dba56c995deaf"],[2975,"nvidia-dev","4e52050cea54dec0493482f429f246c1ea1e9362"],[3008,"nvidia-dev","24fdb7b9297e47af1433a7c1069436becfe7a724"],[3079,"amd-dev","f64494d167f527a48a008fe3fbd7287b497398b0"],[3036,"nvidia-dev","6f3ad70ccc22acb777205cdea1d512bf24421299"]]},{"repo":"fxceless/victory-fork","pairs":[[1280,1286],[1280,1500],[1286,1500],[1126,1140],[885,1489]],"heads":[[92,"main","f31ad9480618ea49b72c7ab55c0331627ab7ae39"],[1140,"main","f2d68c9ddb2bbea7533033f92e806d719b64efc8"],[1500,"main","4351fb43edd626bd8fd450853a17f02ca0c1b6f7"],[1280,"main","97d270bfc31619fca9b02f3b13f2fea2c8f9526f"],[1286,"main","3f3ec37d16bc2f22f4249b435d70e142caf349a0"],[1126,"main","335c089b244627842693e91ed4f9a6a59b33d1f9"],[885,"main","f219179417ecf0d4d9c8585bcccefe91a19d3856"],[1489,"main","b344f5b74c974b602914c8b0a498b000158897ea"]]},{"repo":"KytyPS5/KytyPS5","pairs":[[2172,2357],[2172,2591],[2357,2591]],"heads":[[2172,"main","81d29d43cb151883949d5f0cfd3c1d1a3bf80e13"],[2278,"main","09fcbe2b2692417f3dc4fd799338542f54425070"],[2591,"main","74d2fc98caf61be3708b6d860a524b86bb34c41e"],[2357,"main","d1f980006cc1d92201b6d05d4c4b873310e9d553"]]},{"repo":"boykopovar/AnyPS5","pairs":[[26100,26101],[26100,26047],[26101,26047],[27979,25279]],"heads":[[26100,"main","a00c6029c6648136af721703098e358e69525945"],[26101,"main","a4cbdb998fa08040a2c7676fa84bb5c184fbfed0"],[26047,"main","ab2742cac58552db32188432f34ce89d00cab96f"],[27979,"main","c22ff588ce9be63992322135ef02c6583029e1df"],[25279,"main","8eb74c2335767efa875a3b88a312d885d5d45f97"],[27966,"main","e2e97886eee135e83ea9a55e8cdb769768eba6ff"]]}]''')
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
            for a,b in config["pairs"]:
                report["pairs"].append(dict(check(head(a),head(b)),first=a,second=b))
    except (OSError,RuntimeError,subprocess.TimeoutExpired) as exc:
        report["error"]=str(exc)
    return report
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
    out=list(workers.map(inspect,CONFIG))
Path(os.environ["PB_OPS_REPORT_FILE"]).write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
for r in out:
    from collections import Counter
    print(r["repo"],r.get("error",""),dict(Counter(x["status"] for x in r["singles"])),dict(Counter(x["status"] for x in r["pairs"])))
