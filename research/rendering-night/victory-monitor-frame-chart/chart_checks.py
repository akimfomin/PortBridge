# SPDX-License-Identifier: MIT
"""Check the exact redraw method through a recording canvas, without Tk."""

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent
WALL = "#33363e"
RED = "#e05a4e"
ORANGE = "#e0a34e"


def extract(revision):
    path = ROOT / revision / "victory_monitor.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
    scope = {"tr": lambda key, **values: key}
    assignments = [node for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id in ("CHART_MARKERS", "CHART_WALL_COLOR")
                           for t in node.targets)]
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "MonitorGUI")
    redraw = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "redraw")
    exec(compile(ast.Module(body=[*assignments, redraw], type_ignores=[]), path.name, "exec"), scope)
    return tree, scope["redraw"]


class Canvas:
    def __init__(self, w=600, h=230):
        self.w, self.h = w, h
        self.rectangles, self.lines = [], []

    def delete(self, _):
        self.rectangles.clear()
        self.lines.clear()

    def winfo_width(self):
        return self.w

    def winfo_height(self):
        return self.h

    def create_rectangle(self, *xy, fill, **kwargs):
        self.rectangles.append((xy, fill))

    def create_line(self, *xy, fill, **kwargs):
        self.lines.append((xy, fill))

    def create_text(self, *args, **kwargs):
        pass


def run(redraw, frames, **size):
    canvas = Canvas(**size)
    redraw(SimpleNamespace(canvas=canvas, frames=frames))
    return canvas


def height_sum(canvas):
    return sum(y1 - y0 for (_, y0, _, y1), _ in canvas.rectangles)


def frame(ms, prep=0, copyb=0, gpu=0, copies=0, tex=0):
    return dict(ms=ms, prep=prep, copyb=copyb, gpu=gpu, copies=copies, tex=tex)


class ChartTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original, old = extract("upstream")
        cls.candidate, new = extract("candidate")
        cls.old = staticmethod(old)
        cls.new = staticmethod(new)

    def test_old_chart_adds_gpu_to_wall_even_for_disjoint_sample(self):
        frames = [frame(50, prep=10, copyb=15, gpu=20, copies=4, tex=2)]
        self.assertAlmostEqual(height_sum(run(self.old, frames)), 70)
        changed = run(self.new, frames)
        self.assertAlmostEqual(height_sum(changed), 50)
        self.assertEqual(len(changed.rectangles), 1)
        self.assertEqual(changed.rectangles[0][1], WALL)

    def test_equal_wait_and_copyback_have_independent_marks(self):
        changed = run(self.new, [frame(100, gpu=80, copyb=80)])
        self.assertAlmostEqual(height_sum(changed), 100)
        marks = [pair for pair in changed.lines if pair[1] in (RED, ORANGE)]
        self.assertEqual(len(marks), 2)
        self.assertAlmostEqual(marks[0][0][1], 150)
        self.assertAlmostEqual(marks[1][0][1], 150)
        self.assertNotEqual(marks[0][0][0], marks[1][0][0])

    def test_counter_above_wall_expands_scale_and_stays_visible(self):
        changed = run(self.new, [frame(50, gpu=350)], h=350)
        [(mark, _)] = [pair for pair in changed.lines if pair[1] == RED]
        scale = 350 / (350 * 1.15)
        self.assertAlmostEqual(height_sum(changed), 50 * scale)
        self.assertAlmostEqual(mark[1], 350 - 350 * scale)
        self.assertGreater(mark[1], 0)

    def test_history_fits_narrow_canvas_and_stays_at_last_240(self):
        frames = [frame(20 + i, gpu=0, copyb=1) for i in range(300)]
        changed = run(self.new, frames, w=162)
        self.assertEqual(len(changed.rectangles), 240)
        self.assertEqual(sum(fill == ORANGE for _, fill in changed.lines), 240)
        self.assertFalse(any(fill == RED for _, fill in changed.lines))
        for ((x0, _, x1, _), _) in changed.rectangles:
            self.assertTrue(0 <= x0 < x1 <= 162)

    def test_parser_and_summary_calculation_are_unchanged(self):
        for name in ("parse_line", "summarize", "verdict"):
            old, new = (next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
                        for tree in (self.original, self.candidate))
            self.assertEqual(ast.dump(old), ast.dump(new), name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
