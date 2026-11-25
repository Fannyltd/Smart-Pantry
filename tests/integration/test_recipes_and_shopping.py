"""Tests d'intégration recettes / TheMealDB / courses / analytics (T05 à T09 + démo MVP)."""
from datetime import timedelta

import pytest

from app.config.settings import Settings
from app.exceptions.domain_exceptions import InsufficientStockError, ValidationError
from app.services import build_services
from tests.conftest import TODAY, FakeMealDBClient, days


def stock(container):
    inv = container.inventory
    inv.add_product_with_lot("Poulet", "Viandes", 600, "g", TODAY, days(1))
    inv.add_product_with_lot("Tomate", "Légumes", 2, "unité", TODAY, days(2))
    inv.add_product_with_lot("Fromage", "Laitier", 50, "g", TODAY, days(10))
    inv.add_product_with_lot("Riz", "Féculents", 1, "kg", TODAY, days(300))


def test_t05_search_by_available_ingredient(container):
    stock(container)
    recipes, warnings = container.recipes.search_by_ingredient("Poulet")
    names = {r.name for r in recipes}
    assert {"Chicken Tomato Bake", "Poulet à la crème"} <= names
    assert warnings == []


def test_t06_recipe_details_are_cached(container, fake_client):
    recipe = container.recipes.get_or_fetch("1001")
    assert recipe.instructions and recipe.image_url and len(recipe.ingredients) == 3
    assert recipe.ingredients[0].required_quantity == 500 and recipe.ingredients[0].unit == "g"
    calls = len(fake_client.calls)
    assert container.recipes.get_or_fetch("1001").id == recipe.id
    assert len(fake_client.calls) == calls  # servi depuis le cache


def test_t07_api_results_compared_with_stock(empty_container, fake_client):
    stock(empty_container)
    matches, warnings = empty_container.recommendation.recommend_recipes(include_api=True, allergens=[])
    queried = [p["i"] for e, p in fake_client.calls if e == "filter.php"]
    assert queried[0] == "chicken"  # l'ingrédient le plus urgent d'abord (RM07)
    by_name = {m.recipe.name: m for m in matches}
    assert by_name["Chicken Tomato Bake"].coverage == pytest.approx((1 + 2 / 3 + 0) / 3)
    assert by_name["Cheesy Chicken"].missing  # 300 g de fromage demandés, 50 g en stock
    assert matches[0].recipe.name == "Chicken Tomato Bake"


def test_t08_missing_ingredients_identified_and_listed(empty_container):
    stock(empty_container)
    recipe = empty_container.recipes.get_or_fetch("1002")
    match = empty_container.recommendation.calculate_match_score(recipe)
    missing = {s.name: s.missing_quantity for s in match.missing}
    assert missing == {"Cheese": pytest.approx(250), "Milk": pytest.approx(200)}
    added = empty_container.shopping.generate_shopping_list(recipe)
    assert {(i.name, i.quantity, i.unit) for i in added} == {("Cheese", 250, "g"), ("Milk", 200, "ml")}
    # Re-générer complète l'article existant au lieu de créer un doublon
    empty_container.shopping.generate_shopping_list(recipe)
    assert len(empty_container.shopping.get_shopping_list().items) == 2


def test_t09_api_unavailable_gives_clear_message(settings):
    container = build_services(settings, database_url="sqlite://",
                               mealdb_client=FakeMealDBClient(fail=True))
    stock(container)
    matches, warnings = container.recommendation.recommend_recipes(include_api=True, allergens=[])
    assert any("indisponible" in w for w in warnings)
    assert matches  # les recettes locales restent proposées
    _, search_warnings = container.recipes.search("chicken")
    assert any("indisponible" in w for w in search_warnings)


def test_api_disabled(settings):
    container = build_services(Settings(database_url="sqlite://", api_enabled=False),
                               database_url="sqlite://")
    assert not container.recipes.api_available


