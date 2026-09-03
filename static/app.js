let radarChart = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    fetchMovies();
    
    // Search functionality
    document.getElementById('searchInput').addEventListener('input', (e) => {
        const searchTerm = e.target.value.toLowerCase();
        const items = document.querySelectorAll('.movie-item');
        items.forEach(item => {
            const title = item.querySelector('h4').textContent.toLowerCase();
            if (title.includes(searchTerm)) {
                item.style.display = 'block';
            } else {
                item.style.display = 'none';
            }
        });
    });
});

async function fetchMovies() {
    try {
        const response = await fetch('/api/movies');
        const movies = await response.json();
        
        const listEl = document.getElementById('movieList');
        listEl.innerHTML = ''; // Clear loading
        
        movies.forEach(movie => {
            const li = document.createElement('li');
            li.className = 'movie-item';
            li.innerHTML = `
                <h4>${movie.film_name}</h4>
                <p>NLP: ${movie.avg_predicted_sentiment.toFixed(1)} ⭐</p>
            `;
            li.addEventListener('click', () => {
                // Remove active class from all
                document.querySelectorAll('.movie-item').forEach(el => el.classList.remove('active'));
                li.classList.add('active');
                loadMovieDetails(movie.film_id, movie.film_name);
            });
            listEl.appendChild(li);
        });
    } catch (error) {
        console.error("Error fetching movies:", error);
        document.getElementById('movieList').innerHTML = '<li style="color:red">Error loading datalink.</li>';
    }
}

async function loadMovieDetails(film_id, film_name) {
    // Show UI
    document.getElementById('emptyState').classList.add('hidden');
    document.getElementById('movieDetails').classList.remove('hidden');
    
    // Reset poster
    const posterImg = document.getElementById('moviePoster');
    const posterLoader = document.getElementById('posterLoader');
    posterImg.src = '';
    posterLoader.style.display = 'block';

    try {
        // Fetch details
        const response = await fetch(`/api/movie/${film_id}`);
        const data = await response.json();
        
        // Update DOM
        document.getElementById('movieTitle').textContent = data.film_name;
        document.getElementById('movieGenres').textContent = data.genres || 'Unknown Genre';
        document.getElementById('metricSentiment').textContent = data.avg_predicted_sentiment.toFixed(2);
        document.getElementById('metricRating').textContent = data.avg_original_rating.toFixed(2);
        document.getElementById('metricControversy').textContent = data.std_predicted_sentiment.toFixed(2);
        
        document.getElementById('statReviews').textContent = `${data.total_reviews} Reviews`;
        document.getElementById('statSentences').textContent = `${data.total_sentences} Sentences`;

        // Render Chart
        renderRadarChart(data);

        // Fetch Poster and Description asynchronously so it doesn't block UI
        fetchInfo(film_name);
        
    } catch (error) {
        console.error("Error fetching movie details:", error);
    }
}

async function fetchInfo(film_name) {
    try {
        // Reset description while loading
        document.getElementById('movieDescription').textContent = "Loading description...";
        
        const response = await fetch(`/api/info?film_name=${encodeURIComponent(film_name)}`);
        const data = await response.json();
        
        const posterImg = document.getElementById('moviePoster');
        posterImg.src = data.poster_url;
        
        // Set description
        document.getElementById('movieDescription').textContent = data.description;
        
        // Hide loader when image loads or fails
        posterImg.onload = () => {
            document.getElementById('posterLoader').style.display = 'none';
        };
        posterImg.onerror = () => {
            document.getElementById('posterLoader').style.display = 'none';
            posterImg.src = 'https://via.placeholder.com/300x450/0b0e14/00e5ff?text=No+Poster+Found';
        };
    } catch (error) {
        console.error("Error fetching info:", error);
        document.getElementById('posterLoader').style.display = 'none';
        document.getElementById('movieDescription').textContent = "Failed to load description.";
    }
}

function renderRadarChart(data) {
    const ctx = document.getElementById('emotionRadar').getContext('2d');
    
    const emotions = ['anger', 'disgust', 'fear', 'joy', 'sadness', 'surprise'];
    const values = emotions.map(e => data[`emotion_${e}`] || 0);

    if (radarChart) {
        radarChart.destroy();
    }

    // Chart.js global defaults for dark theme
    Chart.defaults.color = '#8b9bb4';
    Chart.defaults.font.family = "'Inter', sans-serif";

    radarChart = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: emotions.map(e => e.toUpperCase()),
            datasets: [{
                label: 'Emotion Profile',
                data: values,
                backgroundColor: 'rgba(0, 229, 255, 0.2)',
                borderColor: '#00e5ff',
                pointBackgroundColor: '#00b4d8',
                pointBorderColor: '#fff',
                pointHoverBackgroundColor: '#fff',
                pointHoverBorderColor: '#00e5ff',
                borderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                r: {
                    angleLines: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)',
                        circular: true
                    },
                    pointLabels: {
                        color: '#00e5ff',
                        font: {
                            size: 14,
                            weight: '600',
                            family: "'Outfit', sans-serif"
                        }
                    },
                    ticks: {
                        display: false, // Hide numeric ticks on axis
                        max: Math.max(...values, 0.3) + 0.1,
                        min: 0
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: 'rgba(11, 14, 20, 0.9)',
                    titleColor: '#00e5ff',
                    bodyColor: '#fff',
                    borderColor: 'rgba(0, 229, 255, 0.3)',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: false,
                    callbacks: {
                        label: function(context) {
                            return (context.raw * 100).toFixed(1) + '%';
                        }
                    }
                }
            }
        }
    });
}
