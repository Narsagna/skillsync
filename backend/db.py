from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///skillsync.db"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=30,
    pool_timeout=60,
    pool_recycle=3600,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Repository(Base):
    __tablename__ = "repositories"
    id = Column(Integer, primary_key=True, index=True)
    repo_url = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    details = Column(Text)  # Store JSON or text details

    def __repr__(self):
        return f"<Repository(id={self.id}, repo_url='{self.repo_url}', name='{self.name}')>"

def init_db():
    Base.metadata.create_all(bind=engine) 