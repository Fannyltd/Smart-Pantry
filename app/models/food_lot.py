from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING
from .stock_movement import StockMovement, StockEntry, StockConsumption, StockWaste
if TYPE_CHECKING:
    from .food_product import FoodProduct

@dataclass
class FoodLot:
    product: FoodProduct
    quantity: float
    unit: str
    purchase_date: date
    expiration_date: date
    id: int | None = None
    expiration_type: str = "DLC"
    movements: list[StockMovement] = field(default_factory=list, repr=False)

    def __post_init__(self):
        if self.quantity <= 0:
            raise ValueError("La quantité initiale doit être strictement positive.")
        self.unit = self.unit.strip()
        if not self.unit:
            raise ValueError("L'unité est obligatoire.")
        if self.purchase_date > date.today():
            raise ValueError("La date d'achat ne peut pas être dans le futur.")
        if self.expiration_date < self.purchase_date:
            raise ValueError("La date d'expiration ne peut pas précéder l'achat.")
        self.expiration_type = self.expiration_type.upper()
        if self.expiration_type not in {"DLC", "DDM"}:
            raise ValueError("expiration_type doit être DLC ou DDM.")
        self.product.add_lot(self)

    def apply_movement(self, movement: StockMovement):
        """Applique un mouvement sans tester sa classe concrète : polymorphisme."""
        if movement.lot is not self:
            raise ValueError("Le mouvement doit concerner ce lot.")
        movement.apply()
        self.movements.append(movement)

    def add_stock(self, quantity: float) -> StockEntry:
        movement = StockEntry(self, quantity)
        self.apply_movement(movement)
        return movement

    def consume(self, quantity: float) -> StockConsumption:
        movement = StockConsumption(self, quantity)
        self.apply_movement(movement)
        return movement

    def discard(self, quantity: float) -> StockWaste:
        movement = StockWaste(self, quantity)
        self.apply_movement(movement)
        return movement

    def is_expired(self, reference_date: date | None = None) -> bool:
        return self.expiration_date < (reference_date or date.today())

    def days_until_expiration(self, reference_date: date | None = None) -> int:
        return (self.expiration_date - (reference_date or date.today())).days

    def get_expiration_status(self, warning_days: int = 3,
                              reference_date: date | None = None) -> str:
        if warning_days < 0:
            raise ValueError("warning_days ne peut pas être négatif.")
        days = self.days_until_expiration(reference_date)
        if days < 0:
            return "expired"
        return "urgent" if days <= warning_days else "safe"
