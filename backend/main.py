from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import create_app
from backend.config import AppConfig
from backend.socket_handlers import socketio


config = AppConfig.from_env()
app = create_app(config=config)


if __name__ == "__main__":
    if socketio is None:
        app.run(host=config.host, port=config.port, debug=False)
    else:
        socketio.run(app, host=config.host, port=config.port, debug=False)
