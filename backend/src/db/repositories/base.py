from typing import Generic, TypeVar, Type, List, Optional, Any, Dict, Set
from uuid import UUID
from sqlmodel import SQLModel, select, func
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy import delete as sql_delete, update as sql_update
from loguru import logger

T = TypeVar("T", bound=SQLModel)

class BaseRepository(Generic[T]):
    """
    Generic Repository pattern for standard CRUD operations using SQLModel/SQLAlchemy.
    Optimized for bulk operations to avoid N+1 query patterns.
    """

    # Define allowed filter fields for security (override in subclasses)
    # Subclasses MUST define this to prevent SQL injection via filter parameters
    ALLOWED_FILTER_FIELDS: Set[str] = set()

    def _validate_filter_field(self, field: str) -> bool:
        """
        Validate that a filter field is allowed.

        Args:
            field: Field name to validate

        Returns:
            True if field is allowed, False otherwise
        """
        # If no allowed fields defined, reject all filters (secure by default)
        if not self.ALLOWED_FILTER_FIELDS:
            logger.warning(
                f"ALLOWED_FILTER_FIELDS not defined for {self.model.__name__}. "
                f"Filtering on field '{field}' rejected."
            )
            return False

        if field not in self.ALLOWED_FILTER_FIELDS:
            logger.warning(
                f"Field '{field}' not in ALLOWED_FILTER_FIELDS for {self.model.__name__}. "
                f"Allowed fields: {self.ALLOWED_FILTER_FIELDS}"
            )
            return False

        return True

    def __init__(self, session: AsyncSession, model: Type[T]):
        self.session = session
        self.model = model

    async def create(self, obj: T) -> T:
        """Create a new record."""
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def get(self, id: UUID) -> Optional[T]:
        """Get a single record by ID."""
        statement = select(self.model).where(self.model.id == id)
        result = await self.session.exec(statement)
        return result.first()

    async def list(self, limit: int = 100, offset: int = 0) -> List[T]:
        """List records with pagination."""
        statement = select(self.model).offset(offset).limit(limit)
        result = await self.session.exec(statement)
        return result.all()

    async def update(self, id: UUID, values: dict[str, Any]) -> Optional[T]:
        """Update a record by ID with a dictionary of values."""
        db_obj = await self.get(id)
        if not db_obj:
            return None

        for key, value in values.items():
            if hasattr(db_obj, key):
                setattr(db_obj, key, value)

        self.session.add(db_obj)
        await self.session.commit()
        await self.session.refresh(db_obj)
        return db_obj

    async def delete(self, id: UUID) -> bool:
        """Delete a record by ID."""
        db_obj = await self.get(id)
        if not db_obj:
            return False
        await self.session.delete(db_obj)
        await self.session.commit()
        return True

    # =========================================================================
    # BULK OPERATIONS (Optimized to avoid N+1 query patterns)
    # =========================================================================

    async def create_many(self, objects: List[T]) -> List[T]:
        """
        Create multiple records in a single transaction.

        More efficient than individual create() calls.

        Args:
            objects: List of model instances to create

        Returns:
            List of created instances with IDs populated

        Example:
            notebooks = [
                Notebook(title="Notebook 1", user_id=user_id),
                Notebook(title="Notebook 2", user_id=user_id),
            ]
            created = await repo.create_many(notebooks)
        """
        self.session.add_all(objects)
        await self.session.commit()

        # Refresh all objects to get their IDs and relationships
        for obj in objects:
            await self.session.refresh(obj)

        return objects

    async def update_many(self, updates: List[Dict[str, Any]]) -> int:
        """
        Update multiple records efficiently using bulk UPDATE.

        Uses SQLAlchemy's update().where() for single-query execution
        instead of N+1 individual SELECT/UPDATE pattern.

        Args:
            updates: List of dicts with 'id' and fields to update

        Returns:
            Number of records updated

        Example:
            updates = [
                {"id": uuid1, "status": "completed", "updated_at": now},
                {"id": uuid2, "status": "failed", "error": "timeout"},
            ]
            count = await repo.update_many(updates)
        """
        if not updates:
            return 0

        # Validate all updates have 'id' field
        valid_updates = [u for u in updates if "id" in u]
        if len(valid_updates) != len(updates):
            invalid_count = len(updates) - len(valid_updates)
            logger.warning(f"update_many: {invalid_count} updates missing 'id' field")

        if not valid_updates:
            return 0

        try:
            # Extract all IDs
            ids = [u["id"] for u in valid_updates]

            # Collect all fields to update (excluding 'id')
            all_fields: Set[str] = set()
            for update in valid_updates:
                all_fields.update(k for k in update.keys() if k != "id")

            # Build bulk update statement using CASE for different values per row
            from sqlalchemy import case

            update_values = {}
            for field in all_fields:
                # Build CASE statement: CASE WHEN id=x THEN value ELSE ... END
                whens = {
                    u["id"]: u[field]
                    for u in valid_updates
                    if field in u
                }
                if whens:
                    update_values[field] = case(whens, value=self.model.id)

            if update_values:
                stmt = (
                    sql_update(self.model)
                    .where(self.model.id.in_(ids))
                    .values(**update_values)
                )

                result = await self.session.execute(stmt)
                await self.session.commit()

                updated = result.rowcount
                logger.debug(f"Bulk updated {updated} records in single query")
                return updated

            return 0

        except Exception as e:
            logger.error(f"Bulk update failed: {e}", exc_info=True)
            await self.session.rollback()
            raise

    async def update_many_batched(
        self,
        updates: List[Dict[str, Any]],
        batch_size: int = 100
    ) -> int:
        """
        Update large numbers of records in batches to avoid query size limits.

        Args:
            updates: List of update dicts
            batch_size: Number of records per batch

        Returns:
            Total number of records updated
        """
        if not updates:
            return 0

        total_updated = 0

        for i in range(0, len(updates), batch_size):
            batch = updates[i:i + batch_size]
            count = await self.update_many(batch)
            total_updated += count

            logger.debug(f"Batch {i//batch_size + 1}: Updated {count} records")

        return total_updated

    async def delete_many(self, ids: List[UUID]) -> int:
        """
        Delete multiple records by IDs in a single query.

        Much more efficient than calling delete() in a loop.

        Args:
            ids: List of UUIDs to delete

        Returns:
            Number of records deleted

        Example:
            deleted = await repo.delete_many([uuid1, uuid2, uuid3])
        """
        if not ids:
            return 0

        # Use bulk DELETE with IN clause
        result = await self.session.execute(
            sql_delete(self.model).where(self.model.id.in_(ids))
        )
        await self.session.commit()

        return result.rowcount

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Count records matching filters.

        Args:
            filters: Dict of field_name: value to filter by

        Returns:
            Number of matching records

        Example:
            # Count all notebooks
            total = await repo.count()

            # Count user's notebooks
            user_count = await repo.count({"user_id": user_id})
        """
        statement = select(func.count()).select_from(self.model)

        if filters:
            for field, value in filters.items():
                # SECURITY: Check if field is in allowed list
                if not self._validate_filter_field(field):
                    continue

                if hasattr(self.model, field):
                    statement = statement.where(getattr(self.model, field) == value)

        result = await self.session.exec(statement)
        return result.one()

    async def exists(self, id: UUID) -> bool:
        """
        Check if a record exists by ID without fetching it.

        More efficient than get() when you only need to know existence.

        Args:
            id: UUID to check

        Returns:
            True if record exists, False otherwise

        Example:
            if await repo.exists(notebook_id):
                # Notebook exists
        """
        statement = select(func.count()).select_from(self.model).where(
            self.model.id == id
        )
        result = await self.session.exec(statement)
        return result.one() > 0
