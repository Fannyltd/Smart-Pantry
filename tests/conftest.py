"""Fixtures partagées : base SQLite en mémoire et faux client TheMealDB."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import Settings  # noqa: E402
from app.exceptions.domain_exceptions import ExternalAPIError  # noqa: E402
from app.models import FoodLot, FoodProduct  # noqa: E402
from app.services import build_services  # noqa: E402
from app.services.recipe_service import TheMealDBClient  # noqa: E402

TODAY = date.today()


def meal(meal_id: str, name: str, ingredients: list[tuple[str, str]], category: str = "Chicken") -> dict:
    payload = {"idMeal": meal_id, "strMeal": name, "strCategory": category,
               "strInstructions": f"Cook {name}.", "strMealThumb": f"https://img/{meal_id}.jpg"}
    for index, (ingredient, measure) in enumerate(ingredients, start=1):
        payload[f"strIngredient{index}"] = ingredient
        payload[f"strMeasure{index}"] = measure
    for index in range(len(ingredients) + 1, 21):
        payload[f"strIngredient{index}"] = ""
        payload[f"strMeasure{index}"] = ""
    return payload


MEALS = {
    "1001": meal("1001", "Chicken Tomato Bake", [("Chicken", "500g"), ("Tomato", "3"), ("Onion", "1")]),
    "1002": meal("1002", "Cheesy Chicken", [("Chicken Breast", "2"), ("Cheese", "300g"), ("Milk", "200ml")]),
    "1003": meal("1003", "Rice Pudding", [("Rice", "100g"), ("Milk", "1 litre"), ("Sugar", "50g")],
                 category="Dessert"),
}


class FakeMealDBClient(TheMealDBClient):
    """Simule TheMealDB sans réseau ; ``fail=True`` simule une panne (T09)."""

    def __init__(self, fail: bool = False):
        super().__init__("https://fake.local/api/", default_servings=4)
        self.fail = fail
        self.calls: list[tuple[str, dict | None]] = []

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        self.calls.append((endpoint, params))
        if self.fail:
            raise ExternalAPIError("TheMealDB est momentanément indisponible.")
        if endpoint == "filter.php" and "i" in params:
            wanted = params["i"].replace("_", " ")
            found = [{"idMeal": m["idMeal"], "strMeal": m["strMeal"]} for m in MEALS.values()
                     if any((m.get(f"strIngredient{i}") or "").lower() == wanted for i in range(1, 21))]
            return {"meals": found or None}
        if endpoint == "filter.php" and "c" in params:
            return {"meals": [{"idMeal": m["idMeal"]} for m in MEALS.values()
                              if m["strCategory"] == params["c"]] or None}
        if endpoint == "lookup.php":
            found = MEALS.get(params["i"])
            return {"meals": [found] if found else None}
        if endpoint == "search.php":
            return {"meals": [m for m in MEALS.values() if params["s"].lower() in m["strMeal"].lower()] or None}
        if endpoint == "categories.php":
            return {"categories": [{"strCategory": "Chicken"}, {"strCategory": "Dessert"}]}
        if endpoint == "random.php":
            return {"meals": [MEALS["1001"]]}
        return {"meals": None}


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(database_url="sqlite://", data_dir=ROOT / "data")


@pytest.fixture
def fake_client() -> FakeMealDBClient:
    return FakeMealDBClient()


@pytest.fixture
def container(settings, fake_client):
    """Application complète sur une base vierge (catégories + recettes locales chargées)."""
    return build_services(settings, database_url="sqlite://", mealdb_client=fake_client)


@pytest.fixture
def empty_container(settings, fake_client):
    """Application sans données de référence (aucune recette locale)."""
    return build_services(settings, database_url="sqlite://", mealdb_client=fake_client, seed=False)


@pytest.fixture
def product() -> FoodProduct:
    return FoodProduct("Tomate", "Légumes", "unité", id=1)


@pytest.fixture
def make_lot(product):
    def _make(quantity=5.0, days_left=5, expiration_type="DLC", unit="unité", purchased_days_ago=None,
              target=None):
        if purchased_days_ago is None:
            purchased_days_ago = max(1, 1 - days_left)
        return FoodLot(target or product, quantity, unit, TODAY - timedelta(days=purchased_days_ago),
                       TODAY + timedelta(days=days_left), id=None, expiration_type=expiration_type)
    return _make


def days(n: int) -> date:
    return TODAY + timedelta(days=n)
