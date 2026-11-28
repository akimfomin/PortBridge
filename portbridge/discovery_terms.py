"""Controlled technical cues shared by public metadata ingestion and Discovery."""

import re

from .matching import ISA_OPCODE

API_SYMBOL = re.compile(
    r"\b(?:vk(?:[A-Z][A-Za-z0-9]{1,62})|ID3D12[A-Za-z0-9_]{1,58}|"
    r"IDXGI[A-Za-z0-9_]{1,59}|(?:VK_ERROR|DXGI_ERROR|D3D12_ERROR|D3D12_MESSAGE_ID|"
    r"STATUS_ACCESS|SPV_ERROR|XAUDIO2_E)_[A-Z0-9_]{1,43}|VUID-[A-Za-z0-9_-]{1,59}|"
    r"(?:OpAtomic|OpGroupNonUniform)[A-Z][A-Za-z0-9]{0,46}|"
    r"ExecuteIndirect|DispatchMesh|DrawIndexedInstanced|CreateGraphicsPipelineState|"
    r"0[xX](?:887[Aa]00[0-9a-fA-F]{2}|80070057|8007000[Ee]|80004005|[Cc]0000005))\b"
)

DISCOVERY_SYMBOL = re.compile(
    r"\b(?:DXGI|D3D12|VK|SPV|GL)_[A-Z0-9_]{3,60}\b|"
    r"\b(?:UpdateTileMappings|GetCopyableFootprints|CopyTextureRegion|EnumAdapterByGpuPreference|"
    r"requiredSubgroupSize|R\d+G\d+B\d+E\d+|ds_bpermute(?:_b32)?)\b"
)
MECHANISMS = re.compile(
    r"\b(?:subgroup[-_ ]size|shared exponent|memory budget|device loss|typed buffer|"
    r"raw buffer view|pipeline state|frame pacing|texture upload|texture uploads|robust buffer access)\b|"
    r"(?<![a-z0-9])gpu[-_ ]timing\b", re.I
)
# Only normalized values from the typed metadata field use case-insensitive matching.
# Raw prose must keep its original casing (e.g. a Vulkan vkFoo call).
STORED_SYMBOL = re.compile(f"(?:{DISCOVERY_SYMBOL.pattern}|{API_SYMBOL.pattern}|{ISA_OPCODE.pattern})", re.I | re.ASCII)
MAX_CUES = 16


def cues(text):
    # Calls describe the operation. A non-diagnostic enum normally describes
    # one of its arguments. Keep both, but spend a single lookup on the call.
    operations, enums = [], []
    for pattern in (DISCOVERY_SYMBOL, API_SYMBOL, ISA_OPCODE):
        for match in pattern.finditer(text):
            value = match[0]
            if len(value) <= 80:
                is_enum = (value.isupper() and value.startswith(("DXGI_", "D3D12_", "VK_", "SPV_", "GL_"))
                           and "_ERROR_" not in value and "_MESSAGE_ID_" not in value)
                (enums if is_enum else operations).append(value.casefold())
    values = operations + enums
    values.extend(match[0].casefold().replace("_", " ").replace("-", " ") for match in MECHANISMS.finditer(text))
    return list(dict.fromkeys(values))[:MAX_CUES]


def stored_cue(value):
    return (isinstance(value, str) and len(value) <= 80 and
            (STORED_SYMBOL.fullmatch(value) or MECHANISMS.fullmatch(value)))
