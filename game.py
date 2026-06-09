from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
import random
from typing import Any

from board import Board, normalize_char
from tile_bag import (
    DEFAULT_RANDOM_DRAW_COUNT,
    STANDARD_TILE_DISTRIBUTION,
    draw_tiles,
    make_custom_rack,
)


BoardFactory = Callable[[Any], Board]


@dataclass
class Game:
    """Single-player Bananagrams session state."""

    board: Board
    bag: Counter[str]
    rng: random.Random
    mode: str

    @classmethod
    def new_random(
        cls,
        board_factory: BoardFactory = Board,
        rng: random.Random | None = None,
    ) -> "Game":
        rng = rng or random.Random()
        bag = STANDARD_TILE_DISTRIBUTION.copy()
        rack = draw_tiles(bag, DEFAULT_RANDOM_DRAW_COUNT, rng)
        return cls(board_factory(rack), bag, rng, "random")

    @classmethod
    def new_custom(
        cls,
        letters: str,
        board_factory: BoardFactory = Board,
        rng: random.Random | None = None,
    ) -> "Game":
        rng = rng or random.Random()
        return cls(board_factory(make_custom_rack(letters)), Counter(), rng, "custom")

    @property
    def rack_count(self) -> int:
        return sum(self.board.unplaced_letters.values())

    @property
    def bag_count(self) -> int:
        return sum(self.bag.values())

    @property
    def can_peel(self) -> bool:
        return self.board.is_valid_board() and self.rack_count == 0 and self.bag_count > 0

    @property
    def can_dump(self) -> bool:
        return self.rack_count > 0 and self.bag_count > 0

    @property
    def is_game_over(self) -> bool:
        return self.bag_count == 0 and self.rack_count == 0 and self.board.is_valid_board()

    def peel(self) -> Counter[str]:
        """Draw one tile after all rack tiles are placed in a valid arrangement."""
        if self.bag_count == 0:
            raise ValueError("No tiles remain in the bag.")

        if self.rack_count > 0:
            raise ValueError("Place all rack tiles before peeling.")

        if not self.board.is_valid_board():
            raise ValueError("The board must be valid before peeling.")

        drawn = draw_tiles(self.bag, 1, self.rng)
        self.board.unplaced_letters.update(drawn)
        return drawn

    def dump(self, char: str) -> Counter[str]:
        """Return one rack tile to the bag and draw up to three replacement tiles."""
        char = normalize_char(char)
        if self.board.unplaced_letters[char] <= 0:
            raise ValueError(f"No {char} tile is available to dump.")

        if self.bag_count == 0:
            raise ValueError("No tiles remain in the bag.")

        self.board.unplaced_letters[char] -= 1
        if self.board.unplaced_letters[char] <= 0:
            del self.board.unplaced_letters[char]

        self.bag[char] += 1
        draw_count = min(3, self.bag_count)
        drawn = draw_tiles(self.bag, draw_count, self.rng)
        self.board.unplaced_letters.update(drawn)
        return drawn

    def to_state(self) -> dict:
        state = self.board.to_state()
        state.update({
            "bag_count": self.bag_count,
            "can_peel": self.can_peel,
            "can_dump": self.can_dump,
            "is_game_over": self.is_game_over,
            "mode": self.mode,
        })

        if self.is_game_over:
            state["messages"] = ["Game complete! All tiles are placed in valid words."]
        elif self.can_peel:
            state["messages"] = ["Peel is available. Draw one new tile."]

        return state
