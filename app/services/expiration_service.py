"""F2 — Suivi des dates de péremption (ExpirationService)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.config.settings import Settings
from app.models import FoodLot, FoodProduct
from app.repositories.food_repository import FoodRepository

STATUS_COLORS = {"expired": "red", "urgent": "orange", "safe": "green"}   # §2.2 du cahier des charges
STATUS_LABELS = {"expired": "Dépassé", "urgent": "À consommer rapidement", "safe": "OK"}
STATUS_ICONS = {"expired": "🔴", "urgent": "🟠", "safe": "🟢"}
TYPE_LABELS = {
    "DLC": "Date limite de consommation (à consommer jusqu'au)",
    "DDM": "Date de durabilité minimale (à consommer de préférence avant)",
}


@dataclass
class ExpirationAlert:
    lot: FoodLot
    product: FoodProduct
    status: str            # expired | urgent | safe
    days_left: int

    @property
    def color(self) -> str:
        return STATUS_COLORS[self.status]

    @property
    def icon(self) -> str:
        return STATUS_ICONS[self.status]

    @property
    def label(self) -> str:
        return STATUS_LABELS[self.status]

    @property
    def message(self) -> str:
        name = self.product.name
        if self.status == "expired":
            if self.lot.expiration_type == "DDM":
                return (f"{name} : DDM dépassée de {-self.days_left} j — encore consommable "
                        f"après vérification (aspect, odeur).")
            return f"{name} : DLC dépassée de {-self.days_left} j — ne pas consommer."
        if self.status == "urgent":
            when = "aujourd'hui" if self.days_left == 0 else (
                "demain" if self.days_left == 1 else f"dans {self.days_left} jours")
            return f"{name} : expire {when} — à consommer en priorité."
        return f"{name} : expire dans {self.days_left} jours."


class ExpirationService:
    def __init__(self, food_repository: FoodRepository, settings: Settings):
        self.food_repository = food_repository
        self.settings = settings

    def classify_expiration_risk(self, lot: FoodLot, reference_date: date | None = None,
                                 warning_days: int | None = None) -> str:
        """expired (rouge) / urgent (orange) / safe (vert) — BR08, BR09."""
        days = self.settings.expiration_warning_days if warning_days is None else warning_days
        return lot.get_expiration_status(days, reference_date)

    def get_alerts(self, reference_date: date | None = None, warning_days: int | None = None,
                   products: list[FoodProduct] | None = None) -> list[ExpirationAlert]:
        """Tous les lots non vides, triés par date d'expiration croissante (BR10)."""
        products = products if products is not None else self.food_repository.list_products(
            with_movements=False)
        alerts = [
            ExpirationAlert(lot=lot, product=product,
                            status=self.classify_expiration_risk(lot, reference_date, warning_days),
                            days_left=lot.days_until_expiration(reference_date))
            for product in products for lot in product.get_available_lots()
        ]
        return sorted(alerts, key=lambda alert: (alert.lot.expiration_date, alert.product.name))

    def get_expiring_lots(self, reference_date: date | None = None,
                          warning_days: int | None = None) -> list[ExpirationAlert]:
        return [a for a in self.get_alerts(reference_date, warning_days) if a.status == "urgent"]

    def get_expired_lots(self, reference_date: date | None = None) -> list[ExpirationAlert]:
        return [a for a in self.get_alerts(reference_date) if a.status == "expired"]

    def get_priority_products(self, reference_date: date | None = None,
                              products: list[FoodProduct] | None = None) -> list[ExpirationAlert]:
        """Produits à consommer en priorité (BR12) : lots urgents ou DDM dépassée."""
        return [a for a in self.get_alerts(reference_date, products=products)
                if a.status == "urgent" or (a.status == "expired" and a.lot.expiration_type == "DDM")]

    def urgency_score(self, lot: FoodLot, reference_date: date | None = None) -> float:
        """Urgence normalisée dans [0, 1] utilisée pour P(r).

        1 = à consommer aujourd'hui (ou DDM dépassée) ; 0 = au-delà de l'horizon.
        Une DLC dépassée vaut 0 : le lot n'est plus utilisable.
        """
        days = lot.days_until_expiration(reference_date)
        if days < 0:
            return 1.0 if lot.expiration_type == "DDM" else 0.0
        horizon = self.settings.priority_horizon_days
        return max(0.0, min(1.0, 1 - days / horizon))
