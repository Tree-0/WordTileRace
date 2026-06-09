from collections import Counter
import random
import unittest

from tile_bag import (
    DEFAULT_RANDOM_DRAW_COUNT,
    STANDARD_TILE_DISTRIBUTION,
    draw_tiles,
    draw_random_rack,
    make_custom_rack,
)


class TileBagTests(unittest.TestCase):
    def test_standard_distribution_has_144_tiles(self):
        self.assertEqual(sum(STANDARD_TILE_DISTRIBUTION.values()), 144)

    def test_draw_random_rack_draws_default_21_tiles(self):
        rack = draw_random_rack(rng=random.Random(7))

        self.assertEqual(sum(rack.values()), DEFAULT_RANDOM_DRAW_COUNT)
        self.assertLessEqual(rack, STANDARD_TILE_DISTRIBUTION)

    def test_draw_random_rack_can_use_custom_count(self):
        rack = draw_random_rack(count=5, rng=random.Random(11))

        self.assertEqual(sum(rack.values()), 5)

    def test_make_custom_rack_normalizes_letters(self):
        self.assertEqual(make_custom_rack("Bean"), Counter({"B": 1, "E": 1, "A": 1, "N": 1}))

    def test_make_custom_rack_rejects_non_letters(self):
        with self.assertRaises(ValueError):
            make_custom_rack("BEAN!")

    def test_make_custom_rack_rejects_empty_input(self):
        with self.assertRaises(ValueError):
            make_custom_rack("   ")

    def test_draw_tiles_mutates_bag(self):
        bag = Counter({"A": 2, "B": 1})

        drawn = draw_tiles(bag, 2, random.Random(1))

        self.assertEqual(sum(drawn.values()), 2)
        self.assertEqual(sum(bag.values()), 1)
        self.assertEqual(drawn + bag, Counter({"A": 2, "B": 1}))


if __name__ == "__main__":
    unittest.main()
