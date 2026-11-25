"""Persistance des recettes (catalogue local + cache TheMealDB)."""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.database.models import RecipeIngredientORM, RecipeORM
from app.exceptions.domain_exceptions import NotFoundError
from app.models import Recipe, RecipeIngredient
from app.repositories.base_repository import BaseRepository


def recipe_to_domain(row: RecipeORM) -> Recipe:
    recipe = Recipe(name=row.name, servings=row.servings, instructions=row.instructions,
                    preparation_time=row.preparation_time, id=row.id, external_id=row.external_id,
                    category=row.category, image_url=row.image_url)
    for ingredient_row in row.ingredients:
        recipe.add_ingredient(RecipeIngredient(
            product=None, required_quantity=ingredient_row.required_quantity,
            unit=ingredient_row.unit or "", ingredient_name=ingredient_row.ingredient_name,
            id=ingredient_row.id))
    return recipe


class RecipeRepository(BaseRepository):
    entity_label = "Recette"

    def _query(self):
        return select(RecipeORM).options(selectinload(RecipeORM.ingredients))

    def list_recipes(self, source: str | None = None) -> list[Recipe]:
        query = self._query().order_by(RecipeORM.name)
        if source:
            query = query.where(RecipeORM.source == source)
        with self._session() as session:
            return [recipe_to_domain(row) for row in session.scalars(query)]

    def get(self, recipe_id: int) -> Recipe:
        with self._session() as session:
            row = session.scalars(self._query().where(RecipeORM.id == recipe_id)).first()
            if row is None:
                raise NotFoundError("Recette", recipe_id)
            return recipe_to_domain(row)

    def get_by_external_id(self, external_id: str) -> Recipe | None:
        with self._session() as session:
            row = session.scalars(self._query().where(RecipeORM.external_id == external_id)).first()
            return recipe_to_domain(row) if row else None

    def search(self, text: str | None = None, category: str | None = None) -> list[Recipe]:
        query = self._query().order_by(RecipeORM.name)
        if text:
            pattern = f"%{text.strip().lower()}%"
            query = query.where(or_(func.lower(RecipeORM.name).like(pattern),
                                    RecipeORM.ingredients.any(
                                        func.lower(RecipeIngredientORM.ingredient_name).like(pattern))))
        if category:
            query = query.where(func.lower(RecipeORM.category) == category.strip().lower())
        with self._session() as session:
            return [recipe_to_domain(row) for row in session.scalars(query)]

    def list_categories(self) -> list[str]:
        with self._session() as session:
            return sorted(c for c in session.scalars(select(RecipeORM.category).distinct()) if c)

    def save(self, recipe: Recipe, source: str = "local") -> Recipe:
        """Insère ou remplace une recette (identifiée par son id ou son external_id)."""
        with self._session() as session:
            row = None
            if recipe.id is not None:
                row = session.get(RecipeORM, recipe.id)
            if row is None and recipe.external_id:
                row = session.scalars(
                    select(RecipeORM).where(RecipeORM.external_id == recipe.external_id)).first()
            if row is None:
                row = RecipeORM(source=source)
                session.add(row)
            row.external_id = recipe.external_id
            row.name, row.servings, row.instructions = recipe.name, recipe.servings, recipe.instructions
            row.preparation_time, row.category = recipe.preparation_time, recipe.category
            row.image_url = recipe.image_url
            row.ingredients.clear()
            session.flush()
            for position, ingredient in enumerate(recipe.ingredients):
                row.ingredients.append(RecipeIngredientORM(
                    ingredient_name=ingredient.ingredient_name or "",
                    required_quantity=ingredient.required_quantity, unit=ingredient.unit or "",
                    product_id=ingredient.product.id if ingredient.product else None,
                    position=position))
            session.flush()
            recipe.id = row.id
            for ingredient, ingredient_row in zip(recipe.ingredients, row.ingredients):
                ingredient.id = ingredient_row.id
        return recipe

    def delete(self, recipe_id: int) -> None:
        with self._session() as session:
            session.delete(self._get_or_raise(session, RecipeORM, recipe_id))

    def count(self) -> int:
        with self._session() as session:
            return session.scalar(select(func.count(RecipeORM.id))) or 0
