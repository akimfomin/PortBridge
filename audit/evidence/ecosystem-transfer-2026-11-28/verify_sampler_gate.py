"""Check the exact sampler/library policy and emit linkable source locations."""
import hashlib
import json
from pathlib import Path
import re
import urllib.request

ANY = "https://raw.githubusercontent.com/LooperSalty/AnyXboxX/daaffd4fc095d4122680d98dacaf91f28ed5d833/third_party/victory/crates/victory-gpu/src/pipeline/"
VICE = "https://raw.githubusercontent.com/TaynanGT/Vice-Tay/ca46856f8250ed0a2f79914fcf3f0d6f4a7ab842/crates/victory-gpu/src/pipeline/"
FILES = {
    "any-gate": (ANY+"host.rs", r"let use_library = samplers\.is_empty\(\) \|\| super::library::allows_static_samplers\(host\);"),
    "any-replay": (ANY+"host.rs", r"super::sampler_order::before\(&host\.device, &samplers\);"),
    "any-nvidia-override": (ANY+"library.rs", r'VICTORY_LIBRARY_STATIC_SAMPLERS"\)\.is_some_and'),
    "any-conditional-cache-name": (ANY+"host.rs", r"use_library\.then_some\(name\.as_str\(\)\)"),
    "vice-gate": (VICE+"host.rs", r"let use_library = samplers\.is_empty\(\)\s*\|\| super::library::allows_static_samplers\(host\)\s*\|\| samplers_settled;"),
    "vice-snapshot": (VICE+"samplers.rs", r"let _ = PRIMED\.set\(primed\);"),
    "vice-root-failure": (VICE+"samplers.rs", r"Err\(e\) => tracing::warn!"),
    "vice-published-keys": (VICE+"samplers.rs", r"seen\.get_or_insert_default\(\)\.extend\(new\);"),
}

def check_sources():
    bodies = {}
    result = {}
    for key, (url, pattern) in FILES.items():
        if url not in bodies:
            with urllib.request.urlopen(url, timeout=20) as response:
                bodies[url] = response.read(500_000)
        body = bodies[url].decode("utf-8")
        match = re.search(pattern, body)
        if match is None:
            raise AssertionError(f"missing evidence '{key}' at {url}")
        offset = body.count("\n", 0, match.start()) + 1
        owner, repo, sha, path = url.removeprefix("https://raw.githubusercontent.com/").split("/",3)
        result[key] = {
            "source": f"https://github.com/{owner}/{repo}/blob/{sha}/{path}#L{offset}",
            "file_sha256": hashlib.sha256(bodies[url]).hexdigest(),
        }
    return result

def warm_policy(enabled, keys, boot_order, failed_at=None):
    """Expected safety policy for an opt-in test, independent of the driver."""
    return not keys or (
        enabled and failed_at is None and set(keys) <= set(boot_order)
    )

def check_test_vectors():
    rows = [
        ("empty root", False, (), (), None, True),
        ("flag off, listed sampler", False, ("linear",), ("linear",), None, False),
        ("first launch", True, ("linear",), (), None, False),
        ("new sampler after replay", True, ("linear","point"), ("linear",), None, False),
        ("next launch after rediscovery", True, ("linear","point"), ("linear","point"), None, True),
        ("replayed but one root was refused", True, ("point",), ("linear","point"), 0, False),
        ("point/clamp is a different key", True, ("point-clamp",), ("point-wrap",), None, False),
    ]
    results = {}
    for label, enabled, keys, boot_order, fail_at, expected in rows:
        actual = warm_policy(enabled, keys, boot_order, fail_at)
        if actual != expected:
            raise AssertionError(label)
        results[label] = actual
    return results

if __name__=="__main__":
    print(json.dumps({"source_checks":check_sources(),"expected_policy_vectors":check_test_vectors()},indent=2))

