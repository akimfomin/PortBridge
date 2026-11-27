"""Scoped technical phrases mined from public metadata without retaining prose."""

import re


# Each rule pairs an object with a distinct operation or boundary. Error strings
# and broad topics such as "device loss" do not describe a mechanism.
PIPELINE_CACHE = r"(?:\bpipeline cache\b|\bPSO cache\b|\bpipeline librar(?:y|ies)\b|\b(?:cache|driver(?:'s)?) (?:pipeline )?blob\b|\bpipeline_cache(?:\.d|\.bin)\b)"
COMMAND_LIST = r"(?:\bcommand[ -]lists?\b|\bID3D12(?:Graphics)?CommandList\w*\b)"
MEMORY_COPY = r"(?:\b(?:cop(?:y|ies|ied|ying)|shadow)\w*\b.{0,65}\b(?:pages?|blocks?|views?|mappings?)\b|\b(?:pages?|blocks?|views?|mappings?)\b.{0,65}\b(?:cop(?:y|ies|ied|ying)|shadow)\w*\b)"
BVH = r"(?:\bBVH\b|\bbox(?:16|32)\b|\bimage_bvh(?:64)?_intersect_ray\b)"
RULES = {
    "pipeline-cache/device-identity": (PIPELINE_CACHE, r"\b(?:cache UUID|device identity|driver version|vendor ID|device ID|pipelineCacheUUID)\b"),
    "pipeline-cache/runtime-hit": (PIPELINE_CACHE, r"\b(?:cache hits?|hits? (?:that|the) cache|require[ -]hit|creation feedback|PIPELINE_CREATION_FEEDBACK_APPLICATION_PIPELINE_CACHE_HIT_BIT)\b"),
    "pipeline-cache/compile-fallback": (PIPELINE_CACHE, r"\b(?:stale blobs?|(?:refus\w+|reject\w+|invalid|incompatible) (?:the |a )?(?:blobs?|cache)|(?:compil\w+|creat\w+) (?:it )?(?:again|without (?:the |a )?blob))\b"),
    "command-list/final-release": (COMMAND_LIST, r"\b(?:final release|reference count|AddRef|destructor|destroy\w+ (?:the |a )?wrapper)\b"),
    "command-list/pointer-reuse": (COMMAND_LIST, r"\b(?:address[ -]reuse|pointer[ -]reuse|reuse\w* (?:the |a )?(?:native |real )?(?:address|pointer))\b"),
    "command-list/retirement": (COMMAND_LIST, r"\b(?:recycl\w+|retire\w+|allocator reuse)\b"),
    "memory-copy/write-tracking": (MEMORY_COPY, r"\b(?:guard\w*|write[ -]watch\w*|write faults?|dirty[ -]page\w*)\b"),
    "memory-copy/mapping-change": (MEMORY_COPY, r"\b(?:remap\w*|unmap\w*|alias(?:ed|es|ing)?|mapping change\w*)\b"),
    "memory-copy/selective-refresh": (MEMORY_COPY, r"\b(?:re[ -]copy\w*|instead of copying|cop\w+ (?:them |it )?again|skip\w* (?:the |a )?cop\w+|changed[ -]pages?)\b"),
    "bvh/page-boundary": (BVH, r"\b(?:cross[ -]page|page boundar\w+|across arena\w*|partially[ -]unmapped)\b"),
    "bvh/lane-participation": (BVH, r"\b(?:partial (?:groups?|participation|waves?)|masked[ -]out lanes|inactive lanes|memory guard)\b"),
    "bvh/node-fetch": (BVH, r"\b(?:node.{0,12}(?:loads?|fetches?|reads?)|second[ -]half|(?:two|2)[ -]child|directory lookup)\b"),
}
SCOPE_PATTERNS = [(name, re.compile(scope, re.I), re.compile(action, re.I))
                  for name, (scope, action) in RULES.items()]
CLAUSE = re.compile(r"[\r\n]+|(?<=[.!?])\s+")
DIAGNOSTIC = re.compile(r"(?:0x[0-9a-f]+|vuid-.*|.*_(?:error|message_id)_.*)", re.I)
MAX_WINDOW = 160
MAX_TEXT = 33_500


def mechanisms(text):
    """Return canonical rules whose object and operation occur locally together."""
    names = set()
    for clause in CLAUSE.split(text[:MAX_TEXT]):
        for name, scope, action in SCOPE_PATTERNS:
            if name in names:
                continue
            for symbol in scope.finditer(clause):
                if action.search(clause[max(0, symbol.start() - MAX_WINDOW):symbol.end() + MAX_WINDOW]):
                    names.add(name)
                    break
    return names
