import argparse
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import os
import re

RECEIVER = "95e1ca80b56865b3bf2654f27c7550b05a8d54a9"
BASE = "63b902fe1720a5188ee79d94a88c8de0470f6349"
PRS = {
    1017: "52a4c6f6f43b2d831084b072924c9da01ac896fe",
    1018: "c100068f09fd19e0be3f0d7452e2bec208d04444",
    1015: "7a6729d9847562ca7b5f0d906aa5dc8a34b59f48",
}
LIBRARY = "crates/victory-gpu/src/pipeline/library.rs"
PIXEL = "crates/victory-gpu/src/replay/play/pixel.rs"
RESOURCE = "crates/victory-gpu/src/resource.rs"

def compare(patch_directory=None):
    env = {k:v for k,v in os.environ.items() if not k.startswith(("GIT_","SSH_"))}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_ATTR_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
    with TemporaryDirectory(prefix="pb-altracing-") as directory:
        def git(*args, data=None):
            p = subprocess.run(
                ["git", "-c", "protocol.allow=never", "-c", "protocol.https.allow=always", *args],
                cwd=directory, env=env, input=data, capture_output=True, timeout=100,
            )
            if p.returncode:
                raise RuntimeError(p.stderr.decode(errors="replace").strip())
            return p.stdout
        git("init","--quiet","--bare","--template=")
        alt = "https://github.com/whoalin1/victory-altracing.git"
        nvidia = "https://github.com/trustno1-coder/VIctory-NVIDIA.git"
        options = ("--quiet","--filter=blob:none","--no-tags","--no-recurse-submodules")
        git("fetch",*options,alt,RECEIVER)
        git("fetch",*options,nvidia,BASE,*PRS.values())
        deltas = {
            pr:git("diff","--binary","--no-ext-diff",BASE,head,"--","crates")
            for pr,head in PRS.items()
        }
        if patch_directory is not None:
            patch_directory.mkdir()
            for pr, delta in deltas.items():
                with (patch_directory / f"nvidia-{pr}.patch").open("xb") as output:
                    output.write(delta)
        rows=[]
        for order in [(1017,1018),(1018,1017),(1017,1018,1015),(1015,1018,1017)]:
            git("read-tree",RECEIVER)
            for pr in order:
                git("apply","--cached","--check","--whitespace=error-all",data=deltas[pr])
                git("apply","--cached","--whitespace=error-all",data=deltas[pr])
            tree = git("write-tree").decode().strip()
            fixtures={}
            for tag,file in {"replay":PIXEL,"publication":RESOURCE,"cache":LIBRARY}.items():
                source=git("show",tree+":"+file).decode("utf-8")
                fixtures[tag]={
                    "path":file,
                    "test_functions":[n for n in re.findall(r"fn (\w+)\(",source)
                                      if re.search("depth_probe_reads|a_depth_planes_twin_is_drawn_into_the_plane|adapter_dir",n)],
                }
            rows.append(dict(order=order,tree=tree,fixtures=fixtures))
        assert rows[0]["tree"]==rows[1]["tree"]
        assert rows[2]["tree"]==rows[3]["tree"]
        assert rows[0]["tree"]!=rows[2]["tree"]
        # Existing resource test can return early without exercising the device.
        # Add strict checks to the test fixture only; the source trials above
        # still use the exact, unmodified PR deltas.
        joined_tree = rows[0]["tree"]
        git("read-tree", joined_tree)
        source = git("show", joined_tree+":"+RESOURCE).decode("utf-8")
        tag = "    fn a_depth_planes_twin_is_drawn_into_the_plane() {"
        begin = source.index(tag)
        end = source.index("        // SAFETY: live resources.", begin)
        fixture = source[begin:end]
        for old, replacement in [
            ("        let Some(host) = crate::host::host() else {\n"
             "            return; // no host GPU here\n"
             "        };",
             "        let host = crate::host::host().expect(\"a physical host is required\");\n"
             "        use windows::Win32::Graphics::Dxgi::{CreateDXGIFactory2, DXGI_ADAPTER_FLAG_SOFTWARE, DXGI_CREATE_FACTORY_FLAGS, IDXGIAdapter1, IDXGIFactory4};\n"
             "        // SAFETY: these are read-only queries on the device selected by the test.\n"
             "        let desc = unsafe {\n"
             "            let factory: IDXGIFactory4 = CreateDXGIFactory2(DXGI_CREATE_FACTORY_FLAGS(0)).unwrap();\n"
             "            let adapter: IDXGIAdapter1 = factory.EnumAdapterByLuid(host.device.GetAdapterLuid()).unwrap();\n"
             "            adapter.GetDesc1().unwrap()\n"
             "        };\n"
             "        assert_eq!(desc.VendorId, 0x10de, \"physical NVIDIA required\");\n"
             "        assert_eq!(desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE.0 as u32, 0, \"software adapter\");"),
            ("        let Some(plane) = twin_plane_resource(depth) else {\n"
             "            return; // these twins are turned off\n"
             "        };",
             "        let plane = twin_plane_resource(depth).expect(\"depth-plane twins must be enabled\");"),
        ]:
            assert fixture.count(old) == 1
            fixture = fixture.replace(old, replacement)
        modified = (source[:begin] + fixture + source[end:]).encode("utf-8")
        blob = git("hash-object","-w","--stdin",data=modified).decode().strip()
        git("update-index","--cacheinfo",f"100644,{blob},{RESOURCE}")
        strict = git("diff","--cached","--binary","--no-ext-diff",joined_tree,"--",RESOURCE)
        assert strict
        strict_tree = git("write-tree").decode().strip()
        if patch_directory is not None:
            with (patch_directory / "strict-depth-fixture.patch").open("xb") as output:
                output.write(strict)
        return {"receiver":RECEIVER,"upstream_base":BASE,"pull_heads":PRS,
                "patch_sha256":{pr:hashlib.sha256(d).hexdigest() for pr,d in deltas.items()},
                "combined_trees":rows,"strict_hardware_fixture_tree":strict_tree,
                "strict_hardware_fixture_sha256":hashlib.sha256(strict).hexdigest(),
                "compiled":False,"physical_gpu":False}

if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--patch-dir", type=Path, help="write the three source deltas and the strict test-only delta to a new directory")
    args = parser.parse_args()
    print(json.dumps(compare(args.patch_dir),indent=2))

