"""F1 — Gestion des stocks (InventoryService du diagramme de conception)."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from app.config.settings import Settings
from app.exceptions.domain_exceptions import (DuplicateError, InsufficientStockError,
                                              UnitConversionError, ValidationError)
from app.models import FoodLot, FoodProduct, StockConsumption, StockEntry, StockMovement, StockWaste
from app.repositories.food_repository import FoodRepository
from app.repositories.movement_repository import MovementRepository
from app.utils import unit_converter as units
from app.utils import validators


@dataclass
class ProductStock:
    """Synthèse d'un produit pour l'affichage de l'inventaire."""
    product: FoodProduct
    total_quantity: float          # dans l'unité de base du produit, unités compatibles converties
    unit: str
    lots_count: int
    next_expiration: date | None
    incompatible_lots: int         # lots dont l'unité n'est pas convertible (BR07)


def is_usable(lot: FoodLot, reference_date: date | None = None) -> bool:
    """Un lot est utilisable s'il reste du stock et s'il n'a pas dépassé une DLC.

    Une DDM dépassée n'interdit pas la consommation (BR11) : le produit reste
    utilisable mais il est signalé.
    """
    if lot.quantity <= 0:
        return False
    return not (lot.expiration_type == "DLC" and lot.is_expired(reference_date))


