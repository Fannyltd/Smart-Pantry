# Smart Pantry — Exigences et traçabilité

Ce document résume les exigences du cahier des charges et du MVP, et indique
où chacune est implémentée et testée.

## 1. Exigences fonctionnelles (cahier des charges §4.1)

| Réf. | Exigence | Priorité | Implémentation | Tests |
|------|----------|----------|----------------|-------|
| F01 | Ajouter un aliment | Indispensable | `InventoryService.add_product_with_lot`, page Inventaire | T01 |
| F02 | Modifier et supprimer un aliment | Indispensable | `update_product`, `update_lot`, `delete_product`, `delete_lot` | T02, T03 |
| F03 | Quantités et dates de péremption | Indispensable | `FoodLot`, `InventoryService.add_food_lot` | `test_invalid_input_rejected` |
| F04 | Produits proches de leur péremption | Indispensable | `ExpirationService.get_alerts`, page Péremptions | T04 |
| F05 | Rechercher des recettes avec TheMealDB | Indispensable | `TheMealDBClient`, `RecipeService.search*` | T05 |
| F06 | Détail d'une recette | Indispensable | onglet Détail de la page Recettes | T06 |
| F07 | Comparer ingrédients et stock | Indispensable | `RecipeRecommendationService.evaluate_ingredient` | T07, T08 |
| F08 | Mettre en avant les aliments prioritaires | Indispensable | score P(r), `get_priority_products` | `test_urgent_recipes_ranked_first` |
| F09 | Liste de courses | Souhaitable | `ShoppingListService`, page Liste de courses | `test_purchase_requires_confirmation` |
| F10 | Statistiques de gaspillage | Souhaitable | `AnalyticsService`, page Statistiques | `test_analytics_period_and_history` |
| F11 | Notifications automatiques | Souhaitable | Alertes visuelles (tableau de bord) ; pas de notification push (hors MVP, §8.2) | — |

## 2. Règles métier (MVP)

| ID | Règle | Où |
|----|-------|----|
| RM01 | Quantité jamais négative | `StockMovement._decrease_lot`, contrainte SQL `ck_lot_quantity_non_negative`, `validate_non_negative` |
| RM02 | Plusieurs lots par produit | `FoodProduct.lots`, `find_or_create_product` |
| RM03 | Quantité et date propres à chaque lot | `FoodLot` |
| RM04 | Consommation ≤ stock du lot | `_decrease_lot` → `InsufficientStockError` ; `plan_consumption` vérifie avant toute écriture |
| RM05 | Signaler les produits périmés | `ExpirationService` (rouge) |
| RM06 | Recommandation selon les quantités réelles | C(r) basé sur `min(1, disponible / nécessaire)` |
| RM07 | Priorité aux produits proches de la date | P(r) ; TheMealDB interrogée d'abord avec les ingrédients urgents |
| RM08 | Manquants → liste de courses | `ShoppingListService.generate_shopping_list` |
| RM09 | L'achat ne modifie le stock qu'après confirmation | `mark_as_purchased` (sans effet sur le stock) puis `confirm_purchase` |
| BR01 | Nom non vide | `validate_non_empty`, `FoodProduct.__post_init__` |
| BR02 | Quantité initiale > 0 | `FoodLot.__post_init__`, contrainte SQL |
| BR03 | Date d'achat ≤ aujourd'hui | `validate_purchase_date` |
| BR04 | Péremption ≥ achat | `validate_expiration_date` |
| BR05 | = RM04 | |
| BR06 | Historisation de chaque mouvement | `MovementRepository.record` (lot + mouvement dans la même transaction) ; l'entrée initiale est historisée |
| BR07 | Addition seulement si unités compatibles | `unit_converter.are_compatible / convert` |
| BR08 / BR09 | Dépassé / proche | `FoodLot.get_expiration_status` |
| BR10 | Tri par date croissante | `ExpirationService.get_alerts` |
| BR11 | DLC ≠ DDM | DLC dépassée = inutilisable ; DDM dépassée = utilisable, signalée |
| BR12 | Recommandations : utiliser d'abord | P(r), `priority_ingredient_names` |
| BR13 | La liste tient compte du stock | quantité manquante = nécessaire − disponible |
| BR14 | = RM09 | |
| BR15 | Consommation et gaspillage séparés | `StockConsumption` / `StockWaste`, `calculate_consumption` / `calculate_waste` |
| BR16 | Indicateurs sur une période | tous les calculs prennent `(start, end)` |
| BR17 | Pas de conclusion sans historique | `MIN_HISTORY_MOVEMENTS` (3 par défaut) |

## 3. Score de recommandation

`Score(r) = 0,6 · C(r) + 0,4 · P(r)`

- **C(r)** : moyenne, sur les ingrédients de la recette, de `min(1, quantité disponible / quantité nécessaire)`.
  - les quantités sont converties (g ↔ kg, ml ↔ l, cuillères, tasses) ; « 2 oignons » est comparé à « 500 g d'oignons » grâce à un poids moyen par pièce ;
  - un ingrédient sans quantité (« sel », « to taste ») compte comme disponible s'il est en stock ;
  - un ingrédient en stock dont l'unité n'est pas comparable compte pour 0,5 et est signalé « à vérifier » ;
  - un lot à DLC dépassée ne compte pas.
  - Exemple du MVP : 300 g de fromage demandés, 50 g en stock → contribution 0,17, la recette n'est pas « réalisable ».
- **P(r)** : urgence maximale des produits utilisés, `max(0, 1 − jours_restants / horizon)` avec un horizon de 7 jours (1 = expire aujourd'hui, DDM dépassée = 1).
- **Allergènes** : les recettes contenant un allergène déclaré sont exclues.
- **Statut** : « Réalisable », « Quelques ingrédients à ajouter » (≤ 2 manquants), « Ingrédients insuffisants ».

## 4. Contraintes techniques (§4.2, §4.3)

- API externe TheMealDB V1 (JSON), un ingrédient par requête → recherches successives puis comparaison côté application.
- Pannes de l'API : `ExternalAPIError` avec message compréhensible ; repli sur le catalogue local (`data/recipes.csv`) et le cache.
- Données d'inventaire en base SQLite (SQLAlchemy), indépendante des recettes.
- Normalisation des noms (accents, casse, pluriels) et traduction FR → EN des ingrédients courants ; correspondance approximative (inclusion de mots, similarité).
- Message adapté lorsqu'aucune recette pertinente n'est trouvée.

## 5. Hors périmètre (§8.2)

Reconnaissance d'images, codes-barres, notifications push, multi-utilisateurs, comptes utilisateurs, planification des repas.
