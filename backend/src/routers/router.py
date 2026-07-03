from fastapi import APIRouter
from src.routers import health, auth, documents, chat, sources, settings, generation, notebooks, tasks, feedback, notes, gdrive

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(notebooks.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
api_router.include_router(notes.router)
api_router.include_router(sources.router)
api_router.include_router(settings.router)
api_router.include_router(generation.router)
api_router.include_router(tasks.router)
api_router.include_router(feedback.router)
api_router.include_router(gdrive.router)

