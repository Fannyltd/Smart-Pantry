import sqlite3
from pathlib import Path

# Racine du projet
BASE_DIR = Path(__file__).resolve().parents[2]

# Chemin de la base de données
DB_PATH = BASE_DIR / "data" / "db.sqlite"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    # Activation des clés étrangères
    connection.execute("PRAGMA foreign_keys = ON")

    return connection