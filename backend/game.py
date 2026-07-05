from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from backend.board import Board


BoardFactory = Callable[[Any], Board]


@dataclass
class Player:
    player_name: str | None = None
    id: UUID = field(default_factory=uuid4)


@dataclass
class PlayerState:
    """Private state for one Bananagrams player."""

    player: Player
    board: Board
    mode: str

    @classmethod
    def new_player_state(
        cls,
        player: Player,
        tiles: Counter[str],
        board_factory: BoardFactory = Board,
        mode: str = "random",
    ) -> "PlayerState":
        return cls(player, board_factory(tiles), mode)

    @property
    def rack_count(self) -> int:
        return sum(self.board.unplaced_letters.values())

    @property
    def board_is_valid(self) -> bool:
        return self.board.is_valid_board()

    @property
    def can_peel_board(self) -> bool:
        return self.rack_count == 0 and self.board_is_valid

    @property
    def can_dump_rack(self) -> bool:
        return self.rack_count > 0

    def to_private_state(self) -> dict:
        state = self.board.to_state()
        state.update({
            "player_id": str(self.player.id),
            "player_name": self.player.player_name,
            "rack_count": self.rack_count,
            "can_peel_board": self.can_peel_board,
            "can_dump_rack": self.can_dump_rack,
            "mode": self.mode,
        })
        return state

    def to_public_state(self) -> dict:
        return {
            "player_id": str(self.player.id),
            "player_name": self.player.player_name,
            "rack_count": self.rack_count,
            "board_is_valid": self.board_is_valid,
            "can_peel_board": self.can_peel_board,
            "mode": self.mode,
        }

    def to_state(self) -> dict:
        return self.to_private_state()
