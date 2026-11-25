"""Socle commun des repositories (pattern Repository).

Chaque repository reçoit une *fabrique de sessions* SQLAlchemy et gère ses
propres transactions. Il expose et reçoit uniquement des objets du domaine
(``app.models``), jamais des objets ORM.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, TypeVar

from sqlalchemy.orm import Session

from app.database.connection import SessionFactory
from app.exceptions.domain_exceptions import NotFoundError

OrmT = TypeVar("OrmT")


class BaseRepository:
    entity_label: str = "Entité"

    def __init__(self, session_factory: SessionFactory):
        self._session_factory = session_factory

    @contextmanager
    def _session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _get_or_raise(self, session: Session, orm_class: type[OrmT], identifier: int,
                      label: str | None = None) -> OrmT:
        instance = session.get(orm_class, identifier)
        if instance is None:
            raise NotFoundError(label or self.entity_label, identifier)
        return instance
