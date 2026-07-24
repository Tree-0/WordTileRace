from collections import Counter
import unittest

from backend.app import create_app
from backend.board import Board
from backend.test.test_board import FakeTrie
from backend.word_definitions import DefinitionLookupError


class AppTests(unittest.TestCase):
    def make_app(self, definition_lookup=None):
        def board_factory(rack: Counter[str]) -> Board:
            board = Board(rack)
            board.valid_words = FakeTrie({"BE", "BEAN"})
            return board

        app = create_app(
            board_factory=board_factory,
            definition_lookup=definition_lookup,
        )
        app.config.update(TESTING=True)
        return app

    def test_index_serves_browser_app(self):
        client = self.make_app().test_client()

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Word Tile Race", response.data)
        self.assertIn(b'id="home-view"', response.data)
        self.assertIn(b'id="random-game-button"', response.data)
        self.assertIn(b'id="join-game-form"', response.data)
        self.assertIn(b'id="new-game-settings"', response.data)
        self.assertIn(b'id="custom-game-id"', response.data)
        self.assertIn(b'maxlength="24"', response.data)
        self.assertIn(b'id="custom-bag-multiplier"', response.data)
        self.assertIn(b'<span>NONE</span>', response.data)
        self.assertIn(b'Maximum 4&times;', response.data)
        self.assertIn(b'id="game-view"', response.data)
        self.assertIn(b'id="home-button"', response.data)
        self.assertIn(b'id="nickname-input"', response.data)
        self.assertIn(b'id="players-drawer"', response.data)
        self.assertIn(b'id="overwrite-block-moves"', response.data)
        self.assertIn(b'id="undo-button"', response.data)
        self.assertIn(b'id="round-lobby"', response.data)
        self.assertIn(b'id="start-round-button"', response.data)
        self.assertIn(b'id="winner-play-again-button"', response.data)
        self.assertIn(b'id="winner-leave-button"', response.data)
        self.assertIn(b'id="help-dialog"', response.data)
        self.assertIn(b'id="winner-dialog"', response.data)

    def test_health_endpoint_returns_success(self):
        client = self.make_app().test_client()

        response = client.get("/api/health")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["storage"], "memory")

    def test_definitions_endpoint_returns_grouped_meanings(self):
        def definition_lookup(word: str):
            self.assertEqual(word, "hello")
            return {
                "word": "HELLO",
                "meanings": [
                    {
                        "part_of_speech": "noun",
                        "definitions": [
                            {"definition": "an utterance of hello."},
                        ],
                    },
                ],
            }

        client = self.make_app(definition_lookup=definition_lookup).test_client()

        response = client.get("/api/definitions/hello")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["word"], "HELLO")
        self.assertEqual(data["meanings"][0]["part_of_speech"], "noun")

    def test_definitions_endpoint_rejects_invalid_word(self):
        def definition_lookup(word: str):
            raise ValueError("Word must contain only A-Z letters.")

        client = self.make_app(definition_lookup=definition_lookup).test_client()

        response = client.get("/api/definitions/hello1")
        data = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(data["success"])
        self.assertEqual(data["word"], "HELLO1")

    def test_definitions_endpoint_returns_json_for_lookup_failure(self):
        def definition_lookup(word: str):
            raise DefinitionLookupError("Definition lookup failed.")

        client = self.make_app(definition_lookup=definition_lookup).test_client()

        response = client.get("/api/definitions/hello")
        data = response.get_json()

        self.assertEqual(response.status_code, 502)
        self.assertFalse(data["success"])
        self.assertEqual(data["message"], "Definition lookup failed.")


if __name__ == "__main__":
    unittest.main()
