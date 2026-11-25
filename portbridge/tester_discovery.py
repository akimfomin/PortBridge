"""Find public hardware reporters in a fixed set of project test threads."""

import argparse
from datetime import datetime, timedelta, timezone
from functools import partial
import json
import re
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, build_opener

from .activity import source_time
from .github import API, NoRedirect


# GitHub places pull request conversation comments under its issues endpoint.
XCL_GPU = ("xcl-dev/xcl", "issues", 42)
XCL_PERMUTE = ("xcl-dev/xcl", "pull", 925)
XCL_FMA = ("xcl-dev/xcl", "pull", 1100)
XCL_DISPATCH = ("xcl-dev/xcl", "pull", 2080)
XCL_SCRATCH = ("xcl-dev/xcl", "pull", 2126)
INTEL_WAVE32 = "d3d12-wave32"
INTEL_TESTS = {
    XCL_SCRATCH: ("dispatch_chain_payload_skips_middle_piece", "dispatch_chain_payload_survives_reused_edge_slot"),
    XCL_DISPATCH: ("dispatch_chain_wave32_live_loops",),
}
REFORGE_PRESENT = ("LeonidaReforge/Leonida", "pull", 86)
CONTINUED_RECT = ("ubiquitarianism/leonida", "pull", 207)
CONTINUED_LAZY = ("ubiquitarianism/leonida", "pull", 511)
CONTINUED_D16 = ("ubiquitarianism/leonida", "pull", 265)

NATIVE_THREADS = (XCL_PERMUTE, XCL_FMA, XCL_GPU)
THREADS = {
    "d3d12-native-wave64": NATIVE_THREADS,
    "d3d12-native-wave64-rdna4": NATIVE_THREADS,
    "win32-vulkan-1.3": (REFORGE_PRESENT,),
    "win32-vulkan-geometry": (CONTINUED_RECT, CONTINUED_LAZY),
    "python-cpu": (CONTINUED_D16,),
}
GPU_THREADS = (XCL_GPU, XCL_PERMUTE, XCL_FMA, REFORGE_PRESENT, CONTINUED_RECT, CONTINUED_LAZY)
THREAD_TESTS = {
    XCL_GPU: ("gpu_wave32_program_in_wave64_hardware",),
    XCL_PERMUTE: ("gpu_ds_permute_b32", "gpu_wave32_program_in_wave64_hardware"),
    XCL_FMA: ("gpu_fma_f32_abs_neg_clamp_oracle", "gpu_wave32_program_in_wave64_hardware"),
    REFORGE_PRESENT: ("vk_presenter_sync_test", "vk_presenter_sync"),
    CONTINUED_RECT: ("d3d12_rect_list_test", "d3d12_rect_list"),
    CONTINUED_LAZY: ("d3d12_rect_list_test", "d3d12_rect_list"),
    CONTINUED_D16: ("test_wave64_halves_partial_dst", "ps_wave64_d16_xyz"),
}

