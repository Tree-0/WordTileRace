from __future__ import annotations

from collections.abc import Callable
import random
from typing import Any
from uuid import UUID

from backend.board import Board, Point
from backend.game_session import GameSession

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
sessions: dict[str, GameSession] = {}
connections: dict[str, tuple[str, UUID]] = {}


def init_socketio(
    app,
    *,
    board_factory: BoardFactory = Board,
    rng: random.Random | None = None,
):
    if socketio is None:
        return None

    socketio.init_app(app, cors_allowed_origins="*")
    register_socket_handlers(board_factory=board_factory, rng=rng)
    return socketio


def register_socket_handlers(
    *,
    board_factory: BoardFactory = Board,
    rng: random.Random | None = None,
) -> None:
    rng = rng or random.Random()

    @socketio.on("create_game")
    def create_game(payload=None):
        payload = _payload(payload)
        try:
            _leave_existing_room()
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
            sessions[game_id] = session
            _bind_connection(game_id, player_state.player.id)
            _emit_joined(session, player_state.player.id)
            _broadcast_session(session, message="Started a new game.")
            return {"success": True, "game_id": game_id, "player_id": str(player_state.player.id)}
        except ValueError as error:
            _emit_error(str(error))
            return {"success": False, "message": str(error)}

    @socketio.on("join_game")
    def join_game(payload=None):
        payload = _payload(payload)
        try:
            _leave_existing_room()
            game_id = str(payload.get("game_id", ""))
            session = _session(game_id)
            player_state = session.add_player(payload.get("player_name"))
            _bind_connection(game_id, player_state.player.id)
            _emit_joined(session, player_state.player.id)
            _broadcast_session(session, message="Joined the game.")
            return {"success": True, "game_id": game_id, "player_id": str(player_state.player.id)}
        except ValueError as error:
            _emit_error(str(error))
            return {"success": False, "message": str(error)}

    @socketio.on("request_state")
    def request_state(payload=None):
        try:
            session, player_id = _current_session()
            _emit_private(session, player_id)
            return {"success": True}
        except ValueError as error:
            _emit_error(str(error))
            return {"success": False, "message": str(error)}

    @socketio.on("place_tile")
    def place_tile(payload=None):
        try:
            payload = _payload(payload)
            session, player_id = _current_session()
            point = _parse_point(payload)
            char = str(payload.get("char", ""))
            overwrite = bool(payload.get("overwrite", False))
            session.place_tile(player_id, char, point.x, point.y, overwrite)
            _broadcast_session(
                session,
                message=f"Placed {char.upper()} at ({point.x}, {point.y}).",
            )
            return {"success": True}
        except ValueError as error:
            _emit_action_failure(str(error))
            return {"success": False, "message": str(error)}

    @socketio.on("move_tile")
    def move_tile(payload=None):
        try:
            payload = _payload(payload)
            session, player_id = _current_session()
            from_point = _parse_point(payload, "from")
            to_point = _parse_point(payload, "to")
            session.move_tile(player_id, from_point, to_point)
            _broadcast_session(
                session,
                message=(
                    f"Moved tile from ({from_point.x}, {from_point.y}) "
                    f"to ({to_point.x}, {to_point.y})."
                ),
            )
            return {"success": True}
        except ValueError as error:
            _emit_action_failure(str(error))
            return {"success": False, "message": str(error)}

    @socketio.on("remove_tile")
    def remove_tile(payload=None):
        try:
            payload = _payload(payload)
            session, player_id = _current_session()
            point = _parse_point(payload)
            session.remove_tile(player_id, point.x, point.y)
            _broadcast_session(session, message=f"Removed tile at ({point.x}, {point.y}).")
            return {"success": True}
        except ValueError as error:
            _emit_action_failure(str(error))
            return {"success": False, "message": str(error)}

    @socketio.on("peel")
    def peel(payload=None):
        try:
            session, player_id = _current_session()
            drawn = session.peel(player_id)
            drawn_text = _drawn_text(drawn)
            message = "Game complete." if session.is_game_over else f"Peeled {drawn_text}."
            _broadcast_session(session, message=message)
            return {"success": True}
        except ValueError as error:
            _emit_action_failure(str(error))
            return {"success": False, "message": str(error)}

    @socketio.on("dump")
    def dump(payload=None):
        try:
            payload = _payload(payload)
            session, player_id = _current_session()
            char = str(payload.get("char", ""))
            drawn = session.dump(player_id, char)
            _broadcast_session(
                session,
                message=f"Dumped {char.upper()} and drew {_drawn_text(drawn)}.",
            )
            return {"success": True}
        except ValueError as error:
            _emit_action_failure(str(error))
            return {"success": False, "message": str(error)}

    @socketio.on("disconnect")
    def disconnect(reason=None):
        sid = request.sid
        existing = connections.pop(sid, None)
        if existing is None:
            return

        game_id, _ = existing
        try:
            leave_room(game_id)
        except Exception:
            return


def _payload(payload) -> dict:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object.")
    return payload


def _bind_connection(game_id: str, player_id: UUID) -> None:
    connections[request.sid] = (game_id, player_id)
    join_room(game_id)


def _leave_existing_room() -> None:
    existing = connections.pop(request.sid, None)
    if existing is not None:
        leave_room(existing[0])


def _current_session() -> tuple[GameSession, UUID]:
    try:
        game_id, player_id = connections[request.sid]
    except KeyError:
        raise ValueError("Join or create a game before sending actions.") from None
    return _session(game_id), player_id


def _session(game_id: str) -> GameSession:
    try:
        return sessions[game_id]
    except KeyError:
        raise ValueError("Game not found.") from None


def _parse_point(payload: dict, name: str | None = None) -> Point:
    source = payload if name is None else payload.get(name)
    if not isinstance(source, dict):
        raise ValueError("Expected point coordinates.")

    try:
        return Point(int(source["x"]), int(source["y"]))
    except (KeyError, TypeError, ValueError):
        raise ValueError("Expected integer x and y coordinates.") from None


def _emit_joined(session: GameSession, player_id: UUID) -> None:
    emit("joined_game", {
        "game_id": str(session.game_id),
        "player_id": str(player_id),
    }, to=request.sid)


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
    for sid, (game_id, player_id) in list(connections.items()):
        if game_id == str(session.game_id):
            _emit_private(session, player_id, message=message, to=sid)
    socketio.emit("public_state", session.public_state(), to=str(session.game_id))


def _emit_action_failure(message: str) -> None:
    try:
        session, player_id = _current_session()
    except ValueError:
        _emit_error(message)
        return
    _emit_private(session, player_id, success=False, message=message)


def _emit_error(message: str) -> None:
    emit("action_error", {"success": False, "message": message}, to=request.sid)


def _drawn_text(drawn: dict[str, int]) -> str:
    tiles = [
        char
        for char, count in sorted(drawn.items())
        for _ in range(count)
    ]
    return ", ".join(tiles) if tiles else "no tiles"
