"""Preset avatars: a figure on a colored tile, stored as "figure.color".

This list is the source of truth. frontend/src/avatars/catalog.js holds the
same ids (and draws them); change both together. There are no uploads, so an
avatar is only ever one of these strings or NULL (initials).
"""

FIGURES: tuple[str, ...] = (
    "owl",
    "fox",
    "cat",
    "bear",
    "frog",
    "penguin",
    "robot",
    "ghost",
    "cactus",
    "rocket",
    "octopus",
    "alien",
)

COLORS: tuple[str, ...] = (
    "sky",
    "navy",
    "orange",
    "sand",
    "apricot",
    "mist",
)

AVATAR_KEYS: frozenset[str] = frozenset(
    f"{figure}.{color}" for figure in FIGURES for color in COLORS
)


def is_valid_avatar_key(key: str) -> bool:
    return key in AVATAR_KEYS
