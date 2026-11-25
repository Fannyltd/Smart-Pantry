"""Tests unitaires des modèles du domaine (RM01-RM05, BR01-BR06, BR08-BR11)."""
from datetime import date, timedelta

import pytest

from app.models import (FoodLot, FoodProduct, Recipe, RecipeIngredient,
                        ShoppingItem, ShoppingList, StockConsumption, StockEntry, StockWaste)
from app.models.stock_movement import MovementType

TODAY = date.today()


class TestFoodProduct:
    def test_name_is_required(self):  # BR01
        with pytest.raises(ValueError):
            FoodProduct("   ", "Légumes", "g")

    def test_fields_are_stripped(self):
        assert FoodProduct("  Riz ", " Féculents ", " g ").name == "Riz"

    def test_several_lots_and_total_same_unit_only(self, make_lot):  # RM02, BR07
        product = FoodProduct("Lait", "Laitier", "ml")
        make_lot(500, unit="ml", target=product)
        make_lot(250, unit="ml", target=product)
        make_lot(1, unit="l", target=product)  # unité différente : non additionnée par le modèle
        assert len(product.lots) == 3
        assert product.get_total_quantity() == 750

    def test_available_lots_excludes_empty(self, make_lot, product):
        lot = make_lot(2)
        lot.consume(2)
        assert product.get_available_lots() == []


class TestFoodLot:
    def test_initial_quantity_must_be_positive(self, product):  # BR02
        with pytest.raises(ValueError):
            FoodLot(product, 0, "unité", TODAY, TODAY)

    def test_purchase_date_not_in_future(self, product):  # BR03
        with pytest.raises(ValueError):
            FoodLot(product, 1, "unité", TODAY + timedelta(days=1), TODAY + timedelta(days=5))

    def test_expiration_after_purchase(self, product):  # BR04
        with pytest.raises(ValueError):
            FoodLot(product, 1, "unité", TODAY, TODAY - timedelta(days=1))

    def test_expiration_type_dlc_or_ddm(self, product):  # BR11
        assert FoodLot(product, 1, "u", TODAY, TODAY, expiration_type="ddm").expiration_type == "DDM"
        with pytest.raises(ValueError):
            FoodLot(product, 1, "u", TODAY, TODAY, expiration_type="XYZ")

    def test_consumption_cannot_exceed_stock(self, make_lot):  # RM04 / BR05
        lot = make_lot(3)
        with pytest.raises(ValueError):
            lot.consume(4)
        assert lot.quantity == 3

    def test_movements_are_historised(self, make_lot):  # BR06
        lot = make_lot(5)
        lot.add_stock(2)
        lot.consume(3)
        lot.discard(1)
        assert lot.quantity == 3
        assert [m.movement_type for m in lot.movements] == [
            MovementType.ENTRY, MovementType.CONSUMPTION, MovementType.WASTE]

    def test_quantity_never_negative(self, make_lot):  # RM01
        lot = make_lot(1)
        lot.discard(1)
        assert lot.quantity == 0
        with pytest.raises(ValueError):
            lot.discard(0.1)

    @pytest.mark.parametrize("days_left, expected", [(-1, "expired"), (0, "urgent"), (3, "urgent"),
                                                     (4, "safe")])
    def test_expiration_status(self, make_lot, days_left, expected):  # BR08, BR09
        assert make_lot(days_left=days_left).get_expiration_status(3) == expected


class TestStockMovement:
    def test_quantity_must_be_positive(self, make_lot):
        with pytest.raises(ValueError):
            StockConsumption(make_lot(), 0)

    def test_cannot_apply_twice(self, make_lot):
        lot = make_lot(5)
        movement = StockEntry(lot, 1)
        movement.apply()
        with pytest.raises(RuntimeError):
            movement.apply()

    def test_polymorphism(self, make_lot):
        lot = make_lot(5)
        for movement in (StockEntry(lot, 1), StockConsumption(lot, 2), StockWaste(lot, 1)):
            lot.apply_movement(movement)
        assert lot.quantity == 3

    def test_movement_must_target_lot(self, make_lot):
        lot_a, lot_b = make_lot(), make_lot()
        with pytest.raises(ValueError):
            lot_a.apply_movement(StockEntry(lot_b, 1))


class TestRecipe:
    def test_validation(self):
        with pytest.raises(ValueError):
            Recipe("", 2, "x")
        with pytest.raises(ValueError):
            Recipe("Soupe", 0, "x")
        with pytest.raises(ValueError):
            Recipe("Soupe", 2, "   ")

    def test_ingredients(self):
        recipe = Recipe("Soupe", 2, "Mixer.")
        ingredient = RecipeIngredient(None, 200, "g", "Carotte")
        recipe.add_ingredient(ingredient)
        assert recipe.get_ingredients() == [ingredient]
        with pytest.raises(TypeError):
            recipe.add_ingredient("carotte")

    def test_ingredient_needs_name_or_product(self):
        with pytest.raises(ValueError):
            RecipeIngredient(None, 1, "g")
        assert RecipeIngredient(None, None, "", "  Sel ").normalized_name == "sel"


class TestShopping:
    def test_mark_as_purchased_does_not_touch_stock(self, make_lot, product):  # RM09
        lot = make_lot(2)
        item = ShoppingItem("Tomate", 3, "unité", product=product)
        item.mark_as_purchased()
        assert item.is_purchased and lot.quantity == 2

    def test_missing_items(self):
        shopping_list = ShoppingList()
        a, b = ShoppingItem("A", 1, "u"), ShoppingItem("B", 1, "u")
        shopping_list.add_item(a)
        shopping_list.add_item(b)
        b.mark_as_purchased()
        assert shopping_list.get_missing_items() == [a]

    def test_add_missing_recipe_ingredients_skips_zero(self):
        shopping_list = ShoppingList()
        added = shopping_list.add_missing_recipe_ingredients([
            (RecipeIngredient(None, 100, "g", "Farine"), 50),
            (RecipeIngredient(None, 100, "g", "Sucre"), 0)])
        assert [i.name for i in added] == ["Farine"]
