"""Import all models so Alembic and SQLAlchemy discover them."""

from app.models.base import BaseModel  # noqa: F401
from app.models.organization import Institution, IndustryOrganization  # noqa: F401
from app.models.user import User, UserRole  # noqa: F401

# Phase 2
from app.models.skill import (  # noqa: F401
    Skill, Competency, SkillRelationship,
    SkillCategory, SkillStatus, RelationshipType, ProficiencyLevel,
)
from app.models.role import RolesCatalog, RoleRequirement  # noqa: F401
from app.models.assessment import (  # noqa: F401
    StudentSkill, AssessmentQuestion, AssessmentAttempt,
    AssessmentAnswer, AssessmentResult,
    QuestionType, DifficultyLevel, AssessmentMode, AttemptStatus,
    EvidenceCredibility,
)

# Phase 3
from app.models.evidence import (  # noqa: F401
    Document, SkillEvidence, SkillPassport,
    EvidenceType, VerificationStatus, PassportVisibility,
)

# Phase 4
from app.models.gap import StudentTargetRole  # noqa: F401

# Phase 5
from app.models.learning import (  # noqa: F401
    LearningResource, LearningPath, LearningPathResource,
    LearningPathEnrollment, LearningProgress,
    ResourceType, ResourceDifficulty, EnrollmentStatus, ProgressStatus,
)
