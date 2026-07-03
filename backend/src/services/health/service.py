from datetime import datetime, timezone
from typing import Dict, Any, List
from loguru import logger
from sqlmodel import select
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
import httpx
import asyncio
from src.config import get_settings
from src.db.session import async_session_factory

class HealthService:
    def __init__(self):
        self.settings = get_settings()

    async def check_database(self) -> Dict[str, Any]:
        """Check PostgreSQL database connectivity."""
        try:
            async with async_session_factory() as session:
                await session.exec(select(1))
            return {
                "status": "healthy",
                "response_time_ms": 0,
                "details": "Database connection successful"
            }
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "details": "Failed to connect to PostgreSQL database"
            }

    async def check_qdrant(self) -> Dict[str, Any]:
        """Check Qdrant vector database connectivity."""
        try:
            client = QdrantClient(
                host=self.settings.qdrant.host,
                api_key=self.settings.qdrant.api_key,
                timeout=5.0
            )

            collection_info = client.get_collection(self.settings.qdrant.collection_name)

            return {
                "status": "healthy",
                "details": f"Connected to collection '{self.settings.qdrant.collection_name}'",
                "vectors_count": collection_info.vectors_count if hasattr(collection_info, 'vectors_count') else "unknown"
            }
        except UnexpectedResponse as e:
            logger.error(f"Qdrant health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "details": f"Failed to access Qdrant collection '{self.settings.qdrant.collection_name}'"
            }
        except Exception as e:
            logger.error(f"Qdrant health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "details": "Failed to connect to Qdrant vector database"
            }

    async def check_storage(self) -> Dict[str, Any]:
        """Check storage service (Supabase Storage) connectivity."""
        try:
            if self.settings.storage.provider == "supabase":
                if not self.settings.storage.supabase_url or not self.settings.storage.supabase_key:
                    return {
                        "status": "unhealthy",
                        "error": "Missing configuration",
                        "details": "Supabase URL or key not configured"
                    }

                # Check Supabase storage endpoint
                # For new sb_secret_... keys, the API Gateway uses the apikey header
                # to mint a temporary JWT. Both headers are sent for compatibility.
                api_key = self.settings.storage.supabase_key
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(
                        f"{self.settings.storage.supabase_url}/storage/v1/bucket",
                        headers={
                            "apikey": api_key,
                            "Authorization": f"Bearer {api_key}",
                        }
                    )

                    if response.status_code == 200:
                        buckets = response.json()
                        return {
                            "status": "healthy",
                            "details": f"Supabase Storage connected, {len(buckets)} buckets available",
                            "provider": "supabase"
                        }
                    else:
                        return {
                            "status": "unhealthy",
                            "error": f"HTTP {response.status_code}",
                            "details": "Failed to access Supabase Storage"
                        }

            elif self.settings.storage.provider == "local":
                return {
                    "status": "healthy",
                    "details": "Local storage configured",
                    "provider": "local"
                }

            else:
                return {
                    "status": "healthy",
                    "details": f"Storage provider: {self.settings.storage.provider}",
                    "provider": self.settings.storage.provider
                }

        except httpx.TimeoutException:
            logger.error("Storage health check timed out")
            return {
                "status": "unhealthy",
                "error": "Timeout",
                "details": "Storage service request timed out"
            }
        except Exception as e:
            logger.error(f"Storage health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "details": f"Failed to connect to storage service ({self.settings.storage.provider})"
            }

    async def check_llm_provider(self) -> Dict[str, Any]:
        """Check LLM provider availability (basic check)."""
        try:
            provider = self.settings.llm.provider

            # Just check if API keys are configured
            if provider == "gemini":
                if not self.settings.llm.gemini_api_key:
                    return {
                        "status": "unhealthy",
                        "error": "Missing API key",
                        "details": "Gemini API key not configured"
                    }
            elif provider == "groq":
                if not self.settings.llm.groq_api_key:
                    return {
                        "status": "unhealthy",
                        "error": "Missing API key",
                        "details": "Groq API key not configured"
                    }
            elif provider == "openai":
                if not self.settings.llm.openai_api_key:
                    return {
                        "status": "unhealthy",
                        "error": "Missing API key",
                        "details": "OpenAI API key not configured"
                    }

            return {
                "status": "healthy",
                "details": f"LLM provider '{provider}' configured",
                "provider": provider,
                "model": self.settings.llm.model_name
            }
        except Exception as e:
            logger.error(f"LLM provider health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "details": "Failed to verify LLM provider configuration"
            }

    async def get_system_health(self) -> Dict[str, Any]:
        """Aggregate health status of all services."""
        start_time = datetime.now(timezone.utc)

        # Run all health checks concurrently
        database_check, qdrant_check, storage_check, llm_check = await asyncio.gather(
            self.check_database(),
            self.check_qdrant(),
            self.check_storage(),
            self.check_llm_provider(),
            return_exceptions=True
        )

        # Handle exceptions from gather
        def safe_check(result, service_name):
            if isinstance(result, Exception):
                logger.error(f"{service_name} health check raised exception: {result}")
                return {
                    "status": "unhealthy",
                    "error": str(result),
                    "details": f"{service_name} health check failed"
                }
            return result

        database = safe_check(database_check, "Database")
        qdrant = safe_check(qdrant_check, "Qdrant")
        storage = safe_check(storage_check, "Storage")
        llm = safe_check(llm_check, "LLM")

        end_time = datetime.now(timezone.utc)
        response_time_ms = int((end_time - start_time).total_seconds() * 1000)

        # Determine overall status
        all_healthy = all([
            database.get("status") == "healthy",
            qdrant.get("status") == "healthy",
            storage.get("status") == "healthy",
            llm.get("status") == "healthy"
        ])

        overall_status = "healthy" if all_healthy else "unhealthy"
        
        return {
            "status": overall_status,
            "timestamp": start_time.isoformat(),
            "response_time_ms": response_time_ms,
            "services": {
                "database": database,
                "vector_database": qdrant,
                "storage": storage,
                "llm_provider": llm
            },
            "environment": self.settings.environment,
            "version": "1.0.0"
        }
