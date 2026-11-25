from dataclasses import dataclass, field
from .recipe_ingredient import RecipeIngredient

@dataclass
class Recipe:
    name: str
    servings: int
    instructions: str
    preparation_time: int | None = None
    id: int | None = None
    external_id: str | None = None
    category: str | None = None
    image_url: str | None = None
    ingredients: list[RecipeIngredient] = field(default_factory=list)

    def __post_init__(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Le nom de la recette est obligatoire.")
        if self.servings <= 0:
            raise ValueError("Le nombre de portions doit être positif.")
        if self.preparation_time is not None and self.preparation_time < 0:
            raise ValueError("Le temps de préparation ne peut pas être négatif.")
        if not self.instructions.strip():
            raise ValueError("Les instructions sont obligatoires.")

    def add_ingredient(self, ingredient: RecipeIngredient):
        if not isinstance(ingredient, RecipeIngredient):
            raise TypeError("L'ingrédient doit être un RecipeIngredient.")
        self.ingredients.append(ingredient)

    def remove_ingredient(self, ingredient: RecipeIngredient):
        self.ingredients.remove(ingredient)

    def get_ingredients(self) -> list[RecipeIngredient]:
        return list(self.ingredients)
