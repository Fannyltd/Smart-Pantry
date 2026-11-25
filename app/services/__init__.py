"""Assemblage des services (injection de dépendances manuelle).

``build_services`` crée toute la chaîne base -> repositories -> services.
``get_services`` renvoie une instance unique par processus (utilisée par
l'interface Streamlit).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.config.settings import Settings, get_settings
from app.database.connection import create_db_engine, create_session_factory, init_db
from app.repositories.food_repository import FoodRepository, ShoppingListRepository
from app.repositories.movement_repository import MovementRepository
from app.repositories.recipe_repository import RecipeRepository
from app.services.analytics_service import AnalyticsService
from app.services.cooking_service import CookingService
from app.services.expiration_service import ExpirationService
from app.services.inventory_service import InventoryService
from app.services.recipe_service import (IngredientMatcher, RecipeRecommendationService,
                                         RecipeService, TheMealDBClient)
from app.services.shopping_service import ShoppingListService


@dataclass
class ServiceContainer:
    settings: Settings
    inventory: InventoryService
    expiration: ExpirationService
    recipes: RecipeService
    recommendation: RecipeRecommendationService
    shopping: ShoppingListService
    cooking: CookingService
    analytics: AnalyticsService


def build_services(settings: Settings | None = None, database_url: str | None = None,
                   mealdb_client: TheMealDBClient | None = None, seed: bool = True,
                   use_api: bool = True) -> ServiceContainer:
    settings = settings or get_settings()
    engine = create_db_engine(database_url or settings.database_url)
    session_factory = create_session_factory(engine)
    init_db(engine, session_factory, settings.data_dir, seed=seed)

    food_repo = FoodRepository(session_factory)
    movement_repo = MovementRepository(session_factory)
    recipe_repo = RecipeRepository(session_factory)
    shopping_repo = ShoppingListRepository(session_factory)

    if mealdb_client is None and use_api:
        mealdb_client = TheMealDBClient(settings.mealdb_url, settings.api_timeout,
                                        default_servings=settings.default_servings)
    matcher = IngredientMatcher(settings.fuzzy_match_threshold)

    inventory = InventoryService(food_repo, movement_repo, settings)
    expiration = ExpirationService(food_repo, settings)
    recipes = RecipeService(recipe_repo, mealdb_client if use_api else None, settings, matcher)
    recommendation = RecipeRecommendationService(recipes, expiration, settings, matcher)
    shopping = ShoppingListService(shopping_repo, inventory, recommendation, settings)
    cooking = CookingService(recipes, recommendation, inventory)
    analytics = AnalyticsService(food_repo, movement_repo, expiration, settings)
    return ServiceContainer(settings, inventory, expiration, recipes, recommendation, shopping,
                            cooking, analytics)


@lru_cache(maxsize=1)
def get_services() -> ServiceContainer:
    return build_services()
