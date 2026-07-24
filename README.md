# Word Tile Race

I played Bananagrams with my friends and lost so badly that I made a tool to practice. 
Then I realized that I needed to actually be able to show my friends that I was 
better than them, so I made it multiplayer.

This is a real-time word-tile web game built with a Python game model,
Flask, Flask-SocketIO, Redis session storage, and a vanilla JavaScript
grid UI.


## Game Rules

Players place tiles on an open grid to form connected words. Words can only read
left-to-right or top-to-bottom. A board is valid when every placed tile belongs
to a formed word and every formed word exists in the dictionary.

Each player has a separate board and rack. The game session owns the shared tile
bag. When a player places every rack tile and has a valid board, they can peel
to draw one tile for every player. A player can dump a rack tile while tiles
remain in the bag; the dumped tile returns to the bag and that player draws up
to three replacement tiles.

Custom matches can scale the standard shared bag
from 1x to 4x, or remove it with the NONE option. Each player gets the same
exact custom rack when one is supplied, or draws 21 random tiles otherwise.

The game ends when fewer tiles remain in the bag than there are players and a
player has an empty rack with a valid board. As of now, there are no timers, no
scores, and no saved info beyond the
scope of the current match (no player stats, streaks, etc.).

## Controls

- Click a grid cell to select it, or move cells with arrow keys.
- Press `A-Z` to place that letter in the selected cell.
  - Alternatively, drag a rack tile onto the grid to place it.
- Press `Shift + Space`, `Backspace`, or `Delete` to return the selected tile
  or block to the rack.
- Drag a placed tile to an empty cell to move it.
- Drag a placed tile back to the rack to remove it.
- Hold `Shift` while dragging across the board, or use `Shift + Arrow`, to
  select the occupied tiles within an area. Empty cells inside the area are
  ignored.
- Press `Ctrl/Cmd + C` or `Ctrl/Cmd + X` to prepare a selected block to move,
  choose its destination with a click or the arrow keys, and press
  `Ctrl/Cmd + V` to place it.
- Drag any tile in a selected block to move the whole block.
- Press `Escape` to cancel a pending block move or collapse a selection.
- Press `Ctrl/Cmd + Z` or click `Undo` to undo one of the last eight board
  edits. Peel preserves undo history; Dump clears it.
- Click `Peel` when it is enabled, or press `Space`, to draw one tile for every
  player.
- Press `Ctrl/Cmd + D` to dump the tile on the selected board cell.
- Click `Dump` below a rack tile to return it and draw replacements.

## Run Locally

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python backend/main.py
```

Open `http://127.0.0.1:5050`.

Local runs use in-memory game storage unless `REDIS_URL` is set. Gameplay
actions use Socket.IO, so start the app with `python backend/main.py` rather
than `flask run`.

To stop the server, return to the terminal running `python backend/main.py` and
press `Ctrl+C`. If another terminal started the process, stop whatever is using
port `5050`:

```bash
lsof -ti tcp:5050 | xargs kill
```

## Run With Docker Compose

```bash
docker compose up --build
```

Open `http://127.0.0.1:5050`. Compose starts both the web app and Redis, so it
matches the deployable runtime shape more closely than the in-memory local run.

## Multiplayer

Opening the app shows a lobby where you can create a random or custom game, or
join one by pasting its game ID or invite URL. Players choose a nickname before
entering a match; opening an invite URL prompts new players for one and reconnects
returning players automatically. Gameplay actions are sent over Socket.IO to the
server, where `GameSession` validates and applies them before broadcasting updated
private player state. The collapsible tab on the left shows everyone in the match.

The sidebar shows the current raw game id and has a copy button for a full
invite URL:

```text
https://your-host.example/?game=<game-id>
```

The browser stores `{gameId, playerId, playerName}` in local storage so refreshes
and revisits can reconnect to the same player when the game still exists. Redis
games expire after `GAME_TTL_SECONDS`, which defaults to 2 hours.

## Production Deployment

Currently deploying one web process and one Redis instance, which is enough for a small friend group
and roughly a handful of concurrent games. Redis stores game
records and also coordinates Socket.IO messages for future scaling.

Required environment variables:

```text
SECRET_KEY=<long random string>
REDIS_URL=redis://...
ALLOWED_ORIGINS=https://your-domain.example
```

Optional environment variables:

```text
GAME_TTL_SECONDS=7200
PORT=5050
HOST=0.0.0.0
WEB_THREADS=20
```

Production command:

```bash
gunicorn --worker-class gthread --threads ${WEB_THREADS:-20} --bind 0.0.0.0:${PORT:-5050} backend.main:app
```

## Files

- `backend/main.py`: Importable app entrypoint and local Socket.IO runner.
- `backend/app.py`: Flask app factory, page route, health endpoint, definitions
  endpoint, store setup, and Socket.IO initialization.
- `backend/socket_handlers.py`: Socket.IO event handlers, rooms, reconnect
  handling, and process-local connection registry.
- `backend/game_store.py`: Memory and Redis game storage.
- `backend/game_session.py`: Authoritative multiplayer session model, shared
  bag, player actions, public/private state, serialization, and win condition.
- `backend/game.py`: Player and player-state models.
- `backend/board.py`: Core board model for tile placement, movement, word
  discovery, validation, and UI state serialization.
- `backend/tile_bag.py`: Standard tile distribution, random rack drawing, and
  custom rack parsing.
- `backend/word_definitions.py`: Dictionary API lookup and response parsing.
- `frontend/templates/index.html`: Main browser UI structure.
- `frontend/static/app.js`: Frontend state rendering, keyboard controls,
  drag/drop, reconnects, invite copying, and Socket.IO gameplay events.
- `frontend/static/styles.css`: App layout, board grid, tile, rack, and status
  styling.
- `Dockerfile`, `compose.yaml`: Containerized deployment and local Redis smoke
  run.
- `requirements.txt`: Python dependencies.
