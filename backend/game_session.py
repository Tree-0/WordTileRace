from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
import random
from typing import Any
from uuid import UUID, uuid4

from backend.board import Board, Point, normalize_char
from backend.game import Player, PlayerState
from backend.tile_bag import (
    DEFAULT_DUMP_DRAW_COUNT,
    DEFAULT_RANDOM_DRAW_COUNT,
    STANDARD_TILE_DISTRIBUTION,
    draw_tiles,
    make_custom_rack,
)


BoardFactory = Callable[[Any], Board]


@dataclass
class GameSession:
    """Authoritative Bananagrams session state."""

    game_id: UUID
    bag: Counter[str]
    rng: random.Random
    player_state: dict[UUID, PlayerState]
    mode: str
    board_factory: BoardFactory = field(default=Board, repr=False)
    custom_rack: Counter[str] | None = None
    winner_id: UUID | None = None

    @classmethod
    def new_game(
        cls,
        letters: str | None = None,
        rng: random.Random | None = None,
        board_factory: BoardFactory = Board,
    ) -> "GameSession":
        rng = rng or random.Random()
        if letters is None:
            return cls(
                uuid4(),
                STANDARD_TILE_DISTRIBUTION.copy(),
                rng,
                {},
                "random",
                board_factory,
            )

        return cls(
            uuid4(),
            Counter(),
            rng,
            {},
            "custom",
            board_factory,
            make_custom_rack(letters),
        )

    @property
    def bag_count(self) -> int:
        return sum(self.bag.values())

    @property
    def is_game_over(self) -> bool:
        return self.winner_id is not None

    @property
    def winner(self) -> PlayerState | None:
        if self.winner_id is None:
            return None
        return self.player_state.get(self.winner_id)

    def add_player(self, player_name: str | None = None) -> PlayerState:
        if self.custom_rack is not None:
            tiles = self.custom_rack.copy()
        else:
            tiles = draw_tiles(self.bag, DEFAULT_RANDOM_DRAW_COUNT, self.rng)

        player_state = PlayerState.new_player_state(
            Player(player_name),
            tiles,
            self.board_factory,
            self.mode,
        )
        self.player_state[player_state.player.id] = player_state
        return player_state

    def place_tile(
        self,
        player_id: UUID | str,
        char: str,
        x: int,
        y: int,
        overwrite: bool = False,
    ) -> None:
        self._ensure_active()
        player_state = self._get_player_state(player_id)
        if overwrite:
            player_state.board.place_or_overwrite_tile(char, x, y)
        else:
            player_state.board.place_tile(char, x, y)
        self._update_winner(player_state)

    def move_tile(
        self,
        player_id: UUID | str,
        from_point: Point,
        to_point: Point,
    ) -> None:
        self._ensure_active()
        player_state = self._get_player_state(player_id)
        player_state.board.move_tile(from_point, to_point)
        self._update_winner(player_state)

    def remove_tile(self, player_id: UUID | str, x: int, y: int) -> None:
        self._ensure_active()
        player_state = self._get_player_state(player_id)
        if not player_state.board.remove_letter(x, y):
            raise ValueError(f"No tile placed at ({x}, {y}).")
        self._update_winner(player_state)

    def player_can_peel(self, player_id: UUID | str) -> bool:
        player_state = self._get_player_state(player_id)
        return player_state.can_peel_board

    def player_can_dump(self, player_id: UUID | str) -> bool:
        player_state = self._get_player_state(player_id)
        return player_state.can_dump_rack and self.bag_count > 0

    def peel(self, player_id: UUID | str) -> Counter[str]:
        self._ensure_active()
        player_state = self._get_player_state(player_id)
        if not player_state.can_peel_board:
            raise ValueError("Player cannot peel.")

        if self.bag_count == 0:
            self.winner_id = player_state.player.id
            return Counter()

        player_count = len(self.player_state)
        if self.bag_count < player_count:
            raise ValueError("Fewer tiles in bag than number of players. Not peeling.")

        drawn_by_player = Counter()
        for other_player_state in self.player_state.values():
            drawn = draw_tiles(self.bag, 1, self.rng)
            other_player_state.board.unplaced_letters.update(drawn)
            drawn_by_player.update(drawn)

        return drawn_by_player

    def dump(self, player_id: UUID | str, char: str) -> Counter[str]:
        self._ensure_active()
        if self.bag_count == 0:
            raise ValueError("No tiles remain in the bag.")

        player_state = self._get_player_state(player_id)
        char = normalize_char(char)
        if player_state.board.unplaced_letters[char] <= 0:
            raise ValueError(f"No {char} tile is available to dump.")

        player_state.board.unplaced_letters[char] -= 1
        if player_state.board.unplaced_letters[char] <= 0:
            del player_state.board.unplaced_letters[char]

        self.bag[char] += 1
        draw_count = min(DEFAULT_DUMP_DRAW_COUNT, self.bag_count)
        drawn = draw_tiles(self.bag, draw_count, self.rng)
        player_state.board.unplaced_letters.update(drawn)
        return drawn

    def private_state(
        self,
        player_id: UUID | str,
        *,
        success: bool = True,
        message: str | None = None,
    ) -> dict:
        player_id = self._normalize_player_id(player_id)
        player_state = self._get_player_state(player_id)
        state = player_state.to_private_state()
        state.update({
            "success": success,
            "game_id": str(self.game_id),
            "bag_count": self.bag_count,
            "can_peel": (
                not self.is_game_over
                and player_state.can_peel_board
                and self.bag_count >= len(self.player_state)
            ),
            "can_dump": (
                not self.is_game_over
                and player_state.can_dump_rack
                and self.bag_count > 0
            ),
            "is_game_over": self.is_game_over,
            "winner_id": str(self.winner_id) if self.winner_id else None,
            "winner_name": (
                self.winner.player.player_name
                if self.winner is not None
                else None
            ),
            "players": self._public_players(),
            "public": self.public_state(),
        })
        if message:
            state["message"] = message
        if self.is_game_over:
            state["messages"] = [self._winner_message()]
        elif state["can_peel"]:
            state["messages"] = ["Peel is available. Draw one new tile for every player."]
        return state

    def public_state(self) -> dict:
        return {
            "game_id": str(self.game_id),
            "bag_count": self.bag_count,
            "is_game_over": self.is_game_over,
            "winner_id": str(self.winner_id) if self.winner_id else None,
            "winner_name": (
                self.winner.player.player_name
                if self.winner is not None
                else None
            ),
            "mode": self.mode,
            "players": self._public_players(),
        }

    def _public_players(self) -> list[dict]:
        return [
            player_state.to_public_state()
            for player_state in sorted(
                self.player_state.values(),
                key=lambda state: state.player.player_name or str(state.player.id),
            )
        ]

    def _update_winner(self, player_state: PlayerState) -> None:
        if (
            self.bag_count == 0
            and player_state.rack_count == 0
            and player_state.board.is_valid_board()
        ):
            self.winner_id = player_state.player.id

    def _ensure_active(self) -> None:
        if self.is_game_over:
            raise ValueError("Game is complete. Start a new game to keep playing.")

    def _get_player_state(self, player_id: UUID | str) -> PlayerState:
        normalized_player_id = self._normalize_player_id(player_id)
        try:
            return self.player_state[normalized_player_id]
        except KeyError:
            raise ValueError("Invalid player id.") from None

    def _normalize_player_id(self, player_id: UUID | str) -> UUID:
        if isinstance(player_id, UUID):
            return player_id
        try:
            return UUID(str(player_id))
        except ValueError:
            raise ValueError("Invalid player id.") from None

    def _winner_message(self) -> str:
        if self.winner is None:
            return "Game complete."
        name = self.winner.player.player_name or "A player"
        return f"{name} won! All tiles are placed in valid words."
