"""Tableau de bord (§2.5, T10)."""
import pandas as pd
import streamlit as st

from app.pages._shared import allergens, qty, services, show_flash, user_action, warning_days

container = services()
st.title("🏠 Tableau de bord")
show_flash()

products = container.inventory.get_inventory()
alerts = container.expiration.get_alerts(warning_days=warning_days(), products=products)
summary = container.analytics.generate_summary()

if not any(p.get_available_lots() for p in products):
    st.info("Votre inventaire est vide. Ajoutez des produits depuis la page **Inventaire**, "
            "ou chargez le jeu de démonstration.")
    if st.button("Charger l'inventaire de démonstration", type="primary"):
        with user_action("Inventaire de démonstration chargé."):
            container.inventory.import_sample_inventory(container.settings.data_dir / "sample_inventory.csv")
    st.stop()

urgent = [a for a in alerts if a.status == "urgent"]
expired = [a for a in alerts if a.status == "expired"]
col1, col2, col3, col4 = st.columns(4)
col1.metric("Produits en stock", summary["products_in_stock"])
col2.metric("Lots", summary["lots_in_stock"])
col3.metric("🟠 À consommer vite", len(urgent))
col4.metric("🔴 Dépassés", len(expired))

left, right = st.columns([1, 1])
with left:
    st.subheader("⚠️ Alertes")
    if not urgent and not expired:
        st.success("Aucun produit à risque. 👌")
    for alert in expired:
        st.error(alert.message)
    for alert in urgent:
        st.warning(alert.message)

with right:
    st.subheader("🍲 Recettes recommandées")
    matches, warnings = container.recommendation.recommend_recipes(
        products=products, allergens=allergens(), limit=3)
    for message in warnings:
        st.info(message)
    for match in matches:
        with st.container(border=True):
            badge = " · ♻️ anti-gaspillage" if match.is_anti_waste else ""
            st.markdown(f"**{match.recipe.name}** — score {match.score:.2f}{badge}")
            st.progress(match.coverage, text=f"Ingrédients disponibles : {match.coverage_percent:.0f} %")
            if match.urgent_products:
                st.caption("Utilise en priorité : " + ", ".join(match.urgent_products))
            if st.button("Voir la recette", key=f"dash_recipe_{match.recipe.id}"):
                st.session_state["selected_recipe_id"] = match.recipe.id
                st.switch_page("pages/recipes.py")

st.subheader("Répartition par catégorie")
distribution = summary["category_distribution"]
if distribution:
    st.bar_chart(pd.DataFrame({"Produits": distribution}), horizontal=True)

start, end = summary["period"]
st.subheader(f"Activité des {(end - start).days} derniers jours")
c1, c2, c3 = st.columns(3)
c1.metric("Consommé", " · ".join(qty(v, u) for u, v in summary["consumption"].items()) or "—")
c2.metric("Jeté", " · ".join(qty(v, u) for u, v in summary["waste"].items()) or "—")
rate = summary["waste_rate"]
c3.metric("Taux de gaspillage", f"{rate:.0%}" if rate is not None else "Données insuffisantes",
          help="Moyenne sur les produits ayant un historique suffisant (BR17).")
