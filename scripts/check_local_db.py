import psycopg

try:
    # Check local Docker PostgreSQL
    c = psycopg.connect(
        host="postgres",
        port=5432,
        dbname="autosaham",
        user="autosaham",
        password="95bb1d25a29aa452de340b7b0dc93ae8"
    )
    cur = c.cursor()
    cur.execute("SELECT version()")
    print("Local DB Version:", cur.fetchone()[0])
    
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
    tables = cur.fetchall()
    print(f"Local DB Tables ({len(tables)}):")
    for r in tables:
        print(" -", r[0])
    
    cur.close()
    c.close()
    print("\nLocal DB connection successful!")
except Exception as e:
    print("Local DB Error:", e)