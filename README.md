# Bananagrams

A small local web version of Bananagrams built with a Python game model,
Flask, Flask-SocketIO, and a vanilla JavaScript grid UI.

## Run The App

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python backend/main.py
```

Open `http://127.0.0.1:5050`.

The app uses Socket.IO for gameplay actions, so start it with
`python backend/main.py` rather than `flask run`.

To stop the server, return to the terminal running `python backend/main.py` and
press `Ctrl+C`.

If the server was started from another terminal or helper session, stop the
process listening on port `5050`:

```bash
lsof -ti tcp:5050 | xargs kill
```

## Multiplayer

Opening the app starts a new random multiplayer game and joins you as the first
player. Gameplay actions are sent over Socket.IO to the server, where
`GameSession` validates and applies them before broadcasting updated state.

To join the same in-memory game from another browser tab or device, use the game
id from the active browser state and open:

```text
http://127.0.0.1:5050/?game=<game-id>
```

The first multiplayer version stores games in server process memory. Restarting
the server clears active games. If you are joining from another device on your
local network, run the server on a reachable host/interface and use that host in
the URL instead of `127.0.0.1`.

## Game Rules

Bananagrams is a word-building tile game. In this version, you place tiles on
an open grid to form connected words. Words can only read left-to-right or
top-to-bottom. The board is valid when every placed tile belongs to a formed
word and every formed word exists in the dictionary.

This version supports a custom starting rack or a random 21-tile rack. Each
player has a separate board and rack. The game session owns the shared tile bag.
When a player places every rack tile and has a valid board, they can peel to draw
one tile for every player. A player can dump a rack tile while tiles remain in
the bag; the dumped tile returns to the bag and that player draws up to three
replacement tiles.

The game ends when the bag is empty and a player has an empty rack with a valid
board. It does not yet include timers, scoring, persistence, or full official
table rules.

## Controls

- Click a grid cell to select it.
- Press `A-Z` to place that letter in the selected cell.
  - Alternatively, drag a rack tile onto the grid to place it.
- Press `Backspace`, `Escape`, or `Delete` to remove the selected tile.
- Press arrow keys to move the selected cell.
- Drag a placed tile to an empty cell to move it.
- Drag a placed tile back to the rack to remove it.
- Click `Peel` when it is enabled (or press `Space`) to draw one tile.
- Click `Dump` below a rack tile to return it and draw replacements.
  - Alternatively, dump the tile in the currently selected cell using `Shift + Space`

## Files

- `backend/main.py`: Starts the Flask development server.
- `backend/app.py`: Defines the Flask app, page route, health endpoint, definitions
  endpoint, and Socket.IO initialization.
- `backend/socket_handlers.py`: Socket.IO event handlers and in-memory session/connection
  registry.
- `backend/game_session.py`: Authoritative multiplayer session model, shared bag,
  player actions, peel/dump logic, public/private state, and win condition.
- `backend/game.py`: Player and player-state models.
- `backend/board.py`: Core board model for tile placement, movement, word discovery,
  validation, and UI state serialization.
- `backend/tile_bag.py`: Standard Bananagrams tile distribution, random rack drawing,
  and custom rack parsing.
- `backend/word_definitions.py`: Dictionary API lookup and response parsing.
- `frontend/templates/index.html`: Main browser UI structure.
- `frontend/static/app.js`: Frontend state rendering, keyboard controls, drag/drop, and
  Socket.IO gameplay events.
- `frontend/static/styles.css`: App layout, board grid, tile, rack, and status styling.
- `backend/dictionary/trie.py`: Trie data structure used for word lookup.
- `backend/dictionary/trie_cache.py`: Builds, saves, and loads the serialized trie.
- `backend/dictionary/dictionary.txt`: Source word list.
- `backend/dictionary/trie.pickle`: Cached serialized trie built from the dictionary.
- `backend/dictionary/__init__.py`: Dictionary package exports.
- `backend/test/test_board.py`: Unit tests for the board model.
- `backend/test/test_game.py`: Unit tests for player state.
- `backend/test/test_game_session.py`: Unit tests for multiplayer session actions,
  shared bag behavior, and game completion.
- `backend/test/test_tile_bag.py`: Unit tests for tile distribution and rack creation.
- `backend/test/test_app.py`: Flask page, health, and definitions endpoint tests.
- `backend/test/test_word_definitions.py`: Unit tests for definition lookup parsing.
- `requirements.txt`: Python dependencies.
- `RULES.txt`: Scratch notes for future rules work.
