# SPDX-License-Identifier: MIT
"""Compare target-width and destination-sensitive HLSL ballot lowering on prepared legal inputs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from scan_wave32_corpus import ballot_sites


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(args):
    cases = []
    excluded = []
    for manifest in args.corpus:
        data = json.loads(manifest.read_bytes())
        if "rows" in data:
            inputs = data["rows"]
            for row in inputs:
                if "changed_sites" not in row:
                    excluded.append([row["source"], row.get("exclusion", "unavailable")])
                    continue
                cases.append((row["source"], row["source_sha256"], row["guest_sha256"],
                              manifest.parent / f"{row['index']:03}" / "shader.rdna2", row["abi"]))
        else:
            for i, row in enumerate(data["observations"]):
                rdna = row.get("rdna")
                if not rdna or row.get("error"):
                    excluded.append([row["source"], str(row.get("error"))])
                    continue
                cases.append((row["source"], row["source_sha256"], rdna["sha256"],
                              manifest.parent / f"{i:03}" / "shader.rdna2", rdna))
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, source_hash, guest_hash, body, abi in cases:
            if sha(body) != guest_hash or abi["wave"] != 32:
                raise ValueError(f"unmatched guest input for {name}")
            calls = {}
            row = {"source": name, "source_sha256": source_hash, "rdna_sha256": guest_hash, "arms": {}}
            for arm in ("stock", "width", "precise"):
                out = Path(tmp)/f"{arm}.hlsl"
                params = [str(abi[k]) for k in ("wave","spi_ps_input_ena","interpolants","color_mask","depth_mode")]
                subprocess.run([str(getattr(args, arm).resolve()), str(body), str(out), *params, "root-4", "generic", "hlsl"],
                               capture_output=True, check=True, timeout=20)
                calls[arm] = ballot_sites(out.read_text(encoding="utf-8"))
                row["arms"][arm] = {"hlsl_sha256": sha(out), "hlsl_bytes": out.stat().st_size,
                                    "calls": dict(Counter(x for lst in calls[arm].values() for x in lst))}
            if calls["stock"].keys() != calls["width"].keys() or calls["stock"].keys() != calls["precise"].keys():
                raise AssertionError("different guest PCs")
            sites = []
            for site in calls["stock"]:
                a, b, c = (calls[k][site] for k in ("stock","width","precise"))
                if a != b or a != c:
                    if any(orig != "ballot_px_local" and new == "ballot_px_local" for orig,new in zip(a,c,strict=True)):
                        raise AssertionError("new local-only assumption")
                    sites.append({"pc":site[0], "isa":site[1], "stock":a, "width":b,"precise":c})
            row["differences"] = sites
            rows.append(row)
    report = {"tools":{k:sha(getattr(args,k)) for k in ("stock","width","precise")},
              "manifests":[{"file":m.name,"sha256":sha(m)} for m in args.corpus],
              "programs":len(rows),"excluded_before_comparison":len(excluded),"rows":rows}
    for arm in ("width","precise"):
        report[arm+"_changed_sites"] = sum(s["stock"] != s[arm] for r in rows for s in r["differences"])
        report[arm+"_changed_programs"] = sum(r["arms"]["stock"]["hlsl_sha256"] != r["arms"][arm]["hlsl_sha256"] for r in rows)
    args.output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print({k:v for k,v in report.items() if k not in ("tools","manifests","rows")})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("stock","width","precise","output"):
        p.add_argument("--"+k, type=Path, required=True)
    p.add_argument("--corpus", type=Path, nargs="+", required=True)
    main(p.parse_args())
