import os
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import event, inspect, text
from sqlalchemy.engine import Engine
import sqlite3

os.makedirs("data", exist_ok=True)

DATABASE_URL = "sqlite:///data/boodschappen.db"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_session():
    with Session(engine) as session:
        yield session


def create_db_and_tables():
    # Import all models so SQLModel registers them
    from models import Recipe, RecipeIngredient, ShoppingList, ShoppingListItem, StapleItem, FamilyMember  # noqa: F401
    SQLModel.metadata.create_all(engine)
    # Migration: add new columns to existing tables if missing
    insp = inspect(engine)
    existing_recipe_cols = {c["name"] for c in insp.get_columns("recipe")}
    with engine.begin() as conn:
        if "prep_time" not in existing_recipe_cols:
            conn.execute(text("ALTER TABLE recipe ADD COLUMN prep_time INTEGER"))
    # Ensure photos directory exists
    os.makedirs("data/photos", exist_ok=True)
