from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
import random
from typing import Any
from uuid import UUID, uuid4

from backend.board import Board, Point, Tile, normalize_char
from backend.game import Player, PlayerState
from backend.tile_bag import (
    DEFAULT_BAG_MULTIPLIER,
    DEFAULT_DUMP_DRAW_COUNT,
    DEFAULT_RANDOM_DRAW_COUNT,
    NONE_BAG_MULTIPLIER,
    draw_tiles,
    make_custom_rack,
    make_tile_bag,
    normalize_bag_multiplier,
)


BoardFactory = Callable[[Any], Board]
MAX_PLAYER_NAME_LENGTH = 24
MAX_UNDO_HISTORY = 8


def _point_payload(point: Point) -> dict[str, int]:
    return {"x": point.x, "y": point.y}


def _tile_payload(tile: Tile) -> dict:
    return {
        "char": tile.char,
        "is_wildcard": tile.is_wildcard,
    }


def _counter_payload(counter: Counter[str]) -> dict[str, int]:
    return {
        char: count
        for char, count in sorted(counter.items())
        if count
    }


def _counter_delta(before: Counter[str], after: Counter[str]) -> dict[str, int]:
    return {
        char: after[char] - before[char]
        for char in sorted(set(before) | set(after))
        if after[char] != before[char]
    }


