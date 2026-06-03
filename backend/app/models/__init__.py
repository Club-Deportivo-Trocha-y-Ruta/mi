from app.models.base import Base
from app.models.user import User, UserRole
from app.models.club import Club, ClubMember, ClubRole
from app.models.athlete import Athlete, ParentAthlete, Sex, FamilyRelationship
from app.models.anthropometry import AnthropometricRecord, MaturationStatus, NutritionalStatus
from app.models.growth import GrowthReferenceLms, GrowthIndicator, GrowthSource
from app.models.parent_invite import ParentInvite
from app.models.privacy_policy import PrivacyPolicy
from app.models.parental_consent import ParentalConsent
from app.models.ai_explanation import AthleteAIExplanation
from app.models.training_session import (
    AttendanceStatus,
    MonthlyReport,
    MonthlyReportStatus,
    SessionAttendance,
    SessionKind,
    SessionStatus,
    TrainingSession,
)
from app.models.club_project_profile import ClubProjectProfile
from app.models.session_media import (
    MediaType,
    SessionMedia,
    SessionMediaAthlete,
)
from app.models.calendar_event import (
    ActualAttendanceStatus,
    AudienceType,
    CalendarEvent,
    EventAttendance,
    EventAudience,
    EventStatus,
    EventType,
    RSVPStatus,
)
from app.models.race_category import CategoryGender, CategoryTier, RaceCategory
from app.models.race_competitor import CompetitorSex, RaceCompetitor
from app.models.race_competitor_link_audit import (
    LinkAuditAction,
    RaceCompetitorLinkAudit,
)
from app.models.race_event import RaceEvent, RaceEventStatus, SurfaceCondition
from app.models.race_import import RaceImport, RaceImportKind, RaceImportStatus
from app.models.race_points_scheme import RacePointsScheme
from app.models.race_result import RaceResult, ResultStatus
from app.models.race_result_revision import RaceResultRevision, RaceResultRevisionAction
from app.models.race_series import RaceSeries

# Race-analysis v2 agentic module (BE-1)
from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.athlete_ai_insight import AthleteAiInsight, InsightConfidence

# Fase 1.8 — Boletín mensual individual
from app.models.athlete_badge import AthleteBadge, BadgeType, BadgeSource
from app.models.athlete_newsletter import AthleteMonthlyNewsletter, NewsletterStatus

__all__ = [
    "Base",
    "User",
    "UserRole",
    "Club",
    "ClubMember",
    "ClubRole",
    "Athlete",
    "ParentAthlete",
    "Sex",
    "FamilyRelationship",
    "AnthropometricRecord",
    "MaturationStatus",
    "NutritionalStatus",
    "GrowthReferenceLms",
    "GrowthIndicator",
    "GrowthSource",
    "ParentInvite",
    "PrivacyPolicy",
    "ParentalConsent",
    "AthleteAIExplanation",
    "SessionStatus",
    "AttendanceStatus",
    "SessionKind",
    "TrainingSession",
    "SessionAttendance",
    "MonthlyReport",
    "MonthlyReportStatus",
    "ClubProjectProfile",
    "MediaType",
    "SessionMedia",
    "SessionMediaAthlete",
    "CalendarEvent",
    "EventAudience",
    "EventAttendance",
    "EventType",
    "EventStatus",
    "AudienceType",
    "RSVPStatus",
    "ActualAttendanceStatus",
    # Race results module (Fase 1.7)
    "RaceCategory",
    "CategoryGender",
    "CategoryTier",
    "RaceSeries",
    "RacePointsScheme",
    "RaceEvent",
    "RaceEventStatus",
    "SurfaceCondition",
    "RaceCompetitor",
    "CompetitorSex",
    "RaceCompetitorLinkAudit",
    "LinkAuditAction",
    "RaceResult",
    "ResultStatus",
    "RaceResultRevision",
    "RaceResultRevisionAction",
    "RaceImport",
    "RaceImportKind",
    "RaceImportStatus",
    # Race-analysis v2 agentic (BE-1)
    "AgentRun",
    "AgentRunStatus",
    "AthleteAiInsight",
    "InsightConfidence",
    # Fase 1.8 — Boletín mensual individual
    "AthleteBadge",
    "BadgeType",
    "BadgeSource",
    "AthleteMonthlyNewsletter",
    "NewsletterStatus",
]
