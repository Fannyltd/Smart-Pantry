"""Validation des saisies utilisateur et normalisation des noms d'ingrédients."""
from __future__ import annotations

import re
import unicodedata
from datetime import date

from app.exceptions.domain_exceptions import ValidationError

_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _singular(word: str) -> str:
    if len(word) > 3 and word.endswith(("s", "x")) and not word.endswith(("ss", "us")):
        return word[:-1]
    return word


def normalize_name(name: str | None) -> str:
    """Normalise un nom pour les correspondances inventaire / recettes.

    "  Tomates  Cerises " -> "tomate cerise" ; "Crème fraîche" -> "creme fraiche".
    """
    if not name:
        return ""
    text = strip_accents(name).casefold().replace("œ", "oe").replace("'", " ").replace("-", " ")
    text = _NON_ALNUM.sub(" ", text)
    return " ".join(_singular(word) for word in text.split())


def validate_non_empty(value: str | None, field_label: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValidationError(f"Le champ « {field_label} » est obligatoire.")
    if len(cleaned) > 120:
        raise ValidationError(f"Le champ « {field_label} » est trop long (120 caractères max).")
    return cleaned


def parse_quantity(value) -> float:
    """Accepte 1.5, "1,5", "2" ; refuse texte vide, NaN, infini."""
    if isinstance(value, str):
        value = value.strip().replace(",", ".")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"Quantité invalide : « {value} ».") from None
    if number != number or number in (float("inf"), float("-inf")):
        raise ValidationError("Quantité invalide.")
    return number


def validate_positive(value, field_label: str = "quantité") -> float:
    number = parse_quantity(value)
    if number <= 0:
        raise ValidationError(f"La {field_label} doit être strictement positive.")
    return number


def validate_non_negative(value, field_label: str = "quantité") -> float:
    number = parse_quantity(value)
    if number < 0:
        raise ValidationError(f"La {field_label} ne peut pas être négative (RM01).")
    return number


def validate_purchase_date(purchase_date: date, today: date | None = None) -> date:
    if purchase_date > (today or date.today()):
        raise ValidationError("La date d'achat ne peut pas être dans le futur (BR03).")
    return purchase_date


def validate_expiration_date(expiration_date: date, purchase_date: date) -> date:
    if expiration_date < purchase_date:
        raise ValidationError("La date de péremption ne peut pas précéder la date d'achat (BR04).")
    return expiration_date


def validate_expiration_type(value: str) -> str:
    normalized = (value or "").strip().upper()
    if normalized not in {"DLC", "DDM"}:
        raise ValidationError("Le type de date doit être DLC ou DDM (BR11).")
    return normalized


def validate_period(start: date, end: date) -> tuple[date, date]:
    if end < start:
        raise ValidationError("La fin de période doit être postérieure au début (BR16).")
    return start, end
