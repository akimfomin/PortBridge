"""Resolve Vulkan common-validity IDs through their explicit refpage includes."""

from collections import defaultdict, deque
import re

from . import code_search

INCLUDE = re.compile(r"^include::\{chapters\}/(commonvalidity/[A-Za-z0-9_]+\.adoc)\[\]\s*$")
TEMPLATE = re.compile(r"^\s*\*\s+\[\[VUID-\{refpage\}-([A-Za-z0-9_]{1,54}-[0-9]{5})\]\]")
ATTRIBUTE = re.compile(r"^:refpage:\s+([A-Za-z_][A-Za-z_0-9]+)\s*$")
REPO = "KhronosGroup/Vulkan-Docs"


def extract(content):
    """Keep source-relative targets and line numbers, without spec prose."""
    lines = content.decode("utf-8").splitlines()
    owner = opaque = attribute = None
    binding_seen = False
    opened = 0
    includes, templates = [], []
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if code_search.DOC_OPAQUE_BLOCK.fullmatch(stripped):
            if opaque is None:
                opaque = stripped
            elif opaque == stripped:
                opaque = None
            continue
        if opaque is not None:
            continue
        refpage = code_search.DOC_REFPAGE.fullmatch(line)
        if refpage and number < len(lines) and lines[number].strip() == "--":
            owner = refpage["name"]
            opened = number + 1
            attribute, binding_seen = None, False
        elif stripped == "--" and number > opened:
            owner = None
        elif stripped.startswith((":refpage:", ":refpage!:", ":!refpage:")):
            binding_seen = True
            binding = ATTRIBUTE.fullmatch(stripped)
            attribute = binding[1] if binding else None
        elif include := INCLUDE.fullmatch(line):
            if owner is not None and owner == attribute:
                includes.append(("chapters/" + include[1], owner, number))
            elif owner is None and not binding_seen:
                includes.append(("chapters/" + include[1], "", number))
        elif template := TEMPLATE.match(line):
            templates.append((template[1], number))
    return includes, templates


def resolve(rows):
    contexts = defaultdict(dict)
    edges = defaultdict(set)
    queue = deque()
    for row in rows:
        includes, _ = row.get("_vulkan_rules", ((), ()))
        for path, owner, line in includes:
            target = (row["revision"], path)
            if owner:
                queue.append((target, owner, row["path"], line))
            elif row["path"].startswith("chapters/commonvalidity/"):
                edges[(row["revision"], row["path"])].add(target)
    while queue:
        target, owner, path, include_line = queue.popleft()
        if owner in contexts[target]:
            continue
        contexts[target][owner] = (path, include_line)
        queue.extend((child, owner, path, include_line) for child in sorted(edges[target]))
    for row in rows:
        if "_vulkan_rules" not in row:
            continue
        _, templates = row.pop("_vulkan_rules")
        origins = {}
        expanded = {}
        for owner, (path, include_line) in sorted(contexts[(row["revision"], row["path"])].items()):
            for tail, source_line in templates:
                vuid = f"VUID-{owner}-{tail}"
                if not code_search.VUID.fullmatch(vuid) or len(vuid) > 87:
                    continue
                diagnostic = code_search.diagnostic_token(vuid)
                anchor = code_search.rule_token(diagnostic)
                # One file may contain repeated mentions. The actual template
                # is preferred, with its concrete caller recorded separately.
                expanded.setdefault(anchor, [source_line])
                expanded.setdefault(diagnostic, [source_line])
                origins.setdefault(anchor, {"id": vuid,
                                   "url": f"https://github.com/{REPO}/blob/{row['revision']}/{path}#L{include_line}"})
        if expanded:
            terms = {**expanded, **{term: lines for term, lines in row["terms"].items() if term not in expanded}}
            row["terms"] = dict(list(terms.items())[:code_search.MAX_TERMS])
            row["rule_includes"] = {anchor: url for anchor, url in origins.items() if anchor in row["terms"]}
