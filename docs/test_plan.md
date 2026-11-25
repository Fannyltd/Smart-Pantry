# Smart Pantry — Plan de tests

## Organisation

| Dossier | Portée | Outils |
|---------|--------|--------|
| `tests/unit/` | Modèles du domaine, utilitaires, matching et score (sans base) | pytest |
| `tests/integration/` | Services + repositories + SQLite en mémoire + faux client TheMealDB | pytest |
| `tests/conftest.py` | Fixtures : `container` (application complète), `FakeMealDBClient` (avec option panne) | |

Lancement : `pytest` (ou `pytest --cov=app` avec `pytest-cov`).
Les tests ne font **aucun appel réseau** : TheMealDB est simulée par `FakeMealDBClient`.

## Scénarios du cahier des charges (§9)

| Test | Scénario | Résultat attendu | Test automatisé |
|------|----------|------------------|-----------------|
| T01 | Ajouter un aliment | L'aliment apparaît dans l'inventaire | `test_t01_add_product_appears_in_inventory` |
| T02 | Modifier une quantité | La nouvelle quantité est enregistrée (et historisée) | `test_t02_update_quantity_is_saved_and_historised` |
| T03 | Supprimer un aliment | L'aliment disparaît | `test_t03_delete_product` |
| T04 | Date proche de péremption | Produit signalé (orange) | `test_t04_expiring_product_flagged` |
| T05 | Recette avec un ingrédient disponible | Recettes proposées | `test_t05_search_by_available_ingredient` |
| T06 | Consulter une recette | Ingrédients et instructions affichés | `test_t06_recipe_details_are_cached` |
| T07 | Plusieurs ingrédients disponibles | Résultats comparés au stock | `test_t07_api_results_compared_with_stock` |
| T08 | Ingrédients manquants | Manquants identifiés et ajoutables à la liste | `test_t08_missing_ingredients_identified_and_listed` |
| T09 | TheMealDB indisponible | Message compréhensible, recettes locales conservées | `test_t09_api_unavailable_gives_clear_message` |
| T10 | Tableau de bord | Informations correctes | `test_demo_scenario` + vérification manuelle |

## Règles métier

| Règle | Test |
|-------|------|
| RM01 / BR02 | `test_quantity_never_negative`, `test_initial_quantity_must_be_positive` |
| RM02 / RM03 | `test_several_lots_same_product` |
| RM04 / BR05 | `test_consumption_cannot_exceed_stock` (unitaire et intégration), `test_cooking_is_atomic` |
| BR01, BR03, BR04, BR11 | `test_invalid_input_rejected`, `TestFoodLot` |
| BR06 | `test_movements_are_historised`, `test_t02_…` |
| BR07 | `TestUnitConverter`, `test_incompatible_lot_unit_refused`, `test_unit_conversion` |
| BR08-BR10 | `test_expiration_status`, `test_t04_…`, `test_expired_and_discard` |
| RM06 (300 g vs 50 g) | `test_quantities_are_taken_into_account` |
| RM07 / BR12 | `test_urgent_recipes_ranked_first`, `test_t07_…` (ordre des requêtes API) |
| Allergènes | `test_allergens_excluded`, `test_allergen_detection` |
| RM08 / BR13 | `test_t08_…` |
| RM09 / BR14 | `test_purchase_requires_confirmation`, `test_mark_as_purchased_does_not_touch_stock` |
| BR15-BR17 | `test_analytics_period_and_history` |

## Scénario de démonstration (MVP)

`test_demo_scenario` enchaîne : ajout de produits dont certains expirent bientôt → produits prioritaires identifiés → recette adaptée recommandée → manquants ajoutés à la liste → consommation validée → stock actualisé → indicateurs recalculés.

## Tests manuels de l'interface

1. Base vide → « Charger l'inventaire de démonstration » sur le tableau de bord.
2. Vérifier les couleurs (rouge / orange / vert) sur la page Péremptions.
3. Recettes → activer « Interroger aussi TheMealDB » (connexion internet requise), ouvrir un détail.
4. « Ajouter les manquants à la liste », puis sur la page Liste de courses : cocher, puis « Ajouter au stock ».
5. « J'ai cuisiné cette recette » → vérifier l'inventaire et la page Statistiques.
6. Couper le réseau (ou `API_ENABLED=false`) → un message clair s'affiche, l'application reste utilisable.
7. Affichage sur mobile et tablette (mise en page Streamlit responsive).
