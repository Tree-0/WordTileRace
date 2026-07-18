from __future__ import annotations

from collections.abc import Callable
import random
from typing import Any
from uuid import UUID

from backend.board import Board, Point
from backend.config import AppConfig
from backend.game_session import GameSession
from backend.game_store import GameStore, MemoryGameStore

try:
    from flask import request
    from flask_socketio import SocketIO, emit, join_room, leave_room
except ModuleNotFoundError:  # pragma: no cover - exercised when dependency is absent.
    request = None
    SocketIO = None
    emit = None
    join_room = None
    leave_room = None


BoardFactory = Callable[[Any], Board]

socketio = SocketIO() if SocketIO is not None else None
connections: dict[str, tuple[str, UUID]] = {}
active_game_store: GameStore | None = None


def init_socketio(
    app,
    *,
    board_factory: BoardFactory = Board,
    rng: random.Random | None = None,
    game_store: GameStore | None = None,
    config: AppConfig | None = None,
):
    if socketio is None:
        return None

    rng = rng or random.Random()
    config = config or AppConfig.from_env()
    game_store = game_store or MemoryGameStore(
        board_factory=board_factory,
        rng=rng,
    )

    global active_game_store
    active_game_store = game_store

    socketio.init_app(
        app,
        cors_allowed_origins=config.allowed_origins,
        message_queue=config.redis_url,
    )
    register_socket_handlers(
        board_factory=board_factory,
        rng=rng,
        game_store=game_store,
    )
    return socketio


def register_socket_handlers(
    *,
    board_factory: BoardFactory = Board,
    rng: random.Random | None = None,
    game_store: GameStore | None = None,
) -> None:
    rng = rng or random.Random()
    store = game_store or active_game_store
    if store is None:
        store = MemoryGameStore(board_factory=board_factory, rng=rng)

    @socketio.on("create_game")
    def create_game(payload=None):
        try:
            payload = _payload(payload)
            _leave_existing_rooms()
            mode = payload.get("mode", "random")
            letters = payload.get("letters")
            player_name = payload.get("player_name")
            if mode == "custom":
                session = GameSession.new_game(
                    str(letters or ""),
                    rng=rng,
                    board_factory=board_factory,
                )
            elif mode == "random":
                session = GameSession.new_game(
                    rng=rng,
                    board_factory=board_factory,
                )
            else:
                raise ValueError("Mode must be custom or random.")

            player_state = session.add_player(player_name)
            game_id = str(session.game_id)
            with store.lock(game_id):
                store.save(session)

            _bind_connection(game_id, player_state.player.id)
            _emit_joined(session, player_state.player.id)
            _broadcast_session(session, message="Started a new game.")
            return _ack(session, player_state.player.id)
        except ValueError as error:
            _emit_error(str(error))
            return {"success": False, "message": str(error)}

    @socketio.on("join_game")
    def join_game(payload=None):
        try:
            payload = _payload(payload)
            _leave_existing_rooms()
            game_id = str(payload.get("game_id", "")).strip()
            if not game_id:
                raise ValueError("Game id is required.")

            player_id = payload.get("player_id")
            player_state = None
            with store.lock(game_id):
                session = _session(store, game_id)
                if player_id:
                    try:
                        player_state = session.get_player_state(player_id)
                    except ValueError:
                        player_state = None

                if player_state is None:
                    player_state = session.add_player(payload.get("player_name"))

                store.save(session)

            _bind_connection(game_id, player_state.player.id)
            _emit_joined(session, player_state.player.id)
            _broadcast_session(session, message="Joined the game.")
            return _ack(session, player_state.player.id)
        except ValueError as error:
            _emit_error(str(error))
            return {"success": False, "message": str(error)}

    @socketio.on("request_state")
    def request_state(payload=None):
        try:
            session, player_id = _current_session(store)
            _emit_private(session, player_id)
            return {"success": True}
        except ValueError as error:
            _emit_error(str(error))
            return {"success": False, "message": str(error)}

    @socketio.on("validate_board")
    def validate_board(payload=None):
        try:
            session, player_id = _current_session(store)
            _emit_private(session, player_id)
            return {"success": True}
        except ValueError as error:
            _emit_error(str(error))
            return {"success": False, "message": str(error)}

    @socketio.on("place_tile")
    def place_tile(payload=None):
        try:
            payload = _payload(payload)
            point = _parse_point(payload)
            char = str(payload.get("char", ""))
            overwrite = bool(payload.get("overwrite", False))

            def mutate(session, player_id):
                return session.place_tile(player_id, char, point.x, point.y, overwrite)

            session, player_id, diff = _mutate_current_session(store, mutate)
            _emit_state_diff(session, player_id, diff)
            _emit_public_player_diff(session, player_id)
            return {"success": True}
        except ValueError as error:
            _emit_action_failure(store, str(error))
            return {"success": False, "message": str(error)}

    @socketio.on("move_tile")
    def move_tile(payload=None):
        try:
            payload = _payload(payload)
            from_point = _parse_point(payload, "from")
            to_point = _parse_point(payload, "to")

            def mutate(session, player_id):
                return session.move_tile(player_id, from_point, to_point)

            session, player_id, diff = _mutate_current_session(store, mutate)
            _emit_state_diff(session, player_id, diff)
            return {"success": True}
        except ValueError as error:
            _emit_action_failure(store, str(error))
            return {"success": False, "message": str(error)}

    @socketio.on("remove_tile")
    def remove_tile(payload=None):
        try:
            payload = _payload(payload)
            point = _parse_point(payload)

            def mutate(session, player_id):
                return session.remove_tile(player_id, point.x, point.y)

            session, player_id, diff = _mutate_current_session(store, mutate)
            _emit_state_diff(session, player_id, diff)
            _emit_public_player_diff(session, player_id)
            return {"success": True}
        except ValueError as error:
            _emit_action_failure(store, str(error))
            return {"success": False, "message": str(error)}

    @socketio.on("peel")
    def peel(payload=None):
        try:
            def mutate(session, player_id):
                return session.peel(player_id)

            session, player_id, diff = _mutate_current_session(store, mutate)
            _emit_peel_diffs(session, player_id, diff)
            return {"success": True}
        except ValueError as error:
            _emit_action_failure(store, str(error), refresh=True)
            return {"success": False, "message": str(error)}

    @socketio.on("dump")
    def dump(payload=None):
        try:
            payload = _payload(payload)
            char = str(payload.get("char", ""))

            def mutate(session, player_id):
                return session.dump(player_id, char)

            session, player_id, diff = _mutate_current_session(store, mutate)
            _emit_state_diff(session, player_id, diff)
            _emit_public_player_diff(session, player_id)
            return {"success": True}
        except ValueError as error:
            _emit_action_failure(store, str(error))
            return {"success": False, "message": str(error)}

    @socketio.on("disconnect")
    def disconnect(reason=None):
        _leave_existing_rooms()


