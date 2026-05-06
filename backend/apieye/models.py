from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from apieye.db import Base


class HeaderSnippet(Base):
    __tablename__ = "header_snippets"
    id = Column(Integer, primary_key=True)
    system_id = Column(Integer, nullable=False, default=1, index=True)
    name = Column(String(100), nullable=False)
    code = Column(Text, nullable=False, default="")
    ttl_seconds = Column(Integer, nullable=False, default=300)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    api_tasks = relationship("ApiTask", back_populates="header_snippet")


class ApiTask(Base):
    __tablename__ = "api_tasks"
    id = Column(Integer, primary_key=True)
    system_id = Column(Integer, nullable=False, default=1, index=True)
    name = Column(String(100), nullable=False)
    method = Column(String(10), nullable=False, default="GET")
    url = Column(Text, nullable=False, default="")
    query_params = Column(JSON, nullable=True)  # list of {key, value, enabled}
    body_type = Column(String(20), nullable=False, default="none")  # none|json|form|raw
    body = Column(Text, nullable=True)
    header_snippet_id = Column(Integer, ForeignKey("header_snippets.id", ondelete="SET NULL"), nullable=True)
    timeout = Column(Integer, nullable=False, default=30)
    polling_interval = Column(Integer, nullable=False, default=60)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

    header_snippet = relationship("HeaderSnippet", back_populates="api_tasks")
    histories = relationship("ApiHistory", back_populates="api_task", cascade="all, delete-orphan")


class ApiHistory(Base):
    __tablename__ = "api_histories"
    id = Column(Integer, primary_key=True)
    api_task_id = Column(Integer, ForeignKey("api_tasks.id", ondelete="CASCADE"), nullable=False)
    system_id = Column(Integer, nullable=False, default=1, index=True)
    status_code = Column(Integer, nullable=True)
    response_headers = Column(JSON, nullable=True)
    response_data = Column(JSON, nullable=True)
    response_text = Column(Text, nullable=True)
    result_data = Column(JSON, nullable=True)  # row-shaped snapshot for hash/diff (same as SQL)
    result_hash = Column(String(64), nullable=False)
    executed_at = Column(DateTime, default=func.now())
    is_different = Column(Boolean, default=True)
    diff_markers = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)

    api_task = relationship("ApiTask", back_populates="histories")
