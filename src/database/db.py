"""Database setup and operations for Letterboxd scraper using SQLite."""

import sqlite3
import logging

logger = logging.getLogger(__name__)


def init_database(database_path: str) -> sqlite3.Connection:
    """Create all tables and return a connection."""
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS films (
            film_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            film_name       TEXT NOT NULL,
            release_year    TEXT,
            director_name   TEXT,
            tagline         TEXT,
            synopsis        TEXT,
            overall_rating  TEXT,
            film_slug       TEXT UNIQUE NOT NULL,
            film_url        TEXT,
            scraped_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS cast_members (
            cast_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            film_id         INTEGER NOT NULL,
            actor_name      TEXT NOT NULL,
            character_name  TEXT,
            FOREIGN KEY (film_id) REFERENCES films(film_id)
        );

        CREATE TABLE IF NOT EXISTS crew_members (
            crew_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            film_id         INTEGER NOT NULL,
            crew_role       TEXT NOT NULL,
            person_name     TEXT NOT NULL,
            FOREIGN KEY (film_id) REFERENCES films(film_id)
        );

        CREATE TABLE IF NOT EXISTS film_details (
            detail_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            film_id         INTEGER NOT NULL,
            detail_type     TEXT NOT NULL,  -- 'studio', 'country', 'language'
            detail_value    TEXT NOT NULL,
            FOREIGN KEY (film_id) REFERENCES films(film_id)
        );

        CREATE TABLE IF NOT EXISTS film_genres (
            genre_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            film_id         INTEGER NOT NULL,
            genre_name      TEXT NOT NULL,
            FOREIGN KEY (film_id) REFERENCES films(film_id)
        );

        CREATE TABLE IF NOT EXISTS film_reviews (
            review_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            film_id         INTEGER NOT NULL,
            reviewer_name   TEXT,
            review_text     TEXT,
            star_rating     TEXT,
            review_date     TEXT,
            FOREIGN KEY (film_id) REFERENCES films(film_id)
        );
    """)

    connection.commit()
    logger.info("Database initialized at %s", database_path)
    return connection


def save_film(connection: sqlite3.Connection, film_data: dict) -> int:
    """Insert or update a film record. Returns film_id."""
    cursor = connection.cursor()

    # ponytail: upsert via INSERT OR REPLACE on slug
    cursor.execute("""
        INSERT OR REPLACE INTO films
            (film_name, release_year, director_name, tagline, synopsis,
             overall_rating, film_slug, film_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        film_data.get("film_name"),
        film_data.get("release_year"),
        film_data.get("director_name"),
        film_data.get("tagline"),
        film_data.get("synopsis"),
        film_data.get("overall_rating"),
        film_data["film_slug"],
        film_data.get("film_url"),
    ))
    film_id = cursor.lastrowid

    # Clear old related data on re-scrape
    for table in ("cast_members", "crew_members", "film_details",
                  "film_genres", "film_reviews"):
        cursor.execute(f"DELETE FROM {table} WHERE film_id = ?", (film_id,))

    # Cast
    for cast_entry in film_data.get("cast_list", []):
        cursor.execute(
            "INSERT INTO cast_members (film_id, actor_name, character_name) VALUES (?, ?, ?)",
            (film_id, cast_entry["actor_name"], cast_entry.get("character_name")),
        )

    # Crew
    for crew_entry in film_data.get("crew_list", []):
        cursor.execute(
            "INSERT INTO crew_members (film_id, crew_role, person_name) VALUES (?, ?, ?)",
            (film_id, crew_entry["crew_role"], crew_entry["person_name"]),
        )

    # Details (studio, country, language)
    for detail_entry in film_data.get("detail_list", []):
        cursor.execute(
            "INSERT INTO film_details (film_id, detail_type, detail_value) VALUES (?, ?, ?)",
            (film_id, detail_entry["detail_type"], detail_entry["detail_value"]),
        )

    # Genres
    for genre_name in film_data.get("genre_list", []):
        cursor.execute(
            "INSERT INTO film_genres (film_id, genre_name) VALUES (?, ?)",
            (film_id, genre_name),
        )

    # Reviews
    for review_entry in film_data.get("review_list", []):
        cursor.execute(
            "INSERT INTO film_reviews (film_id, reviewer_name, review_text, star_rating, review_date) VALUES (?, ?, ?, ?, ?)",
            (film_id, review_entry.get("reviewer_name"), review_entry.get("review_text"),
             review_entry.get("star_rating"), review_entry.get("review_date")),
        )

    connection.commit()
    logger.info("Saved film: %s (id=%d)", film_data.get("film_name"), film_id)
    return film_id
