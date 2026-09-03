# Sentence-level sentiment and emotional profiling of Letterboxd user reviews

## Introduction and project objective

Online movie review platforms contain large quantities of unstructured critique that reflect audience reception across multiple subjective dimensions. While numeric ratings provide an aggregate measure of popularity, they reduce complex reader responses to a single scalar value. A 3-star rating can indicate consistent mediocrity, or it can indicate a sharp division between admiration for cinematography and frustration with narrative pacing.

This project implements an end-to-end natural language processing pipeline and web interface that extracts fine-grained sentiment ratings and emotional profiles from unstructured text reviews on Letterboxd. Rather than treating an entire review as a single classification instance, the system decomposes reviews into individual sentences, tags their language, filters for supported linguistic sets, and runs dual transformer evaluations. The resulting dataset yields two analytical layers: film-level controversy scores derived from sentence variance, and six-dimensional emotional signatures derived from normalized emotion distributions.

## Data provenance and database schema

The source dataset was collected from Letterboxd across 25 pagination tiers of popular releases, capturing up to 100 written reviews per film. The raw data is organized in an SQLite relational database (`letterboxd.db`) of 58.5 MB, spanning 1,754 films released between 1902 and 2026.

### Relational design
The database uses six normalized tables linked by foreign keys to the primary film index:

1. `films`: Contains core attributes including `film_id`, `film_name`, `release_year`, `director_name`, `synopsis`, `overall_rating`, and `film_slug`.
2. `film_reviews`: Stores 175,400 user reviews, recording `review_id`, `film_id`, `reviewer_name`, `review_text`, `star_rating`, and `review_date`.
3. `cast_members`: Catalogs 134,753 credited cast appearances across 63,636 unique actors, linking actor names to specific character roles.
4. `crew_members`: Records 123,539 crew credits across 50,289 individuals, detailing production roles such as director, producer, writer, and cinematographer.
5. `film_details`: Captures 11,818 attribute mappings for production companies, origin countries, and original languages.
6. `film_genres`: Links films to 22 standardized thematic classifications, covering major genres (such as Drama, Comedy, Horror, and Science Fiction) and subcategories.

