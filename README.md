# Bananagrams

A small local web version of Bananagrams built with a Python game model,
a Flask API, and a vanilla JavaScript grid UI.

## Run The App

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Open `http://127.0.0.1:5050`.

To stop the Flask server, return to the terminal running `python main.py` and
press `Ctrl+C`.

If the server was started from another terminal or helper session, stop the
process listening on port `5050`:

```bash
lsof -ti tcp:5050 | xargs kill
```

## Game Rules

Bananagrams is a word-building tile game. In this version, you place tiles on
an open grid to form connected words. Words can only read left-to-right or
top-to-bottom. The board is valid when every placed tile belongs to a formed
word and every formed word exists in the dictionary.

This first version supports a custom starting rack or a random 21-tile rack.
When every tile in your rack has been placed and the board is valid, you can
peel to draw one new tile from the bag. You can dump a rack tile at any time
while tiles remain in the bag; the dumped tile returns to the bag and you draw
up to three replacement tiles.

The game ends when the bag is empty, your rack is empty, and every placed tile
forms a valid arrangement. It does not yet include timers, scoring, multiplayer,
or full official table rules.

## Controls

- Click a grid cell to select it.
- Press `A-Z` to place that letter in the selected cell.
- Press `Backspace` or `Delete` to remove the selected tile.
- Press arrow keys to move the selected cell.
- Drag a rack tile onto the grid to place it.
- Drag a placed tile to an empty cell to move it.
- Drag a placed tile back to the rack to remove it.
- Click `Peel` when it is enabled to draw one tile.
- Click `Dump` below a rack tile to return it and draw replacements.

## Files

- `main.py`: Starts the Flask development server.
- `app.py`: Defines the Flask app, page route, and JSON API endpoints.
- `game.py`: Owns the active game session, remaining bag, peel/dump logic, and
  win condition.
- `board.py`: Core board model for tile placement, movement, word discovery,
  validation, and UI state serialization.
- `tile_bag.py`: Standard Bananagrams tile distribution, random rack drawing,
  and custom rack parsing.
- `templates/index.html`: Main browser UI structure.
- `static/app.js`: Frontend state rendering, keyboard controls, drag/drop, and
  API calls.
- `static/styles.css`: App layout, board grid, tile, rack, and status styling.
- `dictionary/trie.py`: Trie data structure used for word lookup.
- `dictionary/trie_cache.py`: Builds, saves, and loads the serialized trie.
- `dictionary/dictionary.txt`: Source word list.
- `dictionary/trie.pickle`: Cached serialized trie built from the dictionary.
- `dictionary/__init__.py`: Dictionary package exports.
- `test_board.py`: Unit tests for the board model.
- `test_game.py`: Unit tests for peel, dump, bag state, and game completion.
- `test_tile_bag.py`: Unit tests for tile distribution and rack creation.
- `test_app.py`: Flask API tests.
- `requirements.txt`: Python dependencies.
- `RULES.txt`: Scratch notes for future rules work.
