import random
import unittest

from point_view import PointView


class PointViewTests(unittest.TestCase):
    def test_index_is_dense_in_the_current_version(self):
        start = PointView.from_columns({"id": range(17), "position": range(17)}, block_rows=4)
        first = start.select((), lambda index: index % 3 != 0)
        renamed = first.derive("position", ("position",), lambda index, x: x + 100 * index)
        second = renamed.select(("id",), lambda index, point_id: (index + point_id) % 5 >= 2)
        dense = [point_id for point_id in range(17) if point_id % 3 != 0]
        expected = [(point_id, point_id + 100 * i) for i, point_id in enumerate(dense)
                    if (i + point_id) % 5 >= 2]
        self.assertEqual(second.observe(("id", "position")),
                         {"id": tuple(row[0] for row in expected),
                          "position": tuple(row[1] for row in expected)})
        self.assertEqual(start.observe(("position",))["position"], tuple(range(17)))

    def test_sliced_multi_block_view_and_duplicate_occurrences(self):
        source = PointView.from_columns({"id": range(19), "size": range(100, 119)}, block_rows=4)
        left = source.select((), lambda i: i % 2 != 0)
        right = source.select((), lambda i: i % 3 != 0)
        joined = left.concatenate(right)
        order = left.observe(("id",))["id"] + right.observe(("id",))["id"]
        self.assertEqual(joined.observe(("id",))["id"], order)
        for first in range(len(order) + 1):
            for stop in range(first, len(order) + 1):
                self.assertEqual(joined.observe(("size",), first, stop)["size"],
                                 tuple(100 + point_id for point_id in order[first:stop]))
        self.assertIs(left._blocks[0].columns, source._blocks[0].columns)

    def test_rebalance_recovers_slots_without_changing_prior_views(self):
        source = PointView.from_columns({"tag": range(4096)}, block_rows=64)
        sparse = source.select((), lambda index: index % 64 == 63)
        compact = sparse.rebalance(block_rows=64)
        self.assertEqual(sparse.referenced_slots, 4096)
        self.assertEqual(compact.referenced_slots, 64)
        self.assertEqual(sparse.observe(sparse.names), compact.observe(compact.names))
        self.assertEqual(source.observe(("tag",), 0, 2)["tag"], (0, 1))

    def test_invalid_contracts_raise(self):
        with self.assertRaises(ValueError):
            PointView.from_columns({"id": (1, 2), "value": (4,)})
        source = PointView.from_columns({"id": (1, 2, 3)})
        with self.assertRaises(ValueError):
            source.observe(("name",))
        with self.assertRaises(ValueError):
            source.observe(("id",), 0, 4)
        with self.assertRaises(ValueError):
            source.observe(("id", "id"))
        with self.assertRaises(ValueError):
            source.concatenate(PointView.from_columns({"value": (1, 2, 3)}))

    def test_seeded_particle_births_deaths_updates_and_observers(self):
        randomizer = random.Random(552093)
        view = PointView.from_columns({"id": (), "position": (), "age": ()})
        dense = []
        snapshots = []
        serial = 0
        for frame in range(160):
            old = view
            saved = tuple(dense)
            snapshots.append((old, saved))
            birth_count = randomizer.randrange(20)
            born = [(serial + index, randomizer.randrange(-400, 400), 0)
                    for index in range(birth_count)]
            serial += birth_count
            fresh = PointView.from_columns(
                {name: [row[index] for row in born] for index, name in enumerate(view.names)},
                block_rows=7)
            if frame % 2:
                view = view.concatenate(fresh)
                dense.extend(born)
            else:
                view = fresh.concatenate(view)
                dense = born + dense
            view = view.select(("age",), lambda i, age: age < 9 and i % 11 != 6)
            dense = [row for i, row in enumerate(dense) if row[2] < 9 and i % 11 != 6]
            view = view.derive("position", ("position", "id"), lambda i, p, identity: p + i - identity)
            view = view.derive("age", ("age",), lambda i, age: age + 1)
            dense = [(identity, position + i - identity, age + 1)
                     for i, (identity, position, age) in enumerate(dense)]
            self.assertEqual(view.observe(("id", "position")),
                             {"id": tuple(row[0] for row in dense),
                              "position": tuple(row[1] for row in dense)})
            if frame % 13 == 0:
                view = view.rebalance(block_rows=16)
        for earlier, expected in snapshots[::7]:
            self.assertEqual(earlier.observe(("id", "age")),
                             {"id": tuple(row[0] for row in expected),
                              "age": tuple(row[2] for row in expected)})


if __name__ == "__main__":
    unittest.main()
