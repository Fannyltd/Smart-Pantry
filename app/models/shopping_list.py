from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .food_product import FoodProduct
    from .recipe_ingredient import RecipeIngredient

@dataclass
class ShoppingItem:
    name: str
    quantity: float
    unit: str
    is_purchased: bool = False
    product: FoodProduct | None = None
    id: int | None = None

    def __post_init__(self):
        self.name, self.unit = self.name.strip(), self.unit.strip()
        if not self.name:
            raise ValueError("Le nom de l'article est obligatoire.")
        if self.quantity <= 0:
            raise ValueError("La quantité à acheter doit être positive.")
        if not self.unit:
            raise ValueError("L'unité est obligatoire.")

    def mark_as_purchased(self):
        # Ne modifie volontairement pas l'inventaire (RM09 / BR14).
        self.is_purchased = True

    def mark_as_not_purchased(self):
        self.is_purchased = False

@dataclass
class ShoppingList:
    id: int | None = None
    items: list[ShoppingItem] = field(default_factory=list)
    name: str = "Ma liste de courses"

    def add_item(self, item: ShoppingItem):
        if not isinstance(item, ShoppingItem):
            raise TypeError("L'article doit être un ShoppingItem.")
        self.items.append(item)

    def remove_item(self, item: ShoppingItem):
        self.items.remove(item)

    def get_missing_items(self) -> list[ShoppingItem]:
        return [item for item in self.items if not item.is_purchased]

    def add_missing_recipe_ingredients(
        self, missing_ingredients: list[tuple[RecipeIngredient, float]]
    ) -> list[ShoppingItem]:
        """Chaque tuple contient un ingrédient et sa quantité manquante calculée."""
        added = []
        for ingredient, missing_quantity in missing_ingredients:
            if missing_quantity <= 0:
                continue
            name = ingredient.ingredient_name or (
                ingredient.product.name if ingredient.product else ""
            )
            if not name:
                continue
            unit = ingredient.unit or (
                ingredient.product.base_unit if ingredient.product else "unité"
            )
            item = ShoppingItem(name, missing_quantity, unit, product=ingredient.product)
            self.add_item(item)
            added.append(item)
        return added
