"""Tests d'intégration : services + repositories + SQLite (T01 à T04)."""
from datetime import timedelta

import pytest

from app.exceptions.domain_exceptions import (DuplicateError, InsufficientStockError,
                                              UnitConversionError, ValidationError)
from tests.conftest import TODAY, days


def test_t01_add_product_appears_in_inventory(container):
    container.inventory.add_product_with_lot("Tomate", "Légumes", 6, "unité", TODAY, days(5))
    products = container.inventory.get_inventory()
    assert [p.name for p in products] == ["Tomate"]
    lot = products[0].lots[0]
    assert lot.id is not None and lot.quantity == 6
    assert [m.movement_type.value for m in lot.movements] == ["entry"]  # BR06


def test_several_lots_same_product(container):  # RM02 / RM03
    inv = container.inventory
    inv.add_product_with_lot("Lait", "Laitier", 1, "l", TODAY, days(3))
    inv.add_product_with_lot("lait", "Laitier", 50, "cl", TODAY, days(10))
    product = inv.get_inventory()[0]
    assert len(product.lots) == 2
    assert inv.get_total_quantity(product)[0] == pytest.approx(1.5)  # BR07 : 1 l + 50 cl


def test_incompatible_lot_unit_refused(container):
    product = container.inventory.create_product("Farine", "Épicerie", "g")
    with pytest.raises(UnitConversionError):
        container.inventory.add_food_lot(product, 1, "l", TODAY, days(30))


def test_duplicate_product_refused(container):
    container.inventory.create_product("Riz", "Féculents", "g")
    with pytest.raises(DuplicateError):
        container.inventory.create_product(" riz ", "Féculents", "g")


@pytest.mark.parametrize("kwargs", [
    {"quantity": 0}, {"quantity": -2}, {"purchase_date": TODAY + timedelta(days=1)},
    {"expiration_date": TODAY - timedelta(days=5)}, {"expiration_type": "XYZ"}, {"name": "  "},
])
def test_invalid_input_rejected(container, kwargs):
    data = dict(name="Pomme", category="Fruits", quantity=3, unit="unité", purchase_date=TODAY,
                expiration_date=days(5), expiration_type="DLC")
    data.update(kwargs)
    with pytest.raises(ValidationError):
        container.inventory.add_product_with_lot(**data)


def test_t02_update_quantity_is_saved_and_historised(container):
    lot = container.inventory.add_product_with_lot("Riz", "Féculents", 1000, "g", TODAY, days(100))
    container.inventory.update_lot(lot.id, quantity=600)
    reloaded = container.inventory.get_lot(lot.id)
    assert reloaded.quantity == 600
    assert [m.movement_type.value for m in reloaded.movements] == ["entry", "consumption"]
    container.inventory.update_lot(lot.id, quantity=700)
    assert container.inventory.get_lot(lot.id).quantity == 700


def test_t03_delete_product(container):
    lot = container.inventory.add_product_with_lot("Riz", "Féculents", 1, "kg", TODAY, days(100))
    container.inventory.delete_product(lot.product.id)
    assert container.inventory.get_inventory() == []


def test_consumption_cannot_exceed_stock(container):  # RM04 / BR05
    lot = container.inventory.add_product_with_lot("Oeuf", "Œufs", 6, "unité", TODAY, days(10))
    with pytest.raises(InsufficientStockError):
        container.inventory.consume_food(lot.id, 7)
    assert container.inventory.get_lot(lot.id).quantity == 6


def test_fefo_consumption_across_lots(container):
    inv = container.inventory
    late = inv.add_product_with_lot("Lait", "Laitier", 1, "l", TODAY, days(10))
    soon = inv.add_product_with_lot("Lait", "Laitier", 50, "cl", TODAY, days(2))
    inv.consume_product(soon.product.id, 800, "ml")
    assert inv.get_lot(soon.id).quantity == pytest.approx(0)
    assert inv.get_lot(late.id).quantity == pytest.approx(0.7)


def test_t04_expiring_product_flagged(container):
    container.inventory.add_product_with_lot("Poulet", "Viandes", 500, "g", TODAY, days(1))
    container.inventory.add_product_with_lot("Riz", "Féculents", 1, "kg", TODAY, days(200))
    alerts = container.expiration.get_alerts()
    assert [(a.product.name, a.color) for a in alerts] == [("Poulet", "orange"), ("Riz", "green")]


def test_expired_and_discard(container):
    lot = container.inventory.add_product_with_lot("Lait", "Laitier", 1, "l", TODAY - timedelta(days=5),
                                                   TODAY - timedelta(days=1))
    expired = container.expiration.get_expired_lots()
    assert expired[0].color == "red" and "ne pas consommer" in expired[0].message
    wastes = container.inventory.discard_expired_lots()
    assert len(wastes) == 1 and container.inventory.get_lot(lot.id).quantity == 0
