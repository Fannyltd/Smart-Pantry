"""F3 — Catalogue, recommandation et détail d'une recette."""
import pandas as pd
import streamlit as st

from app.exceptions.domain_exceptions import SmartPantryError
from app.pages._shared import (allergens, flash, qty, services, show_flash, show_warnings,
                               user_action)

container = services()
settings = container.settings
st.title("🍲 Recettes")
show_flash()


TAB_RECO, TAB_SEARCH, TAB_DETAIL = "⭐ Recommandations", "🔎 Recherche", "📖 Détail"


def select_recipe(recipe_id: int) -> None:
    """Mémorise la recette choisie et ouvre directement l'onglet « Détail »."""
    st.session_state["selected_recipe_id"] = recipe_id
    st.session_state["recipes_tab"] = TAB_DETAIL


def recipe_card(match, key_prefix: str) -> None:
    recipe = match.recipe
    with st.container(border=True):
        cols = st.columns([1, 3])
        if recipe.image_url:
            cols[0].image(recipe.image_url, width="stretch")
        with cols[1]:
            tags = [match.status]
            if match.is_anti_waste:
                tags.append("♻️ anti-gaspillage")
            if recipe.external_id and recipe.external_id.startswith("mealdb:"):
                tags.append("TheMealDB")
            st.markdown(f"#### {recipe.name}")
            st.caption(" · ".join(tags) + (f" · {recipe.category}" if recipe.category else ""))
            st.progress(match.coverage, text=f"Couverture C = {match.coverage_percent:.0f} % · "
                                             f"Priorité P = {match.priority:.2f} · Score = {match.score:.2f}")
            if match.urgent_products:
                st.markdown("Utilise en priorité : **" + ", ".join(match.urgent_products) + "**")
            if match.missing:
                st.markdown("Manque : " + ", ".join(i.name for i in match.missing))
            st.button("Voir le détail", key=f"{key_prefix}_{recipe.id}", on_click=select_recipe,
                      args=(recipe.id,))


tab_reco, tab_search, tab_detail = st.tabs([TAB_RECO, TAB_SEARCH, TAB_DETAIL], key="recipes_tab",
                                           on_change="rerun")

# ---------------------------------------------------------------- recommandations
with tab_reco:
    st.caption(f"Score(r) = {settings.coverage_weight} × C(r) + {settings.priority_weight} × P(r) — "
               "C : part des ingrédients réellement disponibles (quantités comprises), "
               "P : urgence des produits utilisés.")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        use_api = st.toggle("Interroger aussi TheMealDB", value=False,
                            disabled=not container.recipes.api_available,
                            help="Recherche ingrédient par ingrédient (API V1), les plus urgents d'abord.")
    servings = c2.number_input("Portions", min_value=0, value=0, help="0 = portions de la recette")
    only_doable = c3.checkbox("Réalisables uniquement")
    with st.spinner("Calcul des recommandations…"):
        matches, warnings = container.recommendation.recommend_recipes(
            include_api=use_api, allergens=allergens(), servings=servings or None)
    show_warnings(warnings)
    if only_doable:
        matches = [m for m in matches if not m.missing]
        if not matches:
            st.info("Aucune recette entièrement réalisable : essayez sans ce filtre.")
    for match in matches[:20]:
        recipe_card(match, "reco")

# ---------------------------------------------------------------- recherche
with tab_search:
    categories, cat_warnings = container.recipes.categories()
    show_warnings(cat_warnings)
    with st.form("search"):
        c1, c2, c3 = st.columns([2, 1, 1])
        text = c1.text_input("Nom ou ingrédient", placeholder="ex. chicken, poulet, curry…")
        category = c2.selectbox("Catégorie", [""] + categories)
        mode = c3.radio("Rechercher par", ["Nom", "Ingrédient"], horizontal=True)
        submitted = st.form_submit_button("Rechercher", type="primary")
    if submitted:
        with st.spinner("Recherche…"):
            if mode == "Ingrédient" and text:
                results, warnings = container.recipes.search_by_ingredient(text)
            else:
                results, warnings = container.recipes.search(text or None, category or None)
        st.session_state["search_results"] = [r.id for r in results]
        show_warnings(warnings)
    random_col, _ = st.columns([1, 3])
    if random_col.button("🎲 Idée de repas au hasard", disabled=not container.recipes.api_available):
        recipe, warnings = container.recipes.random_recipe()
        show_warnings(warnings)
        if recipe:
            st.session_state["search_results"] = [recipe.id]
    products = container.inventory.get_inventory()
    for recipe_id in st.session_state.get("search_results", []):
        try:
            recipe = container.recipes.get_recipe(recipe_id)
        except SmartPantryError:
            continue
        recipe_card(container.recommendation.calculate_match_score(recipe, products), "search")

# ---------------------------------------------------------------- détail
with tab_detail:
    recipe_id = st.session_state.get("selected_recipe_id")
    if recipe_id is None:
        st.info("Sélectionnez une recette dans les recommandations ou la recherche.")
    else:
        try:
            recipe = container.recipes.get_recipe(recipe_id)
        except SmartPantryError as exc:
            st.error(str(exc))
            st.stop()
        st.subheader(recipe.name)
        portions = st.number_input("Portions", min_value=1, value=recipe.servings, key="detail_servings")
        match = container.recommendation.calculate_match_score(recipe, servings=portions)
        c1, c2 = st.columns([1, 2])
        if recipe.image_url:
            c1.image(recipe.image_url, width="stretch")
        with c2:
            st.markdown(f"**Statut :** {match.status} · **Couverture :** {match.coverage_percent:.0f} %")
            st.caption(match.explanation(settings.coverage_weight, settings.priority_weight))
            if recipe.preparation_time:
                st.markdown(f"⏱️ {recipe.preparation_time} min")
            found_allergens = container.recommendation.matcher.contains_allergen(recipe, allergens())
            if found_allergens:
                st.error("Contient : " + ", ".join(found_allergens))
        rows = [{
            "": "✅" if status.is_available else ("⚠️" if status.matched_products else "❌"),
            "Ingrédient": status.name,
            "Nécessaire": qty(round(status.required_quantity, 2) if status.required_quantity else None,
                              status.unit),
            "En stock": qty(round(status.available_quantity, 2), status.unit)
            if status.comparable and status.matched_products else "—",
            "Manque": qty(round(status.missing_quantity, 2), status.unit)
            if status.missing_quantity else "",
            "Remarque": status.note,
        } for status in match.ingredients]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

        a1, a2 = st.columns(2)
        if a1.button("🛒 Ajouter les manquants à la liste", disabled=not match.missing):
            with user_action():
                added = container.shopping.generate_shopping_list(recipe, servings=portions)
                flash(f"{len(added)} article(s) ajouté(s) à la liste de courses."
                      if added else "Rien à acheter : le stock couvre déjà les besoins.")
        allow_partial = a2.checkbox("Autoriser une préparation partielle")
        if a2.button("👩‍🍳 J'ai cuisiné cette recette", type="primary"):
            with user_action():
                report = container.cooking.cook_recipe(recipe, portions, allow_partial)
                flash(f"Stock mis à jour : {len(report.consumptions)} consommation(s) enregistrée(s).")
                for skipped in report.skipped:
                    flash(skipped, "info")

        st.markdown("#### Instructions")
        st.write(recipe.instructions)
