import os
import psycopg

try:
    c = psycopg.connect(
        host=os.environ.get("DB_HOST", "dnkproject-do-user-36317256-0.a.db.ondigitalocean.com"),
        port=int(os.environ.get("DB_PORT", 25060)),
        dbname=os.environ.get("DB_NAME", "defaultdb"),
        user=os.environ.get("DB_USER", "doadmin"),
        password=os.environ["DB_PASSWORD"],
        sslmode="require"
    )
    cur = c.cursor()
    
    # List tables
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    tables = cur.fetchall()
    print(f"Tables ({len(tables)}):")
    for r in tables:
        print(" -", r[0])
    
    # Check .env on server
    cur.close()
    c.close()
    print("\nConnection successful!")
except Exception as e:
    print("Error:", e)