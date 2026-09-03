import sqlite3

def print_stats():
    conn = sqlite3.connect('letterboxd.db')
    c = conn.cursor()
    
    print(f"Films: {c.execute('SELECT COUNT(*) FROM films').fetchone()[0]}")
    print(f"Cast Members: {c.execute('SELECT COUNT(*) FROM cast_members').fetchone()[0]}")
    print(f"Crew Members: {c.execute('SELECT COUNT(*) FROM crew_members').fetchone()[0]}")
    print(f"Details: {c.execute('SELECT COUNT(*) FROM film_details').fetchone()[0]}")
    print(f"Genres: {c.execute('SELECT COUNT(*) FROM film_genres').fetchone()[0]}")
    print(f"Reviews: {c.execute('SELECT COUNT(*) FROM film_reviews').fetchone()[0]}")
    
    conn.close()

if __name__ == '__main__':
    print_stats()
