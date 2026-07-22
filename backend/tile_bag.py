from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_DOWN
import random


DEFAULT_RANDOM_DRAW_COUNT = 21
DEFAULT_DUMP_DRAW_COUNT = 3
DEFAULT_BAG_MULTIPLIER = 1.0
NONE_BAG_MULTIPLIER = 0.0
MIN_BAG_MULTIPLIER = 1.0
MAX_BAG_MULTIPLIER = 4.0

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


def normalize_bag_multiplier(value: object = DEFAULT_BAG_MULTIPLIER) -> float:
    """Return a finite bag multiplier truncated to one decimal place."""
    if isinstance(value, bool):
        raise ValueError("Bag size multiplier must be a number.")

    try:
        multiplier = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Bag size multiplier must be a number.") from None

    if not multiplier.is_finite():
        raise ValueError("Bag size multiplier must be a finite number.")

    if multiplier == Decimal(str(NONE_BAG_MULTIPLIER)):
        return NONE_BAG_MULTIPLIER
    if multiplier < Decimal(str(MIN_BAG_MULTIPLIER)):
        raise ValueError(
            "Bag size multiplier must be NONE (0x) or between "
            f"{MIN_BAG_MULTIPLIER:g}x and {MAX_BAG_MULTIPLIER:g}x."
        )
    if multiplier > Decimal(str(MAX_BAG_MULTIPLIER)):
        return MAX_BAG_MULTIPLIER

    multiplier = multiplier.quantize(Decimal("0.1"), rounding=ROUND_DOWN)
    return float(multiplier)


def make_tile_bag(multiplier: object = DEFAULT_BAG_MULTIPLIER) -> Counter[str]:
    """Scale the standard distribution while preserving its proportions."""
    normalized = Decimal(str(normalize_bag_multiplier(multiplier)))
    target_count = int(sum(STANDARD_TILE_DISTRIBUTION.values()) * normalized)
    scaled_bag: Counter[str] = Counter()
    fractional_counts: list[tuple[Decimal, int, str]] = []

    for index, (char, amount) in enumerate(STANDARD_TILE_DISTRIBUTION.items()):
        scaled_amount = Decimal(amount) * normalized
        whole_amount = int(scaled_amount)
        scaled_bag[char] = whole_amount
        fractional_counts.append((scaled_amount - whole_amount, index, char))

    remaining = target_count - sum(scaled_bag.values())
    fractional_counts.sort(key=lambda item: (-item[0], item[1]))
    for _, _, char in fractional_counts[:remaining]:
        scaled_bag[char] += 1

    return +scaled_bag


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
    """Draw a random rack from the standard word-tile distribution."""
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
