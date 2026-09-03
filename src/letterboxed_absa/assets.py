import os
import re
import html
import sqlite3
import pandas as pd
import ftfy
import emoji
import spacy
from dagster import asset, Config, get_dagster_logger

def clean_for_transformers(text: str) -> str:
    """Removes noise and encoding errors while preserving NLP semantics."""
    if not isinstance(text, str):
        return ""
    
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'^\\||\\|$', '', text.strip())
    text = ftfy.fix_text(text)
    text = html.unescape(text)
    text = emoji.replace_emoji(text, replace='')
    
    unicode_replacements = {
        "’": "'", "‘": "'", "‚": "'", "‛": "'", "`": "'",
        "“": '"', "”": '"', "„": '"', "‟": '"',
        "—": " - ", "–": " - ", "―": " - ",
        "\xa0": " ",
        "\u200b": ""
    }
    for bad_char, good_char in unicode_replacements.items():
        text = text.replace(bad_char, good_char)
        
    text = re.sub(r'(!){2,}', '!', text)
    text = re.sub(r'(\?){2,}', '?', text)
    
    return re.sub(r'\s+', ' ', text).strip()

@asset(compute_kind="python")
def raw_reviews() -> pd.DataFrame:
    """Load and clean raw reviews from SQLite database."""
    logger = get_dagster_logger()
    db_path = "data/raw/letterboxd.db"
    
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at {db_path}")
        
    conn = sqlite3.connect(db_path)
    
    query = """
    SELECT 
        r.review_id,
        r.film_id,
        f.film_name,
        CAST(f.release_year AS INTEGER) AS release_year,
        f.overall_rating AS film_overall_rating,
        r.star_rating,
        r.review_date,
        r.review_text,
        GROUP_CONCAT(DISTINCT g.genre_name) AS genres
    FROM film_reviews r
    JOIN films f ON r.film_id = f.film_id
    LEFT JOIN film_genres g ON f.film_id = g.film_id
    WHERE r.review_text IS NOT NULL 
      AND TRIM(r.review_text) != ''
    GROUP BY r.review_id;
    """
    
    df_reviews = pd.read_sql(query, conn)
    conn.close()
    
    logger.info(f"Loaded {len(df_reviews)} reviews.")
    
    df_reviews["film_name"] = df_reviews["film_name"].apply(clean_for_transformers)
    df_reviews["star_rating_num"] = pd.to_numeric(df_reviews["star_rating"], errors="coerce")
    
    # We can optionally limit for testing purposes if it's too large, but let's process all.
    return df_reviews

@asset(compute_kind="spacy")
def preprocessed_sentences(raw_reviews: pd.DataFrame) -> pd.DataFrame:
    """Segment reviews into sentences and clean text."""
    logger = get_dagster_logger()
    
    # Load spacy for sentence boundary detection
    nlp = spacy.load("en_core_web_sm", disable=["tagger", "parser", "ner", "lemmatizer"])
    nlp.enable_pipe("senter")
    
    sentences = []
    batch_size = 2000
    
    # Process only a subset if testing, else all
    docs = nlp.pipe(raw_reviews["review_text"], batch_size=batch_size, n_process=1)
    
    for doc, (_, row) in zip(docs, raw_reviews.iterrows()):
        sent_idx = 0
        for sent in doc.sents:
            cleaned_sent = clean_for_transformers(sent.text)
            word_count = len(cleaned_sent.split())
            
            if word_count >= 3:
                sentences.append({
                    "review_id": row["review_id"],
                    "film_id": row["film_id"],
                    "film_name": row["film_name"],
                    "genres": row["genres"],
                    "star_rating_num": row["star_rating_num"],
                    "sentence_id": f"{row['review_id']}_{sent_idx}",
                    "sentence_text": cleaned_sent,
                    "is_truncated": cleaned_sent.endswith("...")
                })
                sent_idx += 1
                
    df_sentences = pd.DataFrame(sentences)
    logger.info(f"Extracted {len(df_sentences)} sentences.")
    
    # Save to parquet
    os.makedirs("data/processed", exist_ok=True)
    df_sentences.to_parquet("data/processed/letterboxd_sentences.parquet", index=False)
    
    return df_sentences