PER_PAGE = 60
MAX_REQUESTS = 6
REPORT_AGE = timedelta(days=90)
MAX_BODY = 12_000
MAX_REPLY = 2 * 1024 * 1024
TIMEOUT = 4
LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}")
AMD_GPU = re.compile(r"\b(?:AMD\s+)?(?:Radeon\s+)?RX\s+(\d{4})(?:\s+(XTX|XT|GRE|M))?\b", re.I)
NVIDIA_GPU = re.compile(
    r"\b(?:NVIDIA\s+)?(?:GeForce\s+)?(RTX|GTX)\s+(\d{3,4})"
    r"(?:\s+(Ti))?(?:\s+(SUPER))?(?:\s+(Laptop)(?:\s+GPU)?)?\b", re.I,
)
# Radeon RX 9000 models use RDNA 4: https://www.amd.com/en/products/graphics/desktops/radeon.html
RDNA4_GPU = re.compile(r"AMD Radeon RX 90\d0\b")
INTEL_ARC = re.compile(r"\b(?:Intel\s+)?Arc(?:\s*\(TM\)|™)?\s+([AB]\d{3}M?)\b", re.I)
WAVE32 = re.compile(r"\bwave\s*32\b|\b32[- ]lane(?:\s+wave)?\b", re.I)
WAVE32_RUN = re.compile(
    r"\bwave\s*32\b[^.]{0,80}\b(?:issued|ran|executed)\b"
    r"|\b(?:ran|executed)\b[^.]{0,80}\bwave\s*32\b", re.I,
)
SINGLE_PASS = re.compile(r"^1 passed, 0 failed, 0 ignored, 0 (?:GPU |explicit )?skips?\b", re.I)
WINDOWS = re.compile(r"\bWindows\s+(?:10|11)\b", re.I)
NON_WINDOWS = re.compile(r"\b(?:Linux|Ubuntu|Fedora|Arch|Wine|Proton|WSL)\b", re.I)
NATIVE_WAVE64 = re.compile(r"\bnative\s+(?:wave\s*64|64[- ]lane\s+waves?)\b|\bwave64\s+split\s*=\s*false\b", re.I)
NO_NATIVE_WAVE64 = re.compile(
    r"\b(?:no|without|skip(?:ped)?|not\s+tested)\b[^.\n]*\b(?:native\s+)?wave\s*64\b"
    r"|\bnative\s+wave\s*64\s+(?:unavailable|unsupported|not available)\b"
    r"|\b(?:only\s+split\s+wave\s*64|split\s+wave\s*64\s+only)\b", re.I,
)
VULKAN_13 = re.compile(r"\bVulkan\s+1\.3(?:\.\d+)?\b", re.I)
PASS = re.compile(r"\b(?:pass(?:es|ed)?|ok|green|success(?:ful)?)\b", re.I)
FAIL = re.compile(
    r"\b(?:fail(?:ed|s|ures?)?|skip(?:ped|s)?|not\s+(?:run|tested|passing|a pass)|timeout)\b"
    r"|\b(?:not|never|didn['’]t|doesn['’]t)\s+pass\b", re.I,
)
ZERO_FAILURES = re.compile(r"\b(?:0|no|without)\s+(?:failed|failures?|skips?|skipped)\b", re.I)
HYPOTHETICAL = re.compile(
    r"\b(?:would|could|should|please|plan to|expected to|if you|someone|your|their|according to|reported by"
    r"|on behalf of|another tester|(?:my|our) (?:colleague|teammate|friend))\b", re.I,
)
SETUP = re.compile(r"^(?:hardware|machine|setup|environment|test(?:ed| run)?|verified|stack|platform|gpu|os|on|my|i\s+(?:ran|tested|reproduced))\b", re.I)
END_REPORT = re.compile(r"^(?:not tested|negative controls?|next steps?|questions?|ai use)\b", re.I)
PYTHON = re.compile(r"\bPython\s+(3\.\d+(?:\.\d+)?)\b", re.I)


