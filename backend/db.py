from sqlalchemy import create_engine, Column, Integer, String, JSON
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
    repo_url = Column(String, nullable=False)
    name = Column(String, nullable=False)
    details = Column(JSON)  # Store JSON or text details

    def __repr__(self):
        return f"<Repository(id={self.id}, repo_url='{self.repo_url}', name='{self.name}')>"

class PullRequest(Base):
    __tablename__ = "pull_requests"
    id = Column(Integer, primary_key=True, index=True)
    repo_url = Column(String, nullable=False)
    developer = Column(String, nullable=False)
    pr_number = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    details = Column(JSON)  # Store JSON or text details

    def __repr__(self):
        return f"<PullRequest(id={self.id}, repo_url='{self.repo_url}', pr_number={self.pr_number}, developer='{self.developer}', title='{self.title}')>"

def init_db():
    Base.metadata.create_all(bind=engine) 

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
