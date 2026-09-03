"""Letterboxd popular films scraper.

Scrapes movie details from letterboxd.com/films/popular/:
- Film name, year, director, tagline, synopsis, overall rating
- Cast (actor + character), crew (role + name)
- Details (studio, country, language), genres
- Reviews (reviewer, text, star rating, date)

Uses urllib and BeautifulSoup. No Playwright needed.
Stores everything in SQLite via src/database/db.py.
"""

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

# Ensure project root and src directory are on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = Path(__file__).resolve().parent.parent
for directory in (PROJECT_ROOT, SRC_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

try:
    from src.database.db import init_database, save_film
except ImportError:
    from database.db import init_database, save_film

# ── Config ──────────────────────────────────────────────────────────────
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "raw" / "letterboxd.db"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.json"

DEFAULT_CONFIG = {
    "base_url": "https://letterboxd.com",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "max_pages_to_scrape": 25,
    "max_reviews_per_film": 100,
    "request_delay_seconds": 1.0,
    "database_path": str(DEFAULT_DB_PATH),
    "log_level": "INFO",
}


def load_config(config_path: Path | str | None = None) -> dict:
    """Load scraper configuration from config.json if present, falling back to project defaults."""
    config = dict(DEFAULT_CONFIG)

    path_to_try = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if path_to_try.exists():
        try:
            with open(path_to_try, "r", encoding="utf-8") as config_file:
                user_config = json.load(config_file)
                config.update(user_config)
                logging.info("Loaded custom configuration from %s", path_to_try)
        except Exception as e:
            logging.warning("Failed to parse config file at %s: %s. Using defaults.", path_to_try, e)

    return config


# ── Logging ─────────────────────────────────────────────────────────────
def setup_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# ── Scraping helpers ────────────────────────────────────────────────────

def fetch_html(url: str, config: dict) -> str:
    """Fetch HTML content using urllib."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": config.get("user_agent", DEFAULT_CONFIG["user_agent"]),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://letterboxd.com/",
            "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8")


def scrape_popular_film_slugs(config: dict) -> list[str]:
    """Get film slugs from the popular films listing page."""
    base_url = config.get("base_url", DEFAULT_CONFIG["base_url"])
    popular_url = f"{base_url}/csi/films/films-browser-list/popular/"
    max_pages = config.get("max_pages_to_scrape", DEFAULT_CONFIG["max_pages_to_scrape"])
    all_film_slugs = []

    for page_number in range(1, max_pages + 1):
        page_url = f"{popular_url}page/{page_number}/?esiAllowFilters=true" if page_number > 1 else f"{popular_url}?esiAllowFilters=true"

        logging.info("Fetching popular films page %d/%d: %s", page_number, max_pages, page_url)
        try:
            html_content = fetch_html(page_url, config)
            soup = BeautifulSoup(html_content, "html.parser")

            film_posters = soup.select("div[data-item-slug]")
            for poster in film_posters:
                film_slug = poster.get("data-item-slug")
                if film_slug and film_slug not in all_film_slugs:
                    all_film_slugs.append(film_slug)

            logging.info("Found %d films on page %d (total unique: %d)", len(film_posters), page_number, len(all_film_slugs))
        except Exception as e:
            logging.error("Error fetching popular films page %d: %s", page_number, e)

        time.sleep(config.get("request_delay_seconds", DEFAULT_CONFIG["request_delay_seconds"]))

    logging.info("Total unique film slugs collected: %d", len(all_film_slugs))
    return all_film_slugs


def scrape_film_detail(film_slug: str, config: dict) -> dict:
    """Scrape all details for a single film."""
    base_url = config.get("base_url", DEFAULT_CONFIG["base_url"])
    film_url = f"{base_url}/film/{film_slug}/"
    logging.info("Scraping film detail: %s", film_url)

    html_content = fetch_html(film_url, config)
    soup = BeautifulSoup(html_content, "html.parser")

    film_data = {"film_slug": film_slug, "film_url": film_url}

    # ── Name ──
    name_element = soup.select_one("h1.headline-1 span.name")
    film_data["film_name"] = name_element.get_text(strip=True) if name_element else ""

    # ── Year ──
    year_element = soup.select_one("span.releasedate a")
    film_data["release_year"] = year_element.get_text(strip=True) if year_element else ""

    # ── Director ──
    director_element = soup.select_one("p.credits span.contributorlist a.contributor")
    film_data["director_name"] = director_element.get_text(strip=True) if director_element else ""

    # ── Tagline ──
    tagline_element = soup.select_one("h4.tagline")
    film_data["tagline"] = tagline_element.get_text(strip=True) if tagline_element else ""

    # ── Synopsis ──
    synopsis_element = soup.select_one(".production-synopsis .truncate")
    if synopsis_element:
        paragraphs = synopsis_element.find_all("p")
        film_data["synopsis"] = " ".join(p.get_text(strip=True) for p in paragraphs)
    else:
        film_data["synopsis"] = ""

    # ── Overall Rating (from meta tag) ──
    rating_meta = soup.find("meta", attrs={"name": "twitter:data2"})
    if rating_meta:
        rating_text = rating_meta.get("content", "")
        rating_match = re.search(r"([\d.]+)", rating_text)
        film_data["overall_rating"] = rating_match.group(1) if rating_match else ""
    else:
        film_data["overall_rating"] = ""

    # ── Cast ──
    cast_list = []
    cast_panel = soup.select_one("#tab-panel-cast .cast-list")
    if cast_panel:
        cast_links = cast_panel.select("a.text-slug[href*='/actor/']")
        for cast_link in cast_links:
            actor_name = cast_link.get_text(strip=True)
            character_name = cast_link.get("title", "")
            if actor_name and actor_name != "Show All…":
                cast_list.append({
                    "actor_name": actor_name,
                    "character_name": character_name,
                })
    # Also check overflow section
    cast_overflow = soup.select_one("#cast-overflow")
    if cast_overflow:
        for cast_link in cast_overflow.select("a.text-slug[href*='/actor/']"):
            actor_name = cast_link.get_text(strip=True)
            character_name = cast_link.get("title", "")
            if actor_name:
                cast_list.append({
                    "actor_name": actor_name,
                    "character_name": character_name,
                })
    film_data["cast_list"] = cast_list

    # ── Crew ──
    crew_list = []
    crew_panel = soup.select_one("#tab-panel-crew")
    if crew_panel:
        current_role = ""
        for element in crew_panel.children:
            if hasattr(element, "name"):
                if element.name == "h3":
                    role_span = element.select_one("span.crewrole.-full")
                    if not role_span:
                        role_span = element.select_one("span")
                    current_role = role_span.get_text(strip=True) if role_span else ""
                elif element.name == "div" and "text-sluglist" in element.get("class", []):
                    for person_link in element.select("a.text-slug"):
                        person_name = person_link.get_text(strip=True)
                        if person_name:
                            crew_list.append({
                                "crew_role": current_role,
                                "person_name": person_name,
                            })
    film_data["crew_list"] = crew_list

    # ── Details (Studio, Country, Language) ──
    detail_list = []
    details_panel = soup.select_one("#tab-panel-details")
    if details_panel:
        current_detail_type = ""
        for element in details_panel.children:
            if hasattr(element, "name"):
                if element.name == "h3":
                    span = element.select_one("span")
                    raw_type = span.get_text(strip=True).lower() if span else ""
                    if "studio" in raw_type:
                        current_detail_type = "studio"
                    elif "country" in raw_type or "countries" in raw_type:
                        current_detail_type = "country"
                    elif "language" in raw_type:
                        current_detail_type = "language"
                    else:
                        current_detail_type = raw_type
                elif element.name == "div" and "text-sluglist" in element.get("class", []):
                    if current_detail_type in ("studio", "country", "language"):
                        for detail_link in element.select("a.text-slug"):
                            detail_value = detail_link.get_text(strip=True)
                            if detail_value:
                                detail_list.append({
                                    "detail_type": current_detail_type,
                                    "detail_value": detail_value,
                                })
    film_data["detail_list"] = detail_list

    # ── Genres ──
    genre_list = []
    genres_panel = soup.select_one("#tab-panel-genres")
    if genres_panel:
        genre_sluglist = genres_panel.select_one("div.text-sluglist")
        if genre_sluglist:
            for genre_link in genre_sluglist.select("a.text-slug"):
                genre_text = genre_link.get_text(strip=True)
                if genre_text and genre_text != "Show All…":
                    genre_list.append(genre_text)
    film_data["genre_list"] = genre_list

    return film_data


def scrape_film_reviews(film_slug: str, config: dict) -> list[dict]:
    """Scrape reviews for a single film from the reviews page."""
    base_url = config.get("base_url", DEFAULT_CONFIG["base_url"])
    max_reviews = config.get("max_reviews_per_film", DEFAULT_CONFIG["max_reviews_per_film"])

    review_list = []
    page = 1

    while True:
        if page == 1:
            reviews_url = f"{base_url}/film/{film_slug}/reviews/by/activity/"
        else:
            reviews_url = f"{base_url}/film/{film_slug}/reviews/by/activity/page/{page}/"

        logging.info("Scraping reviews page %d: %s", page, reviews_url)
        try:
            html_content = fetch_html(reviews_url, config)
        except Exception as e:
            logging.error("Failed to fetch reviews url %s: %s", reviews_url, e)
            break

        if not html_content:
            break

        soup = BeautifulSoup(html_content, "html.parser")
        review_items = soup.select("div.listitem article")

        if not review_items:
            break

        for review_item in review_items:
            if len(review_list) >= max_reviews:
                break

            review_data = {}

            # Reviewer name
            reviewer_element = review_item.select_one("strong.displayname")
            review_data["reviewer_name"] = reviewer_element.text.strip() if reviewer_element else ""

            # Star rating
            rating_svg = review_item.select_one("span.inline-rating svg")
            if rating_svg and rating_svg.get("aria-label"):
                rating_label = rating_svg.get("aria-label")
                rating_val = rating_label.count("★") + (0.5 if "½" in rating_label else 0)
                review_data["star_rating"] = str(rating_val)
            else:
                review_data["star_rating"] = ""

            # Review text
            review_body = review_item.select_one("div.js-review-body")
            review_data["review_text"] = review_body.get_text(separator="\n", strip=True)[:2000] if review_body else ""

            # Review date
            date_element = review_item.select_one("time.timestamp")
            review_data["review_date"] = date_element.get("datetime", "") if date_element else ""

            if review_data["reviewer_name"] or review_data["review_text"]:
                review_list.append(review_data)

        if len(review_list) >= max_reviews:
            break

        page += 1
        time.sleep(config.get("request_delay_seconds", DEFAULT_CONFIG["request_delay_seconds"]))

    logging.info("Found %d reviews for %s", len(review_list), film_slug)
    return review_list


# ── Main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Letterboxd film and review scraper.")
    parser.add_argument("--config", type=str, default=None, help="Path to custom JSON config file.")
    parser.add_argument("--db", type=str, default=None, help="Output SQLite database path (default: data/raw/letterboxd.db).")
    parser.add_argument("--pages", type=int, default=None, help="Max popular pages to scrape.")
    parser.add_argument("--reviews", type=int, default=None, help="Max reviews per film to collect.")
    parser.add_argument("--delay", type=float, default=None, help="Request delay in seconds.")
    parser.add_argument("--slug", type=str, default=None, help="Scrape a specific film by its slug (e.g. 'oppenheimer').")

    args = parser.parse_args()

    config = load_config(args.config)
    if args.db:
        config["database_path"] = args.db
    if args.pages is not None:
        config["max_pages_to_scrape"] = args.pages
    if args.reviews is not None:
        config["max_reviews_per_film"] = args.reviews
    if args.delay is not None:
        config["request_delay_seconds"] = args.delay

    setup_logging(config.get("log_level", "INFO"))
    logging.info("Starting Letterboxd scraper (urllib + BeautifulSoup)")
    logging.info("Target database: %s", config["database_path"])

    connection = init_database(config["database_path"])

    try:
        if args.slug:
            film_slugs = [args.slug]
        else:
            # Step 1: Get film slugs from popular page
            film_slugs = scrape_popular_film_slugs(config)

        # Step 2: Scrape each film's details + reviews
        for film_index, film_slug in enumerate(film_slugs, 1):
            logging.info("Processing film %d/%d: %s", film_index, len(film_slugs), film_slug)

            try:
                film_data = scrape_film_detail(film_slug, config)
                time.sleep(config.get("request_delay_seconds", DEFAULT_CONFIG["request_delay_seconds"]))

                review_list = scrape_film_reviews(film_slug, config)
                film_data["review_list"] = review_list
                time.sleep(config.get("request_delay_seconds", DEFAULT_CONFIG["request_delay_seconds"]))

                save_film(connection, film_data)

            except Exception as scrape_error:
                logging.error("Failed to scrape %s: %s", film_slug, scrape_error)
                continue

    finally:
        connection.close()

    logging.info("Scraping complete.")


if __name__ == "__main__":
    main()
