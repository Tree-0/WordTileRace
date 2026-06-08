from dataclasses import dataclass
from collections import (
    Counter
)
from pathlib import Path
from dictionary import (
    trie,
    trie_cache
)

DICTIONARY_PATH = Path(__file__).parent / "dictionary" / "dictionary.txt"
CACHE_PATH = Path(__file__).parent / "dictionary" / "trie.pickle"

WILDCARD_CHAR = '*'

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
        char = char.upper()

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
        return {word for word, _ in self.__get_formed_word_paths()}

    def __get_formed_word_paths(self) -> list[tuple[str, set[Point]]]:
        formed_word_paths: list[tuple[str, set[Point]]] = []

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
                    formed_word_paths.append((''.join(letters), points))

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
                    formed_word_paths.append((''.join(letters), points))
        
        return formed_word_paths

    def is_valid_board(self) -> bool:
        """
        Check that all of the formed words on the board are in the dictionary,
        and therefore acceptable. 
        """
        formed_word_paths = self.__get_formed_word_paths()
        if self.placed_tiles and not formed_word_paths:
            return False

        covered_points = set()
        for _, points in formed_word_paths:
            covered_points.update(points)

        if covered_points != set(self.placed_tiles):
            return False

        return all(
            self.__search_valid_words(word)
            for word, _ in formed_word_paths
        )
