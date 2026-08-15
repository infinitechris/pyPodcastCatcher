import sqlite3
from pathlib import Path

db_path = Path("podcasts.db")
with sqlite3.connect(db_path) as conn:
    # Get The Daily feed (ID 2) episodes, ordered by published date, newest first
    rows = conn.execute("""
        SELECT title, published 
        FROM episodes 
        WHERE feed_id = 2 
        ORDER BY published DESC 
        LIMIT 5
    """).fetchall()
    
    print("5 Newest episodes in database for The Daily:")
    for title, published in rows:
        print(f"  {published}: {title}")
