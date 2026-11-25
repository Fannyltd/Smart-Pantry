"""F4 — Gestion de la liste de courses (ShoppingListService)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.config.settings import Settings
from app.exceptions.domain_exceptions import NotFoundError, ValidationError
from app.models import FoodLot, FoodProduct, Recipe, RecipeIngredient, ShoppingItem, ShoppingList
from app.repositories.food_repository import ShoppingListRepository
from app.services.inventory_service import InventoryService
from app.services.recipe_service import IngredientStatus, RecipeRecommendationService
from app.utils import unit_converter as units
from app.utils import validators


@dataclass
class ItemStockInfo:
    """Ce qui est déjà en stock pour un article (§2.4 : éviter les achats inutiles)."""
    item: ShoppingItem
    in_stock_quantity: float
    unit: str
    comparable: bool

    @property
    def already_covered(self) -> bool:
        return self.comparable and self.in_stock_quantity >= self.item.quantity


class ShoppingListService:
    def __init__(self, shopping_repository: ShoppingListRepository,
                 inventory_service: InventoryService,
                 recommendation_service: RecipeRecommendationService, settings: Settings):
        self.shopping_repository = shopping_repository
        self.inventory_service = inventory_service
        self.recommendation_service = recommendation_service
        self.matcher = recommendation_service.matcher
        self.settings = settings

    # ------------------------------------------------------------ lecture
    def get_shopping_list(self) -> ShoppingList:
        products = {p.id: p for p in self.inventory_service.get_inventory()}
        return self.shopping_repository.get_or_create_default(products)

    def _get_item(self, item_id: int) -> tuple[ShoppingList, ShoppingItem]:
        shopping_list = self.get_shopping_list()
        for item in shopping_list.items:
            if item.id == item_id:
                return shopping_list, item
        raise NotFoundError("Article", item_id)

    def get_stock_info(self, item: ShoppingItem,
                       products: list[FoodProduct] | None = None) -> ItemStockInfo:
        products = products if products is not None else self.inventory_service.get_inventory()
        candidates = ([item.product] if item.product else
                      [p for p in products if self.matcher.matches(item.name, p.name)])
        total, comparable = 0.0, False
        forms = self.matcher.canonical_forms(item.name)
        for product in candidates:
            for lot in product.get_available_lots():
                converted = units.convert_for_ingredient(lot.quantity, lot.unit, item.unit, forms)
                if converted is not None:
                    total += converted
                    comparable = True
        return ItemStockInfo(item, total, item.unit, comparable or not candidates)

    # ------------------------------------------------------------ écriture
    def _find_mergeable(self, shopping_list: ShoppingList, name: str, unit: str) -> ShoppingItem | None:
        for item in shopping_list.get_missing_items():
            if self.matcher.matches(item.name, name) and units.are_compatible(item.unit, unit):
                return item
        return None

    def add_item(self, name: str, quantity, unit: str, product_id: int | None = None) -> ShoppingItem:
        """Ajout manuel ; fusionne avec un article identique non acheté."""
        name = validators.validate_non_empty(name, "article")
        quantity = validators.validate_positive(quantity)
        unit = units.normalize_unit(validators.validate_non_empty(unit, "unité"))
        product = self.inventory_service.get_product(product_id) if product_id else None
        shopping_list = self.get_shopping_list()
        existing = self._find_mergeable(shopping_list, name, unit)
        if existing:
            existing.quantity += units.convert(quantity, unit, existing.unit)
            self.shopping_repository.update_item(existing)
            return existing
        try:
            item = ShoppingItem(name, quantity, unit, product=product)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        shopping_list.add_item(item)
        return self.shopping_repository.add_item(shopping_list.id, item)

    def update_item(self, item_id: int, name: str, quantity, unit: str) -> ShoppingItem:
        _, item = self._get_item(item_id)
        item.name = validators.validate_non_empty(name, "article")
        item.quantity = validators.validate_positive(quantity)
        item.unit = units.normalize_unit(validators.validate_non_empty(unit, "unité"))
        self.shopping_repository.update_item(item)
        return item

    def remove_item(self, item_id: int) -> None:
        shopping_list, item = self._get_item(item_id)
        shopping_list.remove_item(item)
        self.shopping_repository.delete_item(item_id)

    def mark_as_purchased(self, item_id: int) -> ShoppingItem:
        """Coche l'article — le stock n'est PAS modifié (RM09 / BR14)."""
        _, item = self._get_item(item_id)
        item.mark_as_purchased()
        self.shopping_repository.update_item(item)
        return item

    def mark_as_not_purchased(self, item_id: int) -> ShoppingItem:
        _, item = self._get_item(item_id)
        item.mark_as_not_purchased()
        self.shopping_repository.update_item(item)
        return item

    def confirm_purchase(self, item_id: int, expiration_date: date, category: str = "Autre",
                         expiration_type: str = "DLC", quantity=None,
                         purchase_date: date | None = None) -> FoodLot:
        """Validation explicite de l'achat : l'article entre en stock (BR14)."""
        _, item = self._get_item(item_id)
        if not item.is_purchased:
            raise ValidationError("Cochez l'article comme acheté avant de l'ajouter au stock.")
        quantity = item.quantity if quantity is None else validators.validate_positive(quantity)
        purchase_date = purchase_date or date.today()
        if item.product is not None:
            lot = self.inventory_service.add_food_lot(item.product, quantity, item.unit, purchase_date,
                                                      expiration_date, expiration_type)
        else:
            existing = [p for p in self.inventory_service.get_inventory()
                        if self.matcher.matches(item.name, p.name)
                        and units.are_compatible(p.base_unit, item.unit)]
            if existing:
                lot = self.inventory_service.add_food_lot(existing[0], quantity, item.unit,
                                                          purchase_date, expiration_date,
                                                          expiration_type)
            else:
                lot = self.inventory_service.add_product_with_lot(
                    item.name, category, quantity, item.unit, purchase_date, expiration_date,
                    expiration_type)
        self.shopping_repository.delete_item(item_id)
        return lot

    def clear_purchased(self) -> int:
        shopping_list = self.get_shopping_list()
        purchased = [i for i in shopping_list.items if i.is_purchased]
        for item in purchased:
            self.shopping_repository.delete_item(item.id)
        return len(purchased)

    # ------------------------------------------------------------ génération
    @staticmethod
    def missing_to_buy(status: IngredientStatus) -> tuple[RecipeIngredient, float, str] | None:
        """Convertit un ingrédient manquant en besoin d'achat, ou None."""
        if status.is_available:
            return None
        missing = status.missing_quantity
        if missing is None:
            if status.matched_products and not status.expired_only:
                return None  # présent mais non mesurable : on n'achète pas en double
            return status.ingredient, (status.required_quantity or 1.0), (status.unit or "unité")
        if missing <= 1e-9:
            return None
        return status.ingredient, round(missing, 2), status.unit or "unité"

    def add_missing_needs(self, needs: list[tuple[RecipeIngredient, float, str]]) -> list[ShoppingItem]:
        """Ajoute des besoins à la liste en fusionnant avec les articles existants."""
        shopping_list = self.get_shopping_list()
        touched: list[ShoppingItem] = []
        for ingredient, quantity, unit in needs:
            name = ingredient.ingredient_name or (ingredient.product.name if ingredient.product else "")
            existing = self._find_mergeable(shopping_list, name, unit)
            if existing:
                existing.quantity += units.convert(quantity, unit, existing.unit) \
                    if units.normalize_unit(unit) != existing.unit else quantity
                existing.quantity = round(existing.quantity, 2)
                self.shopping_repository.update_item(existing)
                touched.append(existing)
                continue
            scaled = RecipeIngredient(ingredient.product, quantity, unit, name)
            for item in shopping_list.add_missing_recipe_ingredients([(scaled, quantity)]):
                self.shopping_repository.add_item(shopping_list.id, item)
                touched.append(item)
        return touched

    def generate_shopping_list(self, recipe: Recipe, servings: int | None = None,
                               reference_date: date | None = None) -> list[ShoppingItem]:
        """RM08 / BR13 : ajoute uniquement ce qui manque réellement au stock."""
        match = self.recommendation_service.calculate_match_score(
            recipe, reference_date=reference_date, servings=servings)
        needs = [need for status in match.ingredients if (need := self.missing_to_buy(status))]
        return self.add_missing_needs(needs)
