"""Éléments partagés par les pages Streamlit (pas une page)."""
from __future__ import annotations

from contextlib import contextmanager

import streamlit as st

from app.exceptions.domain_exceptions import SmartPantryError
from app.services import ServiceContainer, get_services
from app.utils.unit_converter import format_quantity

UNIT_CHOICES = ["g", "kg", "ml", "cl", "l", "unité"]
MOVEMENT_LABELS = {"entry": "Entrée", "consumption": "Consommation", "waste": "Gaspillage"}


def services() -> ServiceContainer:
    return get_services()


def allergens() -> list[str]:
    return list(st.session_state.get("allergens", services().settings.user_allergens))


def warning_days() -> int:
    return int(st.session_state.get("warning_days", services().settings.expiration_warning_days))


def flash(message: str, kind: str = "success") -> None:
    """Message à afficher après le prochain rerun."""
    st.session_state.setdefault("_flash", []).append((kind, message))


def show_flash() -> None:
    for kind, message in st.session_state.pop("_flash", []):
        getattr(st, kind)(message)


@contextmanager
def user_action(success_message: str | None = None, rerun: bool = True):
    """Exécute une action utilisateur : erreurs métier affichées proprement."""
    try:
        yield
    except SmartPantryError as exc:
        st.error(str(exc))
        return
    if success_message:
        flash(success_message)
    if rerun:
        st.rerun()


def qty(quantity: float | None, unit: str | None = "") -> str:
    return format_quantity(quantity, unit)


def show_warnings(messages: list[str]) -> None:
    for message in messages:
        st.info(message)
