"""Read-only browser check for PortBridge's published linked views."""
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import urlencode


SITE = "https://akimfomin.github.io/PortBridge/"
PR = "https://github.com/R0Y00/Xbox2Windows/pull/3255"
CASES = {
    "sources filter": ("?lang=en#/sources?project=xcl&kind=pr", ('class="source-list"', "#/matches?q=")),
    "sources empty": ("?lang=en#/sources?q=zz-unmatched-source-001843874", ("No GitHub sources found",)),
    "project health": ("?lang=en#/projects", ("Last successful update", "Source coverage")),
    "catalog detail": ("?lang=en#/problems/PB-0006", ("FMA", "https://github.com/")),
    "catalog PR": ("?lang=en#/problems?" + urlencode({"q": PR}), ("Ask for a PR check", "template=pr-check.yml")),
    "Radar": ("?lang=en#/partial", ("Cross-project leads", "https://github.com/")),
    "Lab exact task": ("?lang=en#/lab?task=xbox2windows-3255-implicit-derivatives", ('class="card lab-task"', "/issues/159")),
    "People filter": ("?lang=en#/people?project=marvisak%2Fvictory", ("Apply filters", 'class="card community-person"')),
    "Impact filter": ("?lang=en#/impact?project=xcl", ('class="community-metrics"', 'class="community-proof"')),
    "onboarding EN": ("start.html", ("Ask for a PR check", "Connect MCP")),
    "onboarding RU": ("start.ru.html", ("Запросить проверку PR", "Подключить MCP")),
    "partner embed": ("partner.html?project=xcl&kind=result", ("Public sources", '<li>', "#/impact?")),
}
ERRORS = ("Could not load data", "The public feed is unavailable", "ERR_CONNECTION_REFUSED")


def main():
    windows = Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe"
    chrome = next((p for name in ("google-chrome", "chromium", "chromium-browser") if (p := shutil.which(name))),
                  str(windows) if windows.is_file() else None)
    if chrome is None:
        raise SystemExit("Chromium is needed")
    failures = 0
    with TemporaryDirectory() as profile:
        flags = [chrome, "--headless", "--disable-gpu", "--disable-background-networking",
                 "--no-first-run", f"--user-data-dir={profile}", "--virtual-time-budget=9500", "--dump-dom"]
        for name, (route, expected) in CASES.items():
            page = subprocess.run([*flags, SITE + route], capture_output=True, timeout=30,
                                  check=True).stdout.decode("utf-8")
            missing = [marker for marker in expected if marker not in page]
            errors = [marker for marker in ERRORS if marker in page]
            failures += bool(missing or errors)
            print(f"{name}: " + ("PASS" if not (missing or errors) else f"missing={missing}, errors={errors}"),
                  flush=True)
    raise SystemExit(bool(failures))


if __name__ == "__main__":
    main()
