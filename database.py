import sqlite3
import os
from flask import g

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'foodbridge.db')

def dict_factory(cursor, row):
    """Convert SQLite row to dictionary for easier template rendering and JSON API."""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def get_db():
    """Get database connection for current request context."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = dict_factory
        # Enable foreign key support in SQLite
        db.execute('PRAGMA foreign_keys = ON;')
    return db

def close_connection(exception=None):
    """Close database connection at end of request."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db(app=None):
    """Initialize database from schema.sql."""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')
    with open(schema_path, 'r') as f:
        cursor.executescript(f.read())
    conn.commit()
    conn.close()
    print("Database initialized successfully.")
