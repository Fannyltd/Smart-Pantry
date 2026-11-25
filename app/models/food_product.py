from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .food_lot import FoodLot

@dataclass
class FoodProduct:
    name: str
    category: str
    base_unit: str
    id: int | None = None
    lots: list[FoodLot] = field(default_factory=list, repr=False)

    def __post_init__(self):
        self.name, self.category, self.base_unit = (
            self.name.strip(), self.category.strip(), self.base_unit.strip())
        if not self.name or not self.category or not self.base_unit:
            raise ValueError("Le nom, la catégorie et l'unité sont obligatoires.")

    def add_lot(self, lot: FoodLot):
        if lot.product is not self:
            raise ValueError("Ce lot n'est pas associé à ce produit.")
        if lot not in self.lots:
            self.lots.append(lot)

    def get_total_quantity(self) -> float:
        # Pas de conversion automatique entre unités différentes.
        return sum(lot.quantity for lot in self.lots if lot.unit == self.base_unit)

    def get_available_lots(self) -> list[FoodLot]:
        return [lot for lot in self.lots if lot.quantity > 0]

    def __str__(self):
        return f"{self.name} ({self.category})"
