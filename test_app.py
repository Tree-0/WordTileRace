from collections import Counter
import random
import unittest

from app import create_app
from board import Board
from game import Game
from test_board import FakeTrie


class AppTests(unittest.TestCase):
    def make_app(self):
        def board_factory(rack: Counter[str]) -> Board:
            board = Board(rack)
            board.valid_words = FakeTrie({"BE", "BEAN"})
            return board

        app = create_app(board_factory=board_factory)
        app.config.update(TESTING=True)
        return app

    def test_new_custom_game_returns_normalized_rack(self):
        client = self.make_app().test_client()

        response = client.post("/api/new", json={"mode": "custom", "letters": "bean"})
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["rack"], {"A": 1, "B": 1, "E": 1, "N": 1})
        self.assertEqual(data["bag_count"], 0)

    def test_new_random_game_returns_21_tiles(self):
        client = self.make_app().test_client()

        response = client.post("/api/new", json={"mode": "random"})
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(sum(data["rack"].values()), 21)
        self.assertEqual(data["bag_count"], 123)

    def test_place_endpoint_places_tiles_and_reports_valid_words(self):
        client = self.make_app().test_client()
        client.post("/api/new", json={"mode": "custom", "letters": "BE"})

        client.post("/api/place", json={"x": 0, "y": 0, "char": "B"})
        response = client.post("/api/place", json={"x": 1, "y": 0, "char": "E"})
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["is_valid"])
        self.assertTrue(data["is_game_over"])
        self.assertEqual(data["formed_words"][0]["word"], "BE")

    def test_place_endpoint_overwrites_when_available(self):
        client = self.make_app().test_client()
        client.post("/api/new", json={"mode": "custom", "letters": "BE"})
        client.post("/api/place", json={"x": 0, "y": 0, "char": "B"})

        response = client.post("/api/place", json={
            "x": 0,
            "y": 0,
            "char": "E",
            "overwrite": True,
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["placed_tiles"], [
            {"x": 0, "y": 0, "char": "E", "is_wildcard": False},
        ])
        self.assertEqual(data["rack"], {"B": 1})

    def test_place_endpoint_rejects_unavailable_tile(self):
        client = self.make_app().test_client()
        client.post("/api/new", json={"mode": "custom", "letters": "B"})

        response = client.post("/api/place", json={"x": 0, "y": 0, "char": "X"})
        data = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data["success"])
        self.assertEqual(data["placed_tiles"], [])

    def test_remove_endpoint_returns_tile_to_rack(self):
        client = self.make_app().test_client()
        client.post("/api/new", json={"mode": "custom", "letters": "B"})
        client.post("/api/place", json={"x": 0, "y": 0, "char": "B"})

        response = client.post("/api/remove", json={"x": 0, "y": 0})
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["rack"], {"B": 1})
        self.assertEqual(data["placed_tiles"], [])

    def test_move_endpoint_moves_tile_without_changing_rack(self):
        client = self.make_app().test_client()
        client.post("/api/new", json={"mode": "custom", "letters": "B"})
        client.post("/api/place", json={"x": 0, "y": 0, "char": "B"})

        response = client.post("/api/move", json={
            "from": {"x": 0, "y": 0},
            "to": {"x": 2, "y": -1},
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["rack"], {})
        self.assertEqual(data["placed_tiles"], [
            {"x": 2, "y": -1, "char": "B", "is_wildcard": False},
        ])

    def test_move_endpoint_rejects_occupied_target(self):
        client = self.make_app().test_client()
        client.post("/api/new", json={"mode": "custom", "letters": "BE"})
        client.post("/api/place", json={"x": 0, "y": 0, "char": "B"})
        client.post("/api/place", json={"x": 1, "y": 0, "char": "E"})

        response = client.post("/api/move", json={
            "from": {"x": 0, "y": 0},
            "to": {"x": 1, "y": 0},
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data["success"])
        self.assertEqual(len(data["placed_tiles"]), 2)

    def test_peel_endpoint_draws_one_tile_when_ready(self):
        board = Board(Counter({"B": 1, "E": 1}))
        board.valid_words = FakeTrie({"BE"})
        board.place_tile("B", 0, 0)
        board.place_tile("E", 1, 0)
        game = Game(board, Counter({"A": 1}), random.Random(1), "random")
        client = self.make_app_with_game(game).test_client()

        response = client.post("/api/peel", json={})
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["rack"], {"A": 1})
        self.assertEqual(data["bag_count"], 0)
        self.assertFalse(data["is_game_over"])

    def test_peel_endpoint_rejects_when_rack_is_not_empty(self):
        game = Game(
            Board(Counter({"B": 1})),
            Counter({"A": 1}),
            random.Random(1),
            "random",
        )
        game.board.valid_words = FakeTrie({"BE"})
        client = self.make_app_with_game(game).test_client()

        response = client.post("/api/peel", json={})
        data = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data["success"])

    def test_dump_endpoint_returns_tile_and_draws_three(self):
        game = Game(
            Board(Counter({"B": 1})),
            Counter({"A": 1, "C": 1, "D": 1}),
            random.Random(1),
            "random",
        )
        game.board.valid_words = FakeTrie({"BE"})
        client = self.make_app_with_game(game).test_client()

        response = client.post("/api/dump", json={"char": "B"})
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(sum(data["rack"].values()), 3)
        self.assertEqual(data["bag_count"], 1)

    def test_dump_endpoint_rejects_missing_tile(self):
        game = Game(
            Board(Counter({"B": 1})),
            Counter({"A": 3}),
            random.Random(1),
            "random",
        )
        game.board.valid_words = FakeTrie({"BE"})
        client = self.make_app_with_game(game).test_client()

        response = client.post("/api/dump", json={"char": "E"})
        data = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data["success"])

    def test_completed_game_rejects_more_board_mutations(self):
        client = self.make_app().test_client()
        client.post("/api/new", json={"mode": "custom", "letters": "BE"})
        client.post("/api/place", json={"x": 0, "y": 0, "char": "B"})
        client.post("/api/place", json={"x": 1, "y": 0, "char": "E"})

        response = client.post("/api/remove", json={"x": 0, "y": 0})
        data = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data["success"])
        self.assertTrue(data["is_game_over"])
        self.assertEqual(len(data["placed_tiles"]), 2)

    def make_app_with_game(self, game: Game):
        def board_factory(rack: Counter[str]) -> Board:
            board = Board(rack)
            board.valid_words = FakeTrie({"BE", "BEAN"})
            return board

        app = create_app(board_factory=board_factory, initial_game=game)
        app.config.update(TESTING=True)
        return app


if __name__ == "__main__":
    unittest.main()
