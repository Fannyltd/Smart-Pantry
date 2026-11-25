"""F3 — Catalogue et recommandation de recettes.

Contient :
- ``TheMealDBClient`` : client REST de TheMealDB V1 (JSON, gestion des pannes) ;
- ``IngredientMatcher`` : correspondance approximative inventaire <-> recettes
  (normalisation, traduction FR -> EN, inclusion de mots, similarité) ;
- ``RecipeService`` : catalogue (local + TheMealDB, avec cache en base) ;
- ``RecipeRecommendationService`` : score explicable Score(r) = 0.6 C(r) + 0.4 P(r).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher

import requests

from app.config.settings import Settings
from app.exceptions.domain_exceptions import ExternalAPIError
from app.models import FoodLot, FoodProduct, Recipe, RecipeIngredient
from app.repositories.recipe_repository import RecipeRepository
from app.services.expiration_service import ExpirationService
from app.services.inventory_service import is_usable
from app.utils import unit_converter as units
from app.utils.validators import normalize_name

# ============================================================================
# Client TheMealDB
# ============================================================================


class TheMealDBClient:
    """Client de l'API V1 gratuite (un seul ingrédient par filtre, cf. §3.3)."""

    def __init__(self, base_url: str, timeout: float = 8.0, session: requests.Session | None = None,
                 default_servings: int = 4):
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.timeout = timeout
        self.session = session or requests.Session()
        self.default_servings = default_servings

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        try:
            response = self.session.get(self.base_url + endpoint, params=params, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as exc:
            raise ExternalAPIError("TheMealDB ne répond pas (délai dépassé). "
                                   "Les recettes locales restent disponibles.") from exc
        except requests.RequestException as exc:
            raise ExternalAPIError("TheMealDB est momentanément indisponible. "
                                   "Les recettes locales restent disponibles.") from exc
        except ValueError as exc:
            raise ExternalAPIError("Réponse de TheMealDB illisible (JSON invalide).") from exc
        if not isinstance(payload, dict):
            raise ExternalAPIError("Réponse de TheMealDB inattendue.")
        return payload

    # --- endpoints (§3.2) ---------------------------------------------------
    def filter_by_ingredient(self, ingredient: str) -> list[dict]:
        """filter.php?i= → [{idMeal, strMeal, strMealThumb}]"""
        query = "_".join(ingredient.strip().lower().split())
        return self._get("filter.php", {"i": query}).get("meals") or []

    def lookup(self, meal_id: str | int) -> dict | None:
        meals = self._get("lookup.php", {"i": str(meal_id)}).get("meals") or []
        return meals[0] if meals else None

    def search_by_name(self, name: str) -> list[dict]:
        return self._get("search.php", {"s": name.strip()}).get("meals") or []

    def filter_by_category(self, category: str) -> list[dict]:
        return self._get("filter.php", {"c": category.strip()}).get("meals") or []

    def categories(self) -> list[str]:
        return [c["strCategory"] for c in self._get("categories.php").get("categories") or []]

    def list_ingredients(self) -> list[str]:
        return [i["strIngredient"] for i in self._get("list.php", {"i": "list"}).get("meals") or []]

    def random(self) -> dict | None:
        meals = self._get("random.php").get("meals") or []
        return meals[0] if meals else None

    # --- conversion JSON -> domaine -------------------------------------------
    def to_recipe(self, meal: dict) -> Recipe:
        recipe = Recipe(
            name=(meal.get("strMeal") or "Recette sans nom").strip(),
            servings=self.default_servings,
            instructions=(meal.get("strInstructions") or "").strip() or "Instructions non disponibles.",
            external_id=f"mealdb:{meal.get('idMeal')}",
            category=(meal.get("strCategory") or None),
            image_url=meal.get("strMealThumb") or None,
        )
        for index in range(1, 21):
            name = (meal.get(f"strIngredient{index}") or "").strip()
            if not name:
                continue
            quantity, unit = units.parse_measure(meal.get(f"strMeasure{index}"))
            recipe.add_ingredient(RecipeIngredient(product=None, required_quantity=quantity,
                                                   unit=unit, ingredient_name=name))
        return recipe


# ============================================================================
# Correspondance des noms d'ingrédients
# ============================================================================

FR_TO_EN: dict[str, str] = {
    "poulet": "chicken", "blanc de poulet": "chicken breast", "filet de poulet": "chicken breast",
    "cuisse de poulet": "chicken thigh", "boeuf": "beef", "boeuf hache": "minced beef",
    "viande hachee": "minced beef", "steak hache": "minced beef", "porc": "pork", "agneau": "lamb",
    "veau": "veal", "jambon": "ham", "lardon": "bacon", "bacon": "bacon", "saucisse": "sausage",
    "chorizo": "chorizo", "dinde": "turkey", "canard": "duck",
    "saumon": "salmon", "thon": "tuna", "cabillaud": "cod", "crevette": "prawn", "moule": "mussel",
    "oeuf": "egg", "lait": "milk", "beurre": "butter", "creme": "cream", "creme fraiche": "creme fraiche",
    "creme liquide": "double cream", "fromage": "cheese", "fromage rape": "cheese",
    "emmental": "cheese", "gruyere": "gruyere", "parmesan": "parmesan", "mozzarella": "mozzarella",
    "feta": "feta", "chevre": "goat cheese", "yaourt": "yogurt", "yaourt nature": "yogurt",
    "farine": "flour", "sucre": "sugar", "sucre roux": "brown sugar", "sel": "salt",
    "poivre": "black pepper", "huile": "oil", "huile d olive": "olive oil", "vinaigre": "vinegar",
    "riz": "rice", "pate": "pasta", "spaghetti": "spaghetti", "penne": "penne rigate",
    "nouille": "noodle", "semoule": "couscous", "couscous": "couscous", "pain": "bread",
    "lentille": "lentil", "pois chiche": "chickpea", "haricot rouge": "kidney bean",
    "haricot vert": "green bean", "haricot": "bean", "petit poi": "pea",
    "pomme de terre": "potato", "patate douce": "sweet potato", "carotte": "carrot",
    "oignon": "onion", "oignon rouge": "red onion", "echalote": "shallot", "ail": "garlic",
    "tomate": "tomato", "tomate concassee": "chopped tomato", "concentre de tomate": "tomato puree",
    "courgette": "courgette", "aubergine": "aubergine", "poivron": "pepper",
    "poivron rouge": "red pepper", "poivron vert": "green pepper", "champignon": "mushroom",
    "epinard": "spinach", "salade": "lettuce", "laitue": "lettuce", "concombre": "cucumber",
    "brocoli": "broccoli", "chou": "cabbage", "chou fleur": "cauliflower", "poireau": "leek",
    "celeri": "celery", "mais": "sweetcorn", "avocat": "avocado", "citron": "lemon",
    "citron vert": "lime", "pomme": "apple", "banane": "banana", "fraise": "strawberry",
    "orange": "orange", "mangue": "mango", "ananas": "pineapple",
    "persil": "parsley", "basilic": "basil", "coriandre": "coriander", "menthe": "mint",
    "thym": "thyme", "romarin": "rosemary", "gingembre": "ginger", "cumin": "cumin",
    "paprika": "paprika", "curry": "curry powder", "cannelle": "cinnamon", "miel": "honey",
    "chocolat": "chocolate", "lait de coco": "coconut milk", "bouillon": "stock",
    "bouillon de poulet": "chicken stock", "sauce soja": "soy sauce", "moutarde": "mustard",
    "levure": "baking powder", "amande": "almond", "noix": "walnut",
}
_STOPWORDS = {"de", "du", "des", "la", "le", "les", "d", "l", "a", "au", "aux", "en", "et",
              "frais", "fraiche", "of", "the", "fresh", "and", "bio"}


class IngredientMatcher:
    """Mécanisme de correspondance approximative exigé au §4.3 du cahier des charges."""

    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold
        self._cache: dict[str, tuple[str, ...]] = {}

    def canonical_forms(self, name: str | None) -> tuple[str, ...]:
        """Formes normalisées d'un nom : français normalisé + traduction anglaise."""
        key = name or ""
        if key in self._cache:
            return self._cache[key]
        normalized = normalize_name(name)
        forms = [normalized] if normalized else []
        translated = FR_TO_EN.get(normalized)
        if translated is None and normalized:
            tokens = [t for t in normalized.split() if t not in _STOPWORDS]
            core = " ".join(tokens)
            translated = FR_TO_EN.get(core) or " ".join(FR_TO_EN.get(t, t) for t in tokens)
        if translated:
            translated = normalize_name(translated)
            if translated not in forms:
                forms.append(translated)
        self._cache[key] = tuple(forms)
        return self._cache[key]

    def english_name(self, name: str) -> str:
        forms = self.canonical_forms(name)
        return forms[-1] if forms else ""

    def _forms_match(self, form_a: str, form_b: str) -> bool:
        if not form_a or not form_b:
            return False
        if form_a == form_b:
            return True
        tokens_a = {t for t in form_a.split() if t not in _STOPWORDS}
        tokens_b = {t for t in form_b.split() if t not in _STOPWORDS}
        if tokens_a and tokens_b and (tokens_a <= tokens_b or tokens_b <= tokens_a):
            return True
        # Similarité (fautes de frappe, pluriels irréguliers) : réservée aux mots
        # assez longs commençant par la même lettre, pour éviter "oeuf" ~ "boeuf".
        if min(len(form_a), len(form_b)) < 5 or form_a[0] != form_b[0]:
            return False
        return SequenceMatcher(None, form_a, form_b).ratio() >= self.threshold

    def matches(self, name_a: str | None, name_b: str | None) -> bool:
        return any(self._forms_match(a, b)
                   for a in self.canonical_forms(name_a) for b in self.canonical_forms(name_b))

    def find_products(self, ingredient: RecipeIngredient,
                      products: list[FoodProduct]) -> list[FoodProduct]:
        if ingredient.product is not None and ingredient.product.id is not None:
            linked = [p for p in products if p.id == ingredient.product.id]
            if linked:
                return linked
        return [p for p in products if self.matches(ingredient.ingredient_name, p.name)]

    def contains_allergen(self, recipe: Recipe, allergens: list[str] | tuple[str, ...]) -> list[str]:
        found = []
        for allergen in allergens:
            allergen_forms = self.canonical_forms(allergen)
            for ingredient in recipe.ingredients:
                ingredient_forms = self.canonical_forms(ingredient.ingredient_name)
                if any(self._forms_match(a, f)
                       for a in allergen_forms for f in ingredient_forms):
                    found.append(allergen)
                    break
        return found


# ============================================================================
# Catalogue de recettes
# ============================================================================


class RecipeService:
    """Consultation du catalogue (local + TheMealDB) avec cache en base."""

    def __init__(self, recipe_repository: RecipeRepository, client: TheMealDBClient | None,
                 settings: Settings, matcher: IngredientMatcher | None = None):
        self.recipe_repository = recipe_repository
        self.client = client if settings.api_enabled else None
        self.settings = settings
        self.matcher = matcher or IngredientMatcher(settings.fuzzy_match_threshold)

    @property
    def api_available(self) -> bool:
        return self.client is not None

    def list_recipes(self) -> list[Recipe]:
        return self.recipe_repository.list_recipes()

    def get_recipe(self, recipe_id: int) -> Recipe:
        return self.recipe_repository.get(recipe_id)

    def categories(self) -> tuple[list[str], list[str]]:
        """Catégories (API puis repli local) et avertissements."""
        warnings: list[str] = []
        local = self.recipe_repository.list_categories()
        if self.client:
            try:
                return sorted(set(self.client.categories()) | set(local)), warnings
            except ExternalAPIError as exc:
                warnings.append(str(exc))
        return local, warnings

    def _cache_meal(self, meal: dict) -> Recipe:
        recipe = self.client.to_recipe(meal)
        return self.recipe_repository.save(recipe, source="themealdb")

    def get_or_fetch(self, meal_id: str) -> Recipe | None:
        cached = self.recipe_repository.get_by_external_id(f"mealdb:{meal_id}")
        if cached or not self.client:
            return cached
        meal = self.client.lookup(meal_id)
        return self._cache_meal(meal) if meal else None

    def search(self, text: str | None = None, category: str | None = None,
               use_api: bool = True) -> tuple[list[Recipe], list[str]]:
        """Recherche par nom (search.php) et/ou catégorie, fusionnée avec le local."""
        warnings: list[str] = []
        results = {r.id: r for r in self.recipe_repository.search(text, category)}
        if use_api and self.client and (text or category):
            try:
                if text:
                    for meal in self.client.search_by_name(text):
                        if category and (meal.get("strCategory") or "").lower() != category.lower():
                            continue
                        recipe = self._cache_meal(meal)
                        results[recipe.id] = recipe
                else:
                    for meal in self.client.filter_by_category(category)[: self.settings.max_api_recipes]:
                        recipe = self.get_or_fetch(meal["idMeal"])
                        if recipe:
                            results[recipe.id] = recipe
            except ExternalAPIError as exc:
                warnings.append(str(exc))
        if not results:
            warnings.append("Aucune recette ne correspond à cette recherche.")
        return sorted(results.values(), key=lambda r: r.name.casefold()), warnings

    def search_by_ingredient(self, ingredient: str) -> tuple[list[Recipe], list[str]]:
        """T05 : recettes contenant un ingrédient disponible."""
        warnings: list[str] = []
        found: dict[int, Recipe] = {}
        for recipe in self.recipe_repository.list_recipes():
            if any(self.matcher.matches(ingredient, i.ingredient_name) for i in recipe.ingredients):
                found[recipe.id] = recipe
        if self.client:
            try:
                meals = self.client.filter_by_ingredient(self.matcher.english_name(ingredient))
                for meal in meals[: self.settings.max_api_recipes]:
                    recipe = self.get_or_fetch(meal["idMeal"])
                    if recipe:
                        found[recipe.id] = recipe
            except ExternalAPIError as exc:
                warnings.append(str(exc))
        return list(found.values()), warnings

    def fetch_candidates(self, ingredient_names: list[str]) -> tuple[list[Recipe], list[str]]:
        """Interroge filter.php ingrédient par ingrédient (V1), puis lookup.php.

        Les ingrédients sont fournis par ordre de priorité (les plus urgents
        d'abord, RM07) ; les détails sont mis en cache en base.
        """
        warnings: list[str] = []
        if not self.client:
            return [], ["TheMealDB est désactivée : seules les recettes locales sont utilisées."]
        meal_ids: list[str] = []
        queried = 0
        try:
            for name in ingredient_names:
                if queried >= self.settings.max_api_ingredients:
                    break
                english = self.matcher.english_name(name)
                if not english:
                    continue
                queried += 1
                for meal in self.client.filter_by_ingredient(english):
                    if meal["idMeal"] not in meal_ids:
                        meal_ids.append(meal["idMeal"])
            recipes = []
            for meal_id in meal_ids[: self.settings.max_api_recipes]:
                recipe = self.get_or_fetch(meal_id)
                if recipe:
                    recipes.append(recipe)
        except ExternalAPIError as exc:
            warnings.append(str(exc))
            cached = [self.recipe_repository.get_by_external_id(f"mealdb:{i}") for i in meal_ids]
            return [r for r in cached if r], warnings
        if queried and not meal_ids:
            warnings.append("TheMealDB ne connaît aucune recette pour vos ingrédients.")
        return recipes, warnings

    def random_recipe(self) -> tuple[Recipe | None, list[str]]:
        if not self.client:
            return None, ["TheMealDB est désactivée."]
        try:
            meal = self.client.random()
            return (self._cache_meal(meal) if meal else None), []
        except ExternalAPIError as exc:
            return None, [str(exc)]


# ============================================================================
# Recommandation
# ============================================================================


@dataclass
class IngredientStatus:
    ingredient: RecipeIngredient
    required_quantity: float | None      # quantité mise à l'échelle des portions
    unit: str
    matched_products: list[FoodProduct] = field(default_factory=list)
    available_quantity: float = 0.0      # dans l'unité de l'ingrédient (si comparable)
    coverage: float = 0.0                # 0..1
    urgency: float = 0.0                 # 0..1
    comparable: bool = True              # False si unités non convertibles
    expired_only: bool = False           # le produit existe mais uniquement en DLC dépassée

    @property
    def name(self) -> str:
        return self.ingredient.ingredient_name or ""

    @property
    def is_available(self) -> bool:
        return self.coverage >= 0.999

    @property
    def missing_quantity(self) -> float | None:
        """Quantité manquante, ou None si non calculable."""
        if self.is_available:
            return 0.0
        if self.required_quantity is None:
            return None
        if not self.comparable:
            return None
        return max(0.0, self.required_quantity - self.available_quantity)

    @property
    def note(self) -> str:
        if self.expired_only:
            return "En stock mais DLC dépassée"
        if not self.matched_products:
            return "Absent du stock"
        if not self.comparable:
            return "En stock, unités non comparables (à vérifier)"
        if self.required_quantity is None:
            return "En stock (quantité non précisée)"
        if self.is_available:
            return "Disponible"
        return "Quantité insuffisante"


@dataclass
class RecipeMatch:
    recipe: Recipe
    coverage: float                      # C(r) dans [0, 1]
    priority: float                      # P(r) dans [0, 1]
    score: float
    ingredients: list[IngredientStatus]
    urgent_products: list[str]
    allergens: list[str] = field(default_factory=list)

    @property
    def coverage_percent(self) -> float:
        return round(self.coverage * 100, 1)

    @property
    def missing(self) -> list[IngredientStatus]:
        return [i for i in self.ingredients if not i.is_available]

    @property
    def available(self) -> list[IngredientStatus]:
        return [i for i in self.ingredients if i.is_available]

    @property
    def status(self) -> str:
        """Distinction exigée au §3.3 du cahier des charges."""
        if not self.missing:
            return "Réalisable"
        if len(self.missing) <= 2:
            return "Quelques ingrédients à ajouter"
        return "Ingrédients insuffisants"

    @property
    def is_anti_waste(self) -> bool:
        return self.priority >= 0.5

    def explanation(self, coverage_weight: float, priority_weight: float) -> str:
        return (f"Score = {coverage_weight:.1f} × C ({self.coverage:.2f}) + "
                f"{priority_weight:.1f} × P ({self.priority:.2f}) = {self.score:.2f}")


class RecipeRecommendationService:
    def __init__(self, recipe_service: RecipeService, expiration_service: ExpirationService,
                 settings: Settings, matcher: IngredientMatcher | None = None):
        self.recipe_service = recipe_service
        self.expiration_service = expiration_service
        self.settings = settings
        self.matcher = matcher or recipe_service.matcher

    # ------------------------------------------------------------ évaluation
    def evaluate_ingredient(self, ingredient: RecipeIngredient, products: list[FoodProduct],
                            scale: float = 1.0, reference_date: date | None = None) -> IngredientStatus:
        required = ingredient.required_quantity * scale if ingredient.required_quantity else None
        unit = units.normalize_unit(ingredient.unit) or ("unité" if required else "")
        status = IngredientStatus(ingredient=ingredient, required_quantity=required, unit=unit)
        status.matched_products = self.matcher.find_products(ingredient, products)
        all_lots = [lot for p in status.matched_products for lot in p.get_available_lots()]
        usable: list[FoodLot] = [lot for lot in all_lots if is_usable(lot, reference_date)]
        status.expired_only = bool(all_lots) and not usable
        if not usable:
            return status
        status.urgency = max(self.expiration_service.urgency_score(lot, reference_date) for lot in usable)
        if required is None:
            status.coverage = 1.0
            return status
        forms = self.matcher.canonical_forms(ingredient.ingredient_name)
        total, comparable_found = 0.0, False
        for lot in usable:
            converted = units.convert_for_ingredient(lot.quantity, lot.unit, unit, forms)
            if converted is not None:
                total += converted
                comparable_found = True
        if not comparable_found:
            status.comparable = False
            status.coverage = 0.5  # présent mais non mesurable : demi-couverture, signalée
            return status
        status.available_quantity = total
        status.coverage = min(1.0, total / required) if required > 0 else 1.0  # 300 g vs 50 g -> 0.17
        return status

    def calculate_match_score(self, recipe: Recipe, products: list[FoodProduct] | None = None,
                              reference_date: date | None = None,
                              servings: int | None = None) -> RecipeMatch:
        """Score(r) = wC·C(r) + wP·P(r) — C : couverture moyenne pondérée par les
        quantités réellement disponibles ; P : urgence maximale des produits utilisés."""
        if products is None:
            products = self.expiration_service.food_repository.list_products(with_movements=False)
        scale = (servings / recipe.servings) if servings else 1.0
        statuses = [self.evaluate_ingredient(i, products, scale, reference_date)
                    for i in recipe.get_ingredients()]
        coverage = sum(s.coverage for s in statuses) / len(statuses) if statuses else 0.0
        priority = max((s.urgency for s in statuses), default=0.0)
        score = self.settings.coverage_weight * coverage + self.settings.priority_weight * priority
        urgent = sorted({p.name for s in statuses if s.urgency >= 0.5 for p in s.matched_products})
        return RecipeMatch(recipe=recipe, coverage=coverage, priority=priority, score=round(score, 4),
                           ingredients=statuses, urgent_products=urgent)

    # ------------------------------------------------------------ classement
    def priority_ingredient_names(self, products: list[FoodProduct],
                                  reference_date: date | None = None) -> list[str]:
        """Noms des produits utilisables, les plus urgents d'abord (RM07 / BR12)."""
        ranked = []
        for product in products:
            usable = [lot for lot in product.get_available_lots() if is_usable(lot, reference_date)]
            if usable:
                urgency = max(self.expiration_service.urgency_score(l, reference_date) for l in usable)
                soonest = min(lot.expiration_date for lot in usable)
                ranked.append((-urgency, soonest, product.name))
        return [name for *_, name in sorted(ranked)]

    def recommend_recipes(self, products: list[FoodProduct] | None = None, include_api: bool = False,
                          allergens: list[str] | tuple[str, ...] | None = None,
                          servings: int | None = None, limit: int | None = None,
                          reference_date: date | None = None,
                          min_coverage: float = 0.0) -> tuple[list[RecipeMatch], list[str]]:
        """Classe les recettes par score décroissant (RM06, RM07).

        Renvoie (recommandations, messages d'information).
        """
        warnings: list[str] = []
        if products is None:
            products = self.expiration_service.food_repository.list_products(with_movements=False)
        allergens = list(allergens if allergens is not None else self.settings.user_allergens)
        candidates = {r.id: r for r in self.recipe_service.list_recipes()}
        if include_api:
            names = self.priority_ingredient_names(products, reference_date)
            fetched, api_warnings = self.recipe_service.fetch_candidates(names)
            warnings.extend(api_warnings)
            candidates.update({r.id: r for r in fetched})

        matches, excluded = [], 0
        for recipe in candidates.values():
            if not recipe.ingredients:
                continue
            found_allergens = self.matcher.contains_allergen(recipe, allergens) if allergens else []
            if found_allergens:
                excluded += 1
                continue
            match = self.calculate_match_score(recipe, products, reference_date, servings)
            if match.coverage <= min_coverage:
                continue
            matches.append(match)
        matches.sort(key=lambda m: (-m.score, -m.coverage, m.recipe.name.casefold()))
        if excluded:
            warnings.append(f"{excluded} recette(s) exclue(s) car contenant un allergène déclaré.")
        if not matches:
            warnings.append("Aucune recette pertinente n'a été trouvée avec votre stock actuel. "
                            "Ajoutez des produits ou interrogez TheMealDB.")
        return (matches[:limit] if limit else matches), warnings
