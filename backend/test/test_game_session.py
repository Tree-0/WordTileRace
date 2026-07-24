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

    def test_custom_game_adds_player_with_custom_rack_and_standard_bag(self):
        session = GameSession.new_game(
            "bean",
            rng=random.Random(2),
            board_factory=make_board,
        )

        player_state = session.add_player("Natha")
        second_player = session.add_player("Friend")

        self.assertEqual(player_state.board.unplaced_letters, Counter("BEAN"))
        self.assertEqual(second_player.board.unplaced_letters, Counter("BEAN"))
        self.assertEqual(session.bag_count, 144)
        self.assertEqual(session.mode, "custom")

    def test_custom_game_without_rack_draws_21_tiles_for_each_player(self):
        expected_bag_counts = {
            1: 102,
            1.5: 174,
            2: 246,
            2.7: 346,
        }
        for multiplier, expected_bag_count in expected_bag_counts.items():
            with self.subTest(multiplier=multiplier):
                session = GameSession.new_game(
                    "   ",
                    rng=random.Random(2),
                    board_factory=make_board,
                    bag_multiplier=multiplier,
                )

                first_player = session.add_player("One")
                second_player = session.add_player("Two")

                self.assertIsNone(session.custom_rack)
                self.assertEqual(session.mode, "custom")
                self.assertEqual(first_player.rack_count, 21)
                self.assertEqual(second_player.rack_count, 21)
                self.assertEqual(session.bag_count, expected_bag_count)

    def test_record_round_trip_preserves_custom_mode_without_custom_rack(self):
        session = GameSession.new_game(
            "",
            rng=random.Random(2),
            board_factory=make_board,
            bag_multiplier=1.5,
        )
        session.add_player("Natha")

        restored = GameSession.from_record(
            session.to_record(),
            board_factory=make_board,
            rng=random.Random(3),
        )

        self.assertEqual(restored.mode, "custom")
        self.assertIsNone(restored.custom_rack)
        self.assertEqual(restored.bag_multiplier, 1.5)
        self.assertEqual(restored.bag_count, 195)

    def test_legacy_custom_record_infers_none_multiplier_from_empty_bag(self):
        session = GameSession.new_game("BE", board_factory=make_board)
        record = session.to_record()
        record["version"] = 1
        record["bag"] = {}
        del record["bag_multiplier"]

        restored = GameSession.from_record(record, board_factory=make_board)

        self.assertEqual(restored.mode, "custom")
        self.assertEqual(restored.custom_rack, Counter("BE"))
        self.assertEqual(restored.bag_multiplier, 0.0)
        self.assertEqual(restored.bag_count, 0)

    def test_none_bag_requires_and_accepts_custom_rack(self):
        with self.assertRaisesRegex(ValueError, "when bag size is NONE"):
            GameSession.new_game("", board_factory=make_board, bag_multiplier=0)

        session = GameSession.new_game(
            "BEAN",
            board_factory=make_board,
            bag_multiplier=0,
        )
        player_state = session.add_player("Natha")
        second_player = session.add_player("Friend")

        self.assertEqual(player_state.board.unplaced_letters, Counter("BEAN"))
        self.assertEqual(second_player.board.unplaced_letters, Counter("BEAN"))
        self.assertEqual(session.bag_count, 0)

    def test_bag_multiplier_scales_random_and_custom_games(self):
        random_session = GameSession.new_game(
            rng=random.Random(2),
            board_factory=make_board,
            bag_multiplier=1.59,
        )
        random_session.add_player("Random")
        custom_session = GameSession.new_game(
            "BEAN",
            board_factory=make_board,
            bag_multiplier=2,
        )
        custom_session.add_player("Custom")

        self.assertEqual(random_session.bag_multiplier, 1.5)
        self.assertEqual(random_session.bag_count, 195)
        self.assertEqual(custom_session.bag_multiplier, 2.0)
        self.assertEqual(custom_session.bag_count, 288)
        self.assertEqual(custom_session.public_state()["bag_multiplier"], 2.0)

    def test_players_get_normalized_or_default_names_in_public_state(self):
        session = GameSession.new_game("BE", board_factory=make_board)

        named_player = session.add_player("  Alice   Smith  ")
        first_default = session.add_player()
        second_default = session.add_player("   ")

        self.assertEqual(named_player.player.player_name, "Alice Smith")
        self.assertEqual(first_default.player.player_name, "Player 1")
        self.assertEqual(second_default.player.player_name, "Player 2")
        self.assertEqual(
            [player["player_name"] for player in session.public_state()["players"]],
            ["Alice Smith", "Player 1", "Player 2"],
        )

    def test_player_name_rejects_non_text_and_overlong_values(self):
        session = GameSession.new_game("BE", board_factory=make_board)

        with self.assertRaisesRegex(ValueError, "Nickname must be text"):
            session.add_player({"name": "Alice"})
        with self.assertRaisesRegex(ValueError, "24 characters or fewer"):
            session.add_player("A" * 25)

    def test_board_actions_flow_through_session(self):
        session = GameSession.new_game("BE", board_factory=make_board)
        player_state = session.add_player("TestPlayer")

        place_result = session.place_tile(player_state.player.id, "B", 0, 0)
        move_result = session.move_tile(player_state.player.id, Point(0, 0), Point(1, 0))
        remove_result = session.remove_tile(player_state.player.id, 1, 0)

        self.assertEqual(player_state.board.unplaced_letters, Counter({"B": 1, "E": 1}))
        self.assertEqual(player_state.board.placed_tiles, {})
        self.assertEqual(place_result["type"], "tile_placed")
        self.assertEqual(place_result["rack_delta"], {"B": -1})
        self.assertIn("partial_validation", place_result)
        self.assertEqual(move_result["type"], "tile_moved")
        self.assertIn("partial_validation", move_result)
        self.assertEqual(remove_result["type"], "tile_removed")
        self.assertEqual(remove_result["rack_delta"], {"B": 1})
        self.assertIn("partial_validation", remove_result)

    def test_block_actions_include_atomic_diffs_and_rack_changes(self):
        session = GameSession.new_game("BEX", board_factory=make_board)
        player_state = session.add_player("TestPlayer")
        player_id = player_state.player.id
        session.place_tile(player_id, "B", 0, 0)
        session.place_tile(player_id, "E", 1, 0)
        session.place_tile(player_id, "X", 2, 0)

        move_result = session.move_tiles(
            player_id,
            [Point(0, 0), Point(1, 0)],
            Point(1, 0),
            overwrite=True,
        )

        self.assertEqual(move_result["type"], "tiles_moved")
        self.assertEqual(len(move_result["moves"]), 2)
        self.assertEqual(move_result["displaced"][0]["tile"]["char"], "X")
        self.assertEqual(move_result["rack_delta"], {"X": 1})
        self.assertIn("partial_validation", move_result)

        remove_result = session.remove_tiles(
            player_id,
            [Point(1, 0), Point(2, 0)],
        )

        self.assertEqual(remove_result["type"], "tiles_removed")
        self.assertEqual(len(remove_result["removed"]), 2)
        self.assertEqual(remove_result["rack_delta"], {"B": 1, "E": 1})
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

        result = session.peel(first.player.id)

        self.assertEqual(session.bag_count, before_bag_count - 2)
        self.assertEqual(first.rack_count, 1)
        self.assertEqual(second.rack_count, 22)
        self.assertEqual(result["type"], "peeled")
        self.assertEqual(set(result["drawn_by_player"]), {
            str(first.player.id),
            str(second.player.id),
        })

    def test_peel_rejects_invalid_player(self):
        session = GameSession.new_game(board_factory=make_board)

        with self.assertRaises(ValueError):
            session.peel(uuid4())

    def test_dump_returns_one_tile_and_draws_replacements(self):
        session = GameSession.new_game(rng=random.Random(1), board_factory=make_board)
        player_state = session.add_player("TestPlayer")
        player_state.board.unplaced_letters = Counter({"B": 1})
        session.bag = Counter({"A": 1, "C": 1, "D": 1})

        result = session.dump(player_state.player.id, "B")

        self.assertEqual(result["type"], "rack_changed")
        self.assertEqual(sum(result["drawn"].values()), 3)
        self.assertEqual(player_state.rack_count, 3)
        self.assertEqual(session.bag_count, 1)

    def test_winner_detected_when_player_peels_with_empty_bag(self):
        session = GameSession.new_game("BE", board_factory=make_board)
        player_state = session.add_player("Natha")
        session.bag = Counter()

        session.place_tile(player_state.player.id, "B", 0, 0)
        session.place_tile(player_state.player.id, "E", 1, 0)
        result = session.peel(player_state.player.id)

        self.assertEqual(result["type"], "game_over")
        self.assertEqual(result["winner_name"], "Natha")
        self.assertTrue(session.is_game_over)
        self.assertEqual(session.winner_id, player_state.player.id)
        private_state = session.private_state(player_state.player.id)
        self.assertTrue(private_state["is_game_over"])
        self.assertEqual(private_state["winner_name"], "Natha")
        self.assertEqual(session.public_state()["winner_name"], "Natha")
        self.assertEqual(
            private_state["messages"],
            ["Natha wins! All tiles are placed in valid words."],
        )

    def test_winner_detected_when_bag_has_fewer_tiles_than_players(self):
        session = GameSession.new_game(
            rng=random.Random(1),
            board_factory=make_board,
        )
        player_state = session.add_player("Natha")
        session.add_player("Opponent")
        player_state.board.unplaced_letters = Counter({"B": 1, "E": 1})
        player_state.board.place_tile("B", 0, 0)
        player_state.board.place_tile("E", 1, 0)
        session.bag = Counter({"Z": 1})

        self.assertTrue(session.private_state(player_state.player.id)["can_peel"])

        result = session.peel(player_state.player.id)

        self.assertEqual(result["type"], "game_over")
        self.assertEqual(result["bag_count"], 1)
        self.assertEqual(result["winner_name"], "Natha")
        self.assertEqual(session.bag, Counter({"Z": 1}))
        self.assertTrue(session.is_game_over)

    def test_record_round_trip_preserves_game_state(self):
        session = GameSession.new_game("BEAN", board_factory=make_board)
        player_state = session.add_player("Natha")
        session.place_tile(player_state.player.id, "B", 0, 0)
        session.place_tile(player_state.player.id, "E", 1, 0)
        session.bag = Counter({"Z": 2})

        restored = GameSession.from_record(
            session.to_record(),
            board_factory=make_board,
            rng=random.Random(3),
        )
        restored_player = restored.get_player_state(player_state.player.id)

        self.assertEqual(restored.game_id, session.game_id)
        self.assertEqual(restored.mode, "custom")
        self.assertEqual(restored.custom_rack, Counter("BEAN"))
        self.assertEqual(restored.bag_multiplier, 1.0)
        self.assertEqual(restored.bag, Counter({"Z": 2}))
        self.assertEqual(restored_player.player.player_name, "Natha")
        self.assertEqual(restored_player.board.unplaced_letters, Counter({"A": 1, "N": 1}))
        self.assertEqual(
            [tile["char"] for tile in restored_player.board.to_state()["placed_tiles"]],
            ["B", "E"],
        )


if __name__ == "__main__":
    unittest.main()
