"""
Eligibility Assessment ORM model.

Table: tbl_eligibility_assessment
  - Stores the result of evaluating one citizen against one scheme.
  - evaluation_details JSONB preserves per-rule evidence for explainability
    and future welfare-access diagnosis.

evaluation_details structure:
{
  "overall_result": true,
  "group_combining_operator": "AND",
  "groups": [
    {
      "group_name": "Farmer Classification",
      "intra_group_operator": "AND",
      "group_passed": true,
      "rules": [
        {
          "parameter": "citizen_type",
          "actual": "FARMER",
          "operator": "==",
          "required": "FARMER",
          "passed": true,
          "description": "Must be registered as a farmer"
        }
      ]
    }
  ]
}
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class EligibilityAssessment(Base):
    __tablename__ = "tbl_eligibility_assessment"
    __table_args__ = (
        # One assessment record per citizen-scheme pair.
        # Re-evaluation uses upsert (INSERT ... ON CONFLICT DO UPDATE).
        UniqueConstraint("citizen_id", "scheme_id", name="uq_citizen_scheme_assessment"),
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    citizen_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
        nullable=False,
    )
    scheme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_scheme_master.scheme_id", ondelete="CASCADE"),
        nullable=False,
    )
    eligibility_result: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # 1-2 sentence human-readable summary of why the citizen is/is not eligible
    reason: Mapped[str | None] = mapped_column(Text)
    # Full per-rule evidence — see module docstring for schema
    evaluation_details: Mapped[dict | None] = mapped_column(JSONB)
    assessment_date: Mapped[date] = mapped_column(Date, server_default=func.current_date())

    citizen: Mapped["CitizenMaster"] = relationship(back_populates="assessments")  # type: ignore[name-defined]
    scheme: Mapped["SchemeMaster"] = relationship(back_populates="assessments")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        status = "ELIGIBLE" if self.eligibility_result else "INELIGIBLE"
        return f"<EligibilityAssessment {self.citizen_id} → {self.scheme_id}: {status}>"
