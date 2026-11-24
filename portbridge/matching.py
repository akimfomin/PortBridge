"""Rank cross-project leads from references and technical evidence."""

from collections import Counter, defaultdict
from math import log, sqrt
import re
from urllib.parse import urlsplit


WORDS = re.compile(r"[^\W_]+")
ISA_OPCODE = re.compile(
    r"\b(?:ds_(?:nop|append|consume|[a-z][a-z0-9]*(?:_[a-z0-9]+){1,6})|"
    r"image_(?:sample|gather4|load|store|atomic)(?:_[a-z0-9]+){1,6}|"
    r"[vs]_[a-z][a-z0-9]*(?:_[a-z0-9]+){0,4}_[bfiu](?:16|32|64)(?:_[a-z0-9]+){0,2})\b",
    re.I,
)
OPCODE_GROUP = re.compile(
    r"\b((?:ds|image|v|s)_[a-z][a-z0-9_]{1,48}_)\{([a-z0-9_ ,]{3,100})\}((?:_[a-z0-9]+){0,3})(?![\w{])",
    re.I,
)
OPCODE_TYPE_LIST = re.compile(
    r"\b(ds_[a-z][a-z0-9_]{1,42}_)([biuf][0-9]{1,3}(?:/[biuf][0-9]{1,3}){1,6})"
    r"((?:_[a-z0-9]+){0,3})(/_hi)?(?![\w/])"
)
OPCODE_HIGH_HALF = re.compile(r"\b(ds_[a-z][a-z0-9_]{1,48}_d16)/_hi\b")
DOCS_TITLE = re.compile(r"^(?:docs\b|documentation\b|readme\b)", re.I)
BUILD_TITLE = re.compile(r"\b(?:ci|cmake|vulkan-headers|cargo build)\b", re.I)
STOP_WORDS = set("a an the on in to of for by and or from that it its is at with into after before as this then "
                 "test tests tested fix fixes add adds support update merge pull request windows linux xbox "
                 "game would about when build issue code commit main using use like fails error crash "
                 "github make target runtime logs output example version project passed result".split())
ALIASES = {
    "direct3d12": "d3d12", "rectlist": "rectangle",
    "rectlists": "rectangle", "rectangles": "rectangle", "rect": "rectangle", "vertices": "vertex",
    "shaders": "shader", "atomics": "atomic", "queues": "queue", "quads": "quad",
    "lists": "list", "draws": "draw",
}
GENERAL_SOURCE_TERMS = {"d3d12", "dxgi", "vulkan", "shader", "spirv", "wave32", "wave64",
                        "gpu", "runtime", "console", "host", "pipeline", "slot", "slots", "multi",
                        "proton", "vkd3d", "wine", "x86"}

# GitHub repository 1465852099 moved to xcl-dev. Keep its established keys for
# saved plans and topics while addressing GitHub at the verified current name.
REPOSITORY_MOVES = {"ivall/xcl": "xcl-dev/xcl"}
REPOSITORY_IDENTITIES = {current: previous for previous, current in REPOSITORY_MOVES.items()}


def current_repository(repo):
    return REPOSITORY_MOVES.get(repo.casefold(), repo)


def repository_identity(repo):
    return REPOSITORY_IDENTITIES.get(repo.casefold(), repo)


def canonical_url(url):
    path = urlsplit(url).path.rstrip("/").lower()
    parts = path.split("/", 3)
    if len(parts) >= 3 and not parts[0]:
        repo = repository_identity("/".join(parts[1:3]))
        path = f"/{repo}" + (f"/{parts[3]}" if len(parts) == 4 else "")
    return f"https://github.com{path}"


def source_url_aliases(url):
    key = canonical_url(url)
    path = key.removeprefix("https://github.com/").split("/", 2)
    repo = "/".join(path[:2])
    current = current_repository(repo)
    if current == repo:
        return (key,)
    return key, f"https://github.com/{'/'.join([current, *path[2:]])}"


def expand_instruction_groups(text):
    def brace_group(match):
        stem, options, ending = match.groups()
        return " ".join(f"{stem}{option.strip()}{ending}" for option in options.split(",") if option.strip())

    def type_list(match):
        stem, options, ending, high_half = match.groups()
        names = [f"{stem}{option}{ending}" for option in options.split("/")]
        if high_half and ending == "_d16":
            names += [f"{name}_hi" for name in names]
        return " ".join(names)

    text = OPCODE_GROUP.sub(brace_group, text.casefold())
    text = OPCODE_TYPE_LIST.sub(type_list, text)
    return OPCODE_HIGH_HALF.sub(lambda match: f"{match[1]} {match[1]}_hi", text)


def instruction_names(text):
    return list(dict.fromkeys(ISA_OPCODE.findall(expand_instruction_groups(text))))


def terms(text):
    text = expand_instruction_groups(text).replace("spir-v", "spirv")
    opcodes = set(ISA_OPCODE.findall(text))
    words = WORDS.findall(ISA_OPCODE.sub(" ", text))
    return {ALIASES.get(word, word) for word in words
            if len(word) >= 3 and word not in STOP_WORDS and not word.isdecimal()} | opcodes


def subject_kind(title):
    if DOCS_TITLE.match(title):
        return "documentation"
    if BUILD_TITLE.search(title):
        return "build"
    return "implementation"


def source_revision(row):
    metadata = row["metadata"]
    value = metadata.get("sha") or metadata.get("head_sha")
    return value.lower() if isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{40,64}", value) else None


