# Smart Pantry — Architecture

## Vue d'ensemble

Architecture en couches, chaque couche ne dépend que de celles du dessous :

```
┌──────────────────────────────────────────────────────────┐
│  Présentation   app/main.py + app/pages/*.py (Streamlit) │
├──────────────────────────────────────────────────────────┤
│  Services       app/services/*  (règles d'orchestration) │──► TheMealDB (REST/JSON)
├──────────────────────────────────────────────────────────┤
│  Domaine        app/models/*    (entités + invariants)   │
├──────────────────────────────────────────────────────────┤
│  Repositories   app/repositories/* (domaine ↔ ORM)       │
├──────────────────────────────────────────────────────────┤
│  Persistance    app/database/*  (SQLAlchemy, SQLite)     │
└──────────────────────────────────────────────────────────┘
   Transverse : config/settings.py · exceptions/ · utils/
```

- **Domaine** (`app/models`) : dataclasses pures, sans dépendance technique. Elles portent les invariants (quantité positive, dates cohérentes, consommation ≤ stock) et le polymorphisme des mouvements (`StockMovement` abstrait → `StockEntry`, `StockConsumption`, `StockWaste`).
- **Persistance** (`app/database`) : tables SQLAlchemy distinctes des modèles du domaine, contraintes `CHECK` en filet de sécurité (RM01, BR02).
- **Repositories** : convertissent ORM ↔ domaine. `MovementRepository.record` écrit la nouvelle quantité du lot **et** le mouvement dans une seule transaction.
- **Services** : cas d'usage. Ils valident les saisies (`utils/validators`), traduisent les `ValueError` du domaine en exceptions métier (`exceptions/domain_exceptions`) et coordonnent repositories et API.
- **Présentation** : pages Streamlit qui n'appellent que les services, via `app.services.get_services()`.

## Fichiers

| Dossier | Contenu |
|---------|---------|
| `config/settings.py` | Paramètres (variables d'environnement / `.env`) : base, API, seuils, poids du score |
| `database/connection.py` | Moteur, sessions, création du schéma, chargement de `categories.csv` et `recipes.csv` |
| `database/models.py` | Tables : produits, lots, mouvements, catégories, recettes, ingrédients, listes |
| `repositories/base_repository.py` | Gestion de session/transaction commune |
| `repositories/food_repository.py` | `FoodRepository` (produits, lots, catégories), `ShoppingListRepository` |
| `repositories/recipe_repository.py` | `RecipeRepository` (catalogue local + cache TheMealDB) |
| `repositories/movement_repository.py` | `MovementRepository`, `MovementRecord` (vue à plat pour l'historique) |
| `services/inventory_service.py` | CRUD stock, lots, consommation FEFO, mise au rebut, import CSV |
| `services/expiration_service.py` | Statuts vert/orange/rouge, alertes, urgence normalisée |
| `services/recipe_service.py` | `TheMealDBClient`, `IngredientMatcher`, `RecipeService`, `RecipeRecommendationService` |
| `services/shopping_service.py` | Liste de courses, génération depuis une recette, validation d'achat |
| `services/cooking_service.py` | « J'ai cuisiné » : consommation du stock (FEFO) |
| `services/analytics_service.py` | Consommation, gaspillage, taux, répartition, historique |
| `services/__init__.py` | Assemblage des dépendances (`build_services`, `get_services`) |
| `utils/unit_converter.py` | Unités, conversions, analyse des mesures TheMealDB, poids moyens par pièce |
| `utils/validators.py` | Validation des saisies, normalisation des noms |
| `pages/_shared.py` | Aides d'interface partagées (non affiché comme page) |

## Flux de recommandation (§3.3 du cahier des charges)

1. Le stock est lu ; chaque produit utilisable reçoit une urgence (0 à 1).
2. Les noms des produits, triés du plus urgent au moins urgent, sont traduits en anglais (`IngredientMatcher`).
3. Pour les `MAX_API_INGREDIENTS` premiers : `filter.php?i=<ingrédient>` (V1 : un ingrédient par appel).
4. Les identifiants obtenus sont détaillés via `lookup.php?i=<id>` (au plus `MAX_API_RECIPES`), puis **mis en cache** en base.
5. Les recettes locales et en cache sont fusionnées ; les recettes contenant un allergène sont exclues.
6. Chaque recette reçoit C(r), P(r) et le score ; tri par score décroissant.
7. En cas de panne de l'API, un message clair est affiché et les recettes locales et en cache restent proposées.

## Choix de conception

- **Lots chargés depuis la base avec une quantité nulle** : le constructeur de `FoodLot` exige une quantité > 0 (BR02). Le repository instancie donc le lot avec sa quantité initiale puis rétablit la quantité courante.
- **Entrée initiale historisée** : l'ajout d'un lot crée un `StockEntry` marqué comme appliqué, sans doubler la quantité.
- **Consommation multi-lots FEFO** (« premier périmé, premier sorti ») : `plan_consumption` calcule la répartition sans rien modifier, puis les mouvements sont enregistrés ensemble. Une préparation de recette échoue entièrement si un ingrédient manque (sauf préparation partielle demandée).
- **Taux de gaspillage** : calculé par produit, dans son unité, puis moyenné. On n'additionne jamais des grammes et des litres.
- **Égalité des dataclasses** : `FoodProduct` et `FoodLot` se référencent mutuellement et utilisent l'égalité générée par `@dataclass`. Comparer deux instances distinctes peut provoquer une récursion infinie. L'interface sélectionne donc les produits par identifiant (voir la section « Pistes d'évolution »).

## Pistes d'évolution

- Ajouter `compare=False` sur `FoodLot.product`, `FoodLot.movements` et `StockMovement.lot` (ou `eq=False` sur ces classes) pour une égalité sans récursion.
- Comptes utilisateurs et foyers (sécurité, RGPD §7), notifications, codes-barres.
- Remplacer SQLite par PostgreSQL : seule `DATABASE_URL` change.
