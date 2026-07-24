from collections import Counter
import random
import unittest

from backend.board import Board
from backend.game_session import GameSession
from backend.game_store import MemoryGameStore, RedisGameStore
from backend.test.test_board import FakeTrie


def make_board(rack: Counter[str], valid_words: set[str] | None = None) -> Board:
    board = Board(rack)
    board.valid_words = FakeTrie(valid_words or {"BE", "BEAN"})
    return board


class FakeRedisLock:
    def __init__(self):
        self.acquired = False
        self.released = False

    def acquire(self, blocking=True):
        self.acquired = True
        return True

    def release(self):
        self.released = True


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}
        self.last_lock = None
        self.pinged = False

    def ping(self):
        self.pinged = True
        return True

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, ttl, value):
        self.values[key] = value
        self.ttls[key] = ttl

    def lock(self, key, timeout, blocking_timeout):
        self.last_lock = FakeRedisLock()
        return self.last_lock


class GameStoreTests(unittest.TestCase):
    def test_memory_store_round_trips_through_record(self):
        store = MemoryGameStore(
            board_factory=make_board,
            rng=random.Random(1),
        )
        session = GameSession.new_game("BE", board_factory=make_board)
        player_state = session.add_player("Natha")
        session.place_tile(player_state.player.id, "B", 0, 0)

        store.save(session)
        restored = store.get(str(session.game_id))

        self.assertIsNot(restored, session)
        self.assertEqual(restored.game_id, session.game_id)
        self.assertEqual(
            restored.get_player_state(player_state.player.id).board.to_state()["placed_tiles"][0]["char"],
            "B",
        )
        self.assertTrue(restored.private_state(player_state.player.id)["can_undo"])
        restored.undo(player_state.player.id)
        self.assertEqual(
            restored.get_player_state(player_state.player.id).board.placed_tiles,
            {},
        )

    def test_redis_store_sets_ttl_and_restores_session(self):
        redis_client = FakeRedis()
        store = RedisGameStore(
            redis_client,
            board_factory=make_board,
            rng=random.Random(1),
            ttl_seconds=60,
        )
        session = GameSession.new_game("BE", board_factory=make_board)
        player_state = session.add_player("Natha")
        session.place_tile(player_state.player.id, "B", 0, 0)

        store.save(session)
        restored = store.get(str(session.game_id))

        self.assertEqual(redis_client.ttls[f"game:{session.game_id}"], 60)
        self.assertEqual(restored.game_id, session.game_id)
        self.assertEqual(
            restored.get_player_state(player_state.player.id).board.to_state()["placed_tiles"][0]["char"],
            "B",
        )
        self.assertTrue(restored.private_state(player_state.player.id)["can_undo"])
        restored.undo(player_state.player.id)
        self.assertEqual(
            restored.get_player_state(player_state.player.id).board.placed_tiles,
            {},
        )

    def test_redis_store_lock_uses_game_lock_key(self):
        redis_client = FakeRedis()
        store = RedisGameStore(redis_client, board_factory=make_board)

        with store.lock("abc"):
            self.assertTrue(redis_client.last_lock.acquired)

        self.assertTrue(redis_client.last_lock.released)


if __name__ == "__main__":
    unittest.main()
