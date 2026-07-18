from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from copy import deepcopy
import json
import random
from threading import RLock
from typing import Any, Protocol

from backend.board import Board
from backend.game_session import GameSession


BoardFactory = Callable[[Any], Board]
DEFAULT_GAME_TTL_SECONDS = 7_200


class GameStore(Protocol):
    def get(self, game_id: str) -> GameSession | None:
        ...

    def save(self, session: GameSession) -> None:
        ...

    @contextmanager
    def lock(self, game_id: str) -> Iterator[None]:
        ...


class MemoryGameStore:
    def __init__(
        self,
        *,
        board_factory: BoardFactory = Board,
        rng: random.Random | None = None,
    ):
        self.board_factory = board_factory
        self.rng = rng or random.Random()
        self._records: dict[str, dict] = {}
        self._locks: dict[str, RLock] = {}
        self._meta_lock = RLock()

    def get(self, game_id: str) -> GameSession | None:
        record = self._records.get(game_id)
        if record is None:
            return None
        return GameSession.from_record(
            deepcopy(record),
            board_factory=self.board_factory,
            rng=self.rng,
        )

    def save(self, session: GameSession) -> None:
        self._records[str(session.game_id)] = deepcopy(session.to_record())

    @contextmanager
    def lock(self, game_id: str) -> Iterator[None]:
        with self._meta_lock:
            lock = self._locks.setdefault(game_id, RLock())
        with lock:
            yield


class RedisGameStore:
    def __init__(
        self,
        redis_client,
        *,
        board_factory: BoardFactory = Board,
        rng: random.Random | None = None,
        ttl_seconds: int = DEFAULT_GAME_TTL_SECONDS,
    ):
        self.redis = redis_client
        self.board_factory = board_factory
        self.rng = rng or random.Random()
        self.ttl_seconds = ttl_seconds

    @classmethod
    def from_url(
        cls,
        redis_url: str,
        *,
        board_factory: BoardFactory = Board,
        rng: random.Random | None = None,
        ttl_seconds: int = DEFAULT_GAME_TTL_SECONDS,
    ) -> "RedisGameStore":
        import redis

        redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
        redis_client.ping()
        return cls(
            redis_client,
            board_factory=board_factory,
            rng=rng,
            ttl_seconds=ttl_seconds,
        )

    def get(self, game_id: str) -> GameSession | None:
        raw_record = self.redis.get(self._game_key(game_id))
        if raw_record is None:
            return None

        record = json.loads(raw_record)
        return GameSession.from_record(
            record,
            board_factory=self.board_factory,
            rng=self.rng,
        )

    def save(self, session: GameSession) -> None:
        self.redis.setex(
            self._game_key(str(session.game_id)),
            self.ttl_seconds,
            json.dumps(session.to_record(), sort_keys=True),
        )

    @contextmanager
    def lock(self, game_id: str) -> Iterator[None]:
        lock = self.redis.lock(
            self._lock_key(game_id),
            timeout=10,
            blocking_timeout=5,
        )
        acquired = lock.acquire(blocking=True)
        if not acquired:
            raise TimeoutError("Could not acquire game lock.")

        try:
            yield
        finally:
            lock.release()

    def _game_key(self, game_id: str) -> str:
        return f"game:{game_id}"

    def _lock_key(self, game_id: str) -> str:
        return f"game:{game_id}:lock"


def create_game_store(
    *,
    redis_url: str | None,
    board_factory: BoardFactory = Board,
    rng: random.Random | None = None,
    ttl_seconds: int = DEFAULT_GAME_TTL_SECONDS,
) -> GameStore:
    if redis_url:
        return RedisGameStore.from_url(
            redis_url,
            board_factory=board_factory,
            rng=rng,
            ttl_seconds=ttl_seconds,
        )

    return MemoryGameStore(board_factory=board_factory, rng=rng)
