# 🥫 Smart Pantry

Application de gestion intelligente des stocks alimentaires domestiques : suivi des
lots et des dates de péremption, recettes recommandées selon le stock (TheMealDB),
liste de courses et statistiques de gaspillage.

## Fonctionnalités (MVP)

| Module | Contenu |
|--------|---------|
| **F1 Stock** | Produits avec plusieurs lots, ajout / modification / suppression, consommation, mise au rebut, historique de chaque mouvement |
| **F2 Péremptions** | DLC / DDM, statuts 🟢 🟠 🔴, alertes, priorisation, mise au rebut des lots périmés |
| **F3 Recettes** | Catalogue local + TheMealDB, recherche par nom, catégorie ou ingrédient, score `0,6·C + 0,4·P`, ingrédients manquants, allergènes |
| **F4 Courses** | Ajout manuel, génération depuis une recette, stock déjà disponible affiché, achat puis validation en stock |
| **F5 Statistiques** | Consommation et gaspillage par période, taux de gaspillage (avec seuil d'historique), répartition par catégorie, historique |

## Installation

Prérequis : Python 3.10 ou plus récent.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # facultatif
```

## Lancement

Depuis la racine du projet :

```bash
streamlit run app/main.py
```

Au premier lancement, la base SQLite `data/smart_pantry.db` est créée. Les catégories et
10 recettes locales y sont chargées. Le tableau de bord propose ensuite de charger un
**inventaire de démonstration** (`data/sample_inventory.csv`), dont les dates sont calculées
à partir d'aujourd'hui.

## Tests

```bash
pytest                 # 107 tests unitaires et d'intégration, sans réseau
```

Voir `docs/test_plan.md` pour la correspondance avec les scénarios T01 à T10.

## Structure

```
app/
├── main.py              point d'entrée Streamlit (navigation + préférences)
├── pages/               une page par module (+ _shared.py)
├── models/              domaine : produits, lots, mouvements, recettes, courses
├── services/            cas d'usage ; __init__.py assemble les dépendances
├── repositories/        conversion domaine <-> base
├── database/            SQLAlchemy : connexion, tables, données de référence
├── exceptions/          erreurs métier
├── utils/               unités de mesure, validation, normalisation des noms
└── config/settings.py   paramètres (.env)
data/                    recettes locales, catégories, inventaire de démonstration
docs/                    exigences, architecture, diagramme de classes, plan de tests
tests/                   unit/, integration/, conftest.py
```

Détails dans `docs/architecture.md` ; diagramme dans `docs/class_diagram.png`.

## TheMealDB

- URL de base : `https://www.themealdb.com/api/json/v1/1/` (clé de test publique `1`).
- La version gratuite (V1) filtre par **un seul ingrédient** : l'application interroge les ingrédients un par un, les plus urgents d'abord, puis compare les recettes au stock.
- Les noms français de l'inventaire sont traduits pour l'API (poulet → chicken, etc.) ; la correspondance tolère les pluriels, les accents et les variantes (« chicken breast » ↔ « poulet »).
- Les recettes consultées sont mises en cache en base. Si l'API est indisponible, un message s'affiche et les recettes locales ou déjà en cache restent utilisables. `API_ENABLED=false` désactive complètement l'API.

## Configuration

Toutes les options sont décrites dans `.env.example` : base de données, délai de l'API,
seuil d'alerte (3 jours), horizon de priorité (7 jours), poids du score, allergènes,
historique minimum pour les statistiques.