@asset(compute_kind="transformers")
def language_classified_sentences(preprocessed_sentences: pd.DataFrame) -> pd.DataFrame:
    """Classify the language of each sentence."""
    from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
    logger = get_dagster_logger()
    
    model_name = 'qanastek/51-languages-classifier'
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    
    # Use truncation to prevent AcceleratorError
    classifier = pipeline(
        "text-classification", 
        model=model, 
        tokenizer=tokenizer, 
        truncation=True, 
        max_length=512,
        device=-1 # Use CPU by default to avoid CUDA errors, or 0 for GPU if available
    )
    
    import torch
    if torch.cuda.is_available():
        classifier = pipeline(
            "text-classification", 
            model=model, 
            tokenizer=tokenizer, 
            truncation=True, 
            max_length=512,
            device=0
        )
    
    logger.info("Running language classification...")
    
    # Run classification with HF dataset for max efficiency
    from datasets import Dataset
    from transformers.pipelines.pt_utils import KeyDataset
    hf_dataset = Dataset.from_pandas(preprocessed_sentences[['sentence_text']])
    
    BATCH_SIZE = 128
    results = []
    
    for i, out in enumerate(classifier(KeyDataset(hf_dataset, 'sentence_text'), batch_size=BATCH_SIZE, truncation=True, max_length=512)):
        results.append(out['label'])
        if i > 0 and i % 10000 == 0:
            logger.info(f"Processed {i} / {len(preprocessed_sentences)} sentences for language.")
            
    preprocessed_sentences['language'] = results
    
    # Save checkpoint
    preprocessed_sentences.to_parquet("data/processed/letterboxd_sentences_with_language.parquet", index=False)
    return preprocessed_sentences

@asset(compute_kind="pandas")
def filtered_sentences(language_classified_sentences: pd.DataFrame) -> pd.DataFrame:
    """Filter sentences to only include languages supported by the sentiment model."""
    logger = get_dagster_logger()
    
    # The sentiment model 'nlptown/bert-base-multilingual-uncased-sentiment' supports:
    # English, Dutch, German, French, Spanish and Italian.
    supported_langs = ['en', 'nl', 'de', 'fr', 'es', 'it']
    
    df_filtered = language_classified_sentences[language_classified_sentences['language'].isin(supported_langs)].copy()
    
    logger.info(f"Filtered sentences down from {len(language_classified_sentences)} to {len(df_filtered)} supported language sentences.")
    
    return df_filtered

@asset(compute_kind="transformers")
def sentiment_analyzed_sentences(filtered_sentences: pd.DataFrame) -> pd.DataFrame:
    """Run sentiment analysis on the filtered sentences."""
    from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
    import torch
    logger = get_dagster_logger()
    
    sentiment_model_name = 'nlptown/bert-base-multilingual-uncased-sentiment'
    tokenizer = AutoTokenizer.from_pretrained(sentiment_model_name)
    model = AutoModelForSequenceClassification.from_pretrained(sentiment_model_name)
    
    device = 0 if torch.cuda.is_available() else -1
    sentiment_classifier = pipeline(
        "text-classification", 
        model=model, 
        tokenizer=tokenizer, 
        truncation=True, 
        max_length=512,
        device=device
    )
    
    # Run sentiment analysis with HF Dataset
    from datasets import Dataset
    from transformers.pipelines.pt_utils import KeyDataset
    hf_dataset = Dataset.from_pandas(filtered_sentences[['sentence_text']])
    
    BATCH_SIZE = 64
    results = []
    
    for i, out in enumerate(sentiment_classifier(KeyDataset(hf_dataset, 'sentence_text'), batch_size=BATCH_SIZE, truncation=True, max_length=512)):
        results.append(int(out['label'].split()[0]))
        if i > 0 and i % 10000 == 0:
            logger.info(f"Processed {i} / {len(filtered_sentences)} sentences for sentiment.")
            
    filtered_sentences['predicted_sentiment_stars'] = results
    
    # Save final results
    filtered_sentences.to_parquet("data/processed/letterboxd_sentences_sentiment.parquet", index=False)
    return filtered_sentences

