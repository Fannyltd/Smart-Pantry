"""Tests du matching d'ingrédients et du score Score(r) = 0.6 C(r) + 0.4 P(r)."""
from datetime import date, timedelta

import pytest

from app.config.settings import Settings
from app.models import FoodLot, FoodProduct, Recipe, RecipeIngredient
from app.services.expiration_service import ExpirationService
from app.services.recipe_service import (IngredientMatcher, RecipeRecommendationService,
                                         RecipeService)

TODAY = date.today()


class StubRecipeRepository:
    def __init__(self, recipes):
        self.recipes = recipes

    def list_recipes(self):
        return self.recipes


def lot(product, quantity, unit, days_left, expiration_type="DLC"):
    purchase = TODAY - timedelta(days=max(1, 1 - days_left))
    return FoodLot(product, quantity, unit, purchase, TODAY + timedelta(days=days_left),
                   expiration_type=expiration_type)


def recipe(name, *ingredients):
    r = Recipe(name, 2, "Cuire.", id=hash(name) % 10_000)
    for ingredient_name, quantity, unit in ingredients:
        r.add_ingredient(RecipeIngredient(None, quantity, unit, ingredient_name))
    return r


@pytest.fixture
def service():
    settings = Settings(database_url="sqlite://")
    recipes = StubRecipeRepository([])
    recipe_service = RecipeService(recipes, None, settings)
    return RecipeRecommendationService(recipe_service, ExpirationService(None, settings), settings), recipes


class TestMatcher:
    @pytest.mark.parametrize("a, b", [("Poulet", "Chicken"), ("Poulet", "chicken breast"),
                                      ("Tomates", "tomato"), ("Pommes de terre", "Potatoes"),
                                      ("Huile d'olive", "Olive Oil"), ("Oeufs", "Eggs"),
                                      ("Crème fraîche", "creme fraiche"), ("Fromage râpé", "fromage")])
    def test_matches(self, a, b):
        assert IngredientMatcher().matches(a, b)

    @pytest.mark.parametrize("a, b", [("Oeuf", "Boeuf"), ("Egg", "Eggplant"), ("Riz", "Lait"),
                                      ("Sel", "Sucre")])
    def test_does_not_match(self, a, b):
        assert not IngredientMatcher().matches(a, b)

    def test_allergen_detection(self):
        r = recipe("Crêpes", ("lait", 50, "cl"), ("farine", 200, "g"))
        assert IngredientMatcher().contains_allergen(r, ["milk"]) == ["milk"]
        assert IngredientMatcher().contains_allergen(r, ["arachide"]) == []


class TestScore:
    def test_quantities_are_taken_into_account(self, service):
        """300 g de fromage demandés, 50 g en stock : pas « réalisable » (MVP §3)."""
        reco, _ = service
        cheese = FoodProduct("Fromage", "Laitier", "g", id=1)
        lot(cheese, 50, "g", 30)
        match = reco.calculate_match_score(recipe("Gratin", ("fromage", 300, "g")), [cheese])
        assert match.coverage == pytest.approx(50 / 300)
        assert match.status != "Réalisable"
        assert match.missing[0].missing_quantity == pytest.approx(250)

    def test_unit_conversion(self, service):
        reco, _ = service
        rice = FoodProduct("Riz", "Féculents", "kg", id=1)
        lot(rice, 1, "kg", 100)
        match = reco.calculate_match_score(recipe("Riz", ("rice", 250, "g")), [rice])
        assert match.coverage == 1

    def test_expired_dlc_is_not_available_but_ddm_is(self, service):  # RM05, BR11
        reco, _ = service
        milk = FoodProduct("Lait", "Laitier", "ml", id=1)
        lot(milk, 1000, "ml", -2, "DLC")
        assert reco.calculate_match_score(recipe("R", ("lait", 100, "ml")), [milk]).coverage == 0
        yogurt = FoodProduct("Yaourt", "Laitier", "unité", id=2)
        lot(yogurt, 4, "unité", -2, "DDM")
        match = reco.calculate_match_score(recipe("G", ("yaourt", 1, "unité")), [yogurt])
        assert match.coverage == 1 and match.priority == 1

    def test_formula(self, service):
        reco, _ = service
        chicken = FoodProduct("Poulet", "Viandes", "g", id=1)
        lot(chicken, 500, "g", 0)  # urgence maximale
        match = reco.calculate_match_score(recipe("R", ("chicken", 500, "g"), ("basilic", None, "")),
                                           [chicken])
        assert match.coverage == pytest.approx(0.5)
        assert match.priority == pytest.approx(1)
        assert match.score == pytest.approx(0.6 * 0.5 + 0.4 * 1)

    def test_urgent_recipes_ranked_first(self, service):  # RM07 / BR12
        reco, repo = service
        chicken, rice = FoodProduct("Poulet", "V", "g", id=1), FoodProduct("Riz", "F", "g", id=2)
        lot(chicken, 500, "g", 1)
        lot(rice, 500, "g", 200)
        repo.recipes = [recipe("Riz nature", ("riz", 100, "g")), recipe("Poulet rôti", ("poulet", 400, "g"))]
        matches, _ = reco.recommend_recipes([chicken, rice], allergens=[])
        assert [m.recipe.name for m in matches] == ["Poulet rôti", "Riz nature"]

    def test_allergens_excluded(self, service):
        reco, repo = service
        egg = FoodProduct("Oeuf", "O", "unité", id=1)
        lot(egg, 6, "unité", 5)
        repo.recipes = [recipe("Omelette", ("egg", 3, "unité"))]
        matches, warnings = reco.recommend_recipes([egg], allergens=["oeuf"])
        assert matches == [] and any("allergène" in w for w in warnings)

    def test_message_when_nothing_found(self, service):
        reco, repo = service
        repo.recipes = [recipe("Omelette", ("egg", 3, "unité"))]
        matches, warnings = reco.recommend_recipes([], allergens=[])
        assert matches == [] and any("Aucune recette" in w for w in warnings)

    def test_servings_scale_quantities(self, service):
        reco, _ = service
        flour = FoodProduct("Farine", "E", "g", id=1)
        lot(flour, 200, "g", 100)
        r = recipe("Pain", ("farine", 200, "g"))  # 2 portions
        assert reco.calculate_match_score(r, [flour], servings=4).coverage == pytest.approx(0.5)