def _payload(payload) -> dict:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object.")
    return payload


def _bind_connection(game_id: str, player_id: UUID) -> None:
    connections[request.sid] = (game_id, player_id)
    join_room(_game_room(game_id))
    join_room(_player_room(game_id, player_id))


def _leave_existing_rooms() -> None:
    existing = connections.pop(request.sid, None)
    if existing is None:
        return

    game_id, player_id = existing
    leave_room(_game_room(game_id))
    leave_room(_player_room(game_id, player_id))


def _current_session(store: GameStore) -> tuple[GameSession, UUID]:
    game_id, player_id = _current_connection()
    return _session(store, game_id), player_id


def _current_connection() -> tuple[str, UUID]:
    try:
        return connections[request.sid]
    except KeyError:
        raise ValueError("Join or create a game before sending actions.") from None


def _session(store: GameStore, game_id: str) -> GameSession:
    session = store.get(game_id)
    if session is None:
        raise ValueError("Game not found.")
    return session


def _mutate_current_session(store: GameStore, mutator) -> tuple[GameSession, UUID, dict]:
    game_id, player_id = _current_connection()
    with store.lock(game_id):
        session = _session(store, game_id)
        diff = mutator(session, player_id)
        store.save(session)
    return session, player_id, diff


def _parse_point(payload: dict, name: str | None = None) -> Point:
    source = payload if name is None else payload.get(name)
    if not isinstance(source, dict):
        raise ValueError("Expected point coordinates.")

    try:
        return Point(int(source["x"]), int(source["y"]))
    except (KeyError, TypeError, ValueError):
        raise ValueError("Expected integer x and y coordinates.") from None


def _emit_joined(session: GameSession, player_id: UUID) -> None:
    emit("joined_game", _ack(session, player_id), to=request.sid)


def _ack(session: GameSession, player_id: UUID) -> dict:
    return {
        "success": True,
        "game_id": str(session.game_id),
        "player_id": str(player_id),
        "invite_url": _invite_url(session),
    }


