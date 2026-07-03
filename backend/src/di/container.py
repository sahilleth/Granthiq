from typing import Optional, Type, TypeVar, Any
from functools import lru_cache
from contextlib import contextmanager

from src.config import Settings, get_settings
from src.services.storage import StorageService
from src.services.chat.service import ChatService
from src.services.generation.service import GenerationService
from src.services.query.query_engine import QueryEngineService

T = TypeVar('T')


class ServiceLocator:
    """
    Simple service locator for dependency injection.

    Provides:
    - Singleton lifecycle management
    - Lazy initialization
    - Easy mocking for tests
    """

    def __init__(self):
        self._services: dict[Type, Any] = {}
        self._factories: dict[Type, callable] = {}
        self._settings: Optional[Settings] = None

    def register_factory(self, interface: Type[T], factory: callable) -> None:
        """Register a factory function for creating service instances."""
        self._factories[interface] = factory

    def register_instance(self, interface: Type[T], instance: T) -> None:
        """Register a pre-created instance (useful for testing)."""
        self._services[interface] = instance

    def get(self, interface: Type[T]) -> T:
        """Get or create a service instance."""
        # Return existing instance if available
        if interface in self._services:
            return self._services[interface]

        # Create new instance using factory
        if interface in self._factories:
            instance = self._factories[interface](self)
            self._services[interface] = instance
            return instance

        raise KeyError(f"No factory registered for {interface}")

    def clear(self) -> None:
        """Clear all cached instances (useful for testing)."""
        self._services.clear()

    @contextmanager
    def override(self, interface: Type[T], instance: T):
        """Temporarily override a service (for testing)."""
        original = self._services.get(interface)
        self._services[interface] = instance
        try:
            yield
        finally:
            if original is not None:
                self._services[interface] = original
            else:
                self._services.pop(interface, None)


class Container:
    """
    Application DI Container.

    Usage:
        container = get_container()
        storage = container.storage()
        chat_service = container.chat_service()
    """

    def __init__(self, settings: Optional[Settings] = None):
        self._settings = settings or get_settings()
        self._locator = ServiceLocator()
        self._register_defaults()

    def _register_defaults(self):
        """Register default service factories."""
        # Storage service - singleton
        self._locator.register_factory(
            StorageService,
            lambda loc: StorageService()
        )

        # Chat service - singleton
        self._locator.register_factory(
            ChatService,
            lambda loc: ChatService()
        )

        # Generation service - singleton
        self._locator.register_factory(
            GenerationService,
            lambda loc: GenerationService()
        )

        # Query engine service - factory (depends on settings)
        self._locator.register_factory(
            QueryEngineService,
            lambda loc: QueryEngineService.from_settings(self._settings)
        )

    # Service accessors
    def storage(self) -> StorageService:
        return self._locator.get(StorageService)

    def chat_service(self) -> ChatService:
        return self._locator.get(ChatService)

    def generation_service(self) -> GenerationService:
        return self._locator.get(GenerationService)

    def query_engine(self) -> QueryEngineService:
        return self._locator.get(QueryEngineService)

    def override(self, interface: Type[T], instance: T):
        """Get context manager for service override."""
        return self._locator.override(interface, instance)

    def clear(self):
        """Clear all cached instances."""
        self._locator.clear()


@lru_cache()
def get_container() -> Container:
    """Get the singleton container instance."""
    return Container()


def reset_container():
    """Reset the container (useful for testing)."""
    get_container.cache_clear()
