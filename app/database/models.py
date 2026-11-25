"""Tables SQLAlchemy (couche de persistance).

Ces classes ORM sont distinctes des modèles du domaine (``app.models``) :
les repositories assurent la conversion dans les deux sens.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Integer,
                        String, Text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CategoryORM(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)


class FoodProductORM(Base):
    __tablename__ = "food_products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    base_unit: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    lots: Mapped[list["FoodLotORM"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="FoodLotORM.expiration_date")


class FoodLotORM(Base):
    __tablename__ = "food_lots"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_lot_quantity_non_negative"),           # RM01
        CheckConstraint("initial_quantity > 0", name="ck_lot_initial_quantity_positive"),  # BR02
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("food_products.id", ondelete="CASCADE"), index=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    initial_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    expiration_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    expiration_type: Mapped[str] = mapped_column(String(3), default="DLC")

    product: Mapped[FoodProductORM] = relationship(back_populates="lots")
    movements: Mapped[list["StockMovementORM"]] = relationship(
        back_populates="lot", cascade="all, delete-orphan", order_by="StockMovementORM.movement_date")


class StockMovementORM(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_movement_quantity_positive"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lot_id: Mapped[int] = mapped_column(ForeignKey("food_lots.id", ondelete="CASCADE"), index=True)
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    movement_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    lot: Mapped[FoodLotORM] = relationship(back_populates="movements")


class RecipeORM(Base):
    __tablename__ = "recipes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    servings: Mapped[int] = mapped_column(Integer, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    preparation_time: Mapped[int | None] = mapped_column(Integer)
    category: Mapped[str | None] = mapped_column(String(80))
    image_url: Mapped[str | None] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(20), default="local")  # local | themealdb
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    ingredients: Mapped[list["RecipeIngredientORM"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", order_by="RecipeIngredientORM.position")


class RecipeIngredientORM(Base):
    __tablename__ = "recipe_ingredients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("food_products.id", ondelete="SET NULL"))
    ingredient_name: Mapped[str] = mapped_column(String(120), nullable=False)
    required_quantity: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(30), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)

    recipe: Mapped[RecipeORM] = relationship(back_populates="ingredients")


class ShoppingListORM(Base):
    __tablename__ = "shopping_lists"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="Ma liste de courses")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    items: Mapped[list["ShoppingItemORM"]] = relationship(
        back_populates="shopping_list", cascade="all, delete-orphan", order_by="ShoppingItemORM.id")


class ShoppingItemORM(Base):
    __tablename__ = "shopping_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_item_quantity_positive"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shopping_list_id: Mapped[int] = mapped_column(ForeignKey("shopping_lists.id", ondelete="CASCADE"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("food_products.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    is_purchased: Mapped[bool] = mapped_column(Boolean, default=False)

    shopping_list: Mapped[ShoppingListORM] = relationship(back_populates="items")