@dataclass
class GameSession:
    """Authoritative word-tile session state."""

    game_id: UUID
    bag: Counter[str]
    rng: random.Random
    player_state: dict[UUID, PlayerState]
    mode: str
    board_factory: BoardFactory = field(default=Board, repr=False)
    custom_rack: Counter[str] | None = None
    winner_id: UUID | None = None
    bag_multiplier: float = DEFAULT_BAG_MULTIPLIER
    undo_history: dict[UUID, list[dict]] = field(default_factory=dict, repr=False)

    @classmethod
    def new_game(
        cls,
        letters: str | None = None,
        rng: random.Random | None = None,
        board_factory: BoardFactory = Board,
        bag_multiplier: object = DEFAULT_BAG_MULTIPLIER,
    ) -> "GameSession":
        rng = rng or random.Random()
        normalized_multiplier = normalize_bag_multiplier(bag_multiplier)
        bag = make_tile_bag(normalized_multiplier)
        is_custom_mode = letters is not None
        normalized_letters = letters.strip() if letters is not None else ""
        custom_rack = (
            make_custom_rack(normalized_letters)
            if normalized_letters
            else None
        )
        if normalized_multiplier == NONE_BAG_MULTIPLIER and custom_rack is None:
            raise ValueError(
                "Enter custom starting tiles when bag size is NONE."
            )

        return cls(
            game_id=uuid4(),
            bag=bag,
            rng=rng,
            player_state={},
            mode="custom" if is_custom_mode else "random",
            board_factory=board_factory,
            custom_rack=custom_rack,
            bag_multiplier=normalized_multiplier,
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

    @property
    def winner_name(self) -> str | None:
        winner = self.winner
        return winner.player.player_name if winner is not None else None

    def add_player(self, player_name: str | None = None) -> PlayerState:
        if self.custom_rack is not None:
            tiles = self.custom_rack.copy()
        else:
            tiles = draw_tiles(self.bag, DEFAULT_RANDOM_DRAW_COUNT, self.rng)

        player_state = PlayerState.new_player_state(
            Player(self._resolved_player_name(player_name)),
            tiles,
            self.board_factory,
            self.mode,
        )
        self.player_state[player_state.player.id] = player_state
        self.undo_history[player_state.player.id] = []
        return player_state

    def rename_player(
        self,
        player_id: UUID | str,
        player_name: object,
    ) -> PlayerState:
        player_state = self._get_player_state(player_id)
        normalized_name = self._normalize_player_name(player_name)
        if normalized_name is None:
            raise ValueError("Nickname is required.")
        player_state.player.player_name = normalized_name
        return player_state

    def get_player_state(self, player_id: UUID | str) -> PlayerState:
        return self._get_player_state(player_id)

    def place_tile(
        self,
        player_id: UUID | str,
        char: str,
        x: int,
        y: int,
        overwrite: bool = False,
    ) -> dict:
        self._ensure_active()
        player_state = self._get_player_state(player_id)
        before_tiles, before_rack = self._capture_board_edit(player_state.board)
        point = Point(x, y)
        if overwrite:
            tile = player_state.board.place_or_overwrite_tile(char, x, y)
        else:
            tile = player_state.board.place_tile(char, x, y)
        self._remember_board_edit(
            player_state,
            before_tiles,
            before_rack,
            "tile placement",
        )
        return {
            "type": "tile_placed",
            "point": _point_payload(point),
            "tile": _tile_payload(tile),
            "rack_delta": _counter_delta(
                before_rack,
                player_state.board.unplaced_letters,
            ),
            "partial_validation": (
                player_state.board.get_formed_word_details_around_points([point])
            ),
            **self._action_capabilities(player_state),
        }

    def move_tile(
        self,
        player_id: UUID | str,
        from_point: Point,
        to_point: Point,
    ) -> dict:
        self._ensure_active()
        player_state = self._get_player_state(player_id)
        before_tiles, before_rack = self._capture_board_edit(player_state.board)
        tile = player_state.board.move_tile(from_point, to_point)
        self._remember_board_edit(
            player_state,
            before_tiles,
            before_rack,
            "tile move",
        )
        return {
            "type": "tile_moved",
            "from": _point_payload(from_point),
            "to": _point_payload(to_point),
            "tile": _tile_payload(tile),
            "partial_validation": (
                player_state.board.get_formed_word_details_around_points(
                    [from_point, to_point]
                )
            ),
            **self._action_capabilities(player_state),
        }

    def move_tiles(
        self,
        player_id: UUID | str,
        from_points: list[Point],
        offset: Point,
        *,
        overwrite: bool = False,
    ) -> dict:
        self._ensure_active()
        player_state = self._get_player_state(player_id)
        before_tiles, before_rack = self._capture_board_edit(player_state.board)
        moves, displaced = player_state.board.move_tiles(
            from_points,
            offset,
            overwrite=overwrite,
        )
        self._remember_board_edit(
            player_state,
            before_tiles,
            before_rack,
            "block move",
        )
        affected_points = [
            point
            for source, destination, _ in moves
            for point in (source, destination)
        ]
        return {
            "type": "tiles_moved",
            "moves": [
                {
                    "from": _point_payload(source),
                    "to": _point_payload(destination),
                    "tile": _tile_payload(tile),
                }
                for source, destination, tile in moves
            ],
            "displaced": [
                {
                    "point": _point_payload(point),
                    "tile": _tile_payload(tile),
                }
                for point, tile in displaced.items()
            ],
            "rack_delta": _counter_delta(
                before_rack,
                player_state.board.unplaced_letters,
            ),
            "partial_validation": (
                player_state.board.get_formed_word_details_around_points(
                    affected_points
                )
            ),
            **self._action_capabilities(player_state),
        }

    def remove_tiles(
        self,
        player_id: UUID | str,
        points: list[Point],
    ) -> dict:
        self._ensure_active()
        player_state = self._get_player_state(player_id)
        before_tiles, before_rack = self._capture_board_edit(player_state.board)
        removed = player_state.board.remove_letters(points)
        self._remember_board_edit(
            player_state,
            before_tiles,
            before_rack,
            "block removal",
        )
        return {
            "type": "tiles_removed",
            "removed": [
                {
                    "point": _point_payload(point),
                    "tile": _tile_payload(tile),
                }
                for point, tile in removed.items()
            ],
            "rack_delta": _counter_delta(
                before_rack,
                player_state.board.unplaced_letters,
            ),
            "partial_validation": (
                player_state.board.get_formed_word_details_around_points(
                    removed
                )
            ),
            **self._action_capabilities(player_state),
        }

    def remove_tile(self, player_id: UUID | str, x: int, y: int) -> dict:
        self._ensure_active()
        player_state = self._get_player_state(player_id)
        before_tiles, before_rack = self._capture_board_edit(player_state.board)
        point = Point(x, y)
        tile = player_state.board.placed_tiles.get(point)
        if not player_state.board.remove_letter(x, y):
            raise ValueError(f"No tile placed at ({x}, {y}).")
        self._remember_board_edit(
            player_state,
            before_tiles,
            before_rack,
            "tile removal",
        )
        return {
            "type": "tile_removed",
            "point": _point_payload(point),
            "tile": _tile_payload(tile),
            "rack_delta": _counter_delta(
                before_rack,
                player_state.board.unplaced_letters,
            ),
            "partial_validation": (
                player_state.board.get_formed_word_details_around_points([point])
            ),
            **self._action_capabilities(player_state),
        }

    def undo(self, player_id: UUID | str) -> dict:
        """Atomically apply the inverse patch for the latest board edit."""
        self._ensure_active()
        player_state = self._get_player_state(player_id)
        history = self.undo_history.setdefault(player_state.player.id, [])
        if not history:
            raise ValueError("There are no board edits to undo.")

        before_rack = player_state.board.unplaced_letters.copy()
        entry = history[-1]
        self._apply_inverse_patch(player_state.board, entry)
        history.pop()
        board_state = player_state.board.to_state()
        description = str(entry.get("description") or "board edit")
        return {
            "type": "board_undone",
            "validated_board": board_state,
            "rack_delta": _counter_delta(
                before_rack,
                player_state.board.unplaced_letters,
            ),
            "validation_stale": False,
            "is_valid": board_state["is_valid"],
            "message": f"Undid {description}.",
            **self._action_capabilities(player_state),
        }

    def player_can_peel(self, player_id: UUID | str) -> bool:
        player_state = self._get_player_state(player_id)
        return player_state.can_peel_board

    def player_can_dump(self, player_id: UUID | str) -> bool:
        player_state = self._get_player_state(player_id)
        return player_state.can_dump_rack and self.bag_count > 0

    def peel(self, player_id: UUID | str) -> dict:
        self._ensure_active()
        player_state = self._get_player_state(player_id)
        if not player_state.can_peel_board:
            raise ValueError("Player cannot peel.")

        player_count = len(self.player_state)
        if self.bag_count < player_count:
            self.winner_id = player_state.player.id
            self._clear_all_undo_history()
            return {
                "type": "game_over",
                "drawn_by_player": {},
                "bag_count": self.bag_count,
                "winner_id": str(self.winner_id),
                "winner_name": self.winner_name,
            }

        drawn_by_player = {}
        for other_player_state in self.player_state.values():
            drawn = draw_tiles(self.bag, 1, self.rng)
            other_player_state.board.unplaced_letters.update(drawn)
            drawn_by_player[str(other_player_state.player.id)] = _counter_payload(drawn)

        return {
            "type": "peeled",
            "drawn_by_player": drawn_by_player,
            "bag_count": self.bag_count,
        }

    def dump(self, player_id: UUID | str, char: str) -> dict:
        self._ensure_active()
        if self.bag_count == 0:
            raise ValueError("No tiles remain in the bag.")

        player_state = self._get_player_state(player_id)
        char = normalize_char(char)
        if player_state.board.unplaced_letters[char] <= 0:
            raise ValueError(f"No {char} tile is available to dump.")

        before_rack = player_state.board.unplaced_letters.copy()
        player_state.board.unplaced_letters[char] -= 1
        if player_state.board.unplaced_letters[char] <= 0:
            del player_state.board.unplaced_letters[char]

        self.bag[char] += 1
        draw_count = min(DEFAULT_DUMP_DRAW_COUNT, self.bag_count)
        drawn = draw_tiles(self.bag, draw_count, self.rng)
        player_state.board.unplaced_letters.update(drawn)
        self.undo_history[player_state.player.id] = []
        return {
            "type": "rack_changed",
            "dumped": char,
            "drawn": _counter_payload(drawn),
            "rack_delta": _counter_delta(
                before_rack,
                player_state.board.unplaced_letters,
            ),
            "bag_count": self.bag_count,
            **self._action_capabilities(player_state),
        }

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
            "can_peel": self._can_player_attempt_peel(player_state, validate=True),
            "can_dump": (
                not self.is_game_over
                and player_state.can_dump_rack
                and self.bag_count > 0
            ),
            "can_undo": (
                not self.is_game_over
                and bool(self.undo_history.get(player_state.player.id))
            ),
            "is_game_over": self.is_game_over,
            "winner_id": str(self.winner_id) if self.winner_id else None,
            "winner_name": self.winner_name,
            "bag_multiplier": self.bag_multiplier,
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
            "winner_name": self.winner_name,
            "mode": self.mode,
            "bag_multiplier": self.bag_multiplier,
            "players": self._public_players(),
        }

    def public_player_state(
        self,
        player_id: UUID | str,
        *,
        validate: bool = True,
    ) -> dict:
        return self._get_player_state(player_id).to_public_state(validate=validate)

    def player_action_capabilities(self, player_id: UUID | str) -> dict:
        return self._action_capabilities(self._get_player_state(player_id))

    def to_record(self) -> dict:
        return {
            "version": 4,
            "game_id": str(self.game_id),
            "mode": self.mode,
            "bag": dict(self.bag),
            "bag_multiplier": self.bag_multiplier,
            "custom_rack": (
                dict(self.custom_rack)
                if self.custom_rack is not None
                else None
            ),
            "winner_id": str(self.winner_id) if self.winner_id else None,
            "players": [
                {
                    "player_id": str(player_state.player.id),
                    "player_name": player_state.player.player_name,
                    "rack": dict(player_state.board.unplaced_letters),
                    "placed_tiles": [
                        {
                            "x": point.x,
                            "y": point.y,
                            "char": tile.char,
                            "is_wildcard": tile.is_wildcard,
                        }
                        for point, tile in sorted(
                            player_state.board.placed_tiles.items(),
                            key=lambda item: (item[0].y, item[0].x),
                        )
                    ],
                    "undo_history": deepcopy(
                        self.undo_history.get(player_state.player.id, [])
                    ),
                }
                for player_state in sorted(
                    self.player_state.values(),
                    key=lambda state: str(state.player.id),
                )
            ],
        }

    @classmethod
    def from_record(
        cls,
        record: dict,
        *,
        board_factory: BoardFactory = Board,
        rng: random.Random | None = None,
    ) -> "GameSession":
        rng = rng or random.Random()
        record_version = int(record.get("version", 1))
        mode = str(record["mode"])
        bag = Counter(record.get("bag") or {})
        legacy_bag_multiplier = (
            NONE_BAG_MULTIPLIER
            if mode == "custom" and not bag
            else DEFAULT_BAG_MULTIPLIER
        )
        player_state: dict[UUID, PlayerState] = {}
        session = cls(
            game_id=UUID(str(record["game_id"])),
            bag=bag,
            rng=rng,
            player_state=player_state,
            mode=mode,
            board_factory=board_factory,
            custom_rack=(
                Counter(record["custom_rack"])
                if record.get("custom_rack") is not None
                else None
            ),
            bag_multiplier=normalize_bag_multiplier(
                record.get("bag_multiplier", legacy_bag_multiplier)
            ),
            winner_id=(
                UUID(str(record["winner_id"]))
                if record.get("winner_id")
                else None
            ),
        )

        for player_record in record.get("players", []):
            board = board_factory(Counter(player_record.get("rack") or {}))
            for tile_record in player_record.get("placed_tiles", []):
                point = Point(int(tile_record["x"]), int(tile_record["y"]))
                board.placed_tiles[point] = Tile(
                    str(tile_record["char"]),
                    bool(tile_record.get("is_wildcard", False)),
                )
            player = Player(
                session._resolved_player_name(player_record.get("player_name")),
                UUID(str(player_record["player_id"])),
            )
            restored_player_state = PlayerState(player, board, mode)
            session.player_state[player.id] = restored_player_state
            raw_history = player_record.get("undo_history")
            session.undo_history[player.id] = (
                deepcopy(raw_history[-MAX_UNDO_HISTORY:])
                if record_version >= 4 and isinstance(raw_history, list)
                else []
            )

        return session

    def _public_players(self) -> list[dict]:
        return [
            player_state.to_public_state()
            for player_state in sorted(
                self.player_state.values(),
                key=lambda state: (
                    (state.player.player_name or "").casefold(),
                    str(state.player.id),
                ),
            )
        ]

    def _resolved_player_name(self, player_name: object) -> str:
        normalized_name = self._normalize_player_name(player_name)
        if normalized_name is not None:
            return normalized_name

        used_names = {
            player_state.player.player_name.casefold()
            for player_state in self.player_state.values()
            if player_state.player.player_name
        }
        suffix = 1
        while f"player {suffix}" in used_names:
            suffix += 1
        return f"Player {suffix}"

    @staticmethod
    def _normalize_player_name(player_name: object) -> str | None:
        if player_name is None:
            return None
        if not isinstance(player_name, str):
            raise ValueError("Nickname must be text.")

        normalized_name = " ".join(player_name.split())
        if not normalized_name:
            return None
        if len(normalized_name) > MAX_PLAYER_NAME_LENGTH:
            raise ValueError(
                f"Nickname must be {MAX_PLAYER_NAME_LENGTH} characters or fewer."
            )
        return normalized_name

    def _action_capabilities(self, player_state: PlayerState) -> dict:
        return {
            "can_peel": self._can_player_attempt_peel(player_state, validate=False),
            "can_dump": (
                not self.is_game_over
                and player_state.can_dump_rack
                and self.bag_count > 0
            ),
            "can_undo": (
                not self.is_game_over
                and bool(self.undo_history.get(player_state.player.id))
            ),
        }

    @staticmethod
    def _capture_board_edit(
        board: Board,
    ) -> tuple[dict[Point, Tile], Counter[str]]:
        return board.placed_tiles.copy(), board.unplaced_letters.copy()

    def _remember_board_edit(
        self,
        player_state: PlayerState,
        before_tiles: dict[Point, Tile],
        before_rack: Counter[str],
        description: str,
    ) -> None:
        board = player_state.board
        changed_points = sorted(
            (
                point
                for point in set(before_tiles) | set(board.placed_tiles)
                if before_tiles.get(point) != board.placed_tiles.get(point)
            ),
            key=lambda point: (point.y, point.x),
        )
        cell_changes = [
            {
                "point": _point_payload(point),
                "before": (
                    _tile_payload(before_tiles[point])
                    if point in before_tiles
                    else None
                ),
                "after": (
                    _tile_payload(board.placed_tiles[point])
                    if point in board.placed_tiles
                    else None
                ),
            }
            for point in changed_points
        ]
        rack_delta = _counter_delta(before_rack, board.unplaced_letters)
        if not cell_changes and not rack_delta:
            return

        history = self.undo_history.setdefault(player_state.player.id, [])
        history.append({
            "description": description,
            "cells": cell_changes,
            "rack_delta": rack_delta,
        })
        del history[:-MAX_UNDO_HISTORY]

    @classmethod
    def _apply_inverse_patch(cls, board: Board, entry: dict) -> None:
        try:
            changes = []
            seen_points = set()
            for cell_change in entry.get("cells", []):
                point_payload = cell_change["point"]
                point = Point(
                    int(point_payload["x"]),
                    int(point_payload["y"]),
                )
                if point in seen_points:
                    raise ValueError
                seen_points.add(point)
                before_tile = cls._tile_from_patch(cell_change.get("before"))
                after_tile = cls._tile_from_patch(cell_change.get("after"))
                changes.append((point, before_tile, after_tile))

            rack_delta = {
                str(char): int(count)
                for char, count in (entry.get("rack_delta") or {}).items()
                if int(count)
            }
        except (AttributeError, KeyError, TypeError, ValueError):
            raise ValueError("Undo history is invalid.") from None

        if not changes and not rack_delta:
            raise ValueError("Undo history is invalid.")

        for point, _, expected_tile in changes:
            if board.placed_tiles.get(point) != expected_tile:
                raise ValueError(
                    "The board changed since that edit and cannot be undone."
                )

        restored_rack = board.unplaced_letters.copy()
        for char, forward_delta in rack_delta.items():
            restored_rack[char] -= forward_delta
            if restored_rack[char] < 0:
                raise ValueError(
                    "The rack changed since that edit and cannot be undone."
                )
            if restored_rack[char] == 0:
                del restored_rack[char]

        for point, _, _ in changes:
            board.placed_tiles.pop(point, None)
        for point, restored_tile, _ in changes:
            if restored_tile is not None:
                board.placed_tiles[point] = restored_tile
        board.unplaced_letters = restored_rack

    @staticmethod
    def _tile_from_patch(payload: dict | None) -> Tile | None:
        if payload is None:
            return None
        return Tile(
            str(payload["char"]),
            bool(payload.get("is_wildcard", False)),
        )

    def _clear_all_undo_history(self) -> None:
        for player_id in self.player_state:
            self.undo_history[player_id] = []

    def _can_player_attempt_peel(
        self,
        player_state: PlayerState,
        *,
        validate: bool,
    ) -> bool:
        if self.is_game_over:
            return False

        board_ready = (
            player_state.can_peel_board
            if validate
            else player_state.rack_count == 0
        )
        if not board_ready:
            return False

        return True

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
        if self.winner_name is None:
            return "Game complete."
        return f"{self.winner_name} wins! All tiles are placed in valid words."
