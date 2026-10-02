import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from db.models import Base

load_dotenv()

raw_url = os.getenv("DATABASE_URL", "").strip()

# Приводим к формату asyncpg
url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# Отрезаем query-параметры (asyncpg их не понимает в URL)
if "?" in url:
    url = url.split("?", 1)[0]

engine = create_async_engine(
    url,
    echo=False,
    pool_pre_ping=True,
    connect_args={"ssl": "require"},
)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
