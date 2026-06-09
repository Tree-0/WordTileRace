from __future__ import annotations

from collections.abc import Callable
import random
from typing import Any

from flask import Flask, jsonify, render_template, request

from board import Board, Point
from game import Game


BoardFactory = Callable[[Any], Board]


def create_app(
    board_factory: BoardFactory = Board,
    rng: random.Random | None = None,
    initial_game: Game | None = None,
) -> Flask:
    app = Flask(__name__)
    rng = rng or random.Random()
    game = {"session": initial_game or Game.new_random(board_factory, rng)}

    def current_game() -> Game:
        return game["session"]

    def current_board() -> Board:
        return current_game().board

    def state_response(
        *,
        success: bool = True,
        message: str | None = None,
        status_code: int = 200,
    ):
        state = current_game().to_state()
        state["success"] = success
        if message:
            state["message"] = message
        return jsonify(state), status_code

    def request_json() -> dict:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object.")
        return payload

    def parse_point(payload: dict, name: str | None = None) -> Point:
        source = payload if name is None else payload.get(name)
        if not isinstance(source, dict):
            raise ValueError("Expected point coordinates.")

        try:
            return Point(int(source["x"]), int(source["y"]))
        except (KeyError, TypeError, ValueError):
            raise ValueError("Expected integer x and y coordinates.") from None

    def ensure_game_active() -> None:
        if current_game().is_game_over:
            raise ValueError("Game is complete. Start a new game to keep playing.")

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/state")
    def api_state():
        return state_response()

    @app.post("/api/new")
    def api_new():
        try:
            payload = request_json()
            mode = payload.get("mode")

            if mode == "custom":
                game["session"] = Game.new_custom(
                    str(payload.get("letters", "")),
                    board_factory,
                    rng,
                )
                return state_response(message="Started a custom game.")

            if mode == "random":
                game["session"] = Game.new_random(board_factory, rng)
                return state_response(message="Started a random 21-tile game.")

            raise ValueError("Mode must be custom or random.")
        except ValueError as error:
            return state_response(
                success=False,
                message=str(error),
                status_code=400,
            )

    @app.post("/api/place")
    def api_place():
        try:
            payload = request_json()
            point = parse_point(payload)
            char = str(payload.get("char", ""))
            overwrite = bool(payload.get("overwrite", False))
            ensure_game_active()

            if overwrite:
                current_board().place_or_overwrite_tile(char, point.x, point.y)
            else:
                current_board().place_tile(char, point.x, point.y)

            return state_response(message=f"Placed {char.upper()} at ({point.x}, {point.y}).")
        except ValueError as error:
            return state_response(
                success=False,
                message=str(error),
                status_code=400,
            )

    @app.post("/api/peel")
    def api_peel():
        try:
            ensure_game_active()
            drawn = current_game().peel()
            drawn_text = ", ".join(
                char
                for char, count in sorted(drawn.items())
                for _ in range(count)
            )
            return state_response(message=f"Peeled {drawn_text}.")
        except ValueError as error:
            return state_response(
                success=False,
                message=str(error),
                status_code=400,
            )

    @app.post("/api/dump")
    def api_dump():
        try:
            payload = request_json()
            char = str(payload.get("char", ""))
            ensure_game_active()
            drawn = current_game().dump(char)
            drawn_text = ", ".join(
                drawn_char
                for drawn_char, count in sorted(drawn.items())
                for _ in range(count)
            )
            return state_response(message=f"Dumped {char.upper()} and drew {drawn_text}.")
        except ValueError as error:
            return state_response(
                success=False,
                message=str(error),
                status_code=400,
            )

    @app.post("/api/remove")
    def api_remove():
        try:
            payload = request_json()
            point = parse_point(payload)
            ensure_game_active()
            if not current_board().remove_letter(point.x, point.y):
                raise ValueError(f"No tile placed at ({point.x}, {point.y}).")
            return state_response(message=f"Removed tile at ({point.x}, {point.y}).")
        except ValueError as error:
            return state_response(
                success=False,
                message=str(error),
                status_code=400,
            )

    @app.post("/api/move")
    def api_move():
        try:
            payload = request_json()
            from_point = parse_point(payload, "from")
            to_point = parse_point(payload, "to")
            ensure_game_active()
            current_board().move_tile(from_point, to_point)
            return state_response(
                message=(
                    f"Moved tile from ({from_point.x}, {from_point.y}) "
                    f"to ({to_point.x}, {to_point.y})."
                )
            )
        except ValueError as error:
            return state_response(
                success=False,
                message=str(error),
                status_code=400,
            )

    return app
