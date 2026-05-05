from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.session import UserSession


def get_session_or_404(session_id: str, db: Session = Depends(get_db)) -> UserSession:
    session = db.get(UserSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
