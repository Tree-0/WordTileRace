from collections import Counter
import unittest

from backend.board import Board
from backend.game import Player, PlayerState
from backend.test.test_board import FakeTrie


def make_board(rack: Counter[str], valid_words: set[str] | None = None) -> Board:
    board = Board(rack)
    board.valid_words = FakeTrie(valid_words or set())
    return board


class PlayerStateTests(unittest.TestCase):
    def test_new_player_state_builds_board_from_tiles(self):
        player = Player("Natha")

        player_state = PlayerState.new_player_state(
            player,
            Counter({"B": 1, "E": 1}),
            make_board,
            "custom",
        )

        self.assertEqual(player_state.player, player)
        self.assertEqual(player_state.rack_count, 2)
        self.assertEqual(player_state.mode, "custom")

    def test_private_state_serializes_player_and_board(self):
        player_state = PlayerState.new_player_state(
            Player("Natha"),
            Counter({"B": 1, "E": 1}),
            lambda rack: make_board(rack, {"BE"}),
            "custom",
        )
        player_state.board.place_tile("B", 0, 0)
        player_state.board.place_tile("E", 1, 0)

        state = player_state.to_private_state()

        self.assertEqual(state["player_name"], "Natha")
        self.assertEqual(state["rack"], {})
        self.assertTrue(state["is_valid"])
        self.assertTrue(state["can_peel_board"])

    def test_public_state_excludes_private_rack_and_tiles(self):
        player_state = PlayerState.new_player_state(
            Player("Natha"),
            Counter({"B": 1}),
            make_board,
        )

        state = player_state.to_public_state()

        self.assertEqual(state["player_name"], "Natha")
        self.assertEqual(state["rack_count"], 1)
        self.assertNotIn("rack", state)
        self.assertNotIn("placed_tiles", state)


if __name__ == "__main__":
    unittest.main()
