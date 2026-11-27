"""Diagnose known misses by changing corpus coverage while keeping ranking fixed."""
import argparse
import json
from pathlib import Path
import sys


SOURCES = [
    {"origin":"https://github.com/TaynanGT/Vice-Tay/pull/193","repo":"llvm/llvm-project",
     "revision":"7ea8afa0a9ff7a59f79f0b4c70121d4cf4b0e4c9","path":"llvm/lib/Transforms/Scalar/LICM.cpp",
     "license":"Apache-2.0 WITH LLVM-exception","license_path":"llvm/LICENSE.TXT","expected":[1460,1475],
     "human_query":"LICM isSafeToSpeculativelyExecute isGuaranteedToExecute"},
    {"origin":"https://github.com/xcl-dev/xcl/pull/3001","repo":"ubiquitarianism/leonida",
     "revision":"95267b8c7bba786e356bef364dc25862a26ebab8","path":"scripts/check_precompile_verify.py",
     "license":"GPL-3.0","license_path":"LICENSE","expected":[114,170],
     "human_query":"cache hit verification journal driver require_hit"},
    {"origin":"https://github.com/ubiquitarianism/leonida/pull/2461","repo":"KhronosGroup/VK-GL-CTS",
     "revision":"65fff6ac4d782ad42a490b007376e84159a113e3",
     "path":"external/vulkancts/modules/vulkan/synchronization/vktSynchronizationTimelineSemaphoreTests.cpp",
     "license":"Apache-2.0","license_path":"LICENSE","expected":[1665,1706],
     "human_query":"timeline semaphore wait before signal submit queue"},
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product", type=Path)
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.product.resolve()))
    from portbridge import code_search
    from portbridge.catalog import ReadOnlyCatalog
    from portbridge.matching import canonical_url

    catalog = ReadOnlyCatalog(args.database)
    original = code_search.projection(catalog)
    rows = {canonical_url(row["url"]): row for row in catalog.observations(limit=None)}
    additions = []
    for source in SOURCES:
        reference = {key: source[key] for key in ("repo", "revision", "license", "path")}
        reference["license_url"] = f"https://github.com/{source['repo']}/blob/{source['revision']}/{source['license_path']}"
        additions.append(code_search.index_file(reference, code_search._fetch(reference)))
    augmented = {**original, "files": original["files"] + additions}

    results = []
    for source, added in zip(SOURCES, additions):
        origin = source["origin"]
        query = code_search.observation_query(rows[canonical_url(origin)])
        result = {**source, "content_sha256": added["sha256"], "license_url": added["license_url"]}
        for arm, index, title in (("released_query", original, query),
                                  ("source_added", augmented, query),
                                  ("manual_terms", augmented, source["human_query"])):
            hits = code_search.lookup(index, title, origin_url=origin)
            target = next(((rank, row) for rank, row in enumerate(hits, 1)
                           if row["path"] == source["path"] and row["repo"] == source["repo"]), None)
            result[arm] = {
                "rank": target[0] if target else None, "line": target[1]["line"] if target else None,
                "anchor_in_expected_range": bool(target and source["expected"][0] <= target[1]["line"] <= source["expected"][1]),
                "top5": [{"url": row["url"], "signals": row["signals"]} for row in hits],
            }
        results.append(result)
    print(json.dumps(results, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
