import os
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Letterboxd Movie Sentiment", layout="wide")

st.title("🎬 Letterboxd Movie Sentiment Dashboard")

# Function to load data
@st.cache_data
def load_data():
    summary_path = "data/processed/movie_sentiment_summary.parquet"
    if os.path.exists(summary_path):
        return pd.read_parquet(summary_path)
    return None

df_summary = load_data()

if df_summary is None:
    st.warning("⚠️ Data not found! Please run the Dagster pipeline first to generate `data/processed/movie_sentiment_summary.parquet`.")
else:
    # Sidebar for filtering
    st.sidebar.header("Filter Movies")
    
    # Text input for searching by name
    search_term = st.sidebar.text_input("Search by Movie Name", "")
    
    if search_term:
        filtered_df = df_summary[df_summary["film_name"].str.contains(search_term, case=False, na=False)]
    else:
        filtered_df = df_summary
        
    st.sidebar.markdown(f"**{len(filtered_df)} movies found.**")

    # Main Dashboard
    if not filtered_df.empty:
        st.write("### 🎥 Movie Overview")
        
        # Format for display
        display_df = filtered_df.copy()
        display_df["avg_predicted_sentiment"] = display_df["avg_predicted_sentiment"].round(2)
        display_df["avg_original_rating"] = display_df["avg_original_rating"].round(2)
        
        if "std_predicted_sentiment" in display_df.columns:
            display_df["Controversy Score (Std)"] = display_df["std_predicted_sentiment"].round(2)
            cols_to_show = ["film_name", "genres", "total_reviews", "avg_predicted_sentiment", "avg_original_rating", "Controversy Score (Std)"]
        else:
            cols_to_show = ["film_name", "genres", "total_reviews", "avg_predicted_sentiment", "avg_original_rating"]
        
        # Dataframe
        st.dataframe(
            display_df[cols_to_show],
            use_container_width=True
        )

        st.write("---")
        st.write("### 📊 Sentiment vs Original Rating")
        
        # Scatter Plot
        fig = px.scatter(
            filtered_df,
            x="avg_original_rating",
            y="avg_predicted_sentiment",
            size="total_reviews",
            color="avg_predicted_sentiment",
            hover_name="film_name",
            labels={
                "avg_original_rating": "Average Original Rating (Stars)",
                "avg_predicted_sentiment": "Predicted Sentiment (NLP)"
            },
            color_continuous_scale="RdYlGn"
        )
        st.plotly_chart(fig, use_container_width=True)
        
        st.write("---")
        
        # Individual Movie Deep Dive
        st.write("### 🔍 Individual Movie Deep Dive")
        selected_movie = st.selectbox("Select a movie for details", filtered_df["film_name"].tolist())
        
        if selected_movie:
            movie_data = filtered_df[filtered_df["film_name"] == selected_movie].iloc[0]
            
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Predicted Sentiment", f"{movie_data['avg_predicted_sentiment']:.2f} ⭐")
            col2.metric("Original User Rating", f"{movie_data['avg_original_rating']:.2f} ⭐")
            
            if 'std_predicted_sentiment' in movie_data:
                col3.metric("Controversy Score", f"{movie_data['std_predicted_sentiment']:.2f}")
            else:
                col3.metric("Controversy Score", "N/A")
                
            col4.metric("Total Reviews Analyzed", f"{int(movie_data['total_reviews'])}")
            col5.metric("Total Sentences Evaluated", f"{int(movie_data['total_sentences'])}")
            
            st.info(f"**Genres:** {movie_data['genres']}")
            
            # Show actual sentences if available
            st.write("*(Note: To see sentence-level breakdowns, load the sentence dataset!)*")
            
            # Emotion Radar Chart
            emotions = ['anger', 'disgust', 'fear', 'joy', 'sadness', 'surprise']
            emotion_cols = [f"emotion_{e}" for e in emotions]
            
            if all(col in movie_data for col in emotion_cols):
                st.write("---")
                st.write("### 🎭 Emotional Signature")
                
                emotion_values = [movie_data[col] for col in emotion_cols]
                
                radar_df = pd.DataFrame({
                    'Emotion': [e.capitalize() for e in emotions],
                    'Score': emotion_values
                })
                
                fig_radar = px.line_polar(
                    radar_df, 
                    r='Score', 
                    theta='Emotion', 
                    line_close=True
                )
                fig_radar.update_traces(fill='toself', line_color='#00E054') # Letterboxd Green
                fig_radar.update_layout(
                    polar=dict(
                        radialaxis=dict(visible=True, range=[0, max(0.5, max(emotion_values) + 0.1)])
                    ),
                    showlegend=False,
                    margin=dict(l=40, r=40, t=20, b=20)
                )
                st.plotly_chart(fig_radar, use_container_width=True)
            
    else:
        st.info("No movies matched your search.")