class InventoryService:
    def __init__(self, food_repository: FoodRepository, movement_repository: MovementRepository,
                 settings: Settings):
        self.food_repository = food_repository
        self.movement_repository = movement_repository
        self.settings = settings

    # ------------------------------------------------------------------ lecture
    def get_inventory(self) -> list[FoodProduct]:
        return self.food_repository.list_products()

    def get_product(self, product_id: int) -> FoodProduct:
        return self.food_repository.get_product(product_id)

    def get_lot(self, lot_id: int) -> FoodLot:
        return self.food_repository.get_lot(lot_id)

    def get_categories(self) -> list[str]:
        return self.food_repository.list_categories()

    def get_total_quantity(self, product: FoodProduct, usable_only: bool = False,
                           reference_date: date | None = None) -> tuple[float, int]:
        """Quantité totale en unité de base (BR07).

        Renvoie (total, nb_lots_non_convertibles). Les lots d'unités
        incompatibles ne sont pas additionnés.
        """
        total, incompatible = 0.0, 0
        for lot in product.get_available_lots():
            if usable_only and not is_usable(lot, reference_date):
                continue
            converted = units.try_convert(lot.quantity, lot.unit, product.base_unit)
            if converted is None:
                incompatible += 1
            else:
                total += converted
        return total, incompatible

    def get_stock_summary(self, include_empty: bool = False) -> list[ProductStock]:
        summary = []
        for product in self.get_inventory():
            available = product.get_available_lots()
            if not available and not include_empty:
                continue
            total, incompatible = self.get_total_quantity(product)
            summary.append(ProductStock(
                product=product, total_quantity=total, unit=product.base_unit,
                lots_count=len(available),
                next_expiration=min((lot.expiration_date for lot in available), default=None),
                incompatible_lots=incompatible))
        return summary

    # ------------------------------------------------------------ produits
    def create_product(self, name: str, category: str, base_unit: str) -> FoodProduct:
        name = validators.validate_non_empty(name, "nom du produit")          # BR01
        category = validators.validate_non_empty(category, "catégorie")
        base_unit = units.normalize_unit(validators.validate_non_empty(base_unit, "unité"))
        if self.food_repository.find_by_name(name):
            raise DuplicateError(f"Le produit « {name} » existe déjà : ajoutez-lui un nouveau lot.")
        try:
            product = FoodProduct(name, category, base_unit)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        self.food_repository.add_category(category)
        return self.food_repository.save_product(product)

    def find_or_create_product(self, name: str, category: str, base_unit: str) -> FoodProduct:
        existing = self.food_repository.find_by_name(name)
        return existing or self.create_product(name, category, base_unit)

    def update_product(self, product_id: int, name: str, category: str, base_unit: str) -> FoodProduct:
        product = self.get_product(product_id)
        name = validators.validate_non_empty(name, "nom du produit")
        category = validators.validate_non_empty(category, "catégorie")
        base_unit = units.normalize_unit(validators.validate_non_empty(base_unit, "unité"))
        other = self.food_repository.find_by_name(name)
        if other and other.id != product_id:
            raise DuplicateError(f"Un autre produit s'appelle déjà « {name} ».")
        incompatible = [lot for lot in product.lots if not units.are_compatible(lot.unit, base_unit)]
        if incompatible:
            raise UnitConversionError(
                f"L'unité « {base_unit} » est incompatible avec {len(incompatible)} lot(s) existant(s).")
        product.name, product.category, product.base_unit = name, category, base_unit
        self.food_repository.add_category(category)
        return self.food_repository.save_product(product)

    def delete_product(self, product_id: int) -> None:
        self.food_repository.delete_product(product_id)

    # ------------------------------------------------------------ lots
    def add_food_lot(self, product: FoodProduct | int, quantity, unit: str, purchase_date: date,
                     expiration_date: date, expiration_type: str = "DLC") -> FoodLot:
        """Ajoute un lot et historise l'entrée initiale (BR02 à BR04, BR06)."""
        if isinstance(product, int):
            product = self.get_product(product)
        quantity = validators.validate_positive(quantity, "quantité initiale")
        unit = units.normalize_unit(validators.validate_non_empty(unit, "unité"))
        validators.validate_purchase_date(purchase_date)
        validators.validate_expiration_date(expiration_date, purchase_date)
        expiration_type = validators.validate_expiration_type(expiration_type)
        if not units.are_compatible(unit, product.base_unit):
            raise UnitConversionError(
                f"L'unité « {unit} » n'est pas compatible avec l'unité du produit "
                f"« {product.base_unit} » (BR07).")
        try:
            lot = FoodLot(product, quantity, unit, purchase_date, expiration_date,
                          expiration_type=expiration_type)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        # Entrée initiale : la quantité est déjà portée par le lot, on l'historise
        # sans la ré-appliquer.
        entry = StockEntry(lot, quantity, datetime.combine(purchase_date, datetime.now().time()))
        entry._applied = True
        lot.movements.append(entry)
        return self.food_repository.add_lot(lot)

    def add_product_with_lot(self, name: str, category: str, quantity, unit: str,
                             purchase_date: date, expiration_date: date,
                             expiration_type: str = "DLC") -> FoodLot:
        product = self.find_or_create_product(name, category, unit)
        return self.add_food_lot(product, quantity, unit, purchase_date, expiration_date,
                                 expiration_type)

    def update_lot(self, lot_id: int, quantity=None, expiration_date: date | None = None,
                   expiration_type: str | None = None, reduction_is_waste: bool = False) -> FoodLot:
        """Modifie un lot. Toute variation de quantité est historisée (BR06)."""
        lot = self.get_lot(lot_id)
        if expiration_date is not None:
            lot.expiration_date = validators.validate_expiration_date(expiration_date, lot.purchase_date)
        if expiration_type is not None:
            lot.expiration_type = validators.validate_expiration_type(expiration_type)
        self.food_repository.update_lot(lot)
        if quantity is not None:
            new_quantity = validators.validate_non_negative(quantity)  # RM01
            delta = new_quantity - lot.quantity
            if delta > 0:
                self._apply_and_record(lot.add_stock, delta)
            elif delta < 0:
                action = lot.discard if reduction_is_waste else lot.consume
                self._apply_and_record(action, -delta)
        return lot

    def delete_lot(self, lot_id: int) -> None:
        self.food_repository.delete_lot(lot_id)

    # ------------------------------------------------------------ mouvements
    def _apply_and_record(self, action, quantity: float) -> StockMovement:
        try:
            movement = action(quantity)
        except ValueError as exc:
            message = str(exc)
            if "dépasse" in message:
                raise InsufficientStockError(f"{message} (RM04)") from exc
            raise ValidationError(message) from exc
        return self.movement_repository.record(movement)

    def consume_food(self, lot: FoodLot | int, quantity) -> StockConsumption:
        lot = self.get_lot(lot) if isinstance(lot, int) else lot
        quantity = validators.validate_positive(quantity)
        return self._apply_and_record(lot.consume, quantity)

    def discard_food(self, lot: FoodLot | int, quantity=None) -> StockWaste:
        """Mise au rebut (gaspillage, BR15). Sans quantité : tout le lot."""
        lot = self.get_lot(lot) if isinstance(lot, int) else lot
        quantity = lot.quantity if quantity is None else validators.validate_positive(quantity)
        return self._apply_and_record(lot.discard, quantity)

    def discard_expired_lots(self, reference_date: date | None = None) -> list[StockWaste]:
        """Jette tous les lots dont la DLC est dépassée."""
        wastes = []
        for product in self.get_inventory():
            for lot in product.get_available_lots():
                if lot.expiration_type == "DLC" and lot.is_expired(reference_date):
                    wastes.append(self._apply_and_record(lot.discard, lot.quantity))
        return wastes

    def plan_consumption(self, products: list[FoodProduct], quantity: float, unit: str,
                         reference_date: date | None = None) -> list[tuple[FoodLot, float]]:
        """Répartit une consommation sur les lots selon FEFO (premier périmé, premier sorti).

        Ne modifie rien : lève InsufficientStockError si le stock utilisable est
        insuffisant ou si les unités ne sont pas convertibles.
        """
        unit = units.normalize_unit(unit)
        lots = sorted((lot for product in products for lot in product.get_available_lots()
                       if is_usable(lot, reference_date) and units.are_compatible(lot.unit, unit)),
                      key=lambda lot: (lot.expiration_date, lot.id or 0))
        remaining = quantity
        plan: list[tuple[FoodLot, float]] = []
        for lot in lots:
            if remaining <= 1e-9:
                break
            available = units.convert(lot.quantity, lot.unit, unit)
            taken = min(available, remaining)
            plan.append((lot, units.convert(taken, unit, lot.unit)))
            remaining -= taken
        if remaining > 1e-6:
            names = ", ".join(sorted({p.name for p in products})) or "produit"
            raise InsufficientStockError(
                f"Stock insuffisant pour {names} : il manque "
                f"{units.format_quantity(round(remaining, 2), unit)} (RM04).")
        return plan

    def consume_from_products(self, products: list[FoodProduct], quantity, unit: str,
                              reference_date: date | None = None) -> list[StockConsumption]:
        quantity = validators.validate_positive(quantity)
        plan = self.plan_consumption(products, quantity, unit, reference_date)
        movements = []
        for lot, lot_quantity in plan:
            lot_quantity = min(lot_quantity, lot.quantity)  # arrondis de conversion
            movements.append(lot.consume(lot_quantity))
        self.movement_repository.record_many(movements)
        return movements

    def consume_product(self, product_id: int, quantity, unit: str | None = None) -> list[StockConsumption]:
        product = self.get_product(product_id)
        return self.consume_from_products([product], quantity, unit or product.base_unit)

    # ------------------------------------------------------------ import
    def import_sample_inventory(self, csv_path: Path, today: date | None = None) -> int:
        """Charge un inventaire de démonstration (dates relatives à aujourd'hui)."""
        today = today or date.today()
        count = 0
        with Path(csv_path).open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                purchase = today - timedelta(days=int(row["days_since_purchase"]))
                expiration = today + timedelta(days=int(row["days_until_expiration"]))
                if expiration < purchase:
                    expiration = purchase
                self.add_product_with_lot(row["name"], row["category"], row["quantity"], row["unit"],
                                          purchase, expiration, row.get("expiration_type") or "DLC")
                count += 1
        return count
