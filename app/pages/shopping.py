"""F4 — Liste de courses (ajout manuel, génération, achat, validation en stock)."""
from datetime import date, timedelta

import streamlit as st

from app.pages._shared import UNIT_CHOICES, qty, services, show_flash, user_action

container = services()
shopping = container.shopping
st.title("🛒 Liste de courses")
show_flash()

with st.form("add_item", clear_on_submit=True):
    c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
    name = c1.text_input("Article", placeholder="ex. Lait")
    quantity = c2.number_input("Quantité", min_value=0.0, value=1.0, step=0.5)
    unit = c3.selectbox("Unité", UNIT_CHOICES, index=5)
    c4.write("")
    if c4.form_submit_button("Ajouter", type="primary"):
        with user_action(f"{name} ajouté à la liste."):
            shopping.add_item(name, quantity, unit)

shopping_list = shopping.get_shopping_list()
products = container.inventory.get_inventory()
to_buy = shopping_list.get_missing_items()
purchased = [item for item in shopping_list.items if item.is_purchased]

st.subheader(f"À acheter ({len(to_buy)})")
if not to_buy:
    st.caption("Rien à acheter pour le moment.")
for item in to_buy:
    info = shopping.get_stock_info(item, products)
    c1, c2, c3, c4 = st.columns([4, 3, 1, 1])
    if c1.checkbox(f"**{item.name}** — {qty(item.quantity, item.unit)}", key=f"buy_{item.id}"):
        with user_action():
            shopping.mark_as_purchased(item.id)
    if info.in_stock_quantity > 0:
        text = f"Déjà en stock : {qty(round(info.in_stock_quantity, 2), item.unit)}"
        (c2.warning if info.already_covered else c2.caption)(
            text + (" — achat peut-être inutile" if info.already_covered else ""))
    with c3.popover("✏️"):
        new_name = st.text_input("Nom", value=item.name, key=f"n_{item.id}")
        new_quantity = st.number_input("Quantité", min_value=0.0, value=float(item.quantity), key=f"q_{item.id}")
        new_unit = st.text_input("Unité", value=item.unit, key=f"u_{item.id}")
        if st.button("Enregistrer", key=f"save_{item.id}"):
            with user_action("Article modifié."):
                shopping.update_item(item.id, new_name, new_quantity, new_unit)
    if c4.button("🗑️", key=f"del_{item.id}"):
        with user_action("Article supprimé."):
            shopping.remove_item(item.id)

st.subheader(f"Achetés ({len(purchased)})")
st.caption("Cocher un article ne modifie pas le stock : validez l'ajout pour qu'il entre "
           "dans l'inventaire avec sa date de péremption (RM09 / BR14).")
categories = container.inventory.get_categories() or ["Autre"]
for item in purchased:
    with st.expander(f"✅ {item.name} — {qty(item.quantity, item.unit)}"):
        with st.form(f"confirm_{item.id}"):
            c1, c2, c3, c4 = st.columns(4)
            real_quantity = c1.number_input("Quantité achetée", min_value=0.0, value=float(item.quantity))
            expiration = c2.date_input("Péremption", value=date.today() + timedelta(days=7),
                                       min_value=date.today(), format="DD/MM/YYYY")
            expiration_type = c3.selectbox("Type", ["DLC", "DDM"])
            category = c4.selectbox("Catégorie (si nouveau produit)", categories)
            ok, undo = st.columns(2)
            if ok.form_submit_button("Ajouter au stock", type="primary"):
                with user_action(f"{item.name} ajouté à l'inventaire."):
                    shopping.confirm_purchase(item.id, expiration, category, expiration_type, real_quantity)
            if undo.form_submit_button("Décocher"):
                with user_action():
                    shopping.mark_as_not_purchased(item.id)
if purchased and st.button("Retirer les articles achetés sans les ajouter au stock"):
    with user_action("Articles retirés."):
        shopping.clear_purchased()
