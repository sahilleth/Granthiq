from fastapi import APIRouter

# Placeholder router - can be implemented later for global user settings
# Note: Notebook-specific settings are managed via PATCH /notebooks/{notebook_id}
router = APIRouter(prefix="/settings", tags=["settings"])