### Data quality and integrity metrics
The review text is populated in 175,396 of the 175,400 records (99.998% completeness). A total of 9,207 reviews (5.25%) omit an explicit numeric star rating, representing users who logged written reactions without assigning a 1 to 5 star grade. Synopses are present for all 1,754 films. Taglines are absent in 81 films, predominantly older or independent releases. The release year distribution centers heavily between 1990 and 2024, though foundational historical works (such as Georges Méliès's 1902 *Le Voyage dans la Lune*) establish the lower bound.

## Text preprocessing pipeline

User submissions on Letterboxd feature platform-specific stylistic eccentricities, including HTML markup, non-standard unicode characters, emojis, and repeated exclamation points. These elements cause out-of-vocabulary conditions or arbitrary tokenization artifacts in transformer architectures.

### Cleaning methodology
The cleaning pipeline (`clean_for_transformers`) executes sequentially:
1. Strips HTML markup, hyperlinks, and line break tags (`<br>`, `<p>`) using regular expression matching.
2. Repairs encoding mojibake and broken unicode representations using `ftfy.fix_text` and `html.unescape`.
3. Strips graphical emojis through `emoji.replace_emoji(replace='')` to prevent sequence pollution in models not tuned on emoji embeddings.
4. Normalizes typography by mapping curly quotation marks (`’`, `‘`), backticks, and smart quotes to standard ASCII single and double quotes.
5. Normalizes various unicode dash formats (em-dashes, en-dashes, horizontal bars) to standard spaced hyphens.
6. Collapses runs of excessive punctuation (such as `!!!!` or `????`) into single terminal characters, and normalizes consecutive whitespace sequences into single spaces.

### Sentence boundary detection and length thresholding
Following normalization, reviews are segmented into sentences using `spaCy` (`en_core_web_sm`) with non-essential pipeline components (`tagger`, `parser`, `ner`, `lemmatizer`) disabled, enabling only the rule-based sentence segmenter (`senter`). Processing runs in streaming batches of 2,000 documents.

Sentences with fewer than 3 words are discarded. This cutoff removes isolated fragments, conversational interjections (such as "OMG", "Masterpiece", "LOL"), and noise from truncated trailing phrases. Across all 175,400 raw reviews, this stage extracts 399,909 clean sentences suitable for classification.

## Language identification and filtering

Because Letterboxd has an international user base, reviews for English-language films frequently contain paragraphs written in French, Spanish, German, or other languages. Running an English-specific emotion model on foreign text generates false classifications.

### Model architecture and batching
Sentence language is classified using `qanastek/51-languages-classifier`, a fine-tuned sequence classification model based on RoBERTa architecture. The model distinguishes 51 languages with high discriminative capability on short sentences.

To maximize throughput on available hardware, inputs are converted into Hugging Face `Dataset` objects and fed to the pipeline via `KeyDataset` in batches of 128 items with strict input truncation at 512 tokens.

### Empirical language distribution
Language inference across the 399,909 sentence corpus yielded:
- English (`en-US`): 386,937 sentences (96.76%)
- German (`de-DE`): 5,372 sentences (1.34%)
- Spanish (`es-ES`): 4,620 sentences (1.16%)
- French (`fr-FR`): 1,538 sentences (0.38%)
- Dutch (`nl-NL`): 1,066 sentences (0.27%)
- Italian (`it-IT`): 376 sentences (0.09%)

Sentences outside this six-language set (less than 0.5% of total volume) were pruned. The remaining sentences align with the multilingual capability of the subsequent sentiment classifier.

## Transformer-based model inference

The inference stage evaluates every validated sentence across two dimensions: sentiment valence and discrete emotion.

### Multilingual sentiment analysis
Sentiment is evaluated using `nlptown/bert-base-multilingual-uncased-sentiment`, a BERT model fine-tuned on multi-domain reviews in six languages (English, German, French, Spanish, Italian, Dutch). The model maps input text into a 5-class ordinal output corresponding to star ratings 1 through 5.

The resulting distribution across the 399,909 sentences shows:
- 1 star (strongly negative): 72,698 sentences (18.18%)
- 2 stars (negative): 44,561 sentences (11.14%)
- 3 stars (neutral / mixed): 75,476 sentences (18.87%)
- 4 stars (positive): 68,609 sentences (17.16%)
- 5 stars (strongly positive): 138,565 sentences (34.65%)

The global mean sentence sentiment across the corpus is 3.38 stars. The skew toward 4 and 5 stars mirrors the broader positive bias observed on user critique platforms.

### Discrete emotion classification
Emotional signatures are extracted using `j-hartmann/emotion-english-distilroberta-base`. This model is trained on a consolidation of diverse emotion corpora (including SemEval, ISEAR, and WASSA) and classifies text into Ekman's six basic emotions (anger, disgust, fear, joy, sadness, surprise) plus neutral.

Because this model was pre-trained exclusively on English corpora, inference is constrained to the 386,937 English sentences to preserve semantic validity.

Before post-processing, the aggregate emotion distribution across all raw English sentences is:
- Neutral: 39.60% (158,352 sentences)
- Joy: 19.25% (76,966 sentences)
- Surprise: 10.50% (41,980 sentences)
- Disgust: 10.21% (40,833 sentences)
- Sadness: 7.26% (29,021 sentences)
- Anger: 6.86% (27,452 sentences)
- Fear: 6.33% (25,305 sentences)

### Treatment of neutral classifications
Neutral sentences make up nearly 40% of all sentences. Qualitative examination showed that neutral sentences primarily convey plot description, factual exposition, or actor identifications (for example, "The film was directed by David Fincher in 1999" or "Brad Pitt plays the role of Tyler Durden").

Retaining neutral classifications flattens the emotional profile of every film toward an undifferentiated baseline. The pipeline removes the neutral category during film-level emotional aggregation. The remaining six emotion counts are normalized to sum to 1.0, isolating the active affective tone of user critique.

Following neutral removal, the mean distribution across all 1,754 films settles into:
- Joy: 32.36%
- Surprise: 17.83%
- Disgust: 16.21%
- Sadness: 12.11%
- Anger: 11.51%
- Fear: 9.97%

## Metric formulation and aggregation

Sentence-level outputs are aggregated by film into a primary summary table stored in `data/processed/movie_sentiment_summary.parquet`. Each film record contains 14 attributes:

| Metric column | Data type | Formula / Definition |
| :--- | :--- | :--- |
| `film_id` | Integer | Primary key from database |
| `film_name` | String | Standardized film title |
| `total_reviews` | Integer | Count of unique reviews included ($N_{\text{reviews}} \in [43, 100]$, $\mu = 93.5$) |
| `total_sentences` | Integer | Total segmented sentences ($N_{\text{sentences}} \in [114, 393]$, $\mu = 228.0$) |
| `avg_predicted_sentiment` | Float | Arithmetic mean of predicted sentence ratings ($S_i \in \{1,2,3,4,5\}$) |
| `std_predicted_sentiment` | Float | Sample standard deviation of sentence ratings ($\sigma_{\text{sentiment}}$) |
| `avg_original_rating` | Float | Arithmetic mean of explicit user stars ($R_k \in [0.5, 5.0]$) |
| `genres` | String | Comma-delimited list of assigned film genres |
| `emotion_[emotion]` | Float | Normalized frequency of emotion $e \in \{\text{anger, disgust, fear, joy, sadness, surprise}\}$ |

### Controversy score calculation
Audience polarization is quantified through the sample standard deviation of sentence sentiment scores:

$$\sigma = \sqrt{\frac{1}{M - 1} \sum_{i=1}^{M} (S_i - \bar{S})^2}$$

where $M$ is the number of sentences for a given film and $S_i$ is the predicted star rating for sentence $i$. Across all 1,754 movies, the mean standard deviation is 1.49 (min = 1.19, max = 1.78, $\sigma_{\text{std}} = 0.094$).

A high standard deviation indicates that a film's reviews consist of conflicting sentence ratings (for example, many 1-star and 5-star sentences), while a low standard deviation indicates uniform evaluative tone.

### Statistical correlation analysis
Empirical analysis of the aggregated dataset reveals distinct relationships among metrics:

1. **Predicted sentiment versus user rating**: Pearson correlation between `avg_original_rating` and `avg_predicted_sentiment` is $r = 0.651$. This shows strong alignment between sentence-level textual sentiment and explicit star marks, while leaving room for divergence caused by stylistic irony, sarcasm, or rating compression.
2. **Independence of controversy**: Pearson correlation between `avg_original_rating` and `std_predicted_sentiment` is $r = 0.089$. This near-zero correlation confirms that controversy is an orthogonal evaluative dimension. Both critically acclaimed films and low-rated films exhibit varying degrees of audience polarization.

## Pipeline orchestration with Dagster

The data processing pipeline is implemented as a set of software-defined assets using Dagster (`src/letterboxed_absa/assets.py`).

### Asset dependency graph
The pipeline components form a strict directed acyclic graph:
1. `raw_reviews`: Connects to `letterboxd.db`, joins films, genres, and reviews, applies cleaning rules, and returns a consolidated DataFrame.
2. `preprocessed_sentences`: Depends on `raw_reviews`. Runs `spaCy` sentence segmentation and length thresholding. Emits `letterboxd_sentences.parquet`.
3. `language_classified_sentences`: Depends on `preprocessed_sentences`. Executes `qanastek/51-languages-classifier` with PyTorch batching. Emits `letterboxd_sentences_with_language.parquet`.
4. `filtered_sentences`: Filters language-tagged sentences down to the six supported European languages.
5. `sentiment_analyzed_sentences`: Depends on `filtered_sentences`. Runs `nlptown` multilingual sentiment model. Emits `letterboxd_sentences_sentiment.parquet`.
6. `emotion_analyzed_sentences`: Depends on `sentiment_analyzed_sentences`. Runs DistilRoBERTa emotion classification on English sentences. Emits `letterboxd_sentences_emotion.parquet`.
7. `movie_sentiment_summary`: Aggregates the sentence dataset into film-level ratings, controversy scores, and emotion proportions. Emits the final `movie_sentiment_summary.parquet`.

Dagster manages execution metadata, tracks data materialization times, handles GPU allocation checkpoints, and allows independent re-execution of individual asset stages without reprocessing upstream tables.

## Production web application and serving architecture

To explore the analytical outputs, a lightweight, single-page web dashboard was developed. The application emphasizes low latency, clean visual hierarchy, and local data persistence.

### Backend service (`server.py`)
The backend is built on FastAPI and Uvicorn. On application startup, it loads `movie_sentiment_summary.parquet` into an in-memory Pandas DataFrame. It provides three primary endpoints:

- `GET /api/movies`: Returns an array of film objects containing `film_id`, `film_name`, and `avg_predicted_sentiment`, used to populate the navigation sidebar.
- `GET /api/movie/{film_id}`: Returns complete metrics, genre strings, sentence counts, and normalized emotion frequencies for the selected film.
- `GET /api/info?film_name={name}`: Retrieves supplemental descriptive metadata, including the official poster image and a narrative plot summary.

### Persistent caching engine
External web queries for posters and descriptions introduce latency and encounter rate limits when called repeatedly. The server implements a file-based JSON cache (`data/app_cache.json`).

When `/api/info` is requested:
1. The server checks whether the requested `film_name` key exists in `app_cache`.
2. On cache hit, the stored dictionary is returned immediately.
3. On cache miss, the server executes external lookups, stores the retrieved poster URL and plot summary in `app_cache`, writes the updated dictionary to disk, and returns the response.

### External metadata sources
Supplemental data retrieval utilizes targeted services:
- **Poster extraction**: Queries the IMDB Suggest API (`https://v3.sg.media-imdb.com/suggestion/x/{query}.json`). This endpoint responds in under 300 milliseconds and reliably returns official high-resolution movie poster image links without requiring authenticated API keys.
- **Synopsis retrieval**: Queries the MediaWiki API via the Python `wikipedia` package. The query requests a 3-sentence extract for `{film_name} (film)`, providing concise narrative context in the UI.

### Frontend interface (`static/`)
The user interface is constructed with HTML5, CSS3, and JavaScript, using Chart.js for data visualization. It adopts a split-column single-page layout designed to fit within standard desktop viewports without excessive vertical scrolling:

- **Navigation drawer**: Left-hand sidebar listing all 1,754 films, with real-time text filtering and predicted sentiment badges.
- **Left visual column**: Houses the movie poster display card and a synopsis container displaying the retrieved Wikipedia plot summary.
- **Right analytical column**: Houses three metric cards displaying predicted sentiment, Letterboxd user rating, and controversy score, followed by a responsive Chart.js radar graph rendering the film's 6-dimensional emotional signature.

## Analytical observations and practical applications

Analysis of the aggregated corpus demonstrates several practical applications of fine-grained sentiment analysis:

1. **Genre emotional alignment**: Emotional signatures strongly mirror genre categories. Horror films (such as *The Conjuring* or *Hereditary*) regularly record combined fear and disgust values above 45%, whereas comedies record joy percentages above 50%.
2. **Detection of audience polarization**: The controversy metric successfully isolates polarizing releases. Films with unconventional structures or divisive narrative choices (such as *The Last Jedi* or *Mother!*) exhibit high standard deviations ($\sigma > 1.62$), distinguishing them from uniformly well-received films of similar mean scores.
3. **Identification of review skew**: Comparing `avg_predicted_sentiment` with `avg_original_rating` exposes reviews where written praise contradicts numeric ratings, often pointing to sarcastic or ironic review styles common on Letterboxd.

## Computational limitations and future work

Several limitations remain in the current pipeline:

- **Sarcasm and rhetorical irony**: Transformer sentiment models evaluate lexical compositionality but occasionally misclassify sarcastic remarks common in social film critique (for example, "Truly a cinematic masterpiece that put me to sleep in ten minutes").
- **Aspect-level resolution**: While sentence-level processing isolates discrete thoughts, it does not explicitly assign sentiments to specific film elements (such as cinematography, sound design, acting performance, or pacing). Extending the pipeline with aspect-based extraction represents a logical next phase.
- **Single-source bias**: The dataset represents users of a single platform (Letterboxd), whose demographic and aesthetic preferences skew toward auteur-driven, art-house, and genre-specific releases compared to general theatrical audiences.
