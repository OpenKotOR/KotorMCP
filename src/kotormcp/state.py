"""Shared state for KotorMCP: installation cache, game aliases, path resolution."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pykotor.common.misc import Game
from pykotor.extract.installation import Installation
from pykotor.tools.path import CaseAwarePath, find_kotor_paths_from_default

if TYPE_CHECKING:
    from collections.abc import Iterator

INSTALLATIONS: dict[Game, Installation] = {}
DEFAULT_PATH_CACHE = find_kotor_paths_from_default()
GAME_ALIASES: dict[str, Game] = {
    "k1": Game.K1,
    "kotori": Game.K1,
    "swkotor": Game.K1,
    "k2": Game.K2,
    "tsl": Game.K2,
    "kotor2": Game.K2,
}
ENV_HINTS: dict[Game, tuple[str, ...]] = {
    Game.K1: ("K1_PATH", "KOTOR_PATH", "KOTOR1_PATH"),
    Game.K2: ("K2_PATH", "TSL_PATH", "KOTOR2_PATH", "K1_PATH"),
}


def resolve_game(label: str | None) -> Game | None:
    """Resolve game alias (k1, k2, tsl, etc.) to Game enum."""
    if label is None:
        return None
    normalized = label.strip().lower()
    return GAME_ALIASES.get(normalized)


def iter_candidate_paths(game: Game, explicit: str | None) -> Iterator[CaseAwarePath]:
    """Yield candidate installation paths: explicit, then env vars, then defaults."""
    seen: set[str] = set()
    if explicit:
        candidate = CaseAwarePath(explicit).expanduser().resolve()
        key = str(candidate).lower()
        if key not in seen:
            seen.add(key)
            yield candidate
    for env_name in ENV_HINTS.get(game, ()):
        env_value = os.environ.get(env_name)
        if env_value:
            candidate = CaseAwarePath(env_value).expanduser().resolve()
            key = str(candidate).lower()
            if key not in seen:
                seen.add(key)
                yield candidate
    for default_path in DEFAULT_PATH_CACHE.get(game, []):
        key = str(default_path).lower()
        if key not in seen:
            seen.add(key)
            yield default_path


def load_installation(game: Game, explicit_path: str | None = None) -> Installation:
    """Load and cache an installation for the given game."""
    cached = INSTALLATIONS.get(game)
    if cached:
        return cached

    for candidate in iter_candidate_paths(game, explicit_path):
        if candidate.is_dir():
            INSTALLATIONS[game] = Installation(candidate)
            return INSTALLATIONS[game]

    msg = f"Unable to locate installation for {game.name}. Provide --path or set {ENV_HINTS[game][0]}."
    raise ValueError(msg)
