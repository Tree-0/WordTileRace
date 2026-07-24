from __future__ import annotations

from collections.abc import Callable
import random
import time
from typing import Any
from uuid import UUID

from backend.board import Board, Point
from backend.config import AppConfig
from backend.game_session import GameSession, normalize_custom_game_id
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
        debug = _debug_context("create_game", payload)
        try:
            payload = _payload(payload)
            _leave_existing_rooms()
            mode = payload.get("mode", "random")
            letters = payload.get("letters")
            bag_multiplier = payload.get("bag_multiplier", 1)
            player_name = payload.get("player_name")
            custom_game_id = normalize_custom_game_id(payload.get("game_id"))
            if mode == "custom":
                session = GameSession.new_game(
                    str(letters or ""),
                    rng=rng,
                    board_factory=board_factory,
                    bag_multiplier=bag_multiplier,
                    custom_game_id=custom_game_id,
                )
            elif mode == "random":
                session = GameSession.new_game(
                    rng=rng,
                    board_factory=board_factory,
                    bag_multiplier=bag_multiplier,
                    custom_game_id=custom_game_id,
                )
            else:
                raise ValueError("Mode must be custom or random.")

            player_state = session.add_player(player_name)
            game_id = str(session.game_id)
            with store.lock(game_id):
                if store.get(game_id) is not None:
                    raise ValueError(
                        "That game ID is already in use. Choose another one."
                    )
                store.save(session)

            _bind_connection(game_id, player_state.player.id)
            _emit_joined(session, player_state.player.id, debug=debug)
            _broadcast_session(session, message="Started a new game.", debug=debug)
            return _with_debug_timing(_ack(session, player_state.player.id), debug)
        except ValueError as error:
            _emit_error(str(error), debug=debug)
            return _with_debug_timing(
                {"success": False, "message": str(error)},
                debug,
            )

    @socketio.on("join_game")
    def join_game(payload=None):
        debug = _debug_context("join_game", payload)
        try:
            payload = _payload(payload)
            _leave_existing_rooms()
            game_id = str(payload.get("game_id", "")).strip().lower()
            if not game_id:
                raise ValueError("Game id is required.")

            player_id = payload.get("player_id")
            requested_player_name = payload.get("player_name")
            player_state = None
            with store.lock(game_id):
                session = _session(store, game_id)
                if player_id:
                    try:
                        player_state = session.get_player_state(player_id)
                    except ValueError:
                        player_state = None

                if player_state is None:
                    player_state = session.add_player(requested_player_name)
                elif (
                    requested_player_name is not None
                    and (
                        not isinstance(requested_player_name, str)
                        or requested_player_name.strip()
                    )
                ):
                    player_state = session.rename_player(
                        player_state.player.id,
                        requested_player_name,
                    )

                store.save(session)

            _bind_connection(game_id, player_state.player.id)
            _emit_joined(session, player_state.player.id, debug=debug)
            _broadcast_session(session, message="Joined the game.", debug=debug)
            return _with_debug_timing(_ack(session, player_state.player.id), debug)
        except ValueError as error:
            _emit_error(str(error), debug=debug)
            return _with_debug_timing(
                {"success": False, "message": str(error)},
                debug,
            )

    @socketio.on("request_state")
    def request_state(payload=None):
        debug = _debug_context("request_state", payload)
        try:
            session, player_id = _current_session(store)
            _emit_private(session, player_id, debug=debug)
            return _with_debug_timing({"success": True}, debug)
        except ValueError as error:
            _emit_error(str(error), debug=debug)
            return _with_debug_timing(
                {"success": False, "message": str(error)},
                debug,
            )

    @socketio.on("validate_board")
    def validate_board(payload=None):
        debug = _debug_context("validate_board", payload)
        try:
            session, player_id = _current_session(store)
            _emit_private(session, player_id, debug=debug)
            return _with_debug_timing({"success": True}, debug)
        except ValueError as error:
            _emit_error(str(error), debug=debug)
            return _with_debug_timing(
                {"success": False, "message": str(error)},
                debug,
            )

    @socketio.on("place_tile")
    def place_tile(payload=None):
        debug = _debug_context("place_tile", payload)
        try:
            payload = _payload(payload)
            point = _parse_point(payload)
            char = str(payload.get("char", ""))
            overwrite = bool(payload.get("overwrite", False))

            def mutate(session, player_id):
                return session.place_tile(player_id, char, point.x, point.y, overwrite)

            session, player_id, diff = _mutate_current_session(
                store,
                mutate,
                debug=debug,
            )
            _emit_state_diff(session, player_id, diff, debug=debug)
            _emit_public_player_diff(session, player_id)
            return _with_debug_timing({"success": True}, debug)
        except ValueError as error:
            _emit_action_failure(store, str(error), debug=debug)
            return _with_debug_timing(
                {"success": False, "message": str(error)},
                debug,
            )

    @socketio.on("move_tile")
    def move_tile(payload=None):
        debug = _debug_context("move_tile", payload)
        try:
            payload = _payload(payload)
            from_point = _parse_point(payload, "from")
            to_point = _parse_point(payload, "to")

            def mutate(session, player_id):
                return session.move_tile(player_id, from_point, to_point)

            session, player_id, diff = _mutate_current_session(
                store,
                mutate,
                debug=debug,
            )
            _emit_state_diff(session, player_id, diff, debug=debug)
            return _with_debug_timing({"success": True}, debug)
        except ValueError as error:
            _emit_action_failure(store, str(error), debug=debug)
            return _with_debug_timing(
                {"success": False, "message": str(error)},
                debug,
            )

    @socketio.on("move_tiles")
    def move_tiles(payload=None):
        debug = _debug_context("move_tiles", payload)
        try:
            payload = _payload(payload)
            points = _parse_points(payload)
            offset = _parse_point(payload, "offset")
            overwrite = bool(payload.get("overwrite", False))

            def mutate(session, player_id):
                return session.move_tiles(
                    player_id,
                    points,
                    offset,
                    overwrite=overwrite,
                )

            session, player_id, diff = _mutate_current_session(
                store,
                mutate,
                debug=debug,
            )
            _emit_state_diff(session, player_id, diff, debug=debug)
            if diff["rack_delta"]:
                _emit_public_player_diff(session, player_id)
            return _with_debug_timing({"success": True}, debug)
        except ValueError as error:
            _emit_action_failure(store, str(error), debug=debug)
            return _with_debug_timing(
                {"success": False, "message": str(error)},
                debug,
            )

    @socketio.on("remove_tile")
    def remove_tile(payload=None):
        debug = _debug_context("remove_tile", payload)
        try:
            payload = _payload(payload)
            point = _parse_point(payload)

            def mutate(session, player_id):
                return session.remove_tile(player_id, point.x, point.y)

            session, player_id, diff = _mutate_current_session(
                store,
                mutate,
                debug=debug,
            )
            _emit_state_diff(session, player_id, diff, debug=debug)
            _emit_public_player_diff(session, player_id)
            return _with_debug_timing({"success": True}, debug)
        except ValueError as error:
            _emit_action_failure(store, str(error), debug=debug)
            return _with_debug_timing(
                {"success": False, "message": str(error)},
                debug,
            )

    @socketio.on("remove_tiles")
    def remove_tiles(payload=None):
        debug = _debug_context("remove_tiles", payload)
        try:
            payload = _payload(payload)
            points = _parse_points(payload)

            def mutate(session, player_id):
                return session.remove_tiles(player_id, points)

            session, player_id, diff = _mutate_current_session(
                store,
                mutate,
                debug=debug,
            )
            _emit_state_diff(session, player_id, diff, debug=debug)
            _emit_public_player_diff(session, player_id)
            return _with_debug_timing({"success": True}, debug)
        except ValueError as error:
            _emit_action_failure(store, str(error), debug=debug)
            return _with_debug_timing(
                {"success": False, "message": str(error)},
                debug,
            )

    @socketio.on("undo")
    def undo(payload=None):
        debug = _debug_context("undo", payload)
        try:
            def mutate(session, player_id):
                return session.undo(player_id)

            session, player_id, diff = _mutate_current_session(
                store,
                mutate,
                debug=debug,
            )
            _emit_state_diff(session, player_id, diff, debug=debug)
            if diff["rack_delta"]:
                _emit_public_player_diff(session, player_id)
            return _with_debug_timing({"success": True}, debug)
        except ValueError as error:
            _emit_action_failure(store, str(error), debug=debug)
            return _with_debug_timing(
                {"success": False, "message": str(error)},
                debug,
            )

    @socketio.on("peel")
    def peel(payload=None):
        debug = _debug_context("peel", payload)
        try:
            def mutate(session, player_id):
                return session.peel(player_id)

            session, player_id, diff = _mutate_current_session(
                store,
                mutate,
                debug=debug,
            )
            _emit_peel_diffs(session, player_id, diff, debug=debug)
            return _with_debug_timing({"success": True}, debug)
        except ValueError as error:
            _emit_action_failure(store, str(error), refresh=True, debug=debug)
            return _with_debug_timing(
                {"success": False, "message": str(error)},
                debug,
            )

    @socketio.on("dump")
    def dump(payload=None):
        debug = _debug_context("dump", payload)
        try:
            payload = _payload(payload)
            char = str(payload.get("char", ""))

            def mutate(session, player_id):
                return session.dump(player_id, char)

            session, player_id, diff = _mutate_current_session(
                store,
                mutate,
                debug=debug,
            )
            _emit_state_diff(session, player_id, diff, debug=debug)
            _emit_public_player_diff(session, player_id)
            return _with_debug_timing({"success": True}, debug)
        except ValueError as error:
            _emit_action_failure(store, str(error), debug=debug)
            return _with_debug_timing(
                {"success": False, "message": str(error)},
                debug,
            )

    @socketio.on("disconnect")
    def disconnect(reason=None):
        _leave_existing_rooms()


