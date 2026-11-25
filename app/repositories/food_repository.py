"""Persistance des produits, lots, catégories et listes de courses."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.database.models import (CategoryORM, FoodLotORM, FoodProductORM, ShoppingItemORM,
                                 ShoppingListORM, StockMovementORM)
from app.exceptions.domain_exceptions import DuplicateError, NotFoundError
from app.models import FoodLot, FoodProduct, ShoppingItem, ShoppingList
from app.models.stock_movement import MovementType, StockConsumption, StockEntry, StockWaste
from app.repositories.base_repository import BaseRepository
from app.utils.validators import normalize_name

MOVEMENT_CLASSES = {
    MovementType.ENTRY.value: StockEntry,
    MovementType.CONSUMPTION.value: StockConsumption,
    MovementType.WASTE.value: StockWaste,
}


def lot_to_domain(product: FoodProduct, lot_orm: FoodLotORM, with_movements: bool = True) -> FoodLot:
    """Reconstruit un FoodLot.

    Le constructeur du domaine exige une quantité > 0 (BR02) : on instancie avec
    la quantité initiale puis on restaure la quantité courante (éventuellement 0).
    """
    lot = FoodLot(
        product=product,
        quantity=lot_orm.initial_quantity,
        unit=lot_orm.unit,
        purchase_date=lot_orm.purchase_date,
        expiration_date=lot_orm.expiration_date,
        id=lot_orm.id,
        expiration_type=lot_orm.expiration_type,
    )
    lot.quantity = lot_orm.quantity
    if with_movements:
        for movement_orm in lot_orm.movements:
            movement_class = MOVEMENT_CLASSES[movement_orm.movement_type]
            movement = movement_class(lot, movement_orm.quantity, movement_orm.movement_date,
                                      id=movement_orm.id)
            movement._applied = True  # déjà appliqué lors de son enregistrement
            lot.movements.append(movement)
    return lot


def product_to_domain(product_orm: FoodProductORM, with_movements: bool = True) -> FoodProduct:
    product = FoodProduct(product_orm.name, product_orm.category, product_orm.base_unit,
                          id=product_orm.id)
    for lot_orm in product_orm.lots:
        lot_to_domain(product, lot_orm, with_movements)
    return product


class FoodRepository(BaseRepository):
    entity_label = "Produit"

    def _query(self, with_movements: bool = True):
        loader = selectinload(FoodProductORM.lots)
        if with_movements:
            loader = loader.selectinload(FoodLotORM.movements)
        return select(FoodProductORM).options(loader)

    # --- Lecture ------------------------------------------------------------
    def list_products(self, with_movements: bool = True) -> list[FoodProduct]:
        with self._session() as session:
            rows = session.scalars(self._query(with_movements).order_by(FoodProductORM.name))
            return [product_to_domain(row, with_movements) for row in rows]

    def get_product(self, product_id: int) -> FoodProduct:
        with self._session() as session:
            row = session.scalars(self._query().where(FoodProductORM.id == product_id)).first()
            if row is None:
                raise NotFoundError("Produit", product_id)
            return product_to_domain(row)

    def find_by_name(self, name: str) -> FoodProduct | None:
        with self._session() as session:
            row = session.scalars(
                self._query().where(FoodProductORM.normalized_name == normalize_name(name))).first()
            return product_to_domain(row) if row else None

    def get_lot(self, lot_id: int) -> FoodLot:
        """Renvoie le lot rattaché à son produit complet (avec les autres lots)."""
        with self._session() as session:
            lot_orm = session.get(FoodLotORM, lot_id)
            if lot_orm is None:
                raise NotFoundError("Lot", lot_id)
            product_id = lot_orm.product_id
        product = self.get_product(product_id)
        return next(lot for lot in product.lots if lot.id == lot_id)

    # --- Écriture -----------------------------------------------------------
    def save_product(self, product: FoodProduct) -> FoodProduct:
        """Insère ou met à jour les informations d'un produit (pas ses lots)."""
        try:
            with self._session() as session:
                if product.id is None:
                    row = FoodProductORM()
                    session.add(row)
                else:
                    row = self._get_or_raise(session, FoodProductORM, product.id)
                row.name, row.category, row.base_unit = product.name, product.category, product.base_unit
                row.normalized_name = normalize_name(product.name)
                session.flush()
                product.id = row.id
        except IntegrityError:
            raise DuplicateError(f"Un produit nommé « {product.name} » existe déjà.") from None
        return product

    def delete_product(self, product_id: int) -> None:
        with self._session() as session:
            session.delete(self._get_or_raise(session, FoodProductORM, product_id))

    def add_lot(self, lot: FoodLot) -> FoodLot:
        """Insère un lot ; ses mouvements initiaux éventuels sont aussi persistés."""
        if lot.product.id is None:
            raise ValueError("Le produit doit être enregistré avant ses lots.")
        with self._session() as session:
            row = FoodLotORM(
                product_id=lot.product.id, quantity=lot.quantity,
                initial_quantity=max(lot.quantity, 1e-9), unit=lot.unit,
                purchase_date=lot.purchase_date, expiration_date=lot.expiration_date,
                expiration_type=lot.expiration_type)
            for movement in lot.movements:
                row.movements.append(StockMovementORM(
                    movement_type=movement.movement_type.value, quantity=movement.quantity,
                    movement_date=movement.movement_date))
            session.add(row)
            session.flush()
            lot.id = row.id
            for movement, movement_row in zip(lot.movements, row.movements):
                movement.id = movement_row.id
        return lot

    def update_lot(self, lot: FoodLot) -> None:
        """Met à jour les métadonnées d'un lot (dates, type, quantité)."""
        with self._session() as session:
            row = self._get_or_raise(session, FoodLotORM, lot.id, "Lot")
            row.quantity = lot.quantity
            row.expiration_date = lot.expiration_date
            row.expiration_type = lot.expiration_type
            row.unit = lot.unit

    def delete_lot(self, lot_id: int) -> None:
        with self._session() as session:
            session.delete(self._get_or_raise(session, FoodLotORM, lot_id, "Lot"))

    # --- Catégories (classe Category du diagramme UML) -----------------------
    def list_categories(self) -> list[str]:
        with self._session() as session:
            names = set(session.scalars(select(CategoryORM.name)))
            names.update(session.scalars(select(FoodProductORM.category)))
            return sorted(names, key=str.casefold)

    def add_category(self, name: str) -> None:
        with self._session() as session:
            exists = session.scalars(select(CategoryORM).where(CategoryORM.name == name)).first()
            if not exists:
                session.add(CategoryORM(name=name))


