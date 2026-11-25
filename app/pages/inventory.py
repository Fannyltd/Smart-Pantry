"""F1 — Inventaire : ajouter, modifier, supprimer, consulter, plusieurs lots par produit."""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from app.pages._shared import UNIT_CHOICES, qty, services, show_flash, user_action, warning_days

container = services()
inventory = container.inventory
st.title("📦 Inventaire")
show_flash()

tab_list, tab_add, tab_manage = st.tabs(["Mon stock", "➕ Ajouter", "✏️ Modifier / supprimer"])
products = inventory.get_inventory()
categories = inventory.get_categories() or ["Autre"]

# ---------------------------------------------------------------- consultation
with tab_list:
    search = st.text_input("Rechercher un produit", placeholder="ex. tomate")
    category_filter = st.multiselect("Catégories", categories)
    rows = []
    for stock in inventory.get_stock_summary():
        product = stock.product
        if search and search.casefold() not in product.name.casefold():
            continue
        if category_filter and product.category not in category_filter:
            continue
        rows.append({
            "Produit": product.name, "Catégorie": product.category,
            "Quantité totale": qty(round(stock.total_quantity, 2), stock.unit),
            "Lots": stock.lots_count, "Prochaine péremption": stock.next_expiration,
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.info("Aucun produit en stock pour ces critères.")

    st.subheader("Détail des lots")
    for product in products:
        lots = product.get_available_lots()
        if not lots or (search and search.casefold() not in product.name.casefold()):
            continue
        with st.expander(f"{product.name} — {len(lots)} lot(s)"):
            for lot in sorted(lots, key=lambda l: l.expiration_date):
                status = container.expiration.classify_expiration_risk(lot, warning_days=warning_days())
                icon = {"expired": "🔴", "urgent": "🟠", "safe": "🟢"}[status]
                cols = st.columns([3, 2, 2, 2])
                cols[0].markdown(f"{icon} **{qty(lot.quantity, lot.unit)}** · {lot.expiration_type} "
                                 f"{lot.expiration_date:%d/%m/%Y} · acheté le {lot.purchase_date:%d/%m/%Y}")
                amount = cols[1].number_input("Quantité", min_value=0.0, value=float(min(1.0, lot.quantity)),
                                              key=f"amount_{lot.id}", label_visibility="collapsed")
                if cols[2].button("Consommer", key=f"consume_{lot.id}"):
                    with user_action(f"{qty(amount, lot.unit)} de {product.name} consommé(s)."):
                        inventory.consume_food(lot, amount)
                if cols[3].button("Jeter", key=f"waste_{lot.id}"):
                    with user_action(f"{qty(amount, lot.unit)} de {product.name} jeté(s)."):
                        inventory.discard_food(lot, amount)

# ---------------------------------------------------------------- ajout
with tab_add:
    st.caption("Si le produit existe déjà, un nouveau lot lui est ajouté (RM02).")
    with st.form("add_product", clear_on_submit=True):
        existing_names = [""] + [p.name for p in products]
        c1, c2 = st.columns(2)
        picked = c1.selectbox("Produit existant", existing_names,
                              help="Laisser vide pour créer un nouveau produit.")
        new_name = c2.text_input("…ou nouveau produit", placeholder="ex. Tomate")
        c3, c4, c5 = st.columns(3)
        category = c3.selectbox("Catégorie", categories)
        quantity = c4.number_input("Quantité", min_value=0.0, value=1.0, step=0.5)
        unit = c5.selectbox("Unité", UNIT_CHOICES)
        c6, c7, c8 = st.columns(3)
        purchase_date = c6.date_input("Date d'achat", value=date.today(), max_value=date.today(),
                                      format="DD/MM/YYYY")
        expiration_date = c7.date_input("Date de péremption", value=date.today() + timedelta(days=7),
                                        format="DD/MM/YYYY")
        expiration_type = c8.radio("Type de date", ["DLC", "DDM"], horizontal=True,
                                   help="DLC : à consommer jusqu'au. DDM : de préférence avant.")
        if st.form_submit_button("Ajouter au stock", type="primary"):
            name = new_name.strip() or picked
            with user_action(f"{name} ajouté au stock."):
                product = next((p for p in products if p.name == picked), None) if not new_name.strip() else None
                if product:
                    inventory.add_food_lot(product, quantity, unit, purchase_date, expiration_date,
                                           expiration_type)
                else:
                    inventory.add_product_with_lot(name, category, quantity, unit, purchase_date,
                                                   expiration_date, expiration_type)

# ---------------------------------------------------------------- modification
with tab_manage:
    if not products:
        st.info("Aucun produit enregistré.")
        st.stop()
    # On sélectionne par identifiant : comparer deux FoodProduct (dataclasses liées
    # à leurs lots) entre deux exécutions provoquerait une récursion infinie.
    by_id = {p.id: p for p in products}
    product_id = st.selectbox("Produit", list(by_id),
                              format_func=lambda pid: f"{by_id[pid].name} ({by_id[pid].category})")
    product = by_id[product_id]
    with st.form(f"edit_product_{product.id}"):
        st.markdown("**Informations du produit**")
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("Nom", value=product.name)
        category_options = sorted(set(categories) | {product.category})
        category = c2.selectbox("Catégorie", category_options, index=category_options.index(product.category))
        base_unit = c3.text_input("Unité de référence", value=product.base_unit)
        if st.form_submit_button("Enregistrer"):
            with user_action("Produit mis à jour."):
                inventory.update_product(product.id, name, category, base_unit)

    st.markdown("**Lots**")
    for lot in sorted(product.lots, key=lambda l: l.expiration_date):
        with st.form(f"edit_lot_{lot.id}"):
            c1, c2, c3, c4 = st.columns(4)
            new_quantity = c1.number_input(f"Quantité ({lot.unit})", min_value=0.0,
                                           value=float(lot.quantity), key=f"q_{lot.id}")
            new_expiration = c2.date_input("Péremption", value=lot.expiration_date,
                                           min_value=lot.purchase_date, key=f"e_{lot.id}",
                                           format="DD/MM/YYYY")
            new_type = c3.selectbox("Type", ["DLC", "DDM"], index=["DLC", "DDM"].index(lot.expiration_type),
                                    key=f"t_{lot.id}")
            as_waste = c4.checkbox("Baisse = gaspillage", key=f"w_{lot.id}",
                                   help="Une baisse de quantité est historisée comme consommation, "
                                        "ou comme gaspillage si coché (BR06, BR15).")
            save, delete = st.columns(2)
            if save.form_submit_button("Mettre à jour le lot"):
                with user_action("Lot mis à jour."):
                    inventory.update_lot(lot.id, new_quantity, new_expiration, new_type, as_waste)
            if delete.form_submit_button("Supprimer le lot"):
                with user_action("Lot supprimé."):
                    inventory.delete_lot(lot.id)

    st.divider()
    confirm = st.checkbox(f"Je confirme la suppression de « {product.name} » et de tout son historique")
    if st.button("Supprimer le produit", type="secondary", disabled=not confirm):
        with user_action(f"{product.name} supprimé."):
            inventory.delete_product(product.id)
