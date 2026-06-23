import asyncio
import dotenv
import sqlalchemy as sa
dotenv.load_dotenv()

from src.infra.db import async_engine, SQLModel

async def init_db():
    if async_engine is None:
        raise ValueError("Database engine is not initialized. Check your DATABASE_URL in .env")
        
    async with async_engine.begin() as conn:
        # Create legacy C++ engine tables if not exist
        await conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS orders (
                timestamp TEXT,
                strategy_name TEXT,
                orderid TEXT,
                symbol TEXT,
                direction TEXT,
                price DOUBLE PRECISION,
                volume DOUBLE PRECISION,
                traded DOUBLE PRECISION,
                status TEXT
            );
        """))
        
        await conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS trades (
                timestamp TEXT,
                strategy_name TEXT,
                tradeid TEXT,
                symbol TEXT,
                direction TEXT,
                price DOUBLE PRECISION,
                volume DOUBLE PRECISION
            );
        """))
        
        await conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS contract_equity (
                symbol TEXT PRIMARY KEY,
                exchange TEXT,
                product TEXT,
                size DOUBLE PRECISION,
                pricetick DOUBLE PRECISION,
                gateway_name TEXT
            );
        """))
        
        await conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS contract_option (
                symbol TEXT PRIMARY KEY,
                expiry TEXT,
                type TEXT,
                strike DOUBLE PRECISION,
                underlying TEXT
            );
        """))
        
        # Create SQLModel managed tables
        await conn.run_sync(SQLModel.metadata.create_all)
        
        # Insert baseline and deep hedging models in model_registry to satisfy foreign key constraint
        await conn.execute(sa.text("""
            INSERT INTO model_registry (id, torchscript_path, training_run_id, input_shape, validation_cvar, registered_at)
            VALUES ('baseline', '/mock/path', 'mock_run', '[1, 5]'::jsonb, 0.0, NOW())
            ON CONFLICT (id) DO NOTHING;
        """))
        await conn.execute(sa.text("""
            INSERT INTO model_registry (id, torchscript_path, training_run_id, input_shape, validation_cvar, registered_at)
            VALUES ('deep_hedge_ffnn', '/mock/path', 'mock_run', '[1, 5]'::jsonb, 0.0, NOW())
            ON CONFLICT (id) DO NOTHING;
        """))
        await conn.execute(sa.text("""
            INSERT INTO model_registry (id, torchscript_path, training_run_id, input_shape, validation_cvar, registered_at)
            VALUES ('deep_hedge_lstm', '/mock/path', 'mock_run', '[1, 5]'::jsonb, 0.0, NOW())
            ON CONFLICT (id) DO NOTHING;
        """))
        await conn.execute(sa.text("""
            INSERT INTO model_registry (id, torchscript_path, training_run_id, input_shape, validation_cvar, registered_at)
            VALUES ('deep_hedge_adversarial', '/mock/path', 'mock_run', '[1, 5]'::jsonb, 0.0, NOW())
            ON CONFLICT (id) DO NOTHING;
        """))
        await conn.execute(sa.text("""
            INSERT INTO model_registry (id, torchscript_path, training_run_id, input_shape, validation_cvar, registered_at)
            VALUES ('deep_hedge_ffnn_v2', '/mock/path', 'mock_run', '[1, 5]'::jsonb, 0.0, NOW())
            ON CONFLICT (id) DO NOTHING;
        """))
        await conn.execute(sa.text("""
            INSERT INTO model_registry (id, torchscript_path, training_run_id, input_shape, validation_cvar, registered_at)
            VALUES ('deep_hedge_lstm_v2', '/mock/path', 'mock_run', '[1, 5]'::jsonb, 0.0, NOW())
            ON CONFLICT (id) DO NOTHING;
        """))
        await conn.execute(sa.text("""
            INSERT INTO model_registry (id, torchscript_path, training_run_id, input_shape, validation_cvar, registered_at)
            VALUES ('deep_hedge_adversarial_v2', '/mock/path', 'mock_run', '[1, 5]'::jsonb, 0.0, NOW())
            ON CONFLICT (id) DO NOTHING;
        """))
        
    print("Database tables initialized successfully!")

if __name__ == "__main__":
    asyncio.run(init_db())