def _emit_private(
    session: GameSession,
    player_id: UUID,
    *,
    success: bool = True,
    message: str | None = None,
    to: str | None = None,
) -> None:
    emit(
        "state",
        session.private_state(player_id, success=success, message=message),
        to=to or request.sid,
    )


def _broadcast_session(session: GameSession, *, message: str | None = None) -> None:
    for player_state in session.player_state.values():
        socketio.emit(
            "state",
            session.private_state(player_state.player.id, message=message),
            to=_player_room(str(session.game_id), player_state.player.id),
        )
    socketio.emit("public_state", session.public_state(), to=_game_room(str(session.game_id)))


def _emit_state_diff(session: GameSession, player_id: UUID, diff: dict) -> None:
    payload = {"success": True, **diff}
    if diff["type"] in {"tile_placed", "tile_moved", "tile_removed"}:
        payload.update({
            "validation_stale": True,
            "message": "Board changed. Peel will validate before drawing.",
        })
    elif diff["type"] == "rack_changed":
        payload["message"] = (
            f"Dumped {diff['dumped'].upper()} and drew "
            f"{_drawn_text(diff['drawn'])}."
        )

    socketio.emit(
        "state_diff",
        payload,
        to=_player_room(str(session.game_id), player_id),
    )


def _emit_peel_diffs(session: GameSession, peeling_player_id: UUID, diff: dict) -> None:
    if diff["type"] == "game_over":
        for player_state in session.player_state.values():
            payload = {
                "success": True,
                "type": "game_over",
                "bag_count": diff["bag_count"],
                "is_game_over": True,
                "winner_id": diff["winner_id"],
                "winner_name": diff["winner_name"],
                "message": "Game complete.",
            }
            if player_state.player.id == peeling_player_id:
                payload["validated_board"] = player_state.board.to_state()
            socketio.emit(
                "state_diff",
                payload,
                to=_player_room(str(session.game_id), player_state.player.id),
            )
        socketio.emit(
            "public_state_diff",
            {
                "type": "game_over",
                "bag_count": session.bag_count,
                "is_game_over": True,
                "winner_id": diff["winner_id"],
                "winner_name": diff["winner_name"],
            },
            to=_game_room(str(session.game_id)),
        )
        return

    for player_state in session.player_state.values():
        player_id = player_state.player.id
        rack_delta = diff["drawn_by_player"].get(str(player_id), {})
        payload = {
            "success": True,
            "type": "peeled",
            "rack_delta": rack_delta,
            "bag_count": diff["bag_count"],
            "message": f"Peeled {_drawn_text(rack_delta)}.",
            **session.player_action_capabilities(player_id),
        }
        if player_id == peeling_player_id:
            payload.update({
                "validation_stale": False,
                "is_valid": True,
                "validated_board": player_state.board.to_state(),
            })
        socketio.emit(
            "state_diff",
            payload,
            to=_player_room(str(session.game_id), player_id),
        )

    _emit_public_session_diff(session)


def _emit_public_player_diff(session: GameSession, player_id: UUID) -> None:
    socketio.emit(
        "public_state_diff",
        {
            "type": "player_changed",
            "bag_count": session.bag_count,
            "player": session.public_player_state(player_id, validate=False),
        },
        to=_game_room(str(session.game_id)),
    )


def _emit_public_session_diff(session: GameSession) -> None:
    socketio.emit(
        "public_state_diff",
        {
            "type": "session_changed",
            "bag_count": session.bag_count,
            "players": [
                session.public_player_state(player_state.player.id, validate=False)
                for player_state in session.player_state.values()
            ],
        },
        to=_game_room(str(session.game_id)),
    )


def _emit_action_failure(
    store: GameStore,
    message: str,
    *,
    refresh: bool = False,
) -> None:
    if not refresh:
        _emit_error(message)
        return

    try:
        session, player_id = _current_session(store)
    except ValueError:
        _emit_error(message)
        return
    _emit_private(session, player_id, success=False, message=message)


def _emit_error(message: str) -> None:
    emit("action_error", {"success": False, "message": message}, to=request.sid)


def _game_room(game_id: str) -> str:
    return f"game:{game_id}"


def _player_room(game_id: str, player_id: UUID | str) -> str:
    return f"game:{game_id}:player:{player_id}"


def _invite_url(session: GameSession) -> str:
    return f"{request.url_root.rstrip('/')}/?game={session.game_id}"


def _drawn_text(drawn: dict[str, int]) -> str:
    tiles = [
        char
        for char, count in sorted(drawn.items())
        for _ in range(count)
    ]
    return ", ".join(tiles) if tiles else "no tiles"
