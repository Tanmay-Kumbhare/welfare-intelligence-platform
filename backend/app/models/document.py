import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

class CitizenDocument(Base):
    __tablename__ = "tbl_citizen_document"

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    citizen_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"), nullable=False)
    
    # e.g. "12TH_MARKSHEET", "IDENTITY_PROOF"
    requirement_type: Mapped[str] = mapped_column(String(100), nullable=False)
    
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # What did the classifier detect?
    detected_type: Mapped[str | None] = mapped_column(String(100))
    
    # VALID | INVALID | PENDING
    validation_status: Mapped[str] = mapped_column(String(50), default="PENDING")
    validation_message: Mapped[str | None] = mapped_column(Text)
    
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<CitizenDocument {self.document_id} {self.original_filename}>"
