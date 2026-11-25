"""Connexion à la base de données, création du schéma et données de référence."""
from __future__ import annotations

import csv
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import DATA_DIR
from app.database.models import Base, CategoryORM, RecipeIngredientORM, RecipeORM
from app.utils.unit_converter import normalize_unit

SessionFactory = Callable[[], Session]


def create_db_engine(database_url: str) -> Engine:
    kwargs: dict = {}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if database_url in {"sqlite://", "sqlite:///:memory:"}:
            kwargs["poolclass"] = StaticPool  # une seule connexion partagée en mémoire
        else:
            db_path = Path(database_url.replace("sqlite:///", "", 1))
            db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, future=True, **kwargs)

    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):  # pragma: no cover - hook
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(session_factory: SessionFactory) -> Iterator[Session]:
    """Transaction : commit si tout va bien, rollback sinon."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(engine: Engine, session_factory: SessionFactory, data_dir: Path = DATA_DIR,
            seed: bool = True) -> None:
    """Crée les tables et charge les données de référence si la base est vide."""
    Base.metadata.create_all(engine)
    if seed:
        seed_categories(session_factory, data_dir / "categories.csv")
        seed_local_recipes(session_factory, data_dir / "recipes.csv")


def seed_categories(session_factory: SessionFactory, csv_path: Path) -> int:
    if not csv_path.exists():
        return 0
    with session_scope(session_factory) as session:
        existing = set(session.scalars(select(CategoryORM.name)))
        added = 0
        with csv_path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                name = (row.get("name") or "").strip()
                if name and name not in existing:
                    session.add(CategoryORM(name=name))
                    existing.add(name)
                    added += 1
        return added


def _parse_ingredients(raw: str) -> list[tuple[str, float | None, str]]:
    """Format CSV : "nom:quantité:unité|nom:quantité:unité" (quantité facultative)."""
    parsed = []
    for chunk in (raw or "").split("|"):
        parts = [part.strip() for part in chunk.split(":")]
        if not parts or not parts[0]:
            continue
        name = parts[0]
        quantity = float(parts[1].replace(",", ".")) if len(parts) > 1 and parts[1] else None
        unit = normalize_unit(parts[2]) if len(parts) > 2 else ""
        parsed.append((name, quantity, unit))
    return parsed


def seed_local_recipes(session_factory: SessionFactory, csv_path: Path) -> int:
    """Catalogue local : garantit des recettes même si TheMealDB est indisponible."""
    if not csv_path.exists():
        return 0
    with session_scope(session_factory) as session:
        existing = set(session.scalars(select(RecipeORM.external_id)))
        added = 0
        with csv_path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                external_id = f"local:{row['id'].strip()}"
                if external_id in existing:
                    continue
                recipe = RecipeORM(
                    external_id=external_id,
                    name=row["name"].strip(),
                    category=(row.get("category") or "").strip() or None,
                    servings=int(row.get("servings") or 2),
                    preparation_time=int(row["preparation_time"]) if row.get("preparation_time") else None,
                    instructions=row["instructions"].strip(),
                    image_url=(row.get("image_url") or "").strip() or None,
                    source="local",
                )
                for position, (name, quantity, unit) in enumerate(_parse_ingredients(row["ingredients"])):
                    recipe.ingredients.append(RecipeIngredientORM(
                        ingredient_name=name, required_quantity=quantity, unit=unit, position=position))
                session.add(recipe)
                added += 1
        return added
