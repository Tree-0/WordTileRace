from collections import Counter
import random
import unittest
from uuid import uuid4

from backend.board import Board, Point
from backend.game_session import GameSession
from backend.test.test_board import FakeTrie


def make_board(rack: Counter[str], valid_words: set[str] | None = None) -> Board:
    board = Board(rack)
    board.valid_words = FakeTrie(valid_words or {"BE", "BEAN"})
    return board


class GameSessionTests(unittest.TestCase):
    def test_random_game_adds_player_from_shared_bag(self):
        session = GameSession.new_game(
            rng=random.Random(2),
            board_factory=make_board,
        )

        player_state = session.add_player("TestPlayer")

        self.assertEqual(player_state.rack_count, 21)
        self.assertEqual(session.bag_count, 123)
        self.assertEqual(session.player_state[player_state.player.id], player_state)

    def test_custom_game_adds_player_with_custom_rack_and_empty_bag(self):
        session = GameSession.new_game(
            "bean",
            rng=random.Random(2),
            board_factory=make_board,
        )

        player_state = session.add_player("Natha")

        self.assertEqual(player_state.board.unplaced_letters, Counter("BEAN"))
        self.assertEqual(session.bag_count, 0)
        self.assertEqual(session.mode, "custom")

    def test_board_actions_flow_through_session(self):
        session = GameSession.new_game("BE", board_factory=make_board)
        player_state = session.add_player("TestPlayer")

        session.place_tile(player_state.player.id, "B", 0, 0)
        session.move_tile(player_state.player.id, Point(0, 0), Point(1, 0))
        session.remove_tile(player_state.player.id, 1, 0)

        self.assertEqual(player_state.board.unplaced_letters, Counter({"B": 1, "E": 1}))
        self.assertEqual(player_state.board.placed_tiles, {})

    def test_peel_draws_one_tile_for_every_player(self):
        session = GameSession.new_game(rng=random.Random(1), board_factory=make_board)
        first = session.add_player("One")
        second = session.add_player("Two")
        first.board.unplaced_letters = Counter({"B": 1, "E": 1})
        first.board.place_tile("B", 0, 0)
        first.board.place_tile("E", 1, 0)
        first.board.valid_words = FakeTrie({"BE"})

        before_bag_count = session.bag_count

        session.peel(first.player.id)

        self.assertEqual(session.bag_count, before_bag_count - 2)
        self.assertEqual(first.rack_count, 1)
        self.assertEqual(second.rack_count, 22)

    def test_peel_rejects_invalid_player(self):
        session = GameSession.new_game(board_factory=make_board)

        with self.assertRaises(ValueError):
            session.peel(uuid4())

    def test_dump_returns_one_tile_and_draws_replacements(self):
        session = GameSession.new_game(rng=random.Random(1), board_factory=make_board)
        player_state = session.add_player("TestPlayer")
        player_state.board.unplaced_letters = Counter({"B": 1})
        session.bag = Counter({"A": 1, "C": 1, "D": 1})

        drawn = session.dump(player_state.player.id, "B")

        self.assertEqual(sum(drawn.values()), 3)
        self.assertEqual(player_state.rack_count, 3)
        self.assertEqual(session.bag_count, 1)

    def test_winner_detected_when_bag_empty_rack_empty_and_board_valid(self):
        session = GameSession.new_game("BE", board_factory=make_board)
        player_state = session.add_player("Natha")

        session.place_tile(player_state.player.id, "B", 0, 0)
        session.place_tile(player_state.player.id, "E", 1, 0)

        self.assertTrue(session.is_game_over)
        self.assertEqual(session.winner_id, player_state.player.id)
        self.assertTrue(session.private_state(player_state.player.id)["is_game_over"])


if __name__ == "__main__":
    unittest.main()
