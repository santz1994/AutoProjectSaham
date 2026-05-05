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
    cur.execute("SELECT version()")
    print("Version:", cur.fetchone()[0])
    cur.execute("SELECT datname FROM pg_database WHERE datistemplate=false ORDER BY datname")
    print("Databases:")
    for r in cur.fetchall():
        print(" -", r[0])
    cur.execute("SELECT current_user, current_database()")
    print("Connected as:", cur.fetchone())
    cur.close()
    c.close()
    print("Connection successful!")
except Exception as e:
    print("Error:", e)