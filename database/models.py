from sqlalchemy import Column, BigInteger, String, DateTime
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(BigInteger, primary_key=True, index=True)
    
    username = Column(String, nullable=True)
    
    full_name = Column(String, nullable=True)
    
    joined_date = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<User(id={self.id}, name={self.full_name})>"