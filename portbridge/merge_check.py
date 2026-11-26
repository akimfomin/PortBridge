"""Compare a public GitHub pull request head with a pinned receiving commit."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic
from urllib.parse import quote, urlsplit

from .action_summary import source_link
from .github import PR_URL
from .matching import current_repository
from .preflight import public_preflight


SHA = re.compile(r"[0-9a-f]{40}")
TIME_LIMIT = 65


def paths(raw):
    return [item.decode("utf-8", errors="replace") for item in raw.split(b"\0") if item]


def changed_paths(raw):
    changed = paths(raw)
    tests = [path for path in changed if re.search(r"(^|/)(tests?(/|[_.-])|[^/]*[_-]tests?\.)", path, re.I)]
    return changed[:25], tests[:8]


def compare(url, target):
    if not isinstance(url, str) or len(url) > 500 or not PR_URL.fullmatch(url):
        raise ValueError("Enter a public GitHub pull request URL")
    if not isinstance(target, str) or not SHA.fullmatch(target):
        raise ValueError("Enter a full lowercase receiving commit SHA from the PR repository")
    owner, name, _, number = urlsplit(url).path.strip("/").split("/")
    public_repo = f"https://github.com/{current_repository(f'{owner}/{name}')}"
    pull_ref = f"refs/pull/{number}/head"
    result = {"url": url, "target": target, "status": "unverified",
              "conflicts": [], "changed_files": [], "changed_tests": []}
    # Read repository data in a bare repository without local Git configuration, templates or hooks.
    env = {key: val for key, val in os.environ.items() if not key.startswith(("GIT_", "SSH_"))}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_ATTR_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
    deadline = monotonic() + TIME_LIMIT
    with TemporaryDirectory(prefix="portbridge-merge-") as folder:
        def git(*args):
            return subprocess.run(["git", "-c", "http.followRedirects=false", "-c", "protocol.allow=never",
                                   "-c", "protocol.https.allow=always", *args], cwd=folder, env=env,
                                  stdin=subprocess.DEVNULL, capture_output=True, timeout=max(0.25, deadline - monotonic()))

        if git("init", "--quiet", "--bare", "--template=").returncode:
            return {**result, "reason": "Git could not initialize the temporary repository"}
        # Full commit ancestry avoids a false clean result at a shallow boundary.
        if git("remote", "add", "origin", public_repo + ".git").returncode:
            return {**result, "reason": "Git could not register the public source"}
        fetched = git("fetch", "--quiet", "--no-tags", "--no-recurse-submodules", "--filter=blob:none", "origin",
                      f"+{pull_ref}:refs/compare/head", f"+{target}:refs/compare/target")
        if fetched.returncode:
            return {**result, "reason": "Git could not fetch both revisions from this public repository"}
        captured = git("rev-parse", "refs/compare/head", "refs/compare/target").stdout.decode().splitlines()
        if len(captured) != 2 or captured[1] != target or not SHA.fullmatch(captured[0]):
            return {**result, "reason": "Git did not resolve the two requested commits"}
        head = result["head"] = captured[0]
        advertised = git("ls-remote", "--exit-code", "--refs", "origin", pull_ref)
        if advertised.returncode or advertised.stdout.strip() != f"{head}\t{pull_ref}".encode("ascii"):
            return {**result, "reason": "The public PR head moved or could not be rechecked"}
        common = git("merge-base", target, head)
        if common.returncode:
            return {**result, "reason": "Git could not find a common ancestor"}

        base = common.stdout.decode().strip()
        if not SHA.fullmatch(base):
            return {**result, "reason": "Git did not return a comparable merge base"}
        result["merge_base"] = base
        changed = git("diff", "--no-ext-diff", "--diff-filter=AMR", "--name-only", "-z", base, head)
        if changed.returncode == 0:
            result["changed_files"], result["changed_tests"] = changed_paths(changed.stdout)
        merged = git("merge-tree", "--write-tree", "--name-only", "--no-messages", "-z", target, head)
        output = paths(merged.stdout)
        if merged.returncode not in (0, 1) or not output or not SHA.fullmatch(output[0]):
            return {**result, "reason": "Git could not finish the three-way tree comparison"}
        tree, *conflicts = output
        if merged.returncode == 1:
            if not conflicts:
                return {**result, "reason": "Git did not report paths for the conflict"}
            result.update(status="conflict", conflicts=conflicts[:25])
        else:
            previous_tree = git("rev-parse", f"{target}^{{tree}}").stdout.decode().strip()
            if not SHA.fullmatch(previous_tree):
                return {**result, "reason": "Git could not resolve the receiving commit tree"}
            result["status"] = "no tree changes" if previous_tree == tree else "clean merge"
        result["file_evidence"] = [
            f"{public_repo}/blob/{target}/{quote(path, safe='/')}" for path in result["conflicts"]
            if git("cat-file", "-t", f"{target}:{path}").stdout.strip() == b"blob"
        ]
    result["receiving_commit_url"] = f"{public_repo}/commit/{target}"
    result["head_url"] = f"{url}/commits/{head}"

    return result


def report(url, target):
    outcome = compare(url, target)
    if outcome["status"] == "unverified":
        return outcome

    test_paths = outcome.pop("changed_tests")
    head_repo = outcome["receiving_commit_url"].split("/commit/")[0]
    outcome["test_files"] = [f"{head_repo}/blob/{outcome['head']}/{quote(path, safe='/')}" for path in test_paths]
    step = ("Resolve the reported paths on a disposable branch. " if outcome["conflicts"] else "")
    outcome["next_test"] = step + (
        "Start with the changed test linked here. Run it and its negative control at the exact resulting revision."
        if test_paths else "Choose an acceptance test with the author and run it at the exact resulting revision.")
    try:
        catalog = public_preflight(url=url, limit=3)
        check = catalog.get("first_check")
        outcome["catalog_status"] = catalog.get("catalog_status")
        if check and source_link("reported test", check.get("url", "")):
            outcome["reported_test"] = check["url"]
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        outcome["catalog_status"] = "unavailable"
    return outcome


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pull_request", nargs="?", default=os.environ.get("PORTBRIDGE_PR_URL"))
    parser.add_argument("target", nargs="?", default=os.environ.get("PORTBRIDGE_TARGET_SHA"))
    args = parser.parse_args()
    try:
        result = report(args.pull_request, args.target)
    except (OSError, subprocess.TimeoutExpired, TypeError, ValueError, KeyError):
        result = {"status": "unverified", "reason": "Input, public metadata, Git or time budget could not be verified"}
    links = [source_link(title, result.get(key, "")) for title, key in (
        ("PR source", "url"), ("Receiving commit", "receiving_commit_url"), ("PR head", "head_url"),
        ("Catalog test (verify its scope)", "reported_test"))]
    links.extend(source_link("Conflicting file on receiving revision", url) for url in result.get("file_evidence", []))
    links.extend(source_link("Changed test on PR head", url) for url in result.get("test_files", []))
    payload = json.dumps(result, indent=2, ensure_ascii=True).replace(chr(96), r"\u0060")
    fence = chr(96) * 3
    output = f"## PortBridge merge check\n\n**{result['status']}**\n\n"
    output += "\n".join(f"- {link}" for link in links if link)
    if next_test := result.get("next_test"):
        output += f"\n\n{next_test}"
    output += f"\n\n{fence}json\n{payload}\n{fence}\n"
    destination = os.environ.get("GITHUB_STEP_SUMMARY")
    if destination:
        with Path(destination).open("a", encoding="utf-8") as stream:
            stream.write(output)
    else:
        print(output)


if __name__ == "__main__":
    main()
