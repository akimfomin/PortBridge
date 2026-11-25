# SPDX-License-Identifier: GPL-3.0-or-later
"""Extract only the pinned staging transport methods for the fake-device check."""

from difflib import unified_diff
from hashlib import sha256
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PINNED_SHA = "a1dfa72f07ee24ef6ba0e2a77149932cd8df1cdda1c9aaabad8274747e3c3128"
UPSTREAM = ROOT / "upstream" / "d3d12_title_image_upload.h"


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError(f"unexpected source anchor: {before[:65]}")
    return source.replace(before, after, 1)


def candidate(stock):
    text = replace_once(stock, "    VkDeviceSize capacity() const { return capacity_; }\n",
                        """    VkDeviceSize capacity() const { return capacity_; }

    // Access under the existing title-texture registry lock.
    struct Progress {
        std::uint64_t accepted = 0;
        std::uint64_t completed = 0;
        std::uint64_t published = 0;
    };
    Progress progress() const { return progress_; }
""")
    text = replace_once(text, "    bool prepare(Device& d, VkDeviceSize size) {\n",
                        """    bool prepare(Device& d, VkDeviceSize size) {
        if (d.context->is_device_lost()) return false;
        if (progress_.accepted != progress_.completed) {
            // A failed host wait can leave the old buffer and command pending.
            // Query that exact submission before mapping, overwriting or growing staging.
            std::uint64_t observed = 0;
            const auto r = d.context->observe_result(
                d.context->vk.vkGetSemaphoreCounterValue(d.info.device, ready_, &observed),
                "vkGetSemaphoreCounterValue (title staging reuse)");
            if (r != VK_SUCCESS || observed < progress_.accepted) return false;
            progress_.completed = progress_.accepted;
        }
""")
    text = replace_once(text, "        if (r != VK_SUCCESS) return r;\n        // The registry",
                        """        if (r != VK_SUCCESS) return r;
        progress_.accepted = value_;
        // The registry""")
    text = replace_once(text,
                        "        if ((r = vk.vkWaitSemaphores(d.info.device, &done, UINT64_MAX)) != VK_SUCCESS) return r;\n",
                        """        if ((r = vk.vkWaitSemaphores(d.info.device, &done, UINT64_MAX)) != VK_SUCCESS) return r;
        progress_.completed = value_;
""")
    text = replace_once(text,
                        """        for (auto q : consumers_)
            if ((r = vk.vkQueueSubmit(q, 1, &wait, VK_NULL_HANDLE)) != VK_SUCCESS) return r;
        return VK_SUCCESS;
""",
                        """        for (auto q : consumers_)
            if ((r = vk.vkQueueSubmit(q, 1, &wait, VK_NULL_HANDLE)) != VK_SUCCESS) return r;
        progress_.published = value_;
        return VK_SUCCESS;
""")
    return replace_once(text, "    std::uint64_t value_ = 0;\n",
                        "    std::uint64_t value_ = 0;\n    Progress progress_;\n")


def extract(text):
    start = text.index("    template<class Device>\n    void release_buffer(")
    end = text.index("    std::vector<VkBufferImageCopy> regions_;\n", start)
    exact = text[start:end]
    public = text.split("    template<class Device>", 1)[0].split("public:\n", 1)[1]
    return ("// From Continued d3d12_title_image_upload.h at the pinned source hash.\n"
            "// Only transport methods selected. Test access is public.\n"
            "class TitleImageUpload {\npublic:\n" + public + exact + "};\n")


def write(path, contents):
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(contents)


def run():
    raw = UPSTREAM.read_bytes()
    if sha256(raw).hexdigest() != PINNED_SHA:
        raise ValueError("wrong upstream transport source")
    stock = raw.decode("utf-8")
    changed = candidate(stock)
    output = ROOT / "generated"
    output.mkdir(exist_ok=True)
    write(output / "stock.inc", extract(stock))
    write(output / "candidate.inc", extract(changed))
    relative = "runtime/shims/d3d12_title_image_upload.h"
    patch = "".join(unified_diff(stock.splitlines(keepends=True), changed.splitlines(keepends=True),
                                 f"a/{relative}", f"b/{relative}"))
    write(output / "staging-reuse-reference.patch", patch)
    print(f"Verified pinned {PINNED_SHA}; extracted stock and candidate transport methods.")


if __name__ == "__main__":
    run()
