from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from sqleye.db import Base


class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    system_id = Column(Integer, nullable=False, unique=True, default=1)
    name = Column(String(100), nullable=False)
    db_type = Column(String(20), nullable=False)
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String(100), nullable=False)
    password = Column(Text, nullable=False)
    database = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    query_tasks = relationship("QueryTask", back_populates="session", cascade="all, delete-orphan")


class QueryTask(Base):
    __tablename__ = "query_tasks"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    name = Column(String(100), nullable=False)
    sql = Column(Text, nullable=False)
    polling_interval = Column(Integer, default=2)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

    session = relationship("Session", back_populates="query_tasks")


class QueryHistory(Base):
    __tablename__ = "query_histories"
    id = Column(Integer, primary_key=True)
    query_task_id = Column(Integer, ForeignKey("query_tasks.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    result_data = Column(JSON, nullable=False)
    result_hash = Column(String(64), nullable=False)
    executed_at = Column(DateTime, default=func.now())
    is_different = Column(Boolean, default=True)
    diff_markers = Column(JSON)


class FieldSearchTask(Base):
    __tablename__ = "field_search_tasks"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    name = Column(String(100), nullable=False)
    expression = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())
