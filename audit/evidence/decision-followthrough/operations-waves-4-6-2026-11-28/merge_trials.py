import concurrent.futures, json, os, re, subprocess, tempfile, traceback
from pathlib import Path
CONFIG = json.loads(r'''[{"repo":"xcl-dev/xcl","pairs":[],"pair_limit":12,"heads":[[3066,"main","d8a1f5f1fc30b8640afb76266d24d4a7b79896c5"],[2960,"main","40d3a31231a33466d06de3789356ab34a07cb151"],[2961,"main","51cda2f48932cdee512d61d4cd7948f829656722"],[2962,"main","687d553c70da7d2b7d450288b8b56832d12a0411"],[2965,"main","be0c274d642839e451d535a1d481f271bfdd5f38"],[2755,"amd-dev","4bb6b30fc5b19e5dbcec8818134af47e39a68a31"],[3061,"amd-dev","29cb54537ca8c92d3533e8acdbc182b929db5abc"],[2550,"main","e033310cd7b91767391f65080629a79c2664b9f8"],[2543,"main","12141ccbfa162b7e169d913a20c1b7e3fd1bf1dd"],[3039,"nvidia-dev","7cce7d3d4625ac8f90f146f1f89f25a613e32e76"],[2987,"nvidia-dev","f8e75bca1ea903b1cf0e9d4f9387b73f359e5051"],[2578,"main","e60f0835e8c9037513e9c9b553be8e84c2635296"],[2470,"main","d5f6daf79b1780f64d8683337bbd1e9303880b37"],[2424,"main","6ada0232306cf02b85fa4050e5d3345363a2f9e1"],[2398,"main","e9d7aefc3a18bc5223790a9d928b1574bc1198c9"],[2964,"main","86a90eebad296798fb46d8d610203f89eadaee7f"],[1082,"main","3c325a9080790815bae0e79349ac24d93f2bb52b"],[2103,"main","7743842ada44feff940b4785bf94e70b87b7d39c"]]},{"repo":"R0Y00/Xbox2Windows","pairs":[],"pair_limit":12,"heads":[[3251,"main","774646cfa6d88c4e3b08d408531f4d6df7fe131b"],[2344,"main","44f147695c10efd956cfd5fa35b87b3aa868aa57"],[2245,"main","e95f537754922918a6cc0b489774c6e268b6caae"],[2470,"main","206749e454407bd271019d667cf46507894617a8"],[3063,"cpp-migration","64513f26a85867bc74969777eae3e27f9c4ef48a"],[3221,"main","3114bb156ef7523ffec69e4cc37ffeaf902041f4"],[3250,"main","2502da4e8decd985c6f01f0533a8d4b3a9d82cc2"],[3241,"codex/native-shader-modules","cf19be36511993a9de82f8032c35c92049bbdfab"],[3239,"main","acab1a069a36da6b3eb5456e8d69d90f0b6a157b"],[3247,"main","573c3b7c672c82799cba1a492efbc1f3a65eac6c"],[1918,"main","90b39c31604a62593f1533c7bb688d19724ecd9a"],[3232,"main","6fb2316cc93743cf2356ebd949b2de46206be3ec"],[3100,"main","130d32cb535be418cadf705ae0334a5e1e5bce62"],[3119,"main","4968e12475aec89f35bbb2a5b28b6cc1ddae4d2c"],[3123,"main","0594e4332ce30759fd9fef4cce720817b200afe0"],[3135,"main","fbb9aef797c0ef186e1122f164eda512c3b0ca01"],[3136,"main","bd78c3954442a8161b64864ffd8b4293fe7a8ba0"],[3137,"codex/native-shader-modules","13c7cfabdbec75ca1c879691437e23697e45856f"],[3244,"main","9863d46902dbe627c14a05f787ba89165067e253"]]},{"repo":"Marvisak/VIctory","pairs":[],"pair_limit":12,"heads":[[3644,"main","9c81f8cc8aaeed3f452eb29a951dce235fe5e033"],[3643,"main","63f337ca8e1e432ab0fbc8ef94618ae89d9612f4"],[3642,"main","1e7176ae20748131b4c0f89c1fe82ef3821351f6"],[3641,"main","31374faf1a710512dd06e3f4275916ab756f570b"],[3638,"main","d9f222c7f98ee38e55e30b57f55a7c2dc4f031d4"],[2827,"main","ce361dc2ba482799af53add2f849e2d716550cfa"],[3639,"main","e0b5e8f7fbbea890f9a41ec95242305444e6c6e1"],[2516,"main","c9f7f75ac70fd774c78426e95cd399b743e8590e"],[3628,"main","6cb0996720a6aef61c3191b7ac8e32d8758df8e9"],[3274,"main","6964f11508928a985a5bcb4553f62e3c11b99703"],[3604,"main","63bd11f634f8e4170f17bf45288f41048397ea05"],[3640,"main","bffaa159498d2f49721c2de6d4ed50aac1c00381"],[2500,"main","51b7f78fed18f39e0060d010ba3e1d3521076b96"],[3637,"main","8d45f077a20616923f5142836be52c8e0247b3bb"],[3600,"main","6f771e68054ba49aab55b9d909cd72723891de76"],[2079,"main","99d33d41679076941778d17fc016f39530803625"],[3221,"main","b6931ed82a8ae79c2a0fa2bea6deb54e4455b698"],[3313,"main","7592bb4f908d0cfc201b287d058daee4ba09098b"],[3622,"main","f6989c64e2a1962babb12fff855950622b3a1c47"]]},{"repo":"TaynanGT/Vice-Tay","pairs":[],"pair_limit":12,"heads":[[392,"main","3ffa31f5d3ee7b6f9d76530d111cc3590be5886d"],[379,"main","ecc003e18bc17f4635bc0ca1ad53dfe7fe03f520"],[375,"main","5823fa7ab32c3934e5068861bb5574ddf2663da9"],[120,"main","a5a7e247907d778c1ebaa9b6477d990508b898f0"],[118,"main","d833ee0aa4efd917578b1a904cfddfd263930c81"],[260,"main","b77ecacae467fa67e0547600efec7c949630efed"],[275,"main","bcb57f384b3f1868063125fc9a2a7286ef36f9b2"],[276,"main","746ee942bd8bb64f630647c088c9dca523d3ba4b"],[279,"main","1481f9067bf10069812d60162b522cc463cf28a7"],[266,"main","49de7774d9a4f603f9a7981bf7f789da520a1431"],[309,"main","c6466267ec3c31f9237a7a95be672b5015870dd7"],[312,"main","223402fd259ec0780b0a90a09420d3dd51d6aa85"],[289,"main","4ec4b55f15351dc87e8dbc1aa4c56f54f39f6751"],[281,"main","eed4f42caa94101f7abf5218cb0907c56cf11e29"],[305,"main","14c6a0568567034c80d1d9e353f109bc2c76e1f9"]]},{"repo":"ProjectLeonida/mandy","pairs":[],"pair_limit":12,"heads":[[2548,"main","61822f7c5e5e836623e63317d6cdcf758836ce3c"],[2547,"main","1f73cfa98240219bc7b6daf3267beae52a31407d"],[2541,"main","25d460ccb7a895351591a31ba2c6b87f656da245"],[2488,"main","13d94ba1a8199b79886b6f80f5f348e5d0d54e72"],[2522,"main","d411fe9b4a3aab2a75dfbed4d6e4f01d758ef668"],[2538,"main","243e536bd8fa3f36ea94deff725d3b509d73bb15"],[2537,"main","6ff203098302e11208b637ea15a84ccea15e78ef"],[2536,"main","f58e343f574e8db19965970a7cc5f9aa4faceeef"],[2535,"main","0f43a7804beec409cb294cfe7c866c3fca03f8bb"],[2405,"main","148996716b76d32f3a8f12d43670f2e0614685dc"],[2543,"main","4a83ecddcaa2194cff71a765be11ef0f31cacd3d"],[2480,"main","86b890ca172941547db57a3a7193e48d17ef088a"],[2540,"main","698d1ccebc204adcf35fd56fa9c3e615cf839501"],[2438,"main","ac3fb1b43c51c5aceecc3848531dc5465e420a58"],[2525,"main","d1b7d10c76d739125f0e050b52375dff7ab6f4b8"]]},{"repo":"LooperSalty/AnyXboxX","pairs":[],"pair_limit":12,"heads":[[574,"main","3fa09cd0e3ddb145b20abbe6adbef14bce803dbf"],[550,"main","b45603a0106c87fcbaaac893076d664144f30c44"],[458,"main","eb95bc39f5e2f3615c40669fb5ff327b00a5d824"],[554,"main","d9a5a93eca6284961bc60bc9546bbdaf3c230ab2"],[347,"main","ad702c51deb37cb65dba78873473b29475dc5c63"],[480,"main","02936d50c93e3e872457305aed1f89643e92b556"],[472,"main","6b5e5a5711c7b5a005f6acdf5a295deefafb5cb1"],[535,"main","f0162f923d921ac76776af663d1afc8393b71eb9"],[456,"main","1f0aae6f9c7704d3fcf4e5119b6d2bb2adf95aa4"],[350,"main","4142924be4a11181d8342f0180516da0b023e1cd"],[435,"main","d53b8fa689e15fc5673aff5afeb2c0fe55eee528"],[573,"main","a7ec4e74ca3363853bee532e6cc9865164a31d92"],[575,"main","c1ba64581b14885c4c565ec239bed149dd7677a9"],[434,"main","543cbc00ac5a7f82c7e6f4dd274be10cf65bfad8"]]},{"repo":"fxceless/victory-fork","pairs":[],"pair_limit":12,"heads":[[1496,"main","ee732dc02b23effce4b59df721c2f55adba14e0c"],[1333,"main","88efd7ea876f5d5771d95ff3b5f22c076f19ea2a"],[1433,"main","ca4e2a2968070b32411cde5831bc52d916891049"],[1460,"main","b656e5db7f1cffac84453dd816f6d071c104d5f1"],[1486,"main","e0c158bad40814295f9072d07b58fec7e3ab0566"],[1192,"main","cee1b7de2a608aafa6800d138c06f1fb94720ee6"],[1450,"main","17a6f01d7be53a3696614654a2fd970a37879b25"],[1481,"main","9b74145827b15c169cbe9ce646f51701eb78c390"],[1442,"main","c13e2a390930cacfa68fb27a3341445b18c71c2e"],[1458,"main","6dc6bb3962c8afebd12db5027a23ea35f374d85d"],[1006,"main","88fe30bd6e7130f1c7bd098b6dfa7e8990f81a2e"],[854,"main","7c9a2f988dc4ceb8e071ddc5792019b02ba4827e"],[1482,"main","68db5291130f201f83ea28160612474070bc2d49"],[1216,"main","4d983400a003a981817cde8da2df7e06bb77019b"],[1476,"main","e40825961be01faf0b7d695f28f0bf525c8f7b6e"],[1226,"main","b55f71372f2ee632392eafd3068c1fd8cdb03149"]]},{"repo":"KytyPS5/KytyPS5","pairs":[],"pair_limit":12,"heads":[[2141,"main","55ac48ae05a0f5acdde10128725ba045d33d4b21"],[2595,"main","ee689a10f2aec39106b257188e2a628c844486cd"],[1395,"main","cd09ff80ceef784e3ca4053561c6ab2dc3c305e5"],[1307,"main","d44a0511a5322bb4194b801fc31a9d9b55447d2e"],[1405,"main","222d83016cc9776711c1eebdf3c6c50b512c2fe5"],[1289,"main","b531f6f835f3a36e63afce1ef93a91dcf108f0de"],[1270,"main","4301dad64106828ea388b75a2cc33c6b79da2420"],[1294,"main","9490d7beb801f1ddbfbdbb0f00ab7911713d671c"],[2590,"main","52b3e3e5630b5a2603529b3d7cf422b85793a817"],[2358,"main","eee37fdc57620954d05d986138fd0fe30fb3f266"],[1444,"main","1f309cd5c38698a4a63e1fe86c3b91a1afbcc6ff"],[1295,"main","6771fea59469545da24b2a1a7ef9f4580995e73a"],[1197,"main","083a22278b341c5e8931ef26e6c9316da412c195"],[937,"main","2e9d07b97402222b721663c1a469cd94191c7f2d"]]},{"repo":"boykopovar/AnyPS5","pairs":[],"pair_limit":12,"heads":[[17943,"main","4a817932705b2a3ad4580e06b971423d401d1fd2"],[26819,"main","5b5c7676c98571a9d29888130ba839d6e1819169"],[27991,"main","7042da5d054c33622b5f9704acc964960d2305bc"],[26462,"main","d5b8d8e20a136fb7228eef2c10bf1f8f6b81fa85"],[27829,"main","b984d28314be17d09ab7906b921b049af5b67d9e"],[26196,"main","8f9a9cae20d7c67537df81e64ba09e9ce214f9b9"],[16018,"main","84f167f2a31b2f31607e5a75ac26f1bcad108d74"],[22546,"main","ee15f3ca0b96a511428bf954f7a09d3763474892"],[27451,"main","f0182fa9f516f6a44eb96e0fe62e0bb8970f94b8"],[22439,"main","d4c1ba3a31c0fdb1e7208da2a03ba2c301efb10c"],[27887,"main","9ece009800bac311e6b6bccdfb7b9d8014df3109"],[27986,"main","e7bd99dfcc128736bf1ffbb06e75dc10b8fb649c"]]},{"repo":"PastiiJay/klbf-lab","pairs":[],"pair_limit":12,"heads":[[16,"beta","f5a960cdccf8d3a027215de8a01dd7408e5b6077"],[59,"beta","7311cab076733171ad0b48402cde71c9448246ae"],[51,"beta","5810d6b5eccd603deb3d6ac34e8152637afdce46"],[113,"beta-2","0baad46e2048abad0f5855aef91eee13176e3002"],[72,"win10-test","54ca988330b6dcbceb3dd873afa43ef7c7674fbd"],[22,"beta","6b4569bd4df9bfe6d965d43a2d4faa79bd944b13"],[28,"beta","39ad8490478fa205f8f88a74acd237a1e517f97a"],[44,"beta","2e41aaf3281bf06d558da56030d54b3fa7248659"],[58,"beta","d29505a1d5a3eef400b75cc081d88b51bf6a5688"],[60,"beta","6f55eae05c4900b656ff5e723c7d685a3172ef3a"],[41,"beta","2b78ecaec13ddf505cb5a3c511992ecc23cdbc73"],[75,"win10-test","ad121fe90d3768ab030c633d120b89f1a020af84"],[27,"beta","06f4fccace3f6f6a87490afde34105b8b6a39603"],[37,"win10-test","3ecd80f610cf4954cc2377f328662e1fce600c0d"],[14,"beta","d18474523030d0bda09080b48dd52c3a197bead4"],[56,"beta","a7ed24211f2015c00bd537bbc5d21c580add5ab5"]]},{"repo":"shadps4-emu/shadPS4","pairs":[],"pair_limit":12,"heads":[[5772,"main","df2882152752e2ef5d782aa3c613e3754822a117"],[5779,"main","f3c7b459f62d4ef9843663c6e0f1c474bfd103d7"],[5770,"main","11e3ddaa57880564b69eee9909e1c2b3b2599b40"],[5190,"main","ba622f00bb2c3ff5e69eaaf40ee69f703c09f620"],[5773,"main","be61906542bf0f73203ee6d1e65e0f49d139ac21"],[5713,"main","1fbc0a6abb760a1e94110a207bee64b769d46201"],[5768,"main","6204747a11cdb65064bc173c118ec0bafd65dda1"],[5753,"main","4815716d334024e72a1c43cece677fb7f3022d0f"],[5310,"main","5cf71c8b86d6d729c77481819af6e7bac815248d"],[5738,"main","baaf6a38725c3de16cdfb40f77041e1f8d21856d"],[5739,"main","98505c3694c23ed595aee58016d3974844a414d3"],[5218,"main","feb8049ad62e33d10ac98ca28f6a3ec63b445755"],[5549,"main","31a6f09f10ce883141598c503fd27ba1cacc3a68"],[5745,"main","5edf35d3e5436e31e9fd4e3f062ed1c53c2ebc33"],[5762,"main","73be5dd4e5fbb562e70783a88c3821264aa703b8"],[5601,"main","1e6b241129b247fbbc6979d787dcc71c62429f4f"]]},{"repo":"doitsujin/dxvk","pairs":[],"pair_limit":2,"heads":[[5929,"master","42c5f9e54ab2daba22baa1680654e0df94cc79da"],[5828,"master","6863352615f3a7d5b2db6bf1be4544edd68265bb"]]},{"repo":"HansKristian-Work/vkd3d-proton","pairs":[],"pair_limit":2,"heads":[[3534,"master","c0a13a6686cf2e202f4e5d2c2925ff3434ff9303"],[3533,"master","8bdd434b7de0fd40c51027663bbe33f36c290bd3"],[3379,"master","dc2c1f7c7c409626c157ab2e0e0a7b5fcb7e437e"]]},{"repo":"microsoft/DirectXShaderCompiler","pairs":[],"pair_limit":2,"heads":[[8426,"main","49a7b9dbe117a91cc8601ae28b1afdbdfe621c90"],[8719,"main","857ed722cd8079eb86f4a75aa1d101df04d5eaf0"],[8057,"main","9157f8480424a2f6fd440f587858f65f566d01c5"]]},{"repo":"KhronosGroup/Vulkan-ValidationLayers","pairs":[],"pair_limit":2,"heads":[[13708,"main","b9fbaddcb2555adc5ef69b02128ed27905419748"],[13780,"main","642340b20a47f6e779239039b7a287c6aade2532"],[13756,"main","2690ef42d147fd1f0a9efbbf8ebd984c93f164a2"]]},{"repo":"RPCS3/rpcs3","pairs":[],"pair_limit":2,"heads":[[20042,"master","cf59a334c093479a9db8a67fad30053280e7fdd1"],[19785,"master","4bd55cc5cdfec0793fc1aa44daed82467a5671f9"],[19969,"master","eff65991c9318576d78201cbf2b13510abf9d0eb"]]}]''')
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
