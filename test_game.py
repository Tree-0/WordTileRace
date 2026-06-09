from collections import Counter
import random
import unittest

from board import Board
from game import Game
from test_board import FakeTrie


def make_board(rack: Counter[str], valid_words: set[str] | None = None) -> Board:
    board = Board(rack)
    board.valid_words = FakeTrie(valid_words or set())
    return board


class GameTests(unittest.TestCase):
    def test_random_game_starts_with_21_tiles_and_123_in_bag(self):
        game = Game.new_random(make_board, random.Random(2))

        self.assertEqual(game.rack_count, 21)
        self.assertEqual(game.bag_count, 123)
        self.assertFalse(game.is_game_over)

    def test_custom_game_starts_with_empty_bag(self):
        game = Game.new_custom("BE", make_board, random.Random(2))

        self.assertEqual(game.rack_count, 2)
        self.assertEqual(game.bag_count, 0)

    def test_peel_requires_empty_rack_and_valid_board(self):
        game = Game(
            board=make_board(Counter({"B": 1}), {"BE"}),
            bag=Counter({"A": 1}),
            rng=random.Random(1),
            mode="random",
        )

        with self.assertRaises(ValueError):
            game.peel()

    def test_peel_draws_one_tile_when_board_is_ready(self):
        board = make_board(Counter({"B": 1, "E": 1}), {"BE"})
        board.place_tile("B", 0, 0)
        board.place_tile("E", 1, 0)
        game = Game(board, Counter({"A": 1}), random.Random(1), "random")

        drawn = game.peel()

        self.assertEqual(drawn, Counter({"A": 1}))
        self.assertEqual(game.board.unplaced_letters, Counter({"A": 1}))
        self.assertEqual(game.bag_count, 0)

    def test_dump_returns_one_rack_tile_and_draws_three(self):
        game = Game(
            board=make_board(Counter({"B": 1}), {"BE"}),
            bag=Counter({"A": 1, "C": 1, "D": 1}),
            rng=random.Random(1),
            mode="random",
        )

        drawn = game.dump("B")

        self.assertEqual(sum(drawn.values()), 3)
        self.assertEqual(game.rack_count, 3)
        self.assertEqual(game.bag_count, 1)

    def test_dump_rejects_missing_rack_tile(self):
        game = Game(
            board=make_board(Counter({"B": 1}), {"BE"}),
            bag=Counter({"A": 3}),
            rng=random.Random(1),
            mode="random",
        )

        with self.assertRaises(ValueError):
            game.dump("E")

    def test_game_over_when_bag_empty_rack_empty_and_board_valid(self):
        board = make_board(Counter({"B": 1, "E": 1}), {"BE"})
        board.place_tile("B", 0, 0)
        board.place_tile("E", 1, 0)
        game = Game(board, Counter(), random.Random(1), "custom")

        self.assertTrue(game.is_game_over)
        self.assertTrue(game.to_state()["is_game_over"])

    def test_game_not_over_when_bag_empty_but_rack_has_tiles(self):
        game = Game(
            board=make_board(Counter({"B": 1}), {"BE"}),
            bag=Counter(),
            rng=random.Random(1),
            mode="custom",
        )

        self.assertFalse(game.is_game_over)

    def test_game_not_over_when_bag_empty_board_invalid(self):
        board = make_board(Counter({"B": 1}), {"BE"})
        board.place_tile("B", 0, 0)
        game = Game(board, Counter(), random.Random(1), "custom")

        self.assertFalse(game.is_game_over)


if __name__ == "__main__":
    unittest.main()
