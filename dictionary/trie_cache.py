"""
Helpers for building and caching the dictionary trie.

The cache is written with pickle, so only load cache files that were created
locally by this project.
"""

from __future__ import annotations

from pathlib import Path
import pickle

from .trie import Trie


DICTIONARY_PATH = Path(__file__).with_name("dictionary.txt")
TRIE_CACHE_PATH = Path(__file__).with_name("trie.pickle")


def build_trie(dictionary_path: str | Path = DICTIONARY_PATH) -> Trie:
    """Build and return a trie containing every word in the dictionary file."""
    trie = Trie()
    dictionary_path = Path(dictionary_path)

    with dictionary_path.open("r", encoding="utf-8") as dictionary_file:
        for line in dictionary_file:
            word = line.strip()
            if word:
                trie.insert(word)

    return trie


def save_trie(trie: Trie, cache_path: str | Path = TRIE_CACHE_PATH) -> None:
    """Serialize a trie to disk."""
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    with cache_path.open("wb") as cache_file:
        pickle.dump(trie, cache_file, protocol=pickle.HIGHEST_PROTOCOL)


def load_trie(cache_path: str | Path = TRIE_CACHE_PATH) -> Trie:
    """Load a serialized trie from disk."""
    with Path(cache_path).open("rb") as cache_file:
        return pickle.load(cache_file)


def load_or_build_trie(
    dictionary_path: str | Path = DICTIONARY_PATH,
    cache_path: str | Path = TRIE_CACHE_PATH,
    rebuild: bool = False,
) -> Trie:
    """
    Load the trie from cache, or build and cache it if no cache exists.

    Set rebuild=True to force regeneration from the dictionary text file.
    """
    cache_path = Path(cache_path)

    if cache_path.exists() and not rebuild:
        return load_trie(cache_path)

    trie = build_trie(dictionary_path)
    save_trie(trie, cache_path)
    return trie
