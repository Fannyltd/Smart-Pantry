"""Gestion des unités de mesure (BR07, contrainte 4.2).

Trois dimensions sont gérées : masse (base ``g``), volume (base ``ml``) et
dénombrement (base ``unité``). Deux quantités ne sont additionnées ou
comparées que si leurs unités appartiennent à la même dimension. Aucune
conversion masse <-> volume n'est faite (la densité dépend de l'aliment).
"""
from __future__ import annotations

import re
import unicodedata
from fractions import Fraction

from app.exceptions.domain_exceptions import UnitConversionError

MASS, VOLUME, COUNT = "mass", "volume", "count"
BASE_UNITS = {MASS: "g", VOLUME: "ml", COUNT: "unité"}

# unité canonique -> (dimension, facteur vers l'unité de base)
UNIT_DEFINITIONS: dict[str, tuple[str, float]] = {
    "mg": (MASS, 0.001),
    "g": (MASS, 1.0),
    "kg": (MASS, 1000.0),
    "oz": (MASS, 28.3495),
    "lb": (MASS, 453.592),
    "ml": (VOLUME, 1.0),
    "cl": (VOLUME, 10.0),
    "dl": (VOLUME, 100.0),
    "l": (VOLUME, 1000.0),
    "c. à café": (VOLUME, 5.0),
    "c. à soupe": (VOLUME, 15.0),
    "tasse": (VOLUME, 240.0),
    "pincée": (VOLUME, 0.3),
    "unité": (COUNT, 1.0),
    "douzaine": (COUNT, 12.0),
}

UNIT_ALIASES: dict[str, str] = {
    # masse
    "mg": "mg", "milligramme": "mg", "milligrammes": "mg",
    "g": "g", "gr": "g", "grs": "g", "gramme": "g", "grammes": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kgs": "kg", "kilo": "kg", "kilos": "kg", "kilogramme": "kg", "kilogrammes": "kg",
    "kilogram": "kg", "kilograms": "kg",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    # volume
    "ml": "ml", "millilitre": "ml", "millilitres": "ml", "milliliter": "ml", "milliliters": "ml",
    "cl": "cl", "centilitre": "cl", "centilitres": "cl",
    "dl": "dl", "decilitre": "dl", "decilitres": "dl",
    "l": "l", "litre": "l", "litres": "l", "liter": "l", "liters": "l", "ltr": "l",
    "tsp": "c. à café", "teaspoon": "c. à café", "teaspoons": "c. à café", "cac": "c. à café",
    "c. a cafe": "c. à café", "c. à café": "c. à café", "cuillere a cafe": "c. à café",
    "tbsp": "c. à soupe", "tbs": "c. à soupe", "tblsp": "c. à soupe", "tbls": "c. à soupe",
    "tablespoon": "c. à soupe", "tablespoons": "c. à soupe", "cas": "c. à soupe",
    "c. a soupe": "c. à soupe", "c. à soupe": "c. à soupe", "cuillere a soupe": "c. à soupe",
    "cup": "tasse", "cups": "tasse", "tasse": "tasse", "tasses": "tasse",
    "pinch": "pincée", "pinches": "pincée", "pincee": "pincée", "pincée": "pincée", "pincees": "pincée",
    # dénombrement
    "unite": "unité", "unité": "unité", "unites": "unité", "unités": "unité", "u": "unité",
    "piece": "unité", "pièce": "unité", "pieces": "unité", "pièces": "unité", "pcs": "unité",
    "pc": "unité", "x": "unité", "whole": "unité", "large": "unité", "medium": "unité",
    "small": "unité", "unit": "unité", "units": "unité",
    "douzaine": "douzaine", "dozen": "douzaine",
}


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize_unit(unit: str | None) -> str:
    """Renvoie l'unité canonique ; une unité inconnue est renvoyée nettoyée."""
    if unit is None:
        return ""
    cleaned = " ".join(unit.strip().lower().split())
    if not cleaned:
        return ""
    if cleaned in UNIT_ALIASES:
        return UNIT_ALIASES[cleaned]
    no_accent = _strip_accents(cleaned)
    if no_accent in UNIT_ALIASES:
        return UNIT_ALIASES[no_accent]
    no_dot = no_accent.rstrip(".")
    return UNIT_ALIASES.get(no_dot, cleaned)


def get_dimension(unit: str | None) -> str | None:
    definition = UNIT_DEFINITIONS.get(normalize_unit(unit))
    return definition[0] if definition else None


def is_known_unit(unit: str | None) -> bool:
    return get_dimension(unit) is not None


def are_compatible(unit_a: str | None, unit_b: str | None) -> bool:
    """Deux unités sont compatibles si elles sont identiques ou de même dimension."""
    norm_a, norm_b = normalize_unit(unit_a), normalize_unit(unit_b)
    if norm_a and norm_a == norm_b:
        return True
    dim_a, dim_b = get_dimension(norm_a), get_dimension(norm_b)
    return dim_a is not None and dim_a == dim_b


def convert(quantity: float, from_unit: str, to_unit: str) -> float:
    """Convertit une quantité ; lève UnitConversionError si impossible."""
    norm_from, norm_to = normalize_unit(from_unit), normalize_unit(to_unit)
    if norm_from == norm_to and norm_from:
        return float(quantity)
    def_from, def_to = UNIT_DEFINITIONS.get(norm_from), UNIT_DEFINITIONS.get(norm_to)
    if not def_from or not def_to:
        raise UnitConversionError(f"Unité inconnue : « {from_unit} » ou « {to_unit} ».")
    if def_from[0] != def_to[0]:
        raise UnitConversionError(
            f"Impossible de convertir « {from_unit} » en « {to_unit} » (dimensions différentes).")
    return float(quantity) * def_from[1] / def_to[1]


