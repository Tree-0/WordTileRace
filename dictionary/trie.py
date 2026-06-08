"""
A simple trie implementation to store and easily search valid words
from a dictionary. 
"""


class TrieNode:
    """Represents a single node in the Trie structure."""
    def __init__(self):
        # Maps a character to its corresponding TrieNode
        self.children = {}
        # Flag to indicate if a complete word ends at this node
        self.is_end_of_word = False

class Trie:
    """
    A prefix tree used for efficient string storage and retrieval. 
    Strings are **case-insensitive**.
    """
    def __init__(self):
        # The root node does not store any character
        self.root = TrieNode()

    def insert(self, word: str) -> None:
        """Inserts a word into the trie."""
        current = self.root
        for char in word.upper():
            # Create a new node if the character path doesn't exist
            if char not in current.children:
                current.children[char] = TrieNode()
            # Move to the child node
            current = current.children[char]
        # Mark the end of the word
        current.is_end_of_word = True

    def search(self, word: str) -> bool:
        """Returns True if the word is in the trie, False otherwise."""
        current = self.root
        for char in word.upper():
            if char not in current.children:
                return False
            current = current.children[char]
        # Only return True if it marks a complete word
        return current.is_end_of_word

    def starts_with(self, prefix: str) -> bool:
        """Returns True if there is any word in the trie that starts with the given prefix."""
        current = self.root
        for char in prefix.upper():
            if char not in current.children:
                return False
            current = current.children[char]
        # Prefix exists, regardless of whether a complete word ends here
        return True
