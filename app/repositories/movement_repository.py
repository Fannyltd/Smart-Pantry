"""Historique des mouvements de stock (BR06, BR15)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from sqlalchemy import select

from app.database.models import FoodLotORM, FoodProductORM, StockMovementORM
from app.models.stock_movement import StockMovement
from app.repositories.base_repository import BaseRepository


@dataclass(frozen=True)
class MovementRecord:
    """Vue à plat d'un mouvement, destinée à l'historique et aux analyses."""
    id: int
    movement_type: str
    quantity: float
    unit: str
    movement_date: datetime
    lot_id: int
    product_id: int
    product_name: str
    category: str
    base_unit: str


class MovementRepository(BaseRepository):
    entity_label = "Mouvement"

    def record(self, movement: StockMovement) -> StockMovement:
        """Enregistre un mouvement *déjà appliqué* et la nouvelle quantité du lot.

        Les deux écritures sont faites dans la même transaction : le stock et
        son historique ne peuvent pas diverger.
        """
        lot = movement.lot
        with self._session() as session:
            lot_row = self._get_or_raise(session, FoodLotORM, lot.id, "Lot")
            lot_row.quantity = lot.quantity
            row = StockMovementORM(lot_id=lot.id, movement_type=movement.movement_type.value,
                                   quantity=movement.quantity, movement_date=movement.movement_date)
            session.add(row)
            session.flush()
            movement.id = row.id
        return movement

    def record_many(self, movements: list[StockMovement]) -> None:
        with self._session() as session:
            for movement in movements:
                lot_row = self._get_or_raise(session, FoodLotORM, movement.lot.id, "Lot")
                lot_row.quantity = movement.lot.quantity
                row = StockMovementORM(lot_id=movement.lot.id,
                                       movement_type=movement.movement_type.value,
                                       quantity=movement.quantity,
                                       movement_date=movement.movement_date)
                session.add(row)
                session.flush()
                movement.id = row.id

    def list_records(self, start: date | None = None, end: date | None = None,
                     movement_types: list[str] | None = None,
                     product_id: int | None = None) -> list[MovementRecord]:
        query = (select(StockMovementORM, FoodLotORM, FoodProductORM)
                 .join(FoodLotORM, StockMovementORM.lot_id == FoodLotORM.id)
                 .join(FoodProductORM, FoodLotORM.product_id == FoodProductORM.id)
                 .order_by(StockMovementORM.movement_date.desc()))
        if start:
            query = query.where(StockMovementORM.movement_date >= datetime.combine(start, time.min))
        if end:
            query = query.where(StockMovementORM.movement_date <= datetime.combine(end, time.max))
        if movement_types:
            query = query.where(StockMovementORM.movement_type.in_(movement_types))
        if product_id:
            query = query.where(FoodProductORM.id == product_id)
        with self._session() as session:
            return [MovementRecord(
                id=movement.id, movement_type=movement.movement_type, quantity=movement.quantity,
                unit=lot.unit, movement_date=movement.movement_date, lot_id=lot.id,
                product_id=product.id, product_name=product.name, category=product.category,
                base_unit=product.base_unit)
                for movement, lot, product in session.execute(query)]
