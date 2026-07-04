from dataclasses import dataclass
from collections import (
    Counter
)
from pathlib import Path
from backend.dictionary import trie
from backend.dictionary import (
    trie_cache
)

DICTIONARY_PATH = Path(__file__).parent / "dictionary" / "dictionary.txt"
CACHE_PATH = Path(__file__).parent / "dictionary" / "trie.pickle"

WILDCARD_CHAR = '*'


def normalize_char(char: str) -> str:
    """Normalize and validate a playable tile character."""
    normalized = char.strip().upper()
    if normalized == WILDCARD_CHAR:
        return normalized
    if len(normalized) != 1 or not normalized.isalpha():
        raise ValueError("Tile must be a single A-Z letter")
    return normalized


@dataclass(frozen=True)
class Point:
    x: int
    y: int

@dataclass(frozen=True)
class Tile:
    char: str
    is_wildcard: bool = False

class Board:
    def __init__(self, unplaced_letters: Counter[str] | None = None):
        self.unplaced_letters: Counter[str] = Counter()
        if unplaced_letters:
            for char, count in unplaced_letters.items():
                self.unplaced_letters[char.upper()] += count

        self.placed_tiles: dict[Point, Tile] = {}

        # data structure to hold all valid words
        self.valid_words: trie.Trie = trie_cache.load_or_build_trie(
            DICTIONARY_PATH, 
            CACHE_PATH
        )
    
    def __search_valid_words(self, word: str) -> bool:
        """get whether a word exists in the dictionary (is valid)"""
        return self.valid_words.search(word)
    
    def place_tile(self, char: str, x: int, y: int) -> Tile:
        """
        place a letter of the specified char at the (x,y)
        coordinate on the board. Must have a letter to place.
        Returns a reference to the placed tile. 
        """
        char = normalize_char(char)

        # need a char to place
        if self.unplaced_letters[char] == 0:
            raise ValueError(f"No tiles with letter {char} to place")

        p = Point(x,y)
        # need that spot on the board to be free
        if p in self.placed_tiles:
            raise ValueError(f"Tile already placed at ({x}, {y})")
        t = Tile(char, char == WILDCARD_CHAR)
        self.placed_tiles[p] = t
        self.unplaced_letters[char] -= 1

        return t

    def place_or_overwrite_tile(self, char: str, x: int, y: int) -> Tile:
        """
        Place a tile, replacing the existing tile only when the new tile exists.
        The operation is atomic: failed overwrites leave the board unchanged.
        """
        char = normalize_char(char)
        point = Point(x, y)
        existing_tile = self.placed_tiles.get(point)

        if existing_tile is None:
            return self.place_tile(char, x, y)

        if existing_tile.char == char:
            return existing_tile

        if self.unplaced_letters[char] == 0:
            raise ValueError(f"No tiles with letter {char} to place")

        self.unplaced_letters[existing_tile.char] += 1
        self.placed_tiles[point] = Tile(char, char == WILDCARD_CHAR)
        self.unplaced_letters[char] -= 1
        return self.placed_tiles[point]

    def place_tile_maybe(self, char: str, x: int, y: int) -> Tile | None:
        """
        Attempt to place a letter at the (x,y) coordinate
        on the board, if we have any of that type to place.
        Returns a reference to the placed letter, or None
        """
        try:
            return self.place_tile(char, x, y)
        except ValueError:
            return None

    def move_tile(self, from_point: Point, to_point: Point) -> Tile:
        """Move an already placed tile to an empty point without changing rack counts."""
        if from_point not in self.placed_tiles:
            raise ValueError(f"No tile placed at ({from_point.x}, {from_point.y})")

        if from_point == to_point:
            return self.placed_tiles[from_point]

        if to_point in self.placed_tiles:
            raise ValueError(f"Tile already placed at ({to_point.x}, {to_point.y})")

        tile = self.placed_tiles.pop(from_point)
        self.placed_tiles[to_point] = tile
        return tile

    def remove_letter(self, x: int, y: int) -> bool:
        """
        Removes a letter from the board. If no letter is present at the 
        given x, y coordinates, does nothing. Returns success status of removal.
        """
        p = Point(x,y)
        if p not in self.placed_tiles:
            return False
        
        # add back to unplaced letters
        self.unplaced_letters[self.placed_tiles[p].char] += 1
        # remove from self.placed_tiles
        del self.placed_tiles[p]

        return True
    
    def get_formed_words(self) -> set[str]:
        """
        Find all of the left-to-right and top-to-bottom words on the board
        that are formed by sequences of tiles. 
        """
        return {detail["word"] for detail in self.get_formed_word_details()}

    def get_formed_word_details(self) -> list[dict]:
        """Return all formed words with direction, occupied points, and validity."""
        formed_word_details = []

        for p in self.placed_tiles:
            up = Point(p.x, p.y-1)
            if up not in self.placed_tiles:
                # perform vertical scan
                curr_point = p
                letters = []
                points = set()
                while curr_point in self.placed_tiles:
                    letters.append(self.placed_tiles[curr_point].char)
                    points.add(curr_point)
                    curr_point = Point(curr_point.x, curr_point.y+1)
                if len(letters) > 1:
                    word = ''.join(letters)
                    formed_word_details.append({
                        "word": word,
                        "direction": "vertical",
                        "points": self.__serialize_points(points),
                        "is_valid": self.__search_valid_words(word),
                    })

            left = Point(p.x-1, p.y)
            if left not in self.placed_tiles:
                # perform horizontal scan
                curr_point = p
                letters = []
                points = set()
                while curr_point in self.placed_tiles:
                    letters.append(self.placed_tiles[curr_point].char)
                    points.add(curr_point)
                    curr_point = Point(curr_point.x+1, curr_point.y)
                if len(letters) > 1:
                    word = ''.join(letters)
                    formed_word_details.append({
                        "word": word,
                        "direction": "horizontal",
                        "points": self.__serialize_points(points),
                        "is_valid": self.__search_valid_words(word),
                    })
        
        return formed_word_details

    def is_valid_board(self) -> bool:
        """
        Check that all of the formed words on the board are in the dictionary,
        and therefore acceptable. All tiles must also be connected. 
        """

        # Tiles must be adjacent to one another, either up-down or left-right.
        # Board is invalid if sections are disjoint.
        if self.placed_tiles:
            unvisited = set(self.placed_tiles)
            start = next(iter(unvisited))
            unvisited.remove(start)
            stack = [start]
            while stack:
                point = stack.pop()
                x, y = point.x, point.y
                for neighbor in (
                    Point(x + 1, y),
                    Point(x - 1, y),
                    Point(x, y + 1),
                    Point(x, y - 1),
                ):
                    if neighbor in unvisited:
                        unvisited.remove(neighbor)
                        stack.append(neighbor)

            if unvisited:
                return False

        formed_word_details = self.get_formed_word_details()
        if self.placed_tiles and not formed_word_details:
            return False

        covered_points = set()
        for detail in formed_word_details:
            covered_points.update(
                Point(point["x"], point["y"]) for point in detail["points"]
            )

        if covered_points != set(self.placed_tiles):
            return False

        return all(detail["is_valid"] for detail in formed_word_details)

    def to_state(self) -> dict:
        """Serialize board state for the browser UI."""
        formed_word_details = self.get_formed_word_details()
        return {
            "rack": dict(sorted(
                (char, count)
                for char, count in self.unplaced_letters.items()
                if count > 0
            )),
            "placed_tiles": [
                {
                    "x": point.x,
                    "y": point.y,
                    "char": tile.char,
                    "is_wildcard": tile.is_wildcard,
                }
                for point, tile in sorted(
                    self.placed_tiles.items(),
                    key=lambda item: (item[0].y, item[0].x),
                )
            ],
            "formed_words": formed_word_details,
            "is_valid": self.is_valid_board(),
            "messages": self.__validation_messages(formed_word_details),
        }

    def __validation_messages(self, formed_word_details: list[dict]) -> list[str]:
        if not self.placed_tiles:
            return ["Place a tile to start."]

        if not formed_word_details:
            return ["No complete words have been formed yet."]

        covered_points = set()
        for detail in formed_word_details:
            covered_points.update(
                Point(point["x"], point["y"]) for point in detail["points"]
            )

        messages = []
        if covered_points != set(self.placed_tiles):
            messages.append("Every placed tile must belong to a word.")

        invalid_words = [
            detail["word"]
            for detail in formed_word_details
            if not detail["is_valid"]
        ]
        if invalid_words:
            messages.append(f"Invalid words: {', '.join(sorted(invalid_words))}.")

        if not messages:
            messages.append("All formed words are valid.")

        return messages

    def __serialize_points(self, points: set[Point]) -> list[dict[str, int]]:
        return [
            {"x": point.x, "y": point.y}
            for point in sorted(points, key=lambda point: (point.y, point.x))
        ]