def _payload(payload) -> dict:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object.")
    return payload


def _debug_context(event_name: str, payload) -> dict | None:
    if not isinstance(payload, dict):
        return None

    client_action_id = payload.get("_client_action_id")
    if not client_action_id:
        return None

    return {
        "action": event_name,
        "client_action_id": str(client_action_id),
        "client_sent_at_ms": payload.get("_client_sent_at_ms"),
        "server_received_at_ms": round(time.time() * 1000, 3),
        "server_started_at": time.perf_counter(),
        "server_steps_ms": {},
    }


def _with_debug_timing(payload: dict, debug: dict | None) -> dict:
    if debug is None:
        return payload

    return {
        **payload,
        "debug_timing": {
            "action": debug["action"],
            "client_action_id": debug["client_action_id"],
            "client_sent_at_ms": debug["client_sent_at_ms"],
            "server_received_at_ms": debug["server_received_at_ms"],
            "server_process_ms": round(
                (time.perf_counter() - debug["server_started_at"]) * 1000,
                3,
            ),
            "server_steps_ms": debug["server_steps_ms"],
        },
    }


def _debug_step(debug: dict | None, name: str, started_at: float) -> None:
    if debug is None:
        return

    debug["server_steps_ms"][name] = round(
        (time.perf_counter() - started_at) * 1000,
        3,
    )


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


