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
    
    # List all schemas
    cur.execute("SELECT schema_name FROM information_schema.schemata ORDER BY schema_name")
    print("Schemas:")
    for r in cur.fetchall():
        print(" -", r[0])
    
    # List tables in ALL schemas
    cur.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema') ORDER BY table_schema, table_name")
    tables = cur.fetchall()
    print(f"\nTables ({len(tables)}):")
    for r in tables:
        print(f" - {r[0]}.{r[1]}")
    
    # Check if alembic_version exists
    cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name='alembic_version')")
    print(f"\nAlembic version table exists: {cur.fetchone()[0]}")
    
    cur.close()
    c.close()
    print("\nDone!")
except Exception as e:
    print("Error:", e)