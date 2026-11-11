from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, StrictInt, field_validator, model_validator

STAGES = Literal["new", "qualified", "contacted", "proposal_sent", "meeting_booked", "client", "lost"]

class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

class BusinessIn(Input):
    name: str = Field(min_length=2, max_length=160)
    industry: str = Field(default="services", max_length=80)

class MemberIn(Input):
    subject: str = Field(min_length=8, max_length=180)
    email: EmailStr
    role: Literal["admin", "manager", "operator", "viewer"]

class LeadIn(Input):
    business_name: str = Field(min_length=2, max_length=180)
    industry: str = Field(default="other", max_length=100)
    website: HttpUrl | None = None
    phone: str | None = Field(default=None, max_length=48)
    email: EmailStr | None = None
    location: str | None = Field(default=None, max_length=200)
    source: str = Field(default="manual", max_length=80)
    external_id: str | None = Field(default=None, max_length=180)
    metrics: dict[str, StrictInt | None] = Field(default_factory=dict)
    opted_out: bool = False
    lawful_basis: Literal["consent", "legitimate_interest", "contract"] | None = None
    lawful_basis_note: str | None = Field(default=None, max_length=1000)

    @field_validator("metrics")
    @classmethod
    def valid_metrics(cls, values: dict[str, int | None]) -> dict[str, int | None]:
        allowed = {"seo", "reviews", "website", "social", "market"}
        if set(values) - allowed or any(v is not None and (type(v) is not int or not 0 <= v <= 100) for v in values.values()):
            raise ValueError("Metrics must be named seo/reviews/website/social/market with values 0..100")
        return values

class LeadPatch(Input):
    business_name: str | None = Field(default=None, min_length=2, max_length=180)
    industry: str | None = Field(default=None, min_length=1, max_length=100)
    website: HttpUrl | None = None
    phone: str | None = Field(default=None, max_length=48)
    email: EmailStr | None = None
    location: str | None = Field(default=None, max_length=200)
    stage: STAGES | None = None
    metrics: dict[str, StrictInt | None] | None = None
    opted_out: bool | None = None
    lawful_basis: Literal["consent", "legitimate_interest", "contract"] | None = None
    lawful_basis_note: str | None = Field(default=None, max_length=1000)

    @field_validator("metrics")
    @classmethod
    def valid_patch_metrics(cls, value):
        return None if value is None else LeadIn.valid_metrics(value)

    @model_validator(mode="before")
    @classmethod
    def reject_null_required(cls, value):
        if isinstance(value, dict) and any(k in value and value[k] is None for k in ("business_name", "industry", "stage", "opted_out", "metrics")):
            raise ValueError("Required fields cannot be set to null")
        return value

class LeadImport(Input):
    leads: list[LeadIn] = Field(min_length=1, max_length=100)

class LeadOut(Output):
    id: str
    business_name: str
    industry: str
    website: str | None
    email: str | None
    phone: str | None
    location: str | None
    stage: str
    metrics: dict
    score: int | None
    grade: str
    score_confidence: int
    opted_out: bool

class TaskIn(Input):
    title: str = Field(min_length=3, max_length=240)
    description: str = Field(default="", max_length=8000)
    due_at: datetime | None = None
    lead_id: str | None = None
    assigned_subject: str | None = Field(default=None, max_length=180)

class TaskPatch(Input):
    status: Literal["open", "in_progress", "done", "cancelled"]

class ClientIn(Input):
    name: str = Field(min_length=2, max_length=180)
    email: EmailStr | None = None
    lead_id: str | None = None
    monthly_revenue: float = Field(default=0, ge=0, le=1_000_000_000)
    renewal_date: datetime | None = None

class OpportunityIn(Input):
    name: str = Field(min_length=2, max_length=180)
    lead_id: str | None = None
    value: float = Field(ge=0, le=1_000_000_000)
    probability: int = Field(default=0, ge=0, le=100)
    expected_close: datetime | None = None

class CampaignIn(Input):
    name: str = Field(min_length=2, max_length=180)
    channel: Literal["email", "social", "seo", "ads", "other"]
    objective: str = Field(min_length=3, max_length=3000)
    content: dict = Field(default_factory=dict)

class ProposalIn(Input):
    title: str = Field(min_length=3, max_length=180)
    lead_id: str | None = None
    content: str = Field(min_length=10, max_length=30000)
    amount: float | None = Field(default=None, ge=0, le=1_000_000_000)

class WebsiteIn(Input):
    company: str = Field(min_length=2, max_length=180)
    industry: Literal["cleaning", "hvac", "roofing", "plumbing", "electrical", "landscaping", "medical", "dental", "law", "real_estate", "other"]
    tagline: str = Field(min_length=3, max_length=240)
    contact_email: EmailStr
    city: str = Field(min_length=2, max_length=120)
    services: list[str] = Field(min_length=1, max_length=12)

    @field_validator("services")
    @classmethod
    def service_limits(cls, values: list[str]) -> list[str]:
        if any(not 2 <= len(v.strip()) <= 90 for v in values):
            raise ValueError("Each service must be 2..90 characters")
        return [v.strip() for v in values]

class MediaIn(Input):
    kind: Literal["image", "video"]
    title: str = Field(min_length=2, max_length=160)
    subtitle: str = Field(default="", max_length=240)

class MessageIn(Input):
    lead_id: str
    subject: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=10, max_length=15000)

class DecisionIn(Input):
    decision: Literal["approved", "rejected"]
    review_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    reason: str | None = Field(default=None, max_length=240)

class ChatIn(Input):
    message: str = Field(min_length=2, max_length=5000)
    role: Literal["revenue", "sales", "research", "marketing", "operations", "engineering"] | None = None
    use_ai: bool = False

class AIDraftIn(Input):
    prompt: str = Field(min_length=5, max_length=7000)
    task: Literal["quick", "coding", "reasoning", "marketing", "private"] = "marketing"
    role: Literal["revenue", "sales", "research", "marketing", "operations", "engineering"] = "marketing"


class ClientPatch(Input):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    email: EmailStr | None = None
    monthly_revenue: float | None = Field(default=None, ge=0, le=1_000_000_000)
    active: bool | None = None

class OpportunityPatch(Input):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    value: float | None = Field(default=None, ge=0, le=1_000_000_000)
    probability: int | None = Field(default=None, ge=0, le=100)
    stage: Literal["open", "won", "lost"] | None = None

class CampaignPatch(Input):
    channel: Literal["email", "social", "seo", "ads", "other"] | None = None
    name: str | None = Field(default=None, min_length=2, max_length=180)
    objective: str | None = Field(default=None, min_length=3, max_length=3000)
    content: dict | None = None
    status: Literal["draft", "archived"] | None = None

class ProposalPatch(Input):
    title: str | None = Field(default=None, min_length=3, max_length=180)
    content: str | None = Field(default=None, min_length=10, max_length=30000)
    amount: float | None = Field(default=None, ge=0, le=1_000_000_000)
    status: Literal["draft", "accepted", "declined"] | None = None
