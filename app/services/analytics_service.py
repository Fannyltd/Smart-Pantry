"""F5 — Indicateurs (AnalyticsService).

- BR15 : consommation et gaspillage sont calculés séparément ;
- BR16 : tous les indicateurs portent sur une période [start, end] ;
- BR17 : un produit sans historique suffisant n'entre pas dans le taux global.

Les quantités ne sont additionnées qu'après conversion vers l'unité de base de
leur dimension (g, ml, unité) : on ne mélange jamais grammes et litres (BR07).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from app.config.settings import Settings
from app.models.stock_movement import MovementType
from app.repositories.food_repository import FoodRepository
from app.repositories.movement_repository import MovementRecord, MovementRepository
from app.services.expiration_service import ExpirationService
from app.utils import unit_converter as units
from app.utils.validators import validate_period


@dataclass
class ProductWasteStat:
    product_id: int
    product_name: str
    category: str
    unit: str
    consumed: float
    wasted: float
    movements: int
    sufficient_history: bool

    @property
    def waste_rate(self) -> float | None:
        total = self.consumed + self.wasted
        if not self.sufficient_history or total <= 0:
            return None
        return self.wasted / total


class AnalyticsService:
    def __init__(self, food_repository: FoodRepository, movement_repository: MovementRepository,
                 expiration_service: ExpirationService, settings: Settings):
        self.food_repository = food_repository
        self.movement_repository = movement_repository
        self.expiration_service = expiration_service
        self.settings = settings

    def default_period(self, today: date | None = None) -> tuple[date, date]:
        today = today or date.today()
        return today - timedelta(days=self.settings.default_period_days), today

    def _records(self, start: date, end: date, types: list[str] | None = None) -> list[MovementRecord]:
        validate_period(start, end)
        return self.movement_repository.list_records(start, end, types)

    @staticmethod
    def _sum_by_base_unit(records: list[MovementRecord]) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        for record in records:
            quantity, base = units.to_base_unit(record.quantity, record.unit)
            totals[base] += quantity
        return {unit: round(value, 2) for unit, value in totals.items()}

    # ------------------------------------------------------------ indicateurs
    def calculate_consumption(self, start: date, end: date) -> dict[str, float]:
        """Quantités consommées sur la période, par unité de base."""
        return self._sum_by_base_unit(self._records(start, end, [MovementType.CONSUMPTION.value]))

    def calculate_waste(self, start: date, end: date) -> dict[str, float]:
        """Quantités jetées sur la période, par unité de base (BR15)."""
        return self._sum_by_base_unit(self._records(start, end, [MovementType.WASTE.value]))

    def calculate_entries(self, start: date, end: date) -> dict[str, float]:
        return self._sum_by_base_unit(self._records(start, end, [MovementType.ENTRY.value]))

    def waste_by_product(self, start: date, end: date) -> list[ProductWasteStat]:
        stats: dict[int, ProductWasteStat] = {}
        for record in self._records(start, end):
            stat = stats.setdefault(record.product_id, ProductWasteStat(
                record.product_id, record.product_name, record.category, record.base_unit,
                0.0, 0.0, 0, False))
            stat.movements += 1
            quantity = units.try_convert(record.quantity, record.unit, record.base_unit)
            if quantity is None:
                continue
            if record.movement_type == MovementType.CONSUMPTION.value:
                stat.consumed += quantity
            elif record.movement_type == MovementType.WASTE.value:
                stat.wasted += quantity
        for stat in stats.values():
            stat.sufficient_history = stat.movements >= self.settings.min_history_movements
            stat.consumed, stat.wasted = round(stat.consumed, 2), round(stat.wasted, 2)
        return sorted(stats.values(), key=lambda s: (-s.wasted, s.product_name))

    def calculate_waste_rate(self, start: date, end: date) -> float | None:
        """Taux de gaspillage moyen des produits ayant un historique suffisant.

        Chaque produit est mesuré dans sa propre unité, puis les taux sont
        moyennés : cela évite d'additionner des grammes et des litres. Renvoie
        None s'il n'y a pas assez de données (BR17).
        """
        rates = [s.waste_rate for s in self.waste_by_product(start, end) if s.waste_rate is not None]
        return round(sum(rates) / len(rates), 4) if rates else None

    def category_distribution(self) -> dict[str, int]:
        """Nombre de produits en stock par catégorie."""
        counter: Counter[str] = Counter()
        for product in self.food_repository.list_products(with_movements=False):
            if product.get_available_lots():
                counter[product.category] += 1
        return dict(counter.most_common())

    def movements_timeline(self, start: date, end: date) -> list[dict]:
        """Nombre de mouvements par jour et par type (pour un graphique)."""
        counter: Counter[tuple[date, str]] = Counter(
            (r.movement_date.date(), r.movement_type) for r in self._records(start, end))
        days = (end - start).days + 1
        rows = []
        for offset in range(days):
            day = start + timedelta(days=offset)
            rows.append({"date": day, **{t.value: counter.get((day, t.value), 0) for t in MovementType}})
        return rows

    def movement_history(self, start: date, end: date) -> list[MovementRecord]:
        return self._records(start, end)

    def generate_summary(self, start: date | None = None, end: date | None = None,
                         reference_date: date | None = None) -> dict:
        if start is None or end is None:
            start, end = self.default_period(reference_date)
        products = self.food_repository.list_products(with_movements=False)
        in_stock = [p for p in products if p.get_available_lots()]
        alerts = self.expiration_service.get_alerts(reference_date, products=products)
        by_product = self.waste_by_product(start, end)
        return {
            "period": (start, end),
            "products_in_stock": len(in_stock),
            "lots_in_stock": sum(len(p.get_available_lots()) for p in in_stock),
            "urgent_lots": sum(1 for a in alerts if a.status == "urgent"),
            "expired_lots": sum(1 for a in alerts if a.status == "expired"),
            "consumption": self.calculate_consumption(start, end),
            "waste": self.calculate_waste(start, end),
            "entries": self.calculate_entries(start, end),
            "waste_rate": self.calculate_waste_rate(start, end),
            "products_with_enough_history": sum(1 for s in by_product if s.sufficient_history),
            "products_with_movements": len(by_product),
            "category_distribution": self.category_distribution(),
        }
