"""Exceptions métier de Smart Pantry.

Les modèles du domaine lèvent des ``ValueError`` ; les services les traduisent
en exceptions de cette hiérarchie, que l'interface affiche telles quelles.
"""


class SmartPantryError(Exception):
    """Classe mère de toutes les erreurs applicatives."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


class ValidationError(SmartPantryError):
    """Donnée saisie invalide (BR01 à BR04, contraintes de saisie)."""


class NotFoundError(SmartPantryError):
    """Entité introuvable en base."""

    def __init__(self, entity: str, identifier):
        super().__init__(f"{entity} introuvable (id={identifier}).")
        self.entity = entity
        self.identifier = identifier


class DuplicateError(SmartPantryError):
    """Entité déjà existante (ex. produit de même nom)."""


class InsufficientStockError(SmartPantryError):
    """Consommation supérieure au stock disponible (RM04 / BR05)."""


class UnitConversionError(SmartPantryError):
    """Unités incompatibles ou inconnues (BR07)."""


class ExternalAPIError(SmartPantryError):
    """TheMealDB indisponible ou réponse inexploitable (T09)."""
