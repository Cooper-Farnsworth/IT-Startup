import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, Article

db = SessionLocal()
count = db.query(Article).count()
print(f"📊 Всего статей в БД: {count}")
db.close()