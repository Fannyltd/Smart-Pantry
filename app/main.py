"""Point d'entrée de Smart Pantry.

Lancement depuis la racine du projet :

    streamlit run app/main.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="Smart Pantry", page_icon="🥫", layout="wide")

from app.pages._shared import services  # noqa: E402

PAGES_DIR = Path(__file__).parent / "pages"


def sidebar() -> None:
    container = services()
    settings = container.settings
    with st.sidebar:
        st.markdown("### Préférences")
        st.session_state.setdefault("allergens", list(settings.user_allergens))
        st.multiselect(
            "Allergènes à exclure", key="allergens", accept_new_options=True,
            options=sorted(set(st.session_state["allergens"]) | {
                "arachide", "lait", "oeuf", "gluten", "noix", "poisson", "crevette", "soja",
                "sesame", "moutarde", "celeri"}),
            help="Les recettes contenant ces ingrédients ne sont pas recommandées.")
        st.session_state.setdefault("warning_days", settings.expiration_warning_days)
        st.slider("Alerte « bientôt périmé » (jours)", 0, 14, key="warning_days")
        st.divider()
        if container.recipes.api_available:
            st.caption("🌐 TheMealDB activée")
        else:
            st.caption("📴 TheMealDB désactivée (recettes locales uniquement)")
        st.caption("Smart Pantry — moins de gaspillage, plus de recettes.")


def main() -> None:
    pages = [
        st.Page(PAGES_DIR / "dashboard.py", title="Tableau de bord", icon="🏠", default=True),
        st.Page(PAGES_DIR / "inventory.py", title="Inventaire", icon="📦"),
        st.Page(PAGES_DIR / "expiration.py", title="Péremptions", icon="⏰"),
        st.Page(PAGES_DIR / "recipes.py", title="Recettes", icon="🍲"),
        st.Page(PAGES_DIR / "shopping.py", title="Liste de courses", icon="🛒"),
        st.Page(PAGES_DIR / "analytics.py", title="Statistiques", icon="📊"),
    ]
    navigation = st.navigation(pages)
    sidebar()
    navigation.run()


main()
