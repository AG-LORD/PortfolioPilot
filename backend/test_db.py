from sqlalchemy import text

from app.database import engine


with engine.connect() as connection:
    result = connection.execute(text("SELECT 1"))
    print("Database connection successful:", result.scalar())