def try_convert(quantity: float, from_unit: str, to_unit: str) -> float | None:
    try:
        return convert(quantity, from_unit, to_unit)
    except UnitConversionError:
        return None


def to_base_unit(quantity: float, unit: str) -> tuple[float, str]:
    """Convertit vers l'unité de base de la dimension (g, ml ou unité)."""
    dimension = get_dimension(unit)
    if dimension is None:
        return float(quantity), normalize_unit(unit) or "unité"
    base = BASE_UNITS[dimension]
    return convert(quantity, unit, base), base


def format_quantity(quantity: float | None, unit: str | None = "") -> str:
    if quantity is None:
        return unit or "—"
    text = f"{quantity:.2f}".rstrip("0").rstrip(".") if quantity % 1 else str(int(quantity))
    return f"{text} {unit}".strip()


# --- Analyse des mesures TheMealDB ("200g", "1 1/2 cups", "½ tsp", "to taste") ---

_UNICODE_FRACTIONS = {"½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4", "¾": "3/4",
                      "⅛": "1/8", "⅕": "1/5"}
_NUMBER_RE = re.compile(
    r"^\s*(?P<num>\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)(?:\s*-\s*\d+(?:[.,]\d+)?)?\s*(?P<rest>.*)$")


def _parse_number(raw: str) -> float:
    raw = raw.replace(",", ".").strip()
    if " " in raw:  # nombre mixte "1 1/2"
        whole, frac = raw.split(None, 1)
        return float(int(whole) + Fraction(frac))
    if "/" in raw:
        return float(Fraction(raw))
    return float(raw)


def parse_measure(measure: str | None) -> tuple[float | None, str]:
    """Extrait (quantité, unité canonique) d'une mesure texte libre.

    - "200g"        -> (200.0, "g")
    - "1 1/2 cups"  -> (1.5, "tasse")
    - "3"           -> (3.0, "unité")
    - "to taste"    -> (None, "")
    """
    if not measure or not measure.strip():
        return None, ""
    text = measure.strip()
    for symbol, ascii_frac in _UNICODE_FRACTIONS.items():
        text = text.replace(symbol, f" {ascii_frac}")
    text = " ".join(text.split())
    match = _NUMBER_RE.match(text)
    if not match:
        first = text.split()[0].lower()
        unit = normalize_unit(first)
        return None, unit if is_known_unit(unit) else ""
    try:
        quantity = _parse_number(match.group("num"))
    except (ValueError, ZeroDivisionError):
        return None, ""
    if quantity <= 0:
        return None, ""
    rest = match.group("rest").strip().lower()
    if not rest:
        return quantity, "unité"
    tokens = rest.replace("(", " ").replace(")", " ").split()
    # on teste d'abord les unités en deux mots ("c. à soupe" n'est pas utilisé par l'API)
    for size in (3, 2, 1):
        candidate = normalize_unit(" ".join(tokens[:size]))
        if is_known_unit(candidate):
            return quantity, candidate
    return quantity, "unité"


# --- Poids moyens à la pièce : permet de comparer "2 oignons" à "500 g d'oignons" ---
AVERAGE_PIECE_WEIGHTS_G: dict[str, float] = {
    "onion": 150, "oignon": 150, "red onion": 150, "oignon rouge": 150, "shallot": 30, "echalote": 30,
    "egg": 60, "oeuf": 60, "tomato": 120, "tomate": 120, "carrot": 100, "carotte": 100,
    "potato": 180, "pomme de terre": 180, "garlic": 5, "ail": 5, "garlic clove": 5,
    "lemon": 100, "citron": 100, "lime": 70, "citron vert": 70, "apple": 150, "pomme": 150,
    "banana": 120, "banane": 120, "courgette": 200, "zucchini": 200, "aubergine": 250,
    "eggplant": 250, "pepper": 160, "poivron": 160, "red pepper": 160, "green pepper": 160,
    "cucumber": 300, "concombre": 300, "leek": 200, "poireau": 200, "avocado": 170, "avocat": 170,
    "chicken breast": 150, "blanc de poulet": 150, "filet de poulet": 150, "orange": 180,
    "mushroom": 20, "champignon": 20, "bread": 250, "pain": 250, "baguette": 250,
}


def piece_weight(canonical_names: list[str] | tuple[str, ...]) -> float | None:
    for name in canonical_names:
        if name in AVERAGE_PIECE_WEIGHTS_G:
            return AVERAGE_PIECE_WEIGHTS_G[name]
    return None


def convert_for_ingredient(quantity: float, from_unit: str, to_unit: str,
                           canonical_names: list[str] | tuple[str, ...] = ()) -> float | None:
    """Comme try_convert, avec en plus pièce <-> masse via un poids moyen connu."""
    direct = try_convert(quantity, from_unit, to_unit)
    if direct is not None:
        return direct
    weight = piece_weight(canonical_names)
    if weight is None:
        return None
    dim_from, dim_to = get_dimension(from_unit), get_dimension(to_unit)
    if dim_from == COUNT and dim_to == MASS:
        grams = convert(quantity, from_unit, "unité") * weight
        return convert(grams, "g", to_unit)
    if dim_from == MASS and dim_to == COUNT:
        pieces = convert(quantity, from_unit, "g") / weight
        return convert(pieces, "unité", to_unit)
    return None
