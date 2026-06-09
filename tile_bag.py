from collections import Counter
import random


DEFAULT_RANDOM_DRAW_COUNT = 21

STANDARD_TILE_DISTRIBUTION = Counter({
    "A": 13,
    "B": 3,
    "C": 3,
    "D": 6,
    "E": 18,
    "F": 3,
    "G": 4,
    "H": 3,
    "I": 12,
    "J": 2,
    "K": 2,
    "L": 5,
    "M": 3,
    "N": 8,
    "O": 11,
    "P": 3,
    "Q": 2,
    "R": 9,
    "S": 6,
    "T": 9,
    "U": 6,
    "V": 3,
    "W": 3,
    "X": 2,
    "Y": 3,
    "Z": 2,
})


def make_custom_rack(letters: str) -> Counter[str]:
    """Create a rack from user-provided A-Z letters."""
    normalized = letters.strip().upper()
    if not normalized:
        raise ValueError("Enter at least one letter.")

    invalid_chars = [char for char in normalized if not char.isalpha()]
    if invalid_chars:
        raise ValueError("Custom racks can only contain A-Z letters.")

    return Counter(normalized)


def draw_random_rack(
    count: int = DEFAULT_RANDOM_DRAW_COUNT,
    rng: random.Random | None = None,
    distribution: Counter[str] | None = None,
) -> Counter[str]:
    """Draw a random rack from a Bananagrams tile distribution."""
    if count < 0:
        raise ValueError("Draw count cannot be negative.")

    distribution = distribution or STANDARD_TILE_DISTRIBUTION
    total_tiles = sum(distribution.values())
    if count > total_tiles:
        raise ValueError("Cannot draw more tiles than the bag contains.")

    tile_pool = [
        char
        for char, amount in distribution.items()
        for _ in range(amount)
    ]
    rng = rng or random.Random()
    return Counter(rng.sample(tile_pool, count))


def draw_tiles(
    bag: Counter[str],
    count: int,
    rng: random.Random | None = None,
) -> Counter[str]:
    """Draw tiles from a mutable bag counter."""
    if count < 0:
        raise ValueError("Draw count cannot be negative.")

    available_count = sum(bag.values())
    if count > available_count:
        raise ValueError("Cannot draw more tiles than the bag contains.")

    tile_pool = [
        char
        for char, amount in bag.items()
        for _ in range(amount)
    ]
    rng = rng or random.Random()
    drawn_tiles = Counter(rng.sample(tile_pool, count))
    bag.subtract(drawn_tiles)

    for char in list(bag):
        if bag[char] <= 0:
            del bag[char]

    return drawn_tiles