def _mutate_current_session(
    store: GameStore,
    mutator,
    *,
    debug: dict | None = None,
) -> tuple[GameSession, UUID, dict]:
    game_id, player_id = _current_connection()
    lock_started_at = time.perf_counter()
    with store.lock(game_id):
        _debug_step(debug, "lock_wait_ms", lock_started_at)
        load_started_at = time.perf_counter()
        session = _session(store, game_id)
        _debug_step(debug, "load_session_ms", load_started_at)
        mutate_started_at = time.perf_counter()
        diff = mutator(session, player_id)
        _debug_step(debug, "mutate_ms", mutate_started_at)
        save_started_at = time.perf_counter()
        store.save(session)
        _debug_step(debug, "save_session_ms", save_started_at)
    return session, player_id, diff


def _parse_point(payload: dict, name: str | None = None) -> Point:
    source = payload if name is None else payload.get(name)
    if not isinstance(source, dict):
        raise ValueError("Expected point coordinates.")

    try:
        return Point(int(source["x"]), int(source["y"]))
    except (KeyError, TypeError, ValueError):
        raise ValueError("Expected integer x and y coordinates.") from None


def _parse_points(payload: dict, name: str = "points") -> list[Point]:
    sources = payload.get(name)
    if not isinstance(sources, list):
        raise ValueError("Expected a list of point coordinates.")
    return [_parse_point(source) for source in sources]


