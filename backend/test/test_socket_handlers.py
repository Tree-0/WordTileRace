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
        })

        self.assertTrue(ack["success"])
        self.assertIn("invite_url", ack)
        self.assertIsNotNone(store.get(ack["game_id"]))

    def test_join_game_adds_second_player(self):
        app, store = self.make_app_and_store()
        first_client = socketio.test_client(app)
        first_ack = self.emit_ack(first_client, "create_game", {
            "mode": "custom",
            "letters": "BE",
        })
        second_client = socketio.test_client(app)

        second_ack = self.emit_ack(second_client, "join_game", {
            "game_id": first_ack["game_id"],
        })

        session = store.get(first_ack["game_id"])
        self.assertTrue(second_ack["success"])
        self.assertEqual(len(session.player_state), 2)
        self.assertNotEqual(first_ack["player_id"], second_ack["player_id"])

    def test_join_game_reconnects_existing_player(self):
        app, store = self.make_app_and_store()
        first_client = socketio.test_client(app)
        first_ack = self.emit_ack(first_client, "create_game", {
            "mode": "custom",
            "letters": "BE",
        })
        first_client.disconnect()
        reconnect_client = socketio.test_client(app)

        reconnect_ack = self.emit_ack(reconnect_client, "join_game", {
            "game_id": first_ack["game_id"],
            "player_id": first_ack["player_id"],
        })

        session = store.get(first_ack["game_id"])
        self.assertTrue(reconnect_ack["success"])
        self.assertEqual(reconnect_ack["player_id"], first_ack["player_id"])
        self.assertEqual(len(session.player_state), 1)

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
