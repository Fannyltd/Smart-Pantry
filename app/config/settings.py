"""Configuration centralisée de Smart Pantry.

Les valeurs sont lues depuis les variables d'environnement (fichier ``.env``
facultatif à la racine du projet, voir ``.env.example``) avec des valeurs par
défaut adaptées au développement local.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

try:  # python-dotenv est facultatif
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"

if load_dotenv is not None:
    load_dotenv(BASE_DIR / ".env")


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_list(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    # --- Base de données -------------------------------------------------
    database_url: str = f"sqlite:///{(DATA_DIR / 'smart_pantry.db').as_posix()}"

    # --- TheMealDB --------------------------------------------------------
    mealdb_base_url: str = "https://www.themealdb.com/api/json/v1"
    mealdb_api_key: str = "1"  # clé de test publique (usage éducatif)
    api_timeout: float = 8.0
    api_enabled: bool = True
    max_api_ingredients: int = 5      # nb d'ingrédients interrogés via filter.php (V1 = 1 ingrédient/requête)
    max_api_recipes: int = 15         # nb max de recettes détaillées (lookup.php) par recommandation
    default_servings: int = 4         # TheMealDB ne fournit pas le nombre de portions

    # --- Péremption -------------------------------------------------------
    expiration_warning_days: int = 3  # seuil "orange"
    priority_horizon_days: int = 7    # horizon de normalisation de P(r)

    # --- Recommandation : Score(r) = 0.6 C(r) + 0.4 P(r) --------------------
    coverage_weight: float = 0.6
    priority_weight: float = 0.4
    fuzzy_match_threshold: float = 0.85

    # --- Analytics --------------------------------------------------------
    min_history_movements: int = 3   # BR17
    default_period_days: int = 30    # BR16

    # --- Préférences utilisateur ------------------------------------------
    user_allergens: tuple[str, ...] = field(default_factory=tuple)

    # --- Fichiers ---------------------------------------------------------
    data_dir: Path = DATA_DIR

    @property
    def mealdb_url(self) -> str:
        return f"{self.mealdb_base_url.rstrip('/')}/{self.mealdb_api_key}/"


def _resolve_sqlite_url(url: str) -> str:
    """Rend absolu un chemin SQLite relatif (relatif à la racine du projet)."""
    prefix = "sqlite:///"
    if url.startswith(prefix) and not url.startswith(prefix + "/") and ":memory:" not in url:
        return prefix + (BASE_DIR / url[len(prefix):]).as_posix()
    return url


def load_settings() -> Settings:
    defaults = Settings()
    coverage = _env_float("SCORE_COVERAGE_WEIGHT", defaults.coverage_weight)
    priority = _env_float("SCORE_PRIORITY_WEIGHT", defaults.priority_weight)
    if coverage < 0 or priority < 0 or abs(coverage + priority - 1) > 1e-6:
        coverage, priority = defaults.coverage_weight, defaults.priority_weight
    return Settings(
        database_url=_resolve_sqlite_url(_env_str("DATABASE_URL", defaults.database_url)),
        mealdb_base_url=_env_str("MEALDB_BASE_URL", defaults.mealdb_base_url),
        mealdb_api_key=_env_str("MEALDB_API_KEY", defaults.mealdb_api_key),
        api_timeout=_env_float("API_TIMEOUT", defaults.api_timeout),
        api_enabled=_env_str("API_ENABLED", "true").lower() not in {"0", "false", "no", "non"},
        max_api_ingredients=_env_int("MAX_API_INGREDIENTS", defaults.max_api_ingredients),
        max_api_recipes=_env_int("MAX_API_RECIPES", defaults.max_api_recipes),
        default_servings=_env_int("DEFAULT_SERVINGS", defaults.default_servings),
        expiration_warning_days=_env_int("EXPIRATION_WARNING_DAYS", defaults.expiration_warning_days),
        priority_horizon_days=max(1, _env_int("PRIORITY_HORIZON_DAYS", defaults.priority_horizon_days)),
        coverage_weight=coverage,
        priority_weight=priority,
        fuzzy_match_threshold=_env_float("FUZZY_MATCH_THRESHOLD", defaults.fuzzy_match_threshold),
        min_history_movements=_env_int("MIN_HISTORY_MOVEMENTS", defaults.min_history_movements),
        default_period_days=_env_int("DEFAULT_PERIOD_DAYS", defaults.default_period_days),
        user_allergens=_env_list("USER_ALLERGENS"),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
