# Letterboxd Sentiment Analysis

This project performs end-to-end sentiment analysis on movie reviews from Letterboxd. It extracts sentences, classifies their languages, filters for supported languages, performs sentiment analysis using a Hugging Face transformer model, and visualizes the results via an interactive dashboard built with FastAPI, HTML, and JS.

The data pipeline can be executed in two ways:
1. **Dagster Pipeline**: An orchestrated, production-ready data pipeline.
2. **Jupyter Notebooks**: Step-by-step exploratory notebooks.

## Architecture

1. **Data Ingestion**: Reads raw movie reviews from an SQLite database (`data/raw/letterboxd.db`).
2. **Text Cleaning & Segmentation**: Cleans HTML, emojis, and encoding artifacts, and uses `spaCy` to segment full reviews into individual sentences.
3. **Language Classification**: Uses `qanastek/51-languages-classifier` (via Hugging Face `transformers` and `datasets`) to classify the language of every sentence in batches.
4. **Sentiment Analysis**: Filters sentences for supported languages (English, Dutch, German, French, Spanish, Italian) and passes them through `nlptown/bert-base-multilingual-uncased-sentiment` to predict a 1 to 5 star rating.
5. **Aggregation**: Aggregates the predicted sentiments at the movie level and outputs the final metrics to `data/processed/movie_sentiment_summary.parquet`.
6. **Dashboard**: A FastAPI web server (`server.py`) rendering a futuristic frontend (`static/`) for interactive visualization.

## Installation & Setup

This project uses `uv` for lightning-fast Python dependency management.

1. Clone the repository and navigate to the project directory.
2. Sync the dependencies and set up the virtual environment:
   ```bash
   uv sync
   ```
3. Download the necessary `spaCy` model:
   ```bash
   uv run python -m spacy download en_core_web_sm
   ```

## Usage

### 1. Scraping Letterboxd Data (Optional)
The raw data is stored in SQLite at `data/raw/letterboxd.db`. To scrape fresh or additional film details and reviews from Letterboxd:
```bash
# Scrape popular films (default database: data/raw/letterboxd.db)
uv run python src/scraper/scraper.py --pages 5 --reviews 100

# Or scrape a specific film by its slug
uv run python src/scraper/scraper.py --slug oppenheimer --reviews 50

# Check database statistics
uv run python src/database/check_db.py
```

### 2. Running the Data Pipeline (Dagster)
To run the automated data pipeline orchestrator:
```bash
uv run dagster dev -m src.letterboxed_absa
```
Navigate to the provided localhost URL to view the Dagster UI, materialize the assets, and monitor the pipeline execution.

### 3. Exploring via Notebooks
If you prefer to run the steps manually or explore the data interactively:
```bash
uv run jupyter notebook
```
Execute the notebooks in sequence:
* `02_demographics_distribution.ipynb` (EDA)
* `03_cast_crew_and_reviews.ipynb` (EDA)
* `05_language_classification.ipynb` (Data Processing)
* `06_sentiment_analysis.ipynb` (Data Processing)
* `07_movie_sentiment_aggregation.ipynb` (Data Aggregation)

### 4. Running the Dashboard (FastAPI)
Once the data pipeline has finished and `movie_sentiment_summary.parquet` is generated, launch the dashboard:
```bash
uv run uvicorn server:app --host 0.0.0.0 --port 8000
```
Navigate your browser to `http://localhost:8000` to view the glowing, single-page application.
## Hardware Acceleration

The language classification and sentiment analysis steps use Hugging Face `pipelines` wrapped with `KeyDataset` for batched evaluation. The batch size is configured for typical GPUs to maximize VRAM utilization and heavily reduce processing time on the 400,000+ extracted sentences. If you run out of memory, lower the `BATCH_SIZE` in the respective scripts or notebooks.
