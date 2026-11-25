"""Tests des utilitaires : unités (BR07) et validation / normalisation."""
from datetime import date, timedelta

import pytest

from app.exceptions.domain_exceptions import UnitConversionError, ValidationError
from app.utils import unit_converter as units
from app.utils import validators


class TestUnitConverter:
    @pytest.mark.parametrize("raw, expected", [("Grammes", "g"), ("KG", "kg"), ("litres", "l"),
                                               ("pièce", "unité"), ("tbsp", "c. à soupe"),
                                               ("cups", "tasse"), ("cl", "cl")])
    def test_normalize(self, raw, expected):
        assert units.normalize_unit(raw) == expected

    def test_convert_same_dimension(self):
        assert units.convert(1.5, "kg", "g") == 1500
        assert units.convert(25, "cl", "l") == pytest.approx(0.25)

    def test_convert_different_dimension_fails(self):
        with pytest.raises(UnitConversionError):
            units.convert(1, "kg", "l")

    def test_compatibility(self):
        assert units.are_compatible("g", "kg")
        assert not units.are_compatible("g", "ml")
        assert units.are_compatible("boîte", "boîte")  # unité inconnue mais identique

    @pytest.mark.parametrize("measure, expected", [
        ("200g", (200, "g")), ("1 1/2 cups", (1.5, "tasse")), ("½ tsp", (0.5, "c. à café")),
        ("3", (3, "unité")), ("2 large", (2, "unité")), ("1 litre", (1, "l")),
        ("to taste", (None, "")), ("", (None, "")), ("Pinch", (None, "pincée")),
        ("2-3 tbsp", (2, "c. à soupe")), ("1,5 kg", (1.5, "kg")),
    ])
    def test_parse_measure(self, measure, expected):
        assert units.parse_measure(measure) == expected

    def test_piece_weight_conversion(self):
        assert units.convert_for_ingredient(2, "unité", "g", ("onion",)) == 300
        assert units.convert_for_ingredient(300, "g", "unité", ("oignon",)) == 2
        assert units.convert_for_ingredient(2, "unité", "g", ("inconnu",)) is None

    def test_to_base_unit(self):
        assert units.to_base_unit(2, "kg") == (2000, "g")
        assert units.to_base_unit(3, "unité") == (3, "unité")


class TestValidators:
    @pytest.mark.parametrize("raw, expected", [("  Tomates  Cerises ", "tomate cerise"),
                                               ("Crème fraîche", "creme fraiche"),
                                               ("Œufs", "oeuf"), ("Huile d'olive", "huile d olive")])
    def test_normalize_name(self, raw, expected):
        assert validators.normalize_name(raw) == expected

    def test_quantities(self):
        assert validators.validate_positive("1,5") == 1.5
        with pytest.raises(ValidationError):
            validators.validate_positive(0)
        with pytest.raises(ValidationError):
            validators.validate_non_negative(-1)
        with pytest.raises(ValidationError):
            validators.parse_quantity("abc")

    def test_dates(self):
        today = date.today()
        with pytest.raises(ValidationError):
            validators.validate_purchase_date(today + timedelta(days=1))
        with pytest.raises(ValidationError):
            validators.validate_expiration_date(today - timedelta(days=1), today)
        with pytest.raises(ValidationError):
            validators.validate_period(today, today - timedelta(days=1))

    def test_non_empty(self):
        with pytest.raises(ValidationError):
            validators.validate_non_empty("  ", "nom")