def test_purchase_requires_confirmation(container):  # RM09 / BR14
    item = container.shopping.add_item("Beurre", 250, "g")
    with pytest.raises(ValidationError):
        container.shopping.confirm_purchase(item.id, days(20))
    container.shopping.mark_as_purchased(item.id)
    assert container.inventory.get_inventory() == []  # cocher ne modifie pas le stock
    lot = container.shopping.confirm_purchase(item.id, days(20), "Produits laitiers")
    assert lot.product.name == "Beurre" and lot.quantity == 250
    assert container.shopping.get_shopping_list().items == []


def test_shopping_list_shows_existing_stock(container):  # §2.4
    container.inventory.add_product_with_lot("Riz", "Féculents", 1, "kg", TODAY, days(300))
    item = container.shopping.add_item("riz", 500, "g")
    info = container.shopping.get_stock_info(item)
    assert info.in_stock_quantity == 1000 and info.already_covered


def test_manual_items_merge(container):
    container.shopping.add_item("Lait", 1, "l")
    container.shopping.add_item("lait", 50, "cl")
    items = container.shopping.get_shopping_list().items
    assert len(items) == 1 and items[0].quantity == pytest.approx(1.5)


def test_cooking_is_atomic(container):
    stock(container)
    recipe = container.recipes.get_or_fetch("1001")  # 3 tomates nécessaires, 2 en stock
    with pytest.raises(InsufficientStockError):
        container.cooking.cook_recipe(recipe)
    chicken = next(p for p in container.inventory.get_inventory() if p.name == "Poulet")
    assert chicken.lots[0].quantity == 600  # rien consommé
    report = container.cooking.cook_recipe(recipe, allow_partial=True)
    assert report.consumptions and any("Tomato" in s for s in report.skipped)


def test_demo_scenario(container):
    """Scénario minimum du MVP, de bout en bout."""
    stock(container)
    # 1. produits prioritaires identifiés
    priority = [a.product.name for a in container.expiration.get_priority_products()]
    assert priority[:2] == ["Poulet", "Tomate"]
    # 2. recette adaptée recommandée
    matches, _ = container.recommendation.recommend_recipes(include_api=True, allergens=[])
    best = matches[0]
    assert "Poulet" in best.urgent_products
    # 3. ingrédients manquants -> liste de courses
    container.shopping.generate_shopping_list(best.recipe)
    # 4. consommation validée -> stock actualisé
    before = container.analytics.generate_summary(TODAY, TODAY)
    container.cooking.cook_recipe(best.recipe, allow_partial=True)
    after = container.analytics.generate_summary(TODAY, TODAY)
    chicken = next(p for p in container.inventory.get_inventory() if p.name == "Poulet")
    assert container.inventory.get_total_quantity(chicken)[0] < 600
    # 5. indicateurs recalculés
    assert after["consumption"] != before["consumption"]


def test_analytics_period_and_history(container):  # BR15, BR16, BR17
    inv = container.inventory
    lot = inv.add_product_with_lot("Pain", "Épicerie", 4, "unité", TODAY, days(2))
    inv.consume_food(lot.id, 1)
    inv.consume_food(lot.id, 1)
    inv.discard_food(lot.id, 2)
    other = inv.add_product_with_lot("Riz", "Féculents", 1, "kg", TODAY, days(200))
    inv.consume_food(other.id, 0.2)
    analytics = container.analytics
    assert analytics.calculate_consumption(TODAY, TODAY) == {"unité": 2, "g": 200}
    assert analytics.calculate_waste(TODAY, TODAY) == {"unité": 2}
    stats = {s.product_name: s for s in analytics.waste_by_product(TODAY, TODAY)}
    assert stats["Pain"].waste_rate == pytest.approx(0.5)
    assert stats["Riz"].waste_rate is None          # historique insuffisant
    assert analytics.calculate_waste_rate(TODAY, TODAY) == pytest.approx(0.5)
    yesterday = TODAY - timedelta(days=1)
    assert analytics.calculate_consumption(yesterday, yesterday) == {}
    with pytest.raises(ValidationError):
        analytics.calculate_waste_rate(TODAY, yesterday)
