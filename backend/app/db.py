from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .config import settings
engine = create_engine(settings.database_url, pool_pre_ping=True, **({'connect_args':{'connect_timeout':10},'pool_timeout':10} if settings.database_url.startswith('postgresql') else {}))
Session = sessionmaker(engine, expire_on_commit=False)
def get_db():
    with Session() as session:
        yield session
