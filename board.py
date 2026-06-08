from dataclasses import dataclass
from typing import Dict, List
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
        self.unplaced_letters: Counter[str] = unplaced_letters or Counter()
        self.placed_tiles: dict[Point, Tile]

        # data structure to hold all valid words
        self.valid_words: trie.Trie = trie_cache.load_or_build_trie(
            DICTIONARY_PATH, 
            CACHE_PATH
        )
    
    def __search_valid_words(self, word: str) -> bool:
        """get whether a word exists in the dictionary (is valid)"""
        return self.valid_words.search(word)
    

    def place_letter_maybe(self, char, x, y) -> Tile:
        """
        Attempt to place a letter at the (x,y) coordinate
        on the board, if we have any of that type to place.
        Returns a reference to the placed letter, or None
        """
        pass
 
    def place_letter(self, char, x, y) -> Tile:
        """
        place a letter of the specified char at the (x,y)
        coordinate on the board. Must have a letter to place.
        Returns a reference to the placed Letter. 
        """
        pass

    def remove_letter(self, x, y) -> bool:
        """
        Removes a letter from the board. If no letter is present at the 
        given x, y coordinates, does nothing. Returns success status of removal.
        """
        # remove from self.placed_letters

        # add back to self.unplaced_letters, resetting Point field

        # update self.formed_words (this might be complicated)
        pass

    def remove_letter(self, point: Point) -> bool:
        return remove_letter(p.x, p.y)
    
    def get_formed_words():
        """
        Find all of the left-to-right and top-to-bottom words on the board
        that are formed by sequences of tiles. 
        """
        pass

    def is_valid_board():
        """
        Check that all of the formed words on the board are in the dictionary,
        and therefore acceptable. 
        """
        pass