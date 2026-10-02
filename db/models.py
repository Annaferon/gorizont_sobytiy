from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class Post(Base):
    __tablename__ = 'posts'
    id = Column(Integer, primary_key=True)
    title = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    image_url = Column(Text)
    status = Column(String(20), default='draft')
    created_at = Column(DateTime, default=datetime.utcnow)
    published_at = Column(DateTime)
    hash = Column(String(64), unique=True)

class Queue(Base):
    __tablename__ = 'queue'
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey('posts.id', ondelete='CASCADE'))
    scheduled_at = Column(DateTime, nullable=False)
    status = Column(String(20), default='pending')

class BotState(Base):
    __tablename__ = 'bot_state'
    key = Column(String(50), primary_key=True)
    value = Column(Text)
