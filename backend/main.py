from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import create_app
from backend.socket_handlers import socketio


app = create_app()


if __name__ == "__main__":
    if socketio is None:
        app.run(host="127.0.0.1", port=5050, debug=False)
    else:
        socketio.run(app, host="127.0.0.1", port=5050, debug=False)