class RelatedIndex:
    def __init__(self, records):
        self.rows = {canonical_url(row["url"]): row for row in records if row["kind"] in {"issue", "pr", "commit"}}
        self.titles, self.subjects, self.signals, self.kinds = {}, {}, {}, {}
        self.references = defaultdict(set)
        self.postings = defaultdict(set)
        self.symbols = defaultdict(set)
        self.instruction_families = {}
        self.family_postings = defaultdict(set)
        self.revisions = defaultdict(set)
        for url, row in self.rows.items():
            technical = row["metadata"].get("technical") or {}
            self.titles[url] = terms(row["title"])
            self.kinds[url] = subject_kind(row["title"])
            self.subjects[url] = self.titles[url] | terms(" ".join(technical.get("terms", [])))
            self.signals[url] = ({value.casefold() for value in technical.get("signals", [])}
                                 | {word for word in self.titles[url] if ISA_OPCODE.fullmatch(word)})
            for word in self.subjects[url]:
                self.postings[word].add(url)
            for signal in self.signals[url]:
                self.symbols[signal].add(url)
            families = {symbol.removesuffix("_d16_hi").removesuffix("_d16") for symbol in self.signals[url]
                        if symbol.startswith("ds_") and ISA_OPCODE.fullmatch(symbol)}
            self.instruction_families[url] = families
            for family in families:
                self.family_postings[family].add(url)
            revision = source_revision(row)
            if revision:
                self.revisions[revision].add(url)
            for target in technical.get("references", []):
                other = canonical_url(target)
                if other in self.rows and self.rows[other]["project"] != row["project"]:
                    self.references[url].add(other)
                    self.references[other].add(url)
        count = len(self.rows)
        cap = min(160, max(18, count // 8))
        self.weight = {word: 1 + log((count + 1) / (len(urls) + 1))
                       for word, urls in self.postings.items() if len(urls) <= cap}
        self.lengths = {url: sum(self.weight[word] for word in words & self.weight.keys())
                        for url, words in self.subjects.items()}
        self.symbol_cap = cap

    def candidates(self, url, *, use_references=True):
        reference_urls = self.references.get(url, set()) if use_references else set()
        target_hits = Counter(other for term in self.subjects[url] & self.weight.keys()
                              for other in self.postings[term])
        signal_urls = {other for signal in self.signals[url] if len(self.symbols[signal]) <= self.symbol_cap
                       for other in self.symbols[signal]}
        families = {family for family in self.instruction_families[url]
                    if len(self.family_postings[family]) <= self.symbol_cap}
        family_urls = {other for family in families for other in self.family_postings[family]}
        shared_revision = self.revisions.get(source_revision(self.rows[url]), set())
        for other in sorted(set(target_hits) | reference_urls | signal_urls | family_urls | shared_revision):
            if self.rows[url]["project"] == self.rows[other]["project"]:
                continue
            if other in shared_revision:
                yield other, 1.0, "shared_revision", []
                continue
            if other in reference_urls:
                yield other, 1.0, "reference", []
                continue
            if self.kinds[url] != self.kinds[other]:
                continue
            shared = self.subjects[url] & self.subjects[other] & self.weight.keys()
            specific = shared - GENERAL_SOURCE_TERMS
            symbols = {signal for signal in self.signals[url] & self.signals[other]
                       if len(self.symbols[signal]) <= self.symbol_cap}
            if symbols and (specific or any(ISA_OPCODE.fullmatch(symbol) for symbol in symbols)):
                yield other, 0.78 + 0.04 * min(len(symbols), 3), "technical_signal", sorted(symbols)[:6]
                continue
            shared_families = families & self.instruction_families[other]
            if len(shared_families) >= 2:
                yield other, 0.79, "instruction_variants", sorted(shared_families)[:6]
                continue
            if target_hits[other] < 3:
                continue
            title_shared = (self.titles[url] & self.titles[other]) - GENERAL_SOURCE_TERMS
            if len(title_shared) < 2 and len(specific) < 4:
                continue
            weight = sum(self.weight[word] for word in shared)
            score = weight / sqrt(self.lengths[url] * self.lengths[other])
            if score >= 0.26:
                words = sorted(shared, key=lambda word: (-self.weight[word], word))
                yield other, min(score, 0.77), "technical_terms", words[:6]

    def matches(self, stacks, *, origin=None, exclude=None, keep=None, use_references=True, limit=60):
        pairs = set()
        found = []
        origins = self.rows if origin is None else [origin] if origin in self.rows else []
        for url in origins:
            first = self.rows[url]
            for other, score, basis, signals in self.candidates(url, use_references=use_references):
                if exclude and exclude(url, other):
                    continue
                second = self.rows[other]
                if keep and not keep([first, second]):
                    continue
                pair = tuple(sorted((url, other)))
                if pair in pairs:
                    continue
                pairs.add(pair)
                reason = {
                    "reference": "В одном из источников есть прямая ссылка на другой проект.",
                    "shared_revision": "Совпадает полный идентификатор коммита.",
                    "technical_signal": "Совпадают технические идентификаторы.",
                    "instruction_variants": "Совпадают семейства инструкций. Сверьте точные варианты и границы теста.",
                    "technical_terms": "Совпадают редкие технические термины в описании или заголовке.",
                }[basis]
                if signals:
                    reason += " " + ", ".join(signals) + "."
                different = stacks.get(first["project"]) != stacks.get(second["project"])
                if different:
                    reason += " Проверьте различия между архитектурами."
                found.append({
                    "left": {key: first[key] for key in ("project", "title", "url")},
                    "right": {key: second[key] for key in ("project", "title", "url")},
                    "score": round(score, 3), "reason": reason, "basis": basis, "state": "suggested",
                    "problem_id": None, "different_stacks": different,
                })
        return sorted(found, key=lambda row: (-row["score"], row["left"]["url"], row["right"]["url"]))[:limit]
