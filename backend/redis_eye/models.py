from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from redis_eye.db import Base


class RedisSession(Base):
    __tablename__ = "redis_sessions"
    __table_args__ = (
        UniqueConstraint("system_id", "name", name="uq_redis_sessions_system_name"),
        Index("ix_redis_sessions_system_id", "system_id"),
    )

    id = Column(Integer, primary_key=True)
    system_id = Column(Integer, nullable=False, default=1)
    name = Column(String(100), nullable=False)
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False, default=6379)
    password = Column(Text, nullable=True)
    db_index = Column(Integer, nullable=False, default=0)
    use_ssl = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    tasks = relationship("RedisTask", back_populates="session", cascade="all, delete-orphan")


class RedisTask(Base):
    __tablename__ = "redis_tasks"
    __table_args__ = (Index("ix_redis_tasks_system_order", "system_id", "display_order"),)

    id = Column(Integer, primary_key=True)
    system_id = Column(Integer, nullable=False, default=1, index=True)
    redis_session_id = Column(Integer, ForeignKey("redis_sessions.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    redis_key = Column(String(512), nullable=False)
    color_step_percent = Column(Integer, nullable=False, default=10)
    display_order = Column(Integer, nullable=False, default=0)
    latest_value = Column(Text, nullable=True)
    latest_value_type = Column(String(32), nullable=True)
    last_changed_at = Column(DateTime, nullable=True)
    change_count_since_seen = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    session = relationship("RedisSession", back_populates="tasks")
    histories = relationship("RedisTaskHistory", back_populates="task", cascade="all, delete-orphan")


class RedisTaskHistory(Base):
    __tablename__ = "redis_task_histories"
    __table_args__ = (Index("ix_redis_task_histories_task_recorded", "task_id", "recorded_at"),)

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("redis_tasks.id", ondelete="CASCADE"), nullable=False)
    value = Column(Text, nullable=True)
    value_type = Column(String(32), nullable=True)
    recorded_at = Column(DateTime, default=func.now())

    task = relationship("RedisTask", back_populates="histories")
