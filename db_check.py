import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

url = os.getenv("DATABASE_URL")
if not url:
    raise RuntimeError("DATABASE_URL is missing in .env")

if url.startswith("postgresql://"):
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)
elif url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql+psycopg://", 1)

engine = create_engine(url, pool_pre_ping=True)

with engine.connect() as connection:
    version = connection.execute(text("SELECT version()")).scalar_one()
    database = connection.execute(text("SELECT current_database()")).scalar_one()

print("Connection OK")
print("Database:", database)
print("PostgreSQL:", version)
