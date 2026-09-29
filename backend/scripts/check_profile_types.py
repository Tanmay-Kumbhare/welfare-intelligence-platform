import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def main():
    engine = create_async_engine('postgresql+asyncpg://postgres:govt.Welfare%231@db.scqoilhgjhfbxagmgkma.supabase.co:5432/postgres')
    async with engine.connect() as conn:
        result = await conn.execute(text('SELECT citizen_id, profile_types FROM tbl_citizen_master'))
        for row in result:
            print(f"ID: {row[0]}, Profile Types: {row[1]}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
