"""
Education Record ORM Model.

Stores repeatable education qualifications per citizen:
10th/SSC, 12th/HSC, Diploma, ITI, Undergraduate, Postgraduate, PhD, etc.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.citizen import CitizenMaster


class EducationRecord(Base):
    __tablename__ = "tbl_education_record"

    record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    citizen_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 10TH_SSC | 12TH_HSC | DIPLOMA | ITI | UNDERGRADUATE | POSTGRADUATE | PHD | OTHER
    level: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Structured level-specific payload (board, stream, degree, branch, institute, university, semester, etc.)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    passing_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    percentage: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    citizen: Mapped["CitizenMaster"] = relationship(back_populates="education_records")

    def __repr__(self) -> str:
        return f"<EducationRecord {self.record_id} citizen={self.citizen_id} level={self.level}>"
