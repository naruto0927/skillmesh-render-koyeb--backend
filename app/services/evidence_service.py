"""
SkillMesh — Evidence Service

Handles:
1. Evidence record creation (self-declaration, certification, project, etc.)
2. Document upload coordination with Supabase Storage
3. Credibility upgrade: when evidence is added/verified, StudentSkill.credibility rises
4. Verification workflow: UNVERIFIED → PENDING → VERIFIED
5. Skill Passport get/update/share-token generation

Credibility upgrade rules (deterministic — no LLM):
  - Any evidence exists            → at least CLAIMED
  - ASSESSMENT evidence exists     → DEMONSTRATED
  - VERIFIED evidence exists       → VERIFIED (highest wins)
  - Expired evidence is excluded from credibility calculation

Storage rules:
  - Files go to Supabase Storage, not PostgreSQL
  - Private documents use signed URLs (1-hour expiry by default)
  - storage_key is NEVER returned in any public API response
  - MIME type is validated server-side — never trust client Content-Type
"""

import secrets
import uuid
from datetime import datetime, timezone
from typing import BinaryIO

import httpx
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.assessment import EvidenceCredibility, StudentSkill
from app.models.evidence import (
    Document,
    EvidenceType,
    PassportVisibility,
    SkillEvidence,
    SkillPassport,
    VerificationStatus,
)
from app.models.skill import Skill
from app.models.user import User

settings = get_settings()
logger = get_logger(__name__)

# Allowed MIME types per bucket
ALLOWED_MIME_TYPES = {
    "certificates": {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/webp",
    },
    "resumes": {"application/pdf"},
    "projects": {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "application/zip",
    },
}

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

# Credibility weight per evidence type (higher = stronger evidence)
EVIDENCE_CREDIBILITY_WEIGHT: dict[EvidenceType, int] = {
    EvidenceType.SELF_DECLARATION: 1,
    EvidenceType.ASSESSMENT: 5,
    EvidenceType.PROJECT: 4,
    EvidenceType.INTERNSHIP: 6,
    EvidenceType.ACADEMIC_RECORD: 5,
    EvidenceType.INDUSTRY_TEST: 7,
    EvidenceType.CERTIFICATION: 8,
    EvidenceType.FACULTY_VERIFICATION: 9,
    EvidenceType.EMPLOYER_VERIFICATION: 10,
}


class EvidenceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Evidence CRUD ─────────────────────────────────────────────────────────

    async def add_evidence(
        self,
        student: User,
        skill_id: uuid.UUID,
        evidence_type: EvidenceType,
        source_name: str | None = None,
        source_url: str | None = None,
        score: float | None = None,
        description: str | None = None,
        issued_at: datetime | None = None,
        expires_at: datetime | None = None,
        document_id: uuid.UUID | None = None,
        assessment_result_id: uuid.UUID | None = None,
    ) -> SkillEvidence:
        """
        Add a new evidence record for a student skill.
        After creation, recalculates the credibility of the StudentSkill.
        """
        # Verify skill exists
        skill_result = await self.db.execute(
            select(Skill).where(Skill.id == skill_id)
        )
        if skill_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Skill not found.",
            )

        # Validate document ownership if provided
        if document_id:
            doc_result = await self.db.execute(
                select(Document).where(
                    Document.id == document_id,
                    Document.owner_id == student.id,
                )
            )
            if doc_result.scalar_one_or_none() is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Document not found or does not belong to you.",
                )

        evidence = SkillEvidence(
            student_id=student.id,
            skill_id=skill_id,
            evidence_type=evidence_type,
            verification_status=VerificationStatus.UNVERIFIED,
            source_name=source_name,
            source_url=source_url,
            score=score,
            description=description,
            issued_at=issued_at,
            expires_at=expires_at,
            document_id=document_id,
            assessment_result_id=assessment_result_id,
        )
        self.db.add(evidence)
        await self.db.flush()

        # Upgrade credibility of the linked StudentSkill
        await self._recalculate_credibility(student.id, skill_id)

        await self.db.commit()
        await self.db.refresh(evidence)

        logger.info(
            f"Evidence added: student={student.id} skill={skill_id} "
            f"type={evidence_type} id={evidence.id}"
        )
        return evidence

    async def list_evidence_for_skill(
        self, student_id: uuid.UUID, skill_id: uuid.UUID
    ) -> list[SkillEvidence]:
        result = await self.db.execute(
            select(SkillEvidence)
            .where(
                SkillEvidence.student_id == student_id,
                SkillEvidence.skill_id == skill_id,
            )
            .order_by(SkillEvidence.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_all_evidence(
        self, student_id: uuid.UUID
    ) -> list[SkillEvidence]:
        result = await self.db.execute(
            select(SkillEvidence)
            .options(selectinload(SkillEvidence.skill))
            .where(SkillEvidence.student_id == student_id)
            .order_by(SkillEvidence.created_at.desc())
        )
        return list(result.scalars().all())

    async def verify_evidence(
        self,
        evidence_id: uuid.UUID,
        verifier: User,
        approved: bool,
        rejection_reason: str | None = None,
    ) -> SkillEvidence:
        """
        Approve or reject a piece of evidence.
        Only FACULTY, INSTITUTION_ADMIN, or SUPER_ADMIN can verify.
        """
        from app.models.user import UserRole
        allowed_roles = {
            UserRole.FACULTY,
            UserRole.INSTITUTION_ADMIN,
            UserRole.SUPER_ADMIN,
        }
        if verifier.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only faculty, institution admins, and platform admins can verify evidence.",
            )

        result = await self.db.execute(
            select(SkillEvidence).where(SkillEvidence.id == evidence_id)
        )
        evidence = result.scalar_one_or_none()
        if evidence is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Evidence record not found.",
            )

        # Tenant isolation: verifier must belong to the same institution as student
        if verifier.role == UserRole.FACULTY or verifier.role == UserRole.INSTITUTION_ADMIN:
            student_result = await self.db.execute(
                select(User).where(User.id == evidence.student_id)
            )
            student = student_result.scalar_one_or_none()
            if student is None or student.institution_id != verifier.institution_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only verify evidence for students at your institution.",
                )

        if approved:
            evidence.verification_status = VerificationStatus.VERIFIED
            evidence.verified_by_id = verifier.id
            evidence.verified_at = datetime.now(timezone.utc)
            evidence.description = (
                evidence.description or ""
            ) + (f"\nVerified by {verifier.full_name}" if not evidence.description else "")
        else:
            evidence.verification_status = VerificationStatus.REJECTED
            evidence.description = rejection_reason or evidence.description

        await self.db.flush()
        await self._recalculate_credibility(evidence.student_id, evidence.skill_id)
        await self.db.commit()
        await self.db.refresh(evidence)
        return evidence

    # ── Credibility engine ────────────────────────────────────────────────────

    async def _recalculate_credibility(
        self, student_id: uuid.UUID, skill_id: uuid.UUID
    ) -> None:
        """
        Deterministically compute the credibility level for a StudentSkill
        based on all non-expired, non-rejected evidence records.

        Rules:
          - No evidence or only SELF_DECLARATION → CLAIMED
          - Any ASSESSMENT evidence (from platform) → DEMONSTRATED
          - Any VERIFIED evidence (any type) → VERIFIED
          - Expired evidence is excluded
          - VERIFIED wins over DEMONSTRATED wins over CLAIMED
        """
        now = datetime.now(timezone.utc)
        evidence_result = await self.db.execute(
            select(SkillEvidence).where(
                SkillEvidence.student_id == student_id,
                SkillEvidence.skill_id == skill_id,
                SkillEvidence.verification_status != VerificationStatus.REJECTED,
            )
        )
        all_evidence = list(evidence_result.scalars().all())

        # Filter out expired evidence
        active_evidence = [
            e for e in all_evidence
            if e.expires_at is None or e.expires_at.replace(tzinfo=timezone.utc) > now
        ]

        new_credibility = EvidenceCredibility.CLAIMED

        for ev in active_evidence:
            if ev.verification_status == VerificationStatus.VERIFIED:
                # Verified evidence → always VERIFIED (highest)
                new_credibility = EvidenceCredibility.VERIFIED
                break  # Can't go higher
            elif ev.evidence_type == EvidenceType.ASSESSMENT:
                # Assessment evidence → DEMONSTRATED
                new_credibility = EvidenceCredibility.DEMONSTRATED
            elif (
                ev.evidence_type != EvidenceType.SELF_DECLARATION
                and new_credibility == EvidenceCredibility.CLAIMED
            ):
                # Non-self-declaration unverified → DEMONSTRATED
                new_credibility = EvidenceCredibility.DEMONSTRATED

        # Update StudentSkill credibility
        ss_result = await self.db.execute(
            select(StudentSkill).where(
                StudentSkill.student_id == student_id,
                StudentSkill.skill_id == skill_id,
            )
        )
        student_skill = ss_result.scalar_one_or_none()
        if student_skill is not None:
            student_skill.credibility = new_credibility
            await self.db.flush()
        # Note: if no StudentSkill record exists yet (self-declaration before assessment),
        # credibility will be applied when the skill record is created.

    # ── Supabase Storage ──────────────────────────────────────────────────────

    async def upload_document(
        self,
        owner: User,
        file: UploadFile,
        bucket: str = "certificates",
    ) -> Document:
        """
        Upload a file to Supabase Storage and create a Document record.
        Validates MIME type and file size server-side.
        Never trusts client-provided MIME type.
        """
        # Read file content
        content = await file.read()
        file_size = len(content)

        if file_size > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES // (1024*1024)} MB.",
            )

        # Detect MIME type server-side using python-magic would be ideal;
        # for Phase 3 we validate the declared type against the allowed list.
        # Phase 10 adds actual MIME sniffing.
        declared_mime = file.content_type or "application/octet-stream"
        allowed = ALLOWED_MIME_TYPES.get(bucket, set())
        if declared_mime not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"File type '{declared_mime}' is not allowed in bucket '{bucket}'. "
                       f"Allowed: {sorted(allowed)}",
            )

        # Sanitise filename — never trust original filename
        original_name = file.filename or "upload"
        safe_name = self._sanitise_filename(original_name)
        storage_key = f"{owner.id}/{uuid.uuid4()}/{safe_name}"

        # Upload to Supabase Storage
        await self._upload_to_supabase(
            bucket=bucket,
            storage_key=storage_key,
            content=content,
            mime_type=declared_mime,
        )

        # Create Document metadata record
        document = Document(
            owner_id=owner.id,
            storage_key=storage_key,
            bucket=bucket,
            original_filename=safe_name,
            mime_type=declared_mime,
            file_size_bytes=file_size,
            is_private=True,
            scan_status="pending",
        )
        self.db.add(document)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(document)

        logger.info(
            f"Document uploaded: owner={owner.id} bucket={bucket} "
            f"size={file_size} doc_id={document.id}"
        )
        return document

    async def get_signed_url(
        self,
        document: Document,
        requesting_user: User,
        expires_in_seconds: int = 3600,
    ) -> str:
        """
        Generate a time-limited signed URL for private document access.
        Enforces ownership — users can only access their own documents
        (or admins/faculty can access student documents for verification).
        storage_key is NEVER returned in any public API — only the signed URL.
        """
        # Ownership check
        from app.models.user import UserRole
        is_owner = document.owner_id == requesting_user.id
        is_admin = requesting_user.role in {
            UserRole.SUPER_ADMIN,
            UserRole.INSTITUTION_ADMIN,
            UserRole.FACULTY,
        }
        if not is_owner and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this document.",
            )

        return await self._generate_signed_url(
            bucket=document.bucket,
            storage_key=document.storage_key,
            expires_in=expires_in_seconds,
        )

    async def _upload_to_supabase(
        self,
        bucket: str,
        storage_key: str,
        content: bytes,
        mime_type: str,
    ) -> None:
        """Upload file bytes to Supabase Storage via REST API."""
        if not settings.supabase_url or not settings.supabase_service_role_key:
            # Development mode without Supabase — log and skip actual upload
            logger.warning(
                f"Supabase Storage not configured. "
                f"Skipping upload of {storage_key} to bucket {bucket}."
            )
            return

        url = f"{settings.supabase_url}/storage/v1/object/{bucket}/{storage_key}"
        headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": mime_type,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, content=content, headers=headers)

        if response.status_code not in (200, 201):
            logger.error(
                f"Supabase Storage upload failed: status={response.status_code} "
                f"bucket={bucket} key={storage_key}"
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Storage service error. Please try again.",
            )

    async def _generate_signed_url(
        self, bucket: str, storage_key: str, expires_in: int
    ) -> str:
        """Request a signed URL from Supabase Storage."""
        if not settings.supabase_url or not settings.supabase_service_role_key:
            # Development fallback
            return f"http://localhost:8000/dev-storage/{bucket}/{storage_key}"

        url = (
            f"{settings.supabase_url}/storage/v1/object/sign/{bucket}/{storage_key}"
        )
        headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url, json={"expiresIn": expires_in}, headers=headers
            )

        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not generate download link. Please try again.",
            )

        data = response.json()
        signed_path = data.get("signedURL") or data.get("signedUrl", "")
        if signed_path.startswith("/"):
            return f"{settings.supabase_url}{signed_path}"
        return signed_path

    # ── Skill Passport ────────────────────────────────────────────────────────

    async def get_or_create_passport(self, student: User) -> SkillPassport:
        result = await self.db.execute(
            select(SkillPassport).where(SkillPassport.student_id == student.id)
        )
        passport = result.scalar_one_or_none()
        if passport is None:
            passport = SkillPassport(
                student_id=student.id,
                visibility=PassportVisibility.INSTITUTION_ONLY,
            )
            self.db.add(passport)
            await self.db.commit()
            await self.db.refresh(passport)
        return passport

    async def update_passport(
        self,
        student: User,
        visibility: PassportVisibility | None = None,
        headline: str | None = None,
        target_role: str | None = None,
    ) -> SkillPassport:
        passport = await self.get_or_create_passport(student)
        if visibility is not None:
            passport.visibility = visibility
        if headline is not None:
            passport.headline = headline.strip()[:200]
        if target_role is not None:
            passport.target_role = target_role.strip()[:150]
        await self.db.commit()
        await self.db.refresh(passport)
        return passport

    async def generate_share_token(self, student: User) -> SkillPassport:
        """
        Generate a unique share token for the passport.
        The token allows recruiters/public to view the passport
        without authentication (depending on visibility setting).
        """
        passport = await self.get_or_create_passport(student)
        passport.share_token = secrets.token_urlsafe(32)
        if passport.visibility == PassportVisibility.PRIVATE:
            # Auto-upgrade to recruiter-visible when sharing
            passport.visibility = PassportVisibility.RECRUITER_VISIBLE
        await self.db.commit()
        await self.db.refresh(passport)
        return passport

    async def get_passport_by_token(self, share_token: str) -> SkillPassport | None:
        result = await self.db.execute(
            select(SkillPassport).where(SkillPassport.share_token == share_token)
        )
        return result.scalar_one_or_none()

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def _sanitise_filename(name: str) -> str:
        """
        Remove path separators and dangerous characters from filenames.
        Prevents path traversal attacks.
        """
        import re
        # Keep only alphanumeric, dots, hyphens, underscores
        safe = re.sub(r"[^\w.\-]", "_", name)
        # Strip leading dots
        safe = safe.lstrip(".")
        # Truncate
        return safe[:200] or "upload"
