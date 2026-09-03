import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
import os
import json
import wikipedia
import urllib.request
import urllib.parse

app = FastAPI()

# Mount static files
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    return RedirectResponse(url="/static/index.html")

# Load data on startup
df_summary = pd.DataFrame()

CACHE_FILE = "data/app_cache.json"
app_cache = {}

def load_cache():
    global app_cache
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                app_cache = json.load(f)
        except Exception:
            app_cache = {}

def save_cache():
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(app_cache, f)
    except Exception as e:
        print(f"Error saving cache: {e}")

@app.on_event("startup")
def load_data():
    global df_summary
    load_cache()
    try:
        df_summary = pd.read_parquet("data/processed/movie_sentiment_summary.parquet")
        print(f"Loaded {len(df_summary)} movies from summary.")
    except Exception as e:
        print(f"Failed to load summary: {e}")

@app.get("/api/movies")
def get_movies():
    if df_summary.empty:
        return []
    
    # Return a lightweight list for the sidebar
    movies = df_summary[['film_id', 'film_name', 'avg_original_rating', 'avg_predicted_sentiment']].to_dict('records')
    # Sort alphabetically
    movies = sorted(movies, key=lambda x: str(x['film_name']))
    return movies

@app.get("/api/movie/{film_id}")
def get_movie_details(film_id: str):
    if df_summary.empty:
        raise HTTPException(status_code=500, detail="Data not loaded")
    
    movie_row = df_summary[df_summary['film_id'].astype(str) == str(film_id)]
    if movie_row.empty:
        raise HTTPException(status_code=404, detail=f"Movie not found: {film_id}")
        
    return movie_row.iloc[0].fillna(0).to_dict()

@app.get("/api/info")
def get_info(film_name: str):
    if film_name in app_cache:
        return app_cache[film_name]
        
    info = {
        "poster_url": "https://via.placeholder.com/300x450/0b0e14/00e5ff?text=No+Poster+Found",
        "description": "No description available."
    }
    
    # 1. Fetch Poster (IMDB Suggest API - Fast & reliable)
    try:
        query_safe = urllib.parse.quote(film_name.lower())
        url = f"https://v3.sg.media-imdb.com/suggestion/x/{query_safe}.json"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if 'd' in data and len(data['d']) > 0:
                for item in data['d']:
                    # Ensure we grab a movie type if possible
                    if 'i' in item and 'imageUrl' in item['i']:
                        info["poster_url"] = item['i']['imageUrl']
                        break
    except Exception as e:
        print(f"IMDB API error: {e}")
        
    # 2. Fetch Description
    try:
        wikipedia.set_lang("en")
        summary = wikipedia.summary(f"{film_name} (film)", sentences=3)
        info["description"] = summary
    except wikipedia.exceptions.DisambiguationError as e:
        try:
            # Fallback to the first option if disambiguation hits
            summary = wikipedia.summary(e.options[0], sentences=3)
            info["description"] = summary
        except:
            pass
    except Exception as e:
        try:
            summary = wikipedia.summary(f"{film_name}", sentences=3)
            info["description"] = summary
        except:
            print(f"Wikipedia error: {e}")
    
    # Save to cache
    app_cache[film_name] = info
    save_cache()
    
    return info
