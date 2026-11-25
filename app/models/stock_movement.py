from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from .food_lot import FoodLot

class MovementType(str, Enum):
    ENTRY = "entry"
    CONSUMPTION = "consumption"
    WASTE = "waste"

@dataclass
class StockMovement(ABC):
    """Classe mère abstraite des mouvements de stock."""
    lot: FoodLot
    quantity: float
    movement_date: datetime = field(default_factory=datetime.now)
    id: int | None = None
    movement_type: ClassVar[MovementType]
    _applied: bool = field(default=False, init=False, repr=False, compare=False)

    def __post_init__(self):
        if self.quantity <= 0:
            raise ValueError("La quantité du mouvement doit être strictement positive.")

    @abstractmethod
    def apply(self) -> None:
        """Applique le mouvement au lot concerné."""
        raise NotImplementedError

    def _decrease_lot(self):
        if self.quantity > self.lot.quantity:
            raise ValueError("La quantité demandée dépasse le stock disponible.")
        self.lot.quantity -= self.quantity

@dataclass
class StockEntry(StockMovement):
    movement_type: ClassVar[MovementType] = MovementType.ENTRY
    def apply(self):
        if self._applied:
            raise RuntimeError("Ce mouvement a déjà été appliqué.")
        self.lot.quantity += self.quantity
        self._applied = True

@dataclass
class StockConsumption(StockMovement):
    movement_type: ClassVar[MovementType] = MovementType.CONSUMPTION
    def apply(self):
        if self._applied:
            raise RuntimeError("Ce mouvement a déjà été appliqué.")
        self._decrease_lot()
        self._applied = True

@dataclass
class StockWaste(StockMovement):
    movement_type: ClassVar[MovementType] = MovementType.WASTE
    def apply(self):
        if self._applied:
            raise RuntimeError("Ce mouvement a déjà été appliqué.")
        self._decrease_lot()
        self._applied = True
