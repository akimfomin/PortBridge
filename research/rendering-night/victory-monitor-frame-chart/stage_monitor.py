# SPDX-License-Identifier: MIT
"""Prepare an exact public monitor patch without running the monitor or a title."""

import difflib
import hashlib
import shutil
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent
PIN = "0d7631e633f5955269ba9de0154439da9b93f156"
PINS = {
    "victory_monitor.py": "d3494663308205b701d098070865281e71b1dbf9",
    "README.md": "0171f308daf67164bd6377a15669d087acd811a6",
    "LICENSE": "f3234e452f0ad9937aa3ddce252e7a3dafb0b672",
}


def content(name):
    path = ROOT / "upstream" / name
    if path.is_file():
        data = path.read_bytes()
    else:
        with urlopen(f"https://raw.githubusercontent.com/KretliJ/victory-monitor/{PIN}/{name}", timeout=15) as body:
            data = body.read(100_000)
    identity = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    if identity != PINS[name]:
        raise ValueError(f"wrong source blob for {name}: {identity}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data.decode("utf-8")


def replace(text, old, new, count=1):
    if text.count(old) != count:
        raise ValueError(f"expected {count} exact anchors for {old!r}")
    return text.replace(old, new)


original = {name: content(name) for name in PINS}
script = original["victory_monitor.py"]
script = replace(script, "# ------------------------------------------------------------------- i18n", """CHART_WALL_COLOR = "#33363e"
CHART_MARKERS = (
    ("gpu", "legend_gpu", "#e05a4e"),
    ("copyb", "legend_copyb", "#e0a34e"),
    ("tex", "legend_tex", "#b04ec9"),
    ("copies", "legend_copies", "#4ea3e0"),
    ("prep", "legend_prep", "#58b46a"),
)


# ------------------------------------------------------------------- i18n""")
script = replace(script, '"legend_gpu": "GPU",', '"legend_gpu": "espera da submissao",\n        "legend_wall": "tempo do frame",', count=2)
base, english = script.split('    "en-US": {', 1)
english = replace(english, '"legend_gpu": "espera da submissao",\n        "legend_wall": "tempo do frame",',
                  '"legend_gpu": "submit wait",\n        "legend_wall": "frame time",')
script = base + '    "en-US": {' + english
script = replace(script, '"legend_prep": "prep resto",', '"legend_prep": "preparo total",')
script = replace(script, '"legend_prep": "rest of prep",', '"legend_prep": "total prep",')
script = replace(script, '"chart_caption": "ultimos {n} frames | escala ate {m:.0f} ms",',
                 '"chart_caption": "ultimos {n} frames | escala ate {m:.0f} ms | marcadores podem se sobrepor",')
script = replace(script, '"chart_caption": "last {n} frames | scale up to {m:.0f} ms",',
                 '"chart_caption": "last {n} frames | scale up to {m:.0f} ms | markers can overlap",')
base, english = script.split('    "en-US": {', 1)
base = replace(base, '"v_gpu": "GPU (draws)",', '"v_gpu": "espera da submissao",')
english = replace(english, '"v_gpu": "GPU (draws)",', '"v_gpu": "submit wait",')
script = base + '    "en-US": {' + english

script = replace(script, """        for color, name in [("#e05a4e", tr("legend_gpu")), ("#e0a34e", tr("legend_copyb")),
                            ("#b04ec9", tr("legend_tex")), ("#4ea3e0", tr("legend_copies")),
                            ("#58b46a", tr("legend_prep"))]:
            tk.Label(leg, text="■", fg=color, bg=DARK_BG).pack(side=tk.LEFT)
            tk.Label(leg, text=name + "   ", fg=DARK_FG, bg=DARK_BG).pack(side=tk.LEFT)""", """        legend = [("legend_wall", CHART_WALL_COLOR)]
        legend.extend((label, color) for _, label, color in CHART_MARKERS)
        for label, color in legend:
            tk.Label(leg, text="■", fg=color, bg=DARK_BG).pack(side=tk.LEFT)
            tk.Label(leg, text=tr(label) + "   ", fg=DARK_FG, bg=DARK_BG).pack(side=tk.LEFT)""")

script = replace(script, """        maxms = max(max(f["ms"] for f in fs), 200) * 1.15
        n = len(fs)
        bw = max(3, w / n - 1)
        x0 = 6
        for i, f in enumerate(fs):
            x = x0 + i * (bw + 1)
            scale = h / maxms
            # empilhado: resto do frame primeiro (fundo cinza)
            segs = [
                (f["ms"] - f["prep"] - f["copyb"], "#33363e"),   # resto/submit
                (f["prep"] - f["tex"] - f["copies"], "#58b46a"),  # prep resto
                (f["copies"], "#4ea3e0"),
                (f["tex"], "#b04ec9"),
                (f["copyb"], "#e0a34e"),
                (f["gpu"], "#e05a4e"),
            ]
            y = h
            for v, color in segs:
                if v <= 0:
                    continue
                hh = min(v * scale, y)
                y -= hh
                c.create_rectangle(x, y, x + bw, y + hh, fill=color, width=0)
            # linha de 100 ms e de 33 ms""", """        wall_peak = max(f["ms"] for f in fs)
        marker_peak = max(f[field] for f in fs for field, _, _ in CHART_MARKERS)
        maxms = max(wall_peak, marker_peak, 200) * 1.15
        n = len(fs)
        x0 = 6
        slot = (w - x0) / n
        bw = 0.85 * slot
        tick = bw / len(CHART_MARKERS)
        scale = h / maxms
        for i, f in enumerate(fs):
            x = x0 + i * slot
            c.create_rectangle(x, h - f["ms"] * scale, x + bw, h, fill=CHART_WALL_COLOR, width=0)
            # Counters can cover the same time. Plot each from zero.
            for j, (field, _, color) in enumerate(CHART_MARKERS):
                value = f[field]
                if value > 0:
                    y = h - value * scale
                    c.create_line(x + j * tick, y, x + (j + 1) * tick, y, fill=color, width=2)""")
script = replace(script, "            gx = x0 + gi * grid_n * (bw + 1)", "            gx = x0 + gi * grid_n * slot")

readme = replace(original["README.md"], 'frame** ("GPU (draws)", "copy-back", "textures", ...)',
                 'frame** ("submit wait", "copy-back", "textures", ...)')
readme = replace(readme, """- **Stacked bar chart** of the last 240 frames: GPU / copy-back / textures /
  copies / rest-of-preparing, with 33 ms and 100 ms reference lines.""", """- **Frame-time bars** for the last 240 samples, with 33 ms and 100 ms reference
  lines. Independent markers show submit wait, copy-back, textures, copies and
  total preparation. These counters may cover some of the same time.""")

target = ROOT / "candidate"
target.mkdir(exist_ok=True)
shutil.copyfile(ROOT / "upstream" / "LICENSE", target / "LICENSE")
with (ROOT / "victory-monitor-nonadditive-chart.patch").open("w", encoding="utf-8", newline="\n") as patch:
    for name, edited in (("victory_monitor.py", script), ("README.md", readme)):
        (target / name).write_text(edited, encoding="utf-8", newline="\n")
        patch.write(f"diff --git a/{name} b/{name}\n")
        patch.writelines(difflib.unified_diff(original[name].splitlines(keepends=True), edited.splitlines(keepends=True),
                                              "a/" + name, "b/" + name))
