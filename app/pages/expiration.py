"""F2 — Suivi des dates de péremption (vert / orange / rouge)."""
import pandas as pd
import streamlit as st

from app.pages._shared import qty, services, show_flash, user_action, warning_days
from app.services.expiration_service import TYPE_LABELS

container = services()
st.title("⏰ Péremptions")
show_flash()

alerts = container.expiration.get_alerts(warning_days=warning_days())
if not alerts:
    st.info("Aucun lot en stock.")
    st.stop()

counts = {status: sum(1 for a in alerts if a.status == status) for status in ("expired", "urgent", "safe")}
c1, c2, c3 = st.columns(3)
c1.metric("🔴 Dépassés", counts["expired"])
c2.metric(f"🟠 Sous {warning_days()} jours", counts["urgent"])
c3.metric("🟢 OK", counts["safe"])

shown = st.multiselect("Afficher", ["expired", "urgent", "safe"], default=["expired", "urgent", "safe"],
                       format_func={"expired": "🔴 Dépassés", "urgent": "🟠 Bientôt",
                                    "safe": "🟢 OK"}.get)

COLORS = {"expired": "background-color: #f8d7da", "urgent": "background-color: #ffe5b4",
          "safe": "background-color: #d4edda"}
rows = [{
    "": alert.icon, "Produit": alert.product.name, "Catégorie": alert.product.category,
    "Quantité": qty(alert.lot.quantity, alert.lot.unit), "Type": alert.lot.expiration_type,
    "Date": alert.lot.expiration_date.strftime("%d/%m/%Y"), "Jours restants": alert.days_left,
    "Statut": alert.label, "_status": alert.status,
} for alert in alerts if alert.status in shown]

if rows:
    frame = pd.DataFrame(rows)
    styled = frame.drop(columns="_status").style.apply(
        lambda row: [COLORS[frame.loc[row.name, "_status"]]] * len(row), axis=1)
    st.dataframe(styled, hide_index=True, width="stretch")
st.caption(" · ".join(f"**{k}** : {v}" for k, v in TYPE_LABELS.items()))

st.subheader("À consommer en priorité")
priority = container.expiration.get_priority_products()
if priority:
    for alert in priority:
        st.warning(alert.message)
    if st.button("Voir les recettes qui les utilisent"):
        st.switch_page("pages/recipes.py")
else:
    st.success("Rien d'urgent.")

expired_dlc = [a for a in alerts if a.status == "expired" and a.lot.expiration_type == "DLC"]
if expired_dlc:
    st.subheader("Produits à jeter")
    for alert in expired_dlc:
        st.error(alert.message)
    if st.button(f"Mettre au rebut les {len(expired_dlc)} lot(s) à DLC dépassée",
                 help="Enregistré comme gaspillage dans les statistiques (BR15)."):
        with user_action("Lots périmés mis au rebut."):
            container.inventory.discard_expired_lots()