def report_lines(body, *, preserve_blank=False):
    body = re.sub(r"<!--.*?(?:-->|$)", "", body, flags=re.S)
    body = re.sub(r"<(blockquote|details|pre)\b[^>]*>.*?(?:</\1\s*>|$)", "", body, flags=re.I | re.S)
    fence = ""
    for raw in body.splitlines():
        line = raw.strip()
        if marker := re.match(r" {0,3}([`]{3,}|~{3,})(.*)", raw):
            if not fence:
                fence = marker[1]
            elif fence[0] == marker[1][0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = ""
            continue
        if fence or line.startswith((">", "<")) or raw.startswith(("    ", "\t")):
            continue
        if not line:
            if preserve_blank:
                yield ""
            continue
        line = line.lstrip("#*- ").replace("**", "").replace("`", "")
        if END_REPORT.match(line):
            if NO_NATIVE_WAVE64.search(line):
                yield line
            break
        yield line


def _pass_lines(lines, test_names):
    names = re.compile(r"(?<![\w-])(?:" + "|".join(map(re.escape, test_names)) + r")(?![\w-])", re.I)
    for line in lines:
        match = names.search(line)
        if (match and PASS.search(line[match.end():]) and not FAIL.search(ZERO_FAILURES.sub("", line))
                and not HYPOTHETICAL.search(line)):
            yield line


def _setup_lines(lines):
    return [line for i, line in enumerate(lines) if (i < 4 or SETUP.match(line))
            and not HYPOTHETICAL.search(line) and not FAIL.search(ZERO_FAILURES.sub("", line))]


def _windows_gpu(lines, *, include_intel=False):
    # Hardware must appear in a setup line or the beginning of the report.
    setup = _setup_lines(lines)
    if not any(WINDOWS.search(line) for line in setup):
        return None
    if any(NON_WINDOWS.search(re.sub(r"\bno\s+(?:Wine|Proton)\b", "", line, flags=re.I)) for line in setup):
        return None
    models = set()
    for line in setup:
        for model, variant in AMD_GPU.findall(line):
            hardware = f"AMD Radeon RX {model}{' ' + variant.upper() if variant else ''}"
            models.add(("amd", hardware))
        if include_intel:
            models.update(("intel", f"Intel Arc {model.upper()}") for model in INTEL_ARC.findall(line))
        for family, model, ti, super_model, laptop in NVIDIA_GPU.findall(line):
            hardware = " ".join(filter(None, ("NVIDIA GeForce", family.upper(), model,
                                              "Ti" if ti else "", super_model.upper(), "Laptop GPU" if laptop else "")))
            models.add(("nvidia", hardware))
    return next(iter(models)) if len(models) == 1 else None


def _capabilities(thread, equipment, hardware, lines):
    passed = list(_pass_lines(lines, THREAD_TESTS[thread]))
    setup = _setup_lines(lines)
    found = []
    if thread in NATIVE_THREADS and equipment == "amd" and passed:
        native = any(NATIVE_WAVE64.search(line) for line in passed)
        if native and not any(NO_NATIVE_WAVE64.search(ZERO_FAILURES.sub("", line)) for line in lines):
            found.append("d3d12-native-wave64")
            if RDNA4_GPU.match(hardware):
                found.append("d3d12-native-wave64-rdna4")
    if thread in THREADS["win32-vulkan-1.3"] and passed and any(VULKAN_13.search(line) for line in setup + passed):
        found.append("win32-vulkan-1.3")
    if thread in THREADS["win32-vulkan-geometry"] and passed:
        found.append("win32-vulkan-geometry")
    return found, bool(passed)


def _intel_report(lines, thread):
    # Read setup only where the report explicitly says what was tested, or in
    # the usual opening setup fields when it has no separate Tested heading.
    start = next((index + 1 for index, line in enumerate(lines) if line.casefold() == "tested"), 0)
    gpu = _windows_gpu(lines[start:start + 4] if start else lines, include_intel=True)
    if gpu is None or gpu[0] != "intel":
        return None
    tests = INTEL_TESTS[thread]
    # A named result row can prove the case directly. Some single-case
    # reports name the run above its explicit pass/fail/skip summary.
    for line in lines:
        cells = [part.strip() for part in line.strip("|").split("|")]
        if (line.startswith("|") and len(cells) == 4 and cells[0] in tests and WAVE32.search(cells[1])
                and re.fullmatch(r"1\s*/\s*0\s*/\s*0\s*/\s*0", cells[-1])):
            return gpu[1]
    setup = lines[start:start + 4]
    names = [name for line in setup for name in tests
             if re.search(rf"\b{re.escape(name)}\s+ran\s+on\b", line, re.I)
             and not HYPOTHETICAL.search(line) and not FAIL.search(ZERO_FAILURES.sub("", line))]
    if len(names) == 1 and any(SINGLE_PASS.match(line) and WAVE32_RUN.search(line) for line in lines):
        return gpu[1]
    return None


def _candidate(comment, thread, equipment, required):
    if not isinstance(comment, dict) or comment.get("minimized") is True:
        return None
    ident = comment.get("id")
    user = comment.get("user")
    body = comment.get("body")
    reported = source_time(comment.get("created_at"))
    if (type(ident) is not int or ident <= 0 or not isinstance(user, dict) or user.get("type") != "User"
            or not isinstance(body, str) or len(body) > MAX_BODY or reported is None):
        return None
    login = user.get("login")
    if not isinstance(login, str) or not LOGIN.fullmatch(login):
        return None
    repo, kind, number = thread
    evidence_url = f"https://github.com/{repo}/{kind}/{number}#issuecomment-{ident}"
    expected = {"url": f"{API}/repos/{repo}/issues/comments/{ident}",
                "issue_url": f"{API}/repos/{repo}/issues/{number}", "html_url": evidence_url}
    if (any(not isinstance(comment.get(key), str) or comment[key].casefold() != value.casefold()
            for key, value in expected.items()) or str(user.get("html_url")).casefold() != f"https://github.com/{login}".casefold()):
        return None

    lines = list(report_lines(body))
    if equipment == "cpu":
        if thread != CONTINUED_D16 or not any(_pass_lines(lines, THREAD_TESTS[thread])):
            return None
        python = PYTHON.search("\n".join(lines))
        if python is None:
            return None
        hardware, capabilities = f"Python {python[1]} on CPU", ["python-cpu"]
    elif equipment == "intel":
        hardware = _intel_report(lines, thread)
        if hardware is None:
            return None
        capabilities = [INTEL_WAVE32]
    else:
        gpu = _windows_gpu(lines)
        if gpu is None or gpu[0] != equipment:
            return None
        hardware = gpu[1]
        capabilities, exact_pass = _capabilities(thread, equipment, hardware, lines)
        suite_pass = thread == XCL_GPU and any(
            "cargo test --workspace" in line and re.search(r"\b[1-9]\d*\s+passed[;,]\s*0\s+failed\b", line, re.I)
            and not HYPOTHETICAL.search(line) for line in lines
        )
        if not exact_pass and not suite_pass:
            return None
    if not required.issubset(capabilities):
        return None
    return {"login": login, "equipment": equipment, "hardware": hardware, "capabilities": capabilities,
            "evidence_url": evidence_url, "reported_at": reported.isoformat(timespec="seconds").replace("+00:00", "Z")}


def _last_page(link):
    match = re.search(r'<([^>]+)>;\s*rel="last"', link)
    if match:
        parsed = urlsplit(match[1])
        values = parse_qs(parsed.query).get("page", [])
        if parsed.scheme == "https" and parsed.netloc == "api.github.com" and len(values) == 1:
            page = values[0]
            if re.fullmatch(r"[1-9][0-9]{0,5}", page):
                return int(page)
    return 1


def _public_get(opener, path):
    request = Request(API + path, headers={"Accept": "application/vnd.github+json", "User-Agent": "PortBridge Test Lab"})
    with opener.open(request, timeout=TIMEOUT) as response:
        payload = response.read(MAX_REPLY + 1)
        last_page = _last_page(response.headers.get("Link", ""))
    if len(payload) > MAX_REPLY:
        raise ValueError("GitHub report response exceeds size limit")
    return json.loads(payload), last_page


def _report_page(get, path):
    try:
        rows, last_page = get(path)
    except (OSError, TypeError, ValueError):
        return [], 1
    if not isinstance(rows, list) or len(rows) > PER_PAGE:
        return [], 1
    return rows, last_page if type(last_page) is int and 1 <= last_page <= 999999 else 1


def discover_testers(equipment, capabilities=(), *, for_review=False, public_get=None, now=None):
    """Return matching recent self-reports without storing or returning their prose."""
    required = frozenset((capabilities,)) if isinstance(capabilities, str) else frozenset(capabilities or ())
    if equipment == "intel":
        if not for_review or required - {INTEL_WAVE32}:
            return []
        threads = tuple(INTEL_TESTS)
    else:
        if equipment not in {"amd", "nvidia", "cpu"} or required.difference(THREADS):
            return []
        if required:
            threads = tuple(dict.fromkeys(thread for capability in sorted(required) for thread in THREADS[capability]))
        else:
            threads = (CONTINUED_D16,) if equipment == "cpu" else GPU_THREADS
    if public_get is None:
        public_get = partial(_public_get, build_opener(NoRedirect()))

    cutoff = (now or datetime.now(timezone.utc)) - REPORT_AGE
    params = urlencode({"per_page": PER_PAGE, "since": cutoff.isoformat(timespec="seconds").replace("+00:00", "Z")})
    remaining = MAX_REQUESTS
    candidates = {}
    for repo, kind, number in threads:
        if not remaining:
            break
        remaining -= 1
        path = f"/repos/{repo}/issues/{number}/comments?{params}"
        rows, last_page = _report_page(public_get, path)
        if remaining and last_page > 1:
            remaining -= 1
            recent, _ = _report_page(public_get, f"{path}&page={last_page}")
            rows = rows + recent
        for comment in rows:
            row = _candidate(comment, (repo, kind, number), equipment, required)
            if row is None or source_time(row["reported_at"]) < cutoff:
                continue
            key = row["login"].casefold()
            if key not in candidates or row["reported_at"] > candidates[key]["reported_at"]:
                candidates[key] = row
    return sorted(candidates.values(), key=lambda row: (row["reported_at"], row["login"].casefold()), reverse=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Review public Intel Arc Wave32 reports from selected XCL discussions.")
    parser.parse_args(argv)
    candidates = discover_testers("intel", INTEL_WAVE32, for_review=True)
    print(json.dumps({"mode": "human_review", "candidates": candidates}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
