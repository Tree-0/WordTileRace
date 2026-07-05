from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import random
from typing import Any

from flask import Flask, jsonify, render_template

from backend.board import Board
from backend.socket_handlers import init_socketio
from backend.word_definitions import DefinitionLookupError, lookup_definitions


BoardFactory = Callable[[Any], Board]
DefinitionLookup = Callable[[str], dict[str, Any]]
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "frontend"


def create_app(
    board_factory: BoardFactory = Board,
    rng: random.Random | None = None,
    definition_lookup: DefinitionLookup | None = None,
) -> Flask:
    app = Flask(
        __name__,
        static_folder=str(FRONTEND_DIR / "static"),
        template_folder=str(FRONTEND_DIR / "templates"),
    )
    rng = rng or random.Random()
    definition_lookup_func = definition_lookup or lookup_definitions
    init_socketio(app, board_factory=board_factory, rng=rng)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/health")
    def api_health():
        return jsonify({"success": True})

    @app.get("/api/definitions/<word>")
    def api_definitions(word: str):
        try:
            result = definition_lookup_func(word)
            return jsonify({"success": True, **result})
        except ValueError as error:
            return jsonify({
                "success": False,
                "word": word.strip().upper(),
                "message": str(error),
            }), 400
        except DefinitionLookupError as error:
            return jsonify({
                "success": False,
                "word": word.strip().upper(),
                "message": str(error),
            }), 502

    return app
