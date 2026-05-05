from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.session import PhoneVerification, SessionEvent, User, UserSession
from app.utils.language import normalize_user_name
from app.utils.phone import mask_phone_number, normalize_phone_number

logger = logging.getLogger(__name__)


@dataclass
class SentCode:
    provider: str
    expires_at: datetime
    dev_code: str | None = None


class SmsProvider:
    name = "base"

    def send_code(self, phone_number: str, code: str) -> SentCode:  # pragma: no cover - interface
        raise NotImplementedError


class DevSmsProvider(SmsProvider):
    name = "dev"

    def send_code(self, phone_number: str, code: str) -> SentCode:
        logger.info("OTP code generated in dev mode for %s", mask_phone_number(phone_number))
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=get_settings().otp_code_ttl_seconds)
        return SentCode(provider=self.name, expires_at=expires_at, dev_code=code)


class DisabledSmsProvider(SmsProvider):
    name = "disabled"

    def send_code(self, phone_number: str, code: str) -> SentCode:
        raise HTTPException(
            status_code=503,
            detail="SMS-провайдер не настроен. Для production нужно подключить внешний сервис через backend-конфиг.",
        )


def get_sms_provider() -> SmsProvider:
    settings = get_settings()
    if settings.otp_provider == "dev":
        return DevSmsProvider()
    return DisabledSmsProvider()


class PhoneVerificationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.provider = get_sms_provider()

    def request_code(self, session: UserSession, display_name: str | None, phone_number: str) -> dict:
        if session.current_stage != "contact_gate":
            raise HTTPException(status_code=409, detail="Шаг подтверждения телефона ещё не открыт для этой сессии.")

        normalized_phone = normalize_phone_number(phone_number)
        contact_name = self._resolve_contact_name(session, display_name)
        code = self._generate_code()
        now = datetime.now(timezone.utc)

        for existing in session.phone_verifications:
            if existing.status == "pending":
                existing.status = "superseded"
                existing.updated_at = now
                self.db.add(existing)

        sent = self.provider.send_code(normalized_phone, code)
        verification = PhoneVerification(
            session_id=session.id,
            phone_number=normalized_phone,
            display_name=contact_name,
            code_hash=self._hash_code(session.id, normalized_phone, code),
            provider=sent.provider,
            status="pending",
            expires_at=sent.expires_at,
            attempts_count=0,
            max_attempts=self.settings.otp_max_attempts,
        )
        session.contact_name = contact_name
        session.phone_number = normalized_phone
        session.state = {
            **(session.state or {}),
            "contact_name": contact_name,
            "phone_number": normalized_phone,
            "phone_verification_requested_at": now.isoformat(),
            "phone_verified": False,
        }
        self.db.add(verification)
        self.db.add(session)
        self._log(session.id, "phone_code_requested", {"phone_number_masked": mask_phone_number(normalized_phone), "provider": sent.provider})
        self.db.commit()

        return {
            "session_id": session.id,
            "contact_name": contact_name,
            "phone_number": normalized_phone,
            "provider": sent.provider,
            "expires_at": sent.expires_at,
            "dev_code": sent.dev_code if self.settings.otp_dev_mode and sent.provider == "dev" else None,
            "dev_mode": bool(self.settings.otp_dev_mode and sent.provider == "dev"),
        }

    def verify_code(self, session: UserSession, phone_number: str, code: str) -> tuple[UserSession, str]:
        normalized_phone = normalize_phone_number(phone_number)
        verification = self._latest_pending_verification(session.id, normalized_phone)
        if verification is None:
            raise HTTPException(status_code=404, detail="Не найден активный код для этого номера и этой сессии.")

        now = datetime.now(timezone.utc)
        expires_at = verification.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            verification.status = "expired"
            self.db.add(verification)
            self.db.commit()
            raise HTTPException(status_code=400, detail="Срок действия кода истёк. Запроси новый код.")

        if verification.attempts_count >= verification.max_attempts:
            verification.status = "blocked"
            self.db.add(verification)
            self.db.commit()
            raise HTTPException(status_code=429, detail="Лимит попыток исчерпан. Запроси новый код.")

        verification.attempts_count += 1
        expected_hash = self._hash_code(session.id, normalized_phone, code)
        if not secrets.compare_digest(expected_hash, verification.code_hash):
            self.db.add(verification)
            self.db.commit()
            raise HTTPException(status_code=400, detail="Код не подошёл. Проверь цифры и попробуй ещё раз.")

        verification.status = "verified"
        verification.verified_at = now

        user = self._get_or_create_user(verification.display_name, normalized_phone, now)
        self.db.add(user)
        self.db.flush()
        access_token = secrets.token_urlsafe(24)
        session.user_id = user.id
        session.contact_name = verification.display_name
        session.phone_number = normalized_phone
        session.phone_verified_at = now
        session.access_token_hash = self._hash_access_token(session.id, access_token)
        session.state = {
            **(session.state or {}),
            "contact_name": verification.display_name,
            "phone_number": normalized_phone,
            "phone_verified": True,
            "phone_verified_at": now.isoformat(),
        }
        self.db.add_all([verification, session])
        self._log(session.id, "phone_verified", {"phone_number_masked": mask_phone_number(normalized_phone), "user_id": user.id})
        self.db.commit()
        self.db.refresh(session)
        return session, access_token

    def validate_result_access(self, session: UserSession, access_token: str | None) -> None:
        if not session.access_token_hash or not access_token:
            raise HTTPException(status_code=403, detail="Для доступа к результату нужен подтверждённый токен сессии.")

        actual_hash = self._hash_access_token(session.id, access_token)
        if not secrets.compare_digest(actual_hash, session.access_token_hash):
            raise HTTPException(status_code=403, detail="Токен доступа к результату не подошёл.")

    def _resolve_contact_name(self, session: UserSession, display_name: str | None) -> str:
        source = display_name or session.contact_name or (session.state or {}).get("user_name")
        normalized = normalize_user_name(source)
        if len(normalized) < 2:
            raise HTTPException(status_code=400, detail="Нужно указать, как к тебе обращаться в результате.")
        return normalized

    def _generate_code(self) -> str:
        if self.settings.otp_dev_mode and self.settings.otp_dev_fixed_code:
            return self.settings.otp_dev_fixed_code
        return f"{secrets.randbelow(900000) + 100000}"

    def _latest_pending_verification(self, session_id: str, phone_number: str) -> PhoneVerification | None:
        query = (
            select(PhoneVerification)
            .where(
                PhoneVerification.session_id == session_id,
                PhoneVerification.phone_number == phone_number,
                PhoneVerification.status == "pending",
            )
            .order_by(PhoneVerification.created_at.desc(), PhoneVerification.id.desc())
        )
        return self.db.scalars(query).first()

    def _get_or_create_user(self, display_name: str, phone_number: str, now: datetime) -> User:
        user = self.db.scalar(select(User).where(User.phone_number == phone_number))
        if user is None:
            user = User(
                display_name=display_name,
                phone_number=phone_number,
                phone_verified=True,
                phone_verified_at=now,
            )
        else:
            user.display_name = display_name
            user.phone_verified = True
            user.phone_verified_at = now
        return user

    def _hash_code(self, session_id: str, phone_number: str, code: str) -> str:
        payload = f"{self.settings.otp_secret_key}:{session_id}:{phone_number}:{code}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _hash_access_token(self, session_id: str, access_token: str) -> str:
        payload = f"{self.settings.otp_secret_key}:{session_id}:access:{access_token}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _log(self, session_id: str, event_type: str, payload: dict) -> None:
        self.db.add(SessionEvent(session_id=session_id, event_type=event_type, payload=payload))
