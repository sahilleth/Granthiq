from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from src.db.session import get_session
from src.db.models import User
from src.services.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

class UserProfile(BaseModel):
    id: UUID
    email: str
    is_active: bool
    created_at: str
    
    class Config:
        from_attributes = True

@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    user_id: UUID = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Get the current authenticated user's profile.
    This endpoint also triggers JIT user creation if the user doesn't exist.
    """
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserProfile(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at.isoformat()
    )
