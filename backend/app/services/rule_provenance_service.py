"""
Rule provenance service: snapshot → extracted sentences → cited rules.

Completes the defendability chain for scheme rules:

    Government source → fetch (raw snapshot) → EXTRACTED_TEXT
        → sentence search (deterministic segmentation, no NLP)
        → admin links a rule to the exact sentence that justifies it
        → tbl_scheme_rule_provenance row (MANUAL, PENDING)
        → second admin click → VERIFIED (timestamped)

HARD INVARIANT (unchanged): this service never writes to
tbl_scheme_eligibility_rule. Provenance annotates existing rules; rule
values still change only through the reviewed ingestion workflow.
"""

from __future__ import annotations

import html as html_module
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheme import SchemeEligibilityRule, SchemeMaster
from app.models.scheme_source import (
    SchemeIngestionRun,
    SchemeRuleProvenance,
    SchemeSource,
    SchemeSourceContent,
    SchemeSourceDocument,
)

# Sentences longer than this are split-fragments or page noise; cap them so
# the provenance viewer shows quotable text, not concatenated paragraphs.
_MAX_SENTENCE_CHARS = 600
_MIN_SENTENCE_CHARS = 20

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(
    r"<(script|style|noscript)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_WS_RE = re.compile(r"\s+")


class ProvenanceError(Exception):
    status_code = 400
    message = "Provenance error"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message


def extract_sentences(raw_html: str) -> list[str]:
    """Deterministic HTML → sentence list. No NLP: strip scripts/styles/tags,
    unescape entities, split on sentence boundaries. Same input always
    yields the same sentences — the citation must be reproducible."""
    text = _SCRIPT_RE.sub(" ", raw_html)
    text = _TAG_RE.sub(" ", text)
    text = html_module.unescape(text)
    text = _WS_RE.sub(" ", text)

    sentences: list[str] = []
    for chunk in _SENTENCE_SPLIT.split(text):
        chunk = chunk.strip()
        if len(chunk) < _MIN_SENTENCE_CHARS:
            continue
        if len(chunk) > _MAX_SENTENCE_CHARS:
            # Keep long lead-ins quotable: hard-truncate at a word boundary.
            cut = chunk.rfind(" ", 0, _MAX_SENTENCE_CHARS)
            chunk = chunk[: cut if cut > _MIN_SENTENCE_CHARS else _MAX_SENTENCE_CHARS].rstrip()
        sentences.append(chunk)
    return sentences


async def ensure_extracted_content(
    db: AsyncSession, document: SchemeSourceDocument, raw_content: str
) -> SchemeSourceContent:
    """Create (or reuse) the EXTRACTED_TEXT variant of a document's RAW
    content. Idempotent per (document, content_type, language)."""
    existing = await db.execute(
        select(SchemeSourceContent).where(
            SchemeSourceContent.source_document_id == document.source_document_id,
            SchemeSourceContent.content_type == "EXTRACTED_TEXT",
        )
    )
    extracted = existing.scalars().first()
    if extracted is not None and extracted.raw_content:
        return extracted

    sentences = extract_sentences(raw_content)
    body = "\n".join(f"[{index}] {sentence}" for index, sentence in enumerate(sentences))
    if extracted is None:
        extracted = SchemeSourceContent(
            source_document_id=document.source_document_id,
            content_type="EXTRACTED_TEXT",
            raw_content=body,
            language=document.language or "en",
            processing_status="PROCESSED",
            extraction_version="sentence-segment-v1",
            retrieved_at=document.retrieved_at,
        )
        db.add(extracted)
    else:
        extracted.raw_content = body
        extracted.processing_status = "PROCESSED"
        extracted.extraction_version = "sentence-segment-v1"
    await db.flush()
    return extracted


async def sentences_for_document(
    db: AsyncSession, source_document_id: uuid.UUID
) -> list[str]:
    """Parsed sentence list for an extracted document. Extracts on demand
    if the RAW content exists but was never processed."""
    doc_result = await db.execute(
        select(SchemeSourceDocument).where(
            SchemeSourceDocument.source_document_id == source_document_id
        )
    )
    document = doc_result.scalars().first()
    if document is None:
        raise ProvenanceError("Source document not found")

    extracted_result = await db.execute(
        select(SchemeSourceContent).where(
            SchemeSourceContent.source_document_id == source_document_id,
            SchemeSourceContent.content_type == "EXTRACTED_TEXT",
        )
    )
    extracted = extracted_result.scalars().first()
    if extracted is None or not extracted.raw_content:
        raw_result = await db.execute(
            select(SchemeSourceContent).where(
                SchemeSourceContent.source_document_id == source_document_id,
                SchemeSourceContent.content_type == "RAW",
            )
        )
        raw = raw_result.scalars().first()
        if raw is None or not raw.raw_content:
            raise ProvenanceError("No RAW snapshot stored for this document")
        extracted = await ensure_extracted_content(db, document, raw.raw_content)

    # Stored as "[n] sentence" lines; strip the markers for display.
    return [
        line.split("] ", 1)[1]
        for line in extracted.raw_content.splitlines()
        if line.startswith("[") and "] " in line
    ]


def search_sentences(
    sentences: Sequence[str], query: str, limit: int = 30
) -> list[dict[str, Any]]:
    """Deterministic term-overlap ranking. All query terms must appear
    (case-insensitive); rank by total term frequency in the sentence."""
    terms = [t.lower() for t in re.split(r"\s+", query.strip()) if t]
    if not terms:
        return []
    results: list[dict[str, Any]] = []
    for index, sentence in enumerate(sentences):
        lowered = sentence.lower()
        if not all(term in lowered for term in terms):
            continue
        score = sum(lowered.count(term) for term in terms)
        results.append({"index": index, "text": sentence, "score": score})
    results.sort(key=lambda r: (-r["score"], r["index"]))
    return results[:limit]


class RuleProvenanceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Sentence browsing / search
    # ------------------------------------------------------------------

    async def document_sentences(
        self,
        source_document_id: uuid.UUID,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Sentences of one document, optionally filtered. The response
        mirrors the search API so the UI can treat both identically."""
        sentences = await sentences_for_document(self.db, source_document_id)
        if query:
            matches = search_sentences(sentences, query)
            return {
                "source_document_id": source_document_id,
                "query": query,
                "total_sentences": len(sentences),
                "matches": matches,
            }
        return {
            "source_document_id": source_document_id,
            "query": None,
            "total_sentences": len(sentences),
            "matches": [
                {"index": i, "text": s, "score": 0} for i, s in enumerate(sentences)
            ],
        }

    async def latest_document_for_scheme(self, scheme_id: uuid.UUID):
        """The most recent snapshot document relevant to a scheme: prefer
        documents explicitly linked to it, else the newest fetched document
        of any ACTIVE source (single-source platform for now)."""
        linked = await self.db.execute(
            select(SchemeSourceDocument)
            .where(SchemeSourceDocument.scheme_id == scheme_id)
            .order_by(SchemeSourceDocument.retrieved_at.desc())
            .limit(1)
        )
        document = linked.scalars().first()
        if document is not None:
            return document
        any_doc = await self.db.execute(
            select(SchemeSourceDocument)
            .join(SchemeSource, SchemeSource.source_id == SchemeSourceDocument.source_id)
            .where(SchemeSource.status == "ACTIVE")
            .order_by(SchemeSourceDocument.retrieved_at.desc())
            .limit(1)
        )
        return any_doc.scalars().first()

    # ------------------------------------------------------------------
    # Link / unlink / verify
    # ------------------------------------------------------------------

    async def link_rule(
        self,
        rule_id: uuid.UUID,
        source_document_id: uuid.UUID,
        sentence_index: int,
        *,
        admin_email: str | None = None,
    ) -> SchemeRuleProvenance:
        rule = await self.db.get(SchemeEligibilityRule, rule_id)
        if rule is None:
            raise ProvenanceError("Rule not found")
        if rule.scheme_id is None:
            raise ProvenanceError("Rule has no scheme association")

        sentences = await sentences_for_document(self.db, source_document_id)
        if sentence_index < 0 or sentence_index >= len(sentences):
            raise ProvenanceError(
                f"Sentence index {sentence_index} out of range (0..{len(sentences) - 1})"
            )
        sentence_text = sentences[sentence_index]

        # One provenance row per rule per document: relinking replaces the
        # previous citation instead of stacking rows.
        existing_result = await self.db.execute(
            select(SchemeRuleProvenance).where(
                SchemeRuleProvenance.rule_id == rule_id,
                SchemeRuleProvenance.source_document_id == source_document_id,
            )
        )
        provenance = existing_result.scalars().first()
        if provenance is None:
            provenance = SchemeRuleProvenance(
                rule_id=rule_id,
                source_document_id=source_document_id,
            )
            self.db.add(provenance)

        provenance.source_text = sentence_text
        provenance.source_section = f"sentence:{sentence_index}"
        provenance.source_reference = f"SENTENCE:{sentence_index}"
        provenance.extraction_method = "MANUAL"
        provenance.extraction_confidence = None
        # New/changed citation goes back to PENDING for verification.
        provenance.verification_status = "PENDING"
        provenance.verified_at = None
        await self.db.flush()
        return provenance

    async def unlink_rule(self, rule_id: uuid.UUID, provenance_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(SchemeRuleProvenance).where(
                SchemeRuleProvenance.rule_provenance_id == provenance_id,
                SchemeRuleProvenance.rule_id == rule_id,
            )
        )
        provenance = result.scalars().first()
        if provenance is None:
            raise ProvenanceError("Provenance link not found")
        await self.db.delete(provenance)
        await self.db.flush()

    async def verify_rule_link(
        self, rule_id: uuid.UUID, provenance_id: uuid.UUID
    ) -> SchemeRuleProvenance:
        result = await self.db.execute(
            select(SchemeRuleProvenance).where(
                SchemeRuleProvenance.rule_provenance_id == provenance_id,
                SchemeRuleProvenance.rule_id == rule_id,
            )
        )
        provenance = result.scalars().first()
        if provenance is None:
            raise ProvenanceError("Provenance link not found")
        provenance.verification_status = "VERIFIED"
        # Python-side timestamp: SQL-side func.now() would expire the ORM
        # attribute on flush and force an illegal lazy load in async sessions.
        provenance.verified_at = datetime.now(timezone.utc)
        await self.db.flush()
        return provenance

    async def provenance_for_scheme(self, scheme_id: uuid.UUID) -> list[dict[str, Any]]:
        """All rules of a scheme with their provenance (if any), for the
        admin rule list and the public scheme detail page."""
        rules_result = await self.db.execute(
            select(SchemeEligibilityRule)
            .where(SchemeEligibilityRule.scheme_id == scheme_id)
            .order_by(SchemeEligibilityRule.rule_priority)
        )
        rules = rules_result.scalars().all()
        if not rules:
            return []

        prov_result = await self.db.execute(
            select(SchemeRuleProvenance, SchemeSourceDocument.document_url)
            .join(
                SchemeSourceDocument,
                SchemeSourceDocument.source_document_id
                == SchemeRuleProvenance.source_document_id,
            )
            .where(
                SchemeRuleProvenance.rule_id.in_([r.rule_id for r in rules])
            )
        )
        by_rule: dict[uuid.UUID, dict[str, Any]] = {}
        for provenance, document_url in prov_result.all():
            by_rule.setdefault(provenance.rule_id, {
                "rule_provenance_id": provenance.rule_provenance_id,
                "source_text": provenance.source_text,
                "source_reference": provenance.source_reference,
                "extraction_method": provenance.extraction_method,
                "verification_status": provenance.verification_status,
                "verified_at": provenance.verified_at,
                "document_url": document_url,
            })
        return [
            {
                "rule_id": rule.rule_id,
                "parameter_name": rule.parameter_name,
                "operator": rule.operator,
                "required_value": rule.required_value,
                "rule_description": rule.rule_description,
                "provenance": by_rule.get(rule.rule_id),
            }
            for rule in rules
        ]