class ShoppingListRepository(BaseRepository):
    entity_label = "Liste de courses"

    @staticmethod
    def _to_domain(row: ShoppingListORM, products: dict[int, FoodProduct]) -> ShoppingList:
        shopping_list = ShoppingList(id=row.id, name=row.name)
        for item_row in row.items:
            shopping_list.items.append(ShoppingItem(
                name=item_row.name, quantity=item_row.quantity, unit=item_row.unit,
                is_purchased=item_row.is_purchased,
                product=products.get(item_row.product_id) if item_row.product_id else None,
                id=item_row.id))
        return shopping_list

    def get_or_create_default(self, products: dict[int, FoodProduct] | None = None) -> ShoppingList:
        with self._session() as session:
            row = session.scalars(select(ShoppingListORM).options(
                selectinload(ShoppingListORM.items)).order_by(ShoppingListORM.id)).first()
            if row is None:
                row = ShoppingListORM(name="Ma liste de courses")
                session.add(row)
                session.flush()
            return self._to_domain(row, products or {})

    def add_item(self, list_id: int, item: ShoppingItem) -> ShoppingItem:
        with self._session() as session:
            self._get_or_raise(session, ShoppingListORM, list_id)
            row = ShoppingItemORM(shopping_list_id=list_id, name=item.name, quantity=item.quantity,
                                  unit=item.unit, is_purchased=item.is_purchased,
                                  product_id=item.product.id if item.product else None)
            session.add(row)
            session.flush()
            item.id = row.id
        return item

    def update_item(self, item: ShoppingItem) -> None:
        with self._session() as session:
            row = self._get_or_raise(session, ShoppingItemORM, item.id, "Article")
            row.name, row.quantity, row.unit = item.name, item.quantity, item.unit
            row.is_purchased = item.is_purchased
            row.product_id = item.product.id if item.product else None

    def delete_item(self, item_id: int) -> None:
        with self._session() as session:
            session.delete(self._get_or_raise(session, ShoppingItemORM, item_id, "Article"))
