"""Préparation d'une recette : consommation du stock (FEFO)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.exceptions.domain_exceptions import InsufficientStockError
from app.models import Recipe, StockConsumption
from app.services.inventory_service import InventoryService, is_usable
from app.services.recipe_service import RecipeRecommendationService, RecipeService
from app.utils import unit_converter as units


@dataclass
class CookingReport:
    recipe: Recipe
    consumptions: list[StockConsumption] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)   # ingrédients non décomptés (et pourquoi)


class CookingService:
    def __init__(self, recipe_service: RecipeService,
                 recommendation_service: RecipeRecommendationService,
                 inventory_service: InventoryService):
        self.recipe_service = recipe_service
        self.recommendation_service = recommendation_service
        self.inventory_service = inventory_service

    def cook_recipe(self, recipe: Recipe | int, servings: int | None = None,
                    allow_partial: bool = False, reference_date: date | None = None) -> CookingReport:
        """Décompte du stock les ingrédients d'une recette préparée (FEFO).

        Tout est vérifié avant la moindre écriture : si un ingrédient manque et
        que allow_partial est False, rien n'est consommé (RM04).
        """
        if isinstance(recipe, int):
            recipe = self.recipe_service.get_recipe(recipe)
        products = self.inventory_service.get_inventory()
        match = self.recommendation_service.calculate_match_score(recipe, products, reference_date,
                                                                  servings)
        report = CookingReport(recipe=recipe)
        plans = []
        for status in match.ingredients:
            if not status.matched_products:
                report.skipped.append(f"{status.name} : absent du stock")
                continue
            if status.required_quantity is None:
                report.skipped.append(f"{status.name} : quantité non précisée")
                continue
            forms = self.recommendation_service.matcher.canonical_forms(status.name)
            quantity, unit = status.required_quantity, status.unit
            base = status.matched_products[0].base_unit
            if not units.are_compatible(unit, base):
                converted = units.convert_for_ingredient(quantity, unit, base, forms)
                if converted is None:
                    report.skipped.append(f"{status.name} : unités non comparables")
                    continue
                quantity, unit = converted, base
            try:
                plans.append(self.inventory_service.plan_consumption(
                    status.matched_products, quantity, unit, reference_date))
            except InsufficientStockError as exc:
                if not allow_partial:
                    raise
                available = sum(units.try_convert(l.quantity, l.unit, unit) or 0
                                for p in status.matched_products for l in p.get_available_lots()
                                if is_usable(l, reference_date))
                if available > 0:
                    plans.append(self.inventory_service.plan_consumption(
                        status.matched_products, available, unit, reference_date))
                report.skipped.append(f"{status.name} : {exc}")
        movements = []
        for plan in plans:
            for lot, lot_quantity in plan:
                movements.append(lot.consume(min(lot_quantity, lot.quantity)))
        if movements:
            self.inventory_service.movement_repository.record_many(movements)
        report.consumptions = movements
        return report
