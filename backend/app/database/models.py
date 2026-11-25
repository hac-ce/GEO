# SQLAlchemy ORM 模型：用户、品牌、问题、回答和采集任务。

from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTable
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyBaseAccessTokenTable
from backend.app.core.timestamps import utc_now


class Base(DeclarativeBase):
    pass


# 复用 FastAPI Users 的邮箱、密码哈希和用户状态字段。
class User(SQLAlchemyBaseUserTable[int], Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


# 框架维护每次登录的随机令牌和创建时间；退出时删除当前令牌记录。
class AccessToken(SQLAlchemyBaseAccessTokenTable[int], Base):
    __tablename__ = "auth_access_tokens"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


# 品牌记录所有者，旧数据暂时允许 user_id 为空。
class Brand(Base):
    __tablename__ = "brand"
    __table_args__ = (Index("ix_brand_user_id_id", "user_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    aliases: Mapped[list[str]] = mapped_column(JSON)
    domain: Mapped[str] = mapped_column(String(253))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Prompt(Base):
    __tablename__ = "prompts"
    __table_args__ = (Index("ix_prompts_brand_id_id", "brand_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brand.id"))
    question: Mapped[str] = mapped_column(String(500))


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (Index("ix_observations_prompt_id_id", "prompt_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("prompts.id"))
    question: Mapped[str] = mapped_column(String(500))
    answer: Mapped[str] = mapped_column(Text)
    mentioned: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    prompted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utc_now, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)


# 持久化采集状态及提交时的输入快照。
class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_id", "status", "id"),
        Index("ix_jobs_prompt_id_id", "prompt_id", "id"),
        Index("ix_jobs_status_lease", "status", "lease_expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("prompts.id"))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    collection_method: Mapped[str] = mapped_column(String(24), default="api", server_default="api")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    observation_id: Mapped[int | None] = mapped_column(ForeignKey("observations.id"), nullable=True)
    question_snapshot: Mapped[str | None] = mapped_column(String(500), nullable=True)
    brand_name_snapshot: Mapped[str | None] = mapped_column(String(80), nullable=True)
    brand_aliases_snapshot: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utc_now, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    execution_token: Mapped[str | None] = mapped_column(String(32), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# 只有携带幂等编号的提交才保存映射；这不是日志表或回答缓存。
class JobSubmission(Base):
    __tablename__ = "job_submissions"
    __table_args__ = (UniqueConstraint("user_id", "key_hash", name="uq_job_submissions_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    key_hash: Mapped[str] = mapped_column(String(64))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