def _emit_joined(
    session: GameSession,
    player_id: UUID,
    *,
    debug: dict | None = None,
) -> None:
    emit(
        "joined_game",
        _with_debug_timing(_ack(session, player_id), debug),
        to=request.sid,
    )


def _ack(session: GameSession, player_id: UUID) -> dict:
    player_state = session.get_player_state(player_id)
    return {
        "success": True,
        "game_id": str(session.game_id),
        "player_id": str(player_id),
        "player_name": player_state.player.player_name,
        "invite_url": _invite_url(session),
    }


def _emit_private(
    session: GameSession,
    player_id: UUID,
    *,
    success: bool = True,
    message: str | None = None,
    to: str | None = None,
    debug: dict | None = None,
) -> None:
    emit(
        "state",
        _with_debug_timing(
            session.private_state(player_id, success=success, message=message),
            debug,
        ),
        to=to or request.sid,
    )


def _broadcast_session(
    session: GameSession,
    *,
    message: str | None = None,
    debug: dict | None = None,
) -> None:
    for player_state in session.player_state.values():
        socketio.emit(
            "state",
            _with_debug_timing(
                session.private_state(player_state.player.id, message=message),
                debug,
            ),
            to=_player_room(str(session.game_id), player_state.player.id),
        )
    socketio.emit("public_state", session.public_state(), to=_game_room(str(session.game_id)))


def _emit_state_diff(
    session: GameSession,
    player_id: UUID,
    diff: dict,
    *,
    debug: dict | None = None,
) -> None:
    payload = {"success": True, **diff}
    if diff["type"] in {
        "tile_placed",
        "tile_moved",
        "tile_removed",
        "tiles_moved",
        "tiles_removed",
    }:
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
        _with_debug_timing(payload, debug),
        to=_player_room(str(session.game_id), player_id),
    )


def _emit_peel_diffs(
    session: GameSession,
    peeling_player_id: UUID,
    diff: dict,
    *,
    debug: dict | None = None,
) -> None:
    if diff["type"] == "game_over":
        for player_state in session.player_state.values():
            payload = {
                "success": True,
                "type": "game_over",
                "bag_count": diff["bag_count"],
                "is_game_over": True,
                "winner_id": diff["winner_id"],
                "winner_name": diff["winner_name"],
                "message": f"{diff['winner_name']} wins!",
            }
            if player_state.player.id == peeling_player_id:
                payload["validated_board"] = player_state.board.to_state()
            socketio.emit(
                "state_diff",
                _with_debug_timing(payload, debug),
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
            _with_debug_timing(payload, debug),
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
    debug: dict | None = None,
) -> None:
    if not refresh:
        _emit_error(message, debug=debug)
        return

    try:
        session, player_id = _current_session(store)
    except ValueError:
        _emit_error(message, debug=debug)
        return
    _emit_private(session, player_id, success=False, message=message, debug=debug)


def _emit_error(message: str, *, debug: dict | None = None) -> None:
    emit(
        "action_error",
        _with_debug_timing({"success": False, "message": message}, debug),
        to=request.sid,
    )


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
