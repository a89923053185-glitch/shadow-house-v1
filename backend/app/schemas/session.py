from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class SessionCreateResponse(BaseModel):
    session_id: str
    status: str
    assistant_message: str
    input_mode: Literal["text", "choices", "contact", "done"]
    choices: list[dict[str, str]] = Field(default_factory=list)
    progress: dict[str, Any]
    meta: dict[str, Any] = Field(default_factory=dict)


class UserMessageCreate(BaseModel):
    text: Optional[str] = None
    choice: Optional[str] = None


class SessionMessageResponse(BaseModel):
    session_id: str
    status: str
    assistant_message: str
    input_mode: Literal["text", "choices", "contact", "done"]
    choices: list[dict[str, str]] = Field(default_factory=list)
    progress: dict[str, Any]
    meta: dict[str, Any] = Field(default_factory=dict)


class SessionStateResponse(BaseModel):
    session_id: str
    status: str
    current_stage: str
    dream: Optional[str] = None
    user_name: Optional[str] = None
    user_age: Optional[int] = None
    contact_name: Optional[str] = None
    phone_number: Optional[str] = None
    phone_verified: bool = False
    result_unlocked: bool = False
    progress: dict[str, Any]
    state: dict[str, Any]
    result: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ResultResponse(BaseModel):
    session_id: str
    status: str
    result: dict[str, Any]


class ContactCodeRequest(BaseModel):
    display_name: Optional[str] = None
    phone_number: str


class ContactCodeVerify(BaseModel):
    phone_number: str
    code: str


class ContactCodeResponse(BaseModel):
    session_id: str
    contact_name: str
    phone_number: str
    provider: str
    expires_at: datetime
    dev_mode: bool = False
    dev_code: Optional[str] = None


class ContactVerifyResponse(BaseModel):
    session_id: str
    access_token: str
    response: SessionMessageResponse


class AdminSessionSummary(BaseModel):
    session_id: str
    created_at: datetime
    last_activity_at: datetime
    display_name: Optional[str] = None
    phone_number: Optional[str] = None
    current_stage: str
    status_label: str
    stopped_at_label: str
    status: str
    phone_verified: bool = False
    result_unlocked: bool = False
    bonus_downloaded: bool = False
    blueprint_downloaded: bool = False
    top_shadow_names: list[str] = Field(default_factory=list)
    user_age: Optional[int] = None
    dream: Optional[str] = None
    passport_title: Optional[str] = None
    behavior_shadow_name: Optional[str] = None
    personality_shadow_name: Optional[str] = None
    root_shadow_name: Optional[str] = None
    link_key: Optional[str] = None


class AdminSessionListResponse(BaseModel):
    filter: str
    total_count: int
    items: list[AdminSessionSummary] = Field(default_factory=list)
    analytics: dict[str, Any] = Field(default_factory=dict)


class AdminSessionDetailResponse(BaseModel):
    session_id: str
    created_at: datetime
    last_activity_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    display_name: Optional[str] = None
    phone_number: Optional[str] = None
    current_stage: str
    status_label: str
    stopped_at_label: str
    status: str
    dream: Optional[str] = None
    user_age: Optional[int] = None
    user_goal_text: Optional[str] = None
    phone_verified: bool = False
    phone_verified_at: Optional[datetime] = None
    result_unlocked: bool = False
    result_released_at: Optional[datetime] = None
    bonus_downloaded: bool = False
    blueprint_downloaded: bool = False
    top_shadow_names: list[str] = Field(default_factory=list)
    client_text: Optional[str] = None
    internal_addendum: Optional[str] = None
    result_summary: Optional[str] = None
    mechanism_formula: Optional[str] = None
    manifestation: Optional[str] = None
    price: Optional[str] = None
    hidden_resource: Optional[str] = None
    screen_phrase: Optional[str] = None
    micro_permission: Optional[str] = None
    session_state: dict[str, Any] = Field(default_factory=dict)
    v1_2: dict[str, Any] = Field(default_factory=dict)


class AnalyticsOverview(BaseModel):
    total_sessions: int
    completed_sessions: int
    completion_rate: float
    avg_messages_per_session: float
    top_dropoff_stage: Optional[str] = None
    verified_users: int = 0
    pending_verifications: int = 0
