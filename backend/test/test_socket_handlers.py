from collections import Counter
import random
import unittest

from backend.app import create_app
from backend.board import Board
from backend.config import AppConfig
from backend.game_store import MemoryGameStore
from backend.socket_handlers import socketio
from backend.test.test_board import FakeTrie


def make_board(rack: Counter[str]) -> Board:
    board = Board(rack)
    board.valid_words = FakeTrie({"BE", "BEAN"})
    return board


@unittest.skipIf(socketio is None, "Flask-SocketIO is not installed.")
class SocketHandlerTests(unittest.TestCase):
    def make_app_and_store(self):
        rng = random.Random(1)
        store = MemoryGameStore(board_factory=make_board, rng=rng)
        app = create_app(
            board_factory=make_board,
            rng=rng,
            game_store=store,
            config=AppConfig(
                secret_key="test",
                redis_url=None,
                allowed_origins="*",
                game_ttl_seconds=60,
                host="127.0.0.1",
                port=5050,
                web_threads=20,
            ),
        )
        app.config.update(TESTING=True)
        return app, store

    def emit_ack(self, client, event, payload=None):
        ack = client.emit(event, payload or {}, callback=True)
        if isinstance(ack, list):
            return ack[0]
        return ack

    def test_create_game_stores_session_and_returns_invite(self):
        app, store = self.make_app_and_store()
        client = socketio.test_client(app)

        ack = self.emit_ack(client, "create_game", {
            "mode": "custom",
            "letters": "BE",
            "player_name": "  Alice   Smith ",
        })

        self.assertTrue(ack["success"])
        self.assertIn("invite_url", ack)
        self.assertEqual(ack["player_name"], "Alice Smith")
        self.assertEqual(
            store.get(ack["game_id"]).get_player_state(ack["player_id"]).player.player_name,
            "Alice Smith",
        )
        self.assertIsNotNone(store.get(ack["game_id"]))
        joined_events = [
            event["args"][0]
            for event in client.get_received()
            if event["name"] == "joined_game"
        ]
        self.assertEqual(joined_events[-1]["player_name"], "Alice Smith")

    def test_create_game_applies_truncated_and_capped_bag_multiplier(self):
        app, store = self.make_app_and_store()
        client = socketio.test_client(app)

        truncated_ack = self.emit_ack(client, "create_game", {
            "mode": "custom",
            "letters": "BE",
            "bag_multiplier": 1.59,
        })
        capped_ack = self.emit_ack(client, "create_game", {
            "mode": "custom",
            "letters": "BE",
            "bag_multiplier": 9,
        })

        truncated_session = store.get(truncated_ack["game_id"])
        capped_session = store.get(capped_ack["game_id"])
        self.assertEqual(truncated_session.bag_multiplier, 1.5)
        self.assertEqual(truncated_session.bag_count, 216)
        self.assertEqual(capped_session.bag_multiplier, 4.0)
        self.assertEqual(capped_session.bag_count, 576)

    def test_custom_game_without_rack_draws_random_starting_tiles(self):
        app, store = self.make_app_and_store()
        first_client = socketio.test_client(app)
        first_ack = self.emit_ack(first_client, "create_game", {
            "mode": "custom",
            "letters": "   ",
            "bag_multiplier": 1,
        })
        second_client = socketio.test_client(app)
        second_ack = self.emit_ack(second_client, "join_game", {
            "game_id": first_ack["game_id"],
        })

        session = store.get(first_ack["game_id"])
        self.assertTrue(first_ack["success"])
        self.assertTrue(second_ack["success"])
        self.assertEqual(session.mode, "custom")
        self.assertIsNone(session.custom_rack)
        self.assertEqual(
            session.get_player_state(first_ack["player_id"]).rack_count,
            21,
        )
        self.assertEqual(
            session.get_player_state(second_ack["player_id"]).rack_count,
            21,
        )
        self.assertEqual(session.bag_count, 102)

    def test_none_bag_requires_custom_starting_tiles(self):
        app, store = self.make_app_and_store()
        client = socketio.test_client(app)

        rejected_ack = self.emit_ack(client, "create_game", {
            "mode": "custom",
            "letters": "   ",
            "bag_multiplier": 0,
        })
        accepted_ack = self.emit_ack(client, "create_game", {
            "mode": "custom",
            "letters": "BE",
            "bag_multiplier": 0,
        })

        self.assertFalse(rejected_ack["success"])
        self.assertIn("when bag size is NONE", rejected_ack["message"])
        self.assertTrue(accepted_ack["success"])
        self.assertEqual(store.get(accepted_ack["game_id"]).bag_count, 0)

    def test_custom_game_rejects_multiplier_between_none_and_one_x(self):
        app, _ = self.make_app_and_store()
        client = socketio.test_client(app)

        ack = self.emit_ack(client, "create_game", {
            "mode": "custom",
            "letters": "BE",
            "bag_multiplier": 0.5,
        })

        self.assertFalse(ack["success"])
        self.assertIn("NONE (0x) or between 1x and 4x", ack["message"])

    def test_join_game_adds_second_player(self):
        app, store = self.make_app_and_store()
        first_client = socketio.test_client(app)
        first_ack = self.emit_ack(first_client, "create_game", {
            "mode": "custom",
            "letters": "BE",
            "player_name": "Alice",
        })
        first_client.get_received()
        second_client = socketio.test_client(app)

        second_ack = self.emit_ack(second_client, "join_game", {
            "game_id": first_ack["game_id"],
            "player_name": "Bob",
        })

        session = store.get(first_ack["game_id"])
        self.assertTrue(second_ack["success"])
        self.assertEqual(second_ack["player_name"], "Bob")
        self.assertEqual(len(session.player_state), 2)
        self.assertNotEqual(first_ack["player_id"], second_ack["player_id"])
        first_state_events = [
            event["args"][0]
            for event in first_client.get_received()
            if event["name"] == "state"
        ]
        self.assertEqual(
            [player["player_name"] for player in first_state_events[-1]["players"]],
            ["Alice", "Bob"],
        )

    def test_join_game_reconnects_existing_player_and_updates_name(self):
        app, store = self.make_app_and_store()
        first_client = socketio.test_client(app)
        first_ack = self.emit_ack(first_client, "create_game", {
            "mode": "custom",
            "letters": "BE",
            "player_name": "Alice",
        })
        first_client.disconnect()
        reconnect_client = socketio.test_client(app)

        reconnect_ack = self.emit_ack(reconnect_client, "join_game", {
            "game_id": first_ack["game_id"],
            "player_id": first_ack["player_id"],
            "player_name": "Different name",
        })

        session = store.get(first_ack["game_id"])
        self.assertTrue(reconnect_ack["success"])
        self.assertEqual(reconnect_ack["player_id"], first_ack["player_id"])
        self.assertEqual(reconnect_ack["player_name"], "Different name")
        self.assertEqual(len(session.player_state), 1)
        self.assertEqual(
            session.get_player_state(first_ack["player_id"]).player.player_name,
            "Different name",
        )

        reconnect_client.disconnect()
        blank_name_client = socketio.test_client(app)
        blank_name_ack = self.emit_ack(blank_name_client, "join_game", {
            "game_id": first_ack["game_id"],
            "player_id": first_ack["player_id"],
            "player_name": "   ",
        })

        self.assertEqual(blank_name_ack["player_name"], "Different name")
        self.assertEqual(len(store.get(first_ack["game_id"]).player_state), 1)

    def test_game_over_diff_names_winner_for_every_player(self):
        app, store = self.make_app_and_store()
        first_client = socketio.test_client(app)
        first_ack = self.emit_ack(first_client, "create_game", {
            "mode": "custom",
            "letters": "BE",
            "player_name": "Alice",
        })
        second_client = socketio.test_client(app)
        self.emit_ack(second_client, "join_game", {
            "game_id": first_ack["game_id"],
            "player_name": "Bob",
        })
        session = store.get(first_ack["game_id"])
        session.bag = Counter({"Z": 1})
        store.save(session)
        self.emit_ack(first_client, "place_tile", {
            "x": 0,
            "y": 0,
            "char": "B",
        })
        self.emit_ack(first_client, "place_tile", {
            "x": 1,
            "y": 0,
            "char": "E",
        })
        placed_diffs = [
            event["args"][0]
            for event in first_client.get_received()
            if event["name"] == "state_diff"
            and event["args"][0]["type"] == "tile_placed"
        ]
        self.assertTrue(placed_diffs[-1]["can_peel"])
        second_client.get_received()

        action_ack = self.emit_ack(first_client, "peel")

        first_diffs = [
            event["args"][0]
            for event in first_client.get_received()
            if event["name"] == "state_diff"
        ]
        second_diffs = [
            event["args"][0]
            for event in second_client.get_received()
            if event["name"] == "state_diff"
        ]
        session = store.get(first_ack["game_id"])
        self.assertTrue(action_ack["success"])
        self.assertEqual(first_diffs[-1]["type"], "game_over")
        self.assertEqual(first_diffs[-1]["winner_name"], "Alice")
        self.assertEqual(first_diffs[-1]["message"], "Alice wins!")
        self.assertEqual(second_diffs[-1]["winner_name"], "Alice")
        self.assertEqual(session.public_state()["winner_name"], "Alice")
        self.assertEqual(session.bag_count, 1)

    def test_mutation_saves_and_emits_private_diff(self):
        app, store = self.make_app_and_store()
        client = socketio.test_client(app)
        ack = self.emit_ack(client, "create_game", {
            "mode": "custom",
            "letters": "BE",
        })
        client.get_received()

        action_ack = self.emit_ack(client, "place_tile", {
            "x": 0,
            "y": 0,
            "char": "B",
        })
        received = client.get_received()
        diff_events = [
            event["args"][0]
            for event in received
            if event["name"] == "state_diff"
        ]
        state_events = [
            event
            for event in received
            if event["name"] == "state"
        ]

        self.assertTrue(action_ack["success"])
        self.assertEqual(
            store.get(ack["game_id"]).get_player_state(ack["player_id"]).board.to_state()["placed_tiles"][0]["char"],
            "B",
        )
        self.assertFalse(state_events)
        self.assertTrue(diff_events)
        self.assertEqual(diff_events[-1]["type"], "tile_placed")
        self.assertEqual(diff_events[-1]["tile"]["char"], "B")
        self.assertIn("partial_validation", diff_events[-1])

    def test_block_move_overwrite_is_atomic_and_emits_displaced_tiles(self):
        app, store = self.make_app_and_store()
        client = socketio.test_client(app)
        ack = self.emit_ack(client, "create_game", {
            "mode": "custom",
            "letters": "BEX",
        })
        for x, char in enumerate("BEX"):
            self.emit_ack(client, "place_tile", {
                "x": x,
                "y": 0,
                "char": char,
            })
        client.get_received()

        action_ack = self.emit_ack(client, "move_tiles", {
            "points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}],
            "offset": {"x": 1, "y": 0},
            "overwrite": True,
        })
        diff_events = [
            event["args"][0]
            for event in client.get_received()
            if event["name"] == "state_diff"
        ]
        player = store.get(ack["game_id"]).get_player_state(ack["player_id"])

        self.assertTrue(action_ack["success"])
        self.assertEqual(diff_events[-1]["type"], "tiles_moved")
        self.assertEqual(diff_events[-1]["rack_delta"], {"X": 1})
        self.assertEqual(diff_events[-1]["displaced"][0]["tile"]["char"], "X")
        self.assertEqual(
            {
                (point.x, point.y): tile.char
                for point, tile in player.board.placed_tiles.items()
            },
            {(1, 0): "B", (2, 0): "E"},
        )

    def test_block_move_collision_rejects_without_partial_mutation(self):
        app, store = self.make_app_and_store()
        client = socketio.test_client(app)
        ack = self.emit_ack(client, "create_game", {
            "mode": "custom",
            "letters": "BEX",
        })
        for x, char in enumerate("BEX"):
            self.emit_ack(client, "place_tile", {
                "x": x,
                "y": 0,
                "char": char,
            })
        client.get_received()

        action_ack = self.emit_ack(client, "move_tiles", {
            "points": [{"x": 0, "y": 0}, {"x": 1, "y": 0}],
            "offset": {"x": 1, "y": 0},
            "overwrite": False,
        })
        player = store.get(ack["game_id"]).get_player_state(ack["player_id"])

        self.assertFalse(action_ack["success"])
        self.assertIn("overlap existing tiles", action_ack["message"])
        self.assertEqual(
            {
                (point.x, point.y): tile.char
                for point, tile in player.board.placed_tiles.items()
            },
            {(0, 0): "B", (1, 0): "E", (2, 0): "X"},
        )

    def test_remove_tiles_returns_the_selected_block_to_the_rack(self):
        app, store = self.make_app_and_store()
        client = socketio.test_client(app)
        ack = self.emit_ack(client, "create_game", {
            "mode": "custom",
            "letters": "BEX",
        })
        for x, char in enumerate("BEX"):
            self.emit_ack(client, "place_tile", {
                "x": x,
                "y": 0,
                "char": char,
            })
        client.get_received()

        action_ack = self.emit_ack(client, "remove_tiles", {
            "points": [{"x": 0, "y": 0}, {"x": 2, "y": 0}],
        })
        diff_events = [
            event["args"][0]
            for event in client.get_received()
            if event["name"] == "state_diff"
        ]
        player = store.get(ack["game_id"]).get_player_state(ack["player_id"])

        self.assertTrue(action_ack["success"])
        self.assertEqual(diff_events[-1]["type"], "tiles_removed")
        self.assertEqual(diff_events[-1]["rack_delta"], {"B": 1, "X": 1})
        self.assertEqual(
            {
                (point.x, point.y): tile.char
                for point, tile in player.board.placed_tiles.items()
            },
            {(1, 0): "E"},
        )

    def test_local_board_diff_only_goes_to_acting_player(self):
        app, _ = self.make_app_and_store()
        first_client = socketio.test_client(app)
        first_ack = self.emit_ack(first_client, "create_game", {
            "mode": "custom",
            "letters": "BE",
        })
        second_client = socketio.test_client(app)
        self.emit_ack(second_client, "join_game", {
            "game_id": first_ack["game_id"],
        })
        first_client.get_received()
        second_client.get_received()

        self.emit_ack(first_client, "place_tile", {
            "x": 0,
            "y": 0,
            "char": "B",
        })

        first_events = first_client.get_received()
        second_events = second_client.get_received()
        self.assertTrue(any(event["name"] == "state_diff" for event in first_events))
        self.assertFalse(any(event["name"] == "state_diff" for event in second_events))

    def test_peel_emits_rack_diff_to_each_player(self):
        app, store = self.make_app_and_store()
        first_client = socketio.test_client(app)
        first_ack = self.emit_ack(first_client, "create_game", {
            "mode": "random",
        })
        second_client = socketio.test_client(app)
        second_ack = self.emit_ack(second_client, "join_game", {
            "game_id": first_ack["game_id"],
        })

        session = store.get(first_ack["game_id"])
        first = session.get_player_state(first_ack["player_id"])
        first.board.unplaced_letters = Counter({"B": 1, "E": 1})
        first.board.place_tile("B", 0, 0)
        first.board.place_tile("E", 1, 0)
        session.bag = Counter({"A": 2})
        store.save(session)
        first_client.get_received()
        second_client.get_received()

        action_ack = self.emit_ack(first_client, "peel")

        first_diffs = [
            event["args"][0]
            for event in first_client.get_received()
            if event["name"] == "state_diff"
        ]
        second_diffs = [
            event["args"][0]
            for event in second_client.get_received()
            if event["name"] == "state_diff"
        ]
        self.assertTrue(action_ack["success"])
        self.assertEqual(first_diffs[-1]["type"], "peeled")
        self.assertEqual(second_diffs[-1]["type"], "peeled")
        self.assertEqual(sum(first_diffs[-1]["rack_delta"].values()), 1)
        self.assertEqual(sum(second_diffs[-1]["rack_delta"].values()), 1)
        self.assertEqual(first_diffs[-1]["bag_count"], 0)
        self.assertIn("validated_board", first_diffs[-1])
        self.assertNotIn("validated_board", second_diffs[-1])
        self.assertEqual(
            [word["word"] for word in first_diffs[-1]["validated_board"]["formed_words"]],
            ["BE"],
        )
        self.assertEqual(second_ack["game_id"], first_ack["game_id"])

    def test_join_game_rejects_unknown_game(self):
        app, _ = self.make_app_and_store()
        client = socketio.test_client(app)

        ack = self.emit_ack(client, "join_game", {"game_id": "missing"})

        self.assertFalse(ack["success"])
        self.assertEqual(ack["message"], "Game not found.")


if __name__ == "__main__":
    unittest.main()
