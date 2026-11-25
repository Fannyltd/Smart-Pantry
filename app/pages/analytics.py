"""F5 — Statistiques de consommation et de gaspillage (BR15 à BR17)."""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from app.pages._shared import MOVEMENT_LABELS, qty, services, show_flash

container = services()
analytics = container.analytics
st.title("📊 Statistiques")
show_flash()

default_start, default_end = analytics.default_period()
period = st.date_input("Période analysée", value=(default_start, default_end),
                       max_value=date.today(), format="DD/MM/YYYY")
if not isinstance(period, tuple) or len(period) != 2:
    st.info("Choisissez une date de début et une date de fin.")
    st.stop()
start, end = period
summary = analytics.generate_summary(start, end)


def fmt(totals: dict) -> str:
    return " · ".join(qty(value, unit) for unit, value in totals.items()) or "—"


c1, c2, c3, c4 = st.columns(4)
c1.metric("Entrées", fmt(summary["entries"]))
c2.metric("Consommé", fmt(summary["consumption"]))
c3.metric("Jeté", fmt(summary["waste"]))
rate = summary["waste_rate"]
c4.metric("Taux de gaspillage", f"{rate:.0%}" if rate is not None else "n/d")
st.caption(f"Taux calculé sur {summary['products_with_enough_history']} produit(s) ayant au moins "
           f"{container.settings.min_history_movements} mouvements sur la période "
           f"({summary['products_with_movements']} produit(s) avec des mouvements). "
           "Les autres ne font pas l'objet de conclusions (BR17).")

st.subheader("Mouvements par jour")
timeline = pd.DataFrame(analytics.movements_timeline(start, end)).set_index("date")
timeline = timeline.rename(columns=MOVEMENT_LABELS)
if timeline.to_numpy().sum():
    st.bar_chart(timeline, color=["#4c9a2a", "#2b6cb0", "#c0392b"])
else:
    st.info("Aucun mouvement sur cette période.")

left, right = st.columns(2)
with left:
    st.subheader("Par produit")
    stats = analytics.waste_by_product(start, end)
    if stats:
        st.dataframe(pd.DataFrame([{
            "Produit": s.product_name, "Consommé": qty(s.consumed, s.unit), "Jeté": qty(s.wasted, s.unit),
            "Mouvements": s.movements,
            "Gaspillage": f"{s.waste_rate:.0%}" if s.waste_rate is not None else "historique insuffisant",
        } for s in stats]), hide_index=True, width="stretch")
with right:
    st.subheader("Stock par catégorie")
    distribution = summary["category_distribution"]
    if distribution:
        st.bar_chart(pd.DataFrame({"Produits": distribution}), horizontal=True)

st.subheader("Historique des mouvements")
history = analytics.movement_history(start, end)
if history:
    st.dataframe(pd.DataFrame([{
        "Date": r.movement_date.strftime("%d/%m/%Y %H:%M"), "Type": MOVEMENT_LABELS[r.movement_type],
        "Produit": r.product_name, "Quantité": qty(round(r.quantity, 2), r.unit),
    } for r in history]), hide_index=True, width="stretch")
