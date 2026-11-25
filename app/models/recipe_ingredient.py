from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .food_product import FoodProduct

@dataclass
class RecipeIngredient:
    product: FoodProduct | None
    required_quantity: float | None
    unit: str
    ingredient_name: str | None = None
    id: int | None = None

    def __post_init__(self):
        self.unit = self.unit.strip()
        if self.required_quantity is not None and self.required_quantity <= 0:
            raise ValueError("La quantité nécessaire doit être positive.")
        if self.product is None and not (self.ingredient_name or "").strip():
            raise ValueError("Un produit ou un nom d'ingrédient est nécessaire.")
        if self.ingredient_name:
            self.ingredient_name = self.ingredient_name.strip()
        elif self.product:
            self.ingredient_name = self.product.name

    @property
    def normalized_name(self) -> str:
        return " ".join((self.ingredient_name or "").casefold().split())
