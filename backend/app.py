from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import random
from typing import Any

from flask import Flask, jsonify, render_template

from backend.board import Board
from backend.config import AppConfig
from backend.game_store import GameStore, create_game_store
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
    game_store: GameStore | None = None,
    config: AppConfig | None = None,
) -> Flask:
    config = config or AppConfig.from_env()
    app = Flask(
        __name__,
        static_folder=str(FRONTEND_DIR / "static"),
        template_folder=str(FRONTEND_DIR / "templates"),
    )
    app.config["SECRET_KEY"] = config.secret_key
    app.config["APP_CONFIG"] = config
    rng = rng or random.Random()
    definition_lookup_func = definition_lookup or lookup_definitions
    game_store = game_store or create_game_store(
        redis_url=config.redis_url,
        board_factory=board_factory,
        rng=rng,
        ttl_seconds=config.game_ttl_seconds,
    )
    init_socketio(
        app,
        board_factory=board_factory,
        rng=rng,
        game_store=game_store,
        config=config,
    )

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/health")
    def api_health():
        return jsonify({
            "success": True,
            "storage": "redis" if config.redis_url else "memory",
        })

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