@asset(compute_kind="transformers")
def emotion_analyzed_sentences(sentiment_analyzed_sentences: pd.DataFrame) -> pd.DataFrame:
    """Run emotion analysis on the sentences."""
    from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
    import torch
    logger = get_dagster_logger()
    
    emotion_model_name = 'j-hartmann/emotion-english-distilroberta-base'
    tokenizer = AutoTokenizer.from_pretrained(emotion_model_name)
    model = AutoModelForSequenceClassification.from_pretrained(emotion_model_name)
    
    device = 0 if torch.cuda.is_available() else -1
    emotion_classifier = pipeline(
        "text-classification", 
        model=model, 
        tokenizer=tokenizer, 
        truncation=True, 
        max_length=512,
        device=device
    )
    
    # Run emotion analysis with HF Dataset
    from datasets import Dataset
    from transformers.pipelines.pt_utils import KeyDataset
    hf_dataset = Dataset.from_pandas(sentiment_analyzed_sentences[['sentence_text']])
    
    BATCH_SIZE = 64
    results = []
    
    for i, out in enumerate(emotion_classifier(KeyDataset(hf_dataset, 'sentence_text'), batch_size=BATCH_SIZE, truncation=True, max_length=512)):
        results.append(out['label'])
        if i > 0 and i % 10000 == 0:
            logger.info(f"Processed {i} / {len(sentiment_analyzed_sentences)} sentences for emotion.")
            
    sentiment_analyzed_sentences['predicted_emotion'] = results
    
    # Save final results
    sentiment_analyzed_sentences.to_parquet("data/processed/letterboxd_sentences_emotion.parquet", index=False)
    return sentiment_analyzed_sentences

@asset(compute_kind="pandas")
def movie_sentiment_summary(emotion_analyzed_sentences: pd.DataFrame) -> pd.DataFrame:
    """Aggregate sentiment and emotion scores to create a summary for each movie."""
    logger = get_dagster_logger()
    
    logger.info("Aggregating sentiment and emotions by movie...")
    
    # Group by film_id and film_name for base stats
    summary = emotion_analyzed_sentences.groupby(['film_id', 'film_name']).agg(
        total_reviews=('review_id', 'nunique'),
        total_sentences=('sentence_id', 'count'),
        avg_predicted_sentiment=('predicted_sentiment_stars', 'mean'),
        std_predicted_sentiment=('predicted_sentiment_stars', 'std'),
        avg_original_rating=('star_rating_num', 'mean'),
        genres=('genres', 'first')
    ).reset_index()
    
    # Emotion aggregation: ONLY use English sentences, AND drop 'neutral'
    df_emotion = emotion_analyzed_sentences[
        (emotion_analyzed_sentences['language'].str.startswith('en', na=False)) & 
        (emotion_analyzed_sentences['predicted_emotion'] != 'neutral')
    ]
    
    emotions = ['anger', 'disgust', 'fear', 'joy', 'sadness', 'surprise']
    
    if not df_emotion.empty:
        emotion_counts = df_emotion.groupby(['film_id', 'predicted_emotion']).size().unstack(fill_value=0)
        # Normalize to get percentages
        emotion_pct = emotion_counts.div(emotion_counts.sum(axis=1), axis=0).fillna(0.0)
        emotion_pct.columns = [f"emotion_{col}" for col in emotion_pct.columns]
        summary = summary.merge(emotion_pct, on='film_id', how='left')
    
    # Fill any missing emotion columns and NaNs with 0
    for emo in emotions:
        col_name = f"emotion_{emo}"
        if col_name not in summary.columns:
            summary[col_name] = 0.0
    
    summary.fillna({f'emotion_{e}': 0.0 for e in emotions}, inplace=True)
    summary['std_predicted_sentiment'] = summary['std_predicted_sentiment'].fillna(0.0)
    
    # Save the summary to parquet
    summary.to_parquet("data/processed/movie_sentiment_summary.parquet", index=False)
    logger.info(f"Generated sentiment summary for {len(summary)} movies.")
    
    return summary
