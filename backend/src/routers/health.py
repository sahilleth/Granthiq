from uuid import UUID
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
from loguru import logger
from sqlmodel import select
from src.db.session import async_session_factory, get_pool_status
from src.services.health import HealthService
from src.services.auth import get_current_user

router = APIRouter(prefix="/health", tags=["health"])

@router.get("/")
async def health_check(user_id: UUID = Depends(get_current_user)):
    """
    Comprehensive health check endpoint.

    Checks connectivity to all critical services:
    - PostgreSQL database
    - Qdrant vector database
    - Storage service (Supabase Storage)
    - LLM provider configuration

    Returns 200 if all services are healthy, 503 if any service is unhealthy.
    """
    health_service = HealthService()
    health_status = await health_service.get_system_health()
    
    status_code = 200 if health_status["status"] == "healthy" else 503
    
    if health_status["status"] == "healthy":
        logger.info(f"Health check passed in {health_status['response_time_ms']}ms")
    else:
        # Extract unhealthy services for logging
        failed_services = [
            k for k, v in health_status['services'].items() 
            if v.get('status') != 'healthy'
        ]
        logger.warning(f"Health check failed: {failed_services}")

    return JSONResponse(content=health_status, status_code=status_code)


@router.get("/liveness")
async def liveness_probe():
    """
    Simple liveness probe for Kubernetes/Docker.
    Returns 200 if the application is running.
    """
    return {"status": "alive", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/readiness")
async def readiness_probe():
    """
    Readiness probe for Kubernetes/Docker.
    Returns 200 if the application is ready to accept traffic (database connected).
    """
    try:
        # Keep simple DB check in router for minimal overhead readiness probe, 
        # or use health_service.check_database()
        async with async_session_factory() as session:
            await session.exec(select(1))
        return {"status": "ready", "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            content={"status": "not_ready", "error": str(e)},
            status_code=503
        )


@router.get("/pool")
async def pool_status(user_id: UUID = Depends(get_current_user)):
    """
    Get database connection pool status for monitoring.
    Shows current connection usage and saturation levels.
    """
    status = get_pool_status()
    return JSONResponse(content={
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pool": status
    })
