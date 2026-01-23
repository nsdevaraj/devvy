"""
SQLite implementation for desktop app mode.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, delete, update, DateTime, func
from typing import List, Optional, Dict, Any
from .base import DatabaseBase
from .models_sqlite import Base, User, Organization, ToolConfig, Collection, Folder, SavedItem, Favorite
import uuid
from datetime import datetime, timezone


class SQLiteDatabase(DatabaseBase):
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = None
        self.SessionLocal = None
    
    async def connect(self):
        """Initialize SQLite connection"""
        self.engine = create_async_engine(self.database_url, echo=False)
        self.SessionLocal = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        
        # Create tables
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    async def disconnect(self):
        """Close SQLite connection"""
        if self.engine:
            await self.engine.dispose()
    
    def _model_to_dict(self, model) -> Dict[str, Any]:
        """Convert SQLAlchemy model to dictionary"""
        if model is None:
            return None
        result = {}
        for column in model.__table__.columns:
            value = getattr(model, column.name)
            if isinstance(value, datetime):
                result[column.name] = value.isoformat()
            else:
                result[column.name] = value
        return result

    def _fix_datetime_fields(self, model_class, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert ISO strings to datetime objects for DateTime columns"""
        result = data.copy()
        for column in model_class.__table__.columns:
            if isinstance(column.type, DateTime) and column.name in result:
                val = result[column.name]
                if isinstance(val, str):
                    try:
                        result[column.name] = datetime.fromisoformat(val)
                    except ValueError:
                        pass
        return result
    
    # User operations
    async def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        async with self.SessionLocal() as session:
            # Filter user_data keys to match User columns
            valid_keys = User.__table__.columns.keys()
            filtered_data = {k: v for k, v in user_data.items() if k in valid_keys}
            filtered_data = self._fix_datetime_fields(User, filtered_data)

            user = User(**filtered_data)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return self._model_to_dict(user)
    
    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        async with self.SessionLocal() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            return self._model_to_dict(user) if user else None
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        async with self.SessionLocal() as session:
            user = await session.get(User, user_id)
            return self._model_to_dict(user) if user else None
    
    # Organization operations
    async def create_organization(self, org_data: Dict[str, Any]) -> Dict[str, Any]:
        async with self.SessionLocal() as session:
            # Filter org_data keys to match Organization columns
            valid_keys = Organization.__table__.columns.keys()
            filtered_data = {k: v for k, v in org_data.items() if k in valid_keys}
            filtered_data = self._fix_datetime_fields(Organization, filtered_data)

            # Map max_licenses to license_count if needed
            if 'max_licenses' in org_data and 'license_count' not in filtered_data:
                 filtered_data['license_count'] = org_data['max_licenses']

            org = Organization(**filtered_data)
            session.add(org)
            await session.commit()
            await session.refresh(org)
            return self._model_to_dict(org)
    
    async def get_organization(self, org_id: str) -> Optional[Dict[str, Any]]:
        async with self.SessionLocal() as session:
            org = await session.get(Organization, org_id)
            if not org:
                return None

            # Count users for active_licenses
            result = await session.execute(select(func.count(User.id)).where(User.organization_id == org_id))
            count = result.scalar()

            data = self._model_to_dict(org)
            data['max_licenses'] = data.get('license_count', 1)
            data['active_licenses'] = count
            return data

    async def increment_org_licenses(self, org_id: str) -> bool:
        # SQLite implementation calculates active licenses dynamically, so no need to increment counter
        return True
    
    async def get_organizations(self) -> List[Dict[str, Any]]:
        async with self.SessionLocal() as session:
            result = await session.execute(select(Organization))
            orgs = result.scalars().all()
            return [self._model_to_dict(org) for org in orgs]
    
    # Tool configuration operations
    async def get_tool_configs(self) -> List[Dict[str, Any]]:
        async with self.SessionLocal() as session:
            result = await session.execute(select(ToolConfig))
            configs = result.scalars().all()
            return [self._model_to_dict(config) for config in configs]
    
    async def get_tool_config(self, tool_id: str) -> Optional[Dict[str, Any]]:
        async with self.SessionLocal() as session:
            config = await session.get(ToolConfig, tool_id)
            return self._model_to_dict(config) if config else None
    
    async def upsert_tool_config(self, tool_id: str, config_data: Dict[str, Any]) -> Dict[str, Any]:
        async with self.SessionLocal() as session:
            config = await session.get(ToolConfig, tool_id)
            if config:
                for key, value in config_data.items():
                    setattr(config, key, value)
            else:
                config = ToolConfig(tool_id=tool_id, **config_data)
                session.add(config)
            await session.commit()
            await session.refresh(config)
            return self._model_to_dict(config)
    
    # Collection operations
    async def create_collection(self, user_id: str, collection_data: Dict[str, Any]) -> Dict[str, Any]:
        async with self.SessionLocal() as session:
            if 'id' not in collection_data:
                collection_data['id'] = str(uuid.uuid4())
            collection_data['user_id'] = user_id
            collection = Collection(**collection_data)
            session.add(collection)
            await session.commit()
            await session.refresh(collection)
            return self._model_to_dict(collection)
    
    async def get_collections(self, user_id: str) -> List[Dict[str, Any]]:
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(Collection).where(Collection.user_id == user_id)
            )
            collections = result.scalars().all()
            return [self._model_to_dict(c) for c in collections]
    
    async def delete_collection(self, collection_id: str, user_id: str) -> bool:
        async with self.SessionLocal() as session:
            result = await session.execute(
                delete(Collection).where(
                    Collection.id == collection_id,
                    Collection.user_id == user_id
                )
            )
            await session.commit()
            return result.rowcount > 0
    
    # Folder operations
    async def create_folder(self, folder_data: Dict[str, Any]) -> Dict[str, Any]:
        async with self.SessionLocal() as session:
            if 'id' not in folder_data:
                folder_data['id'] = str(uuid.uuid4())
            folder = Folder(**folder_data)
            session.add(folder)
            await session.commit()
            await session.refresh(folder)
            return self._model_to_dict(folder)
    
    async def get_folders(self, collection_id: str, user_id: str) -> List[Dict[str, Any]]:
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(Folder).where(
                    Folder.collection_id == collection_id,
                    Folder.user_id == user_id
                )
            )
            folders = result.scalars().all()
            return [self._model_to_dict(f) for f in folders]
    
    async def update_folder(self, folder_id: str, user_id: str, update_data: Dict[str, Any]) -> bool:
        async with self.SessionLocal() as session:
            result = await session.execute(
                update(Folder).where(
                    Folder.id == folder_id,
                    Folder.user_id == user_id
                ).values(**update_data)
            )
            await session.commit()
            return result.rowcount > 0
    
    async def delete_folder(self, folder_id: str, user_id: str) -> bool:
        async with self.SessionLocal() as session:
            result = await session.execute(
                delete(Folder).where(
                    Folder.id == folder_id,
                    Folder.user_id == user_id
                )
            )
            await session.commit()
            return result.rowcount > 0
    
    async def get_folder(self, folder_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(Folder).where(
                    Folder.id == folder_id,
                    Folder.user_id == user_id
                )
            )
            folder = result.scalar_one_or_none()
            return self._model_to_dict(folder) if folder else None
    
    # Saved items operations
    async def create_saved_item(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        async with self.SessionLocal() as session:
            if 'id' not in item_data:
                item_data['id'] = str(uuid.uuid4())
            item = SavedItem(**item_data)
            session.add(item)
            await session.commit()
            await session.refresh(item)
            return self._model_to_dict(item)
    
    async def get_saved_items(self, collection_id: str, user_id: str) -> List[Dict[str, Any]]:
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(SavedItem).where(
                    SavedItem.collection_id == collection_id,
                    SavedItem.user_id == user_id
                )
            )
            items = result.scalars().all()
            return [self._model_to_dict(i) for i in items]
    
    async def get_saved_item(self, item_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(SavedItem).where(
                    SavedItem.id == item_id,
                    SavedItem.user_id == user_id
                )
            )
            item = result.scalar_one_or_none()
            return self._model_to_dict(item) if item else None
    
    async def delete_saved_items_by_folder(self, folder_id: str, user_id: str) -> int:
        async with self.SessionLocal() as session:
            result = await session.execute(
                delete(SavedItem).where(
                    SavedItem.folder_id == folder_id,
                    SavedItem.user_id == user_id
                )
            )
            await session.commit()
            return result.rowcount
    
    async def delete_saved_items_by_collection(self, collection_id: str, user_id: str) -> int:
        async with self.SessionLocal() as session:
            result = await session.execute(
                delete(SavedItem).where(
                    SavedItem.collection_id == collection_id,
                    SavedItem.user_id == user_id
                )
            )
            await session.commit()
            return result.rowcount
    
    # Favorites operations
    async def add_favorite(self, user_id: str, tool_id: str) -> Dict[str, Any]:
        async with self.SessionLocal() as session:
            favorite = Favorite(user_id=user_id, tool_id=tool_id)
            session.add(favorite)
            await session.commit()
            return {"user_id": user_id, "tool_id": tool_id}
    
    async def remove_favorite(self, user_id: str, tool_id: str) -> bool:
        async with self.SessionLocal() as session:
            result = await session.execute(
                delete(Favorite).where(
                    Favorite.user_id == user_id,
                    Favorite.tool_id == tool_id
                )
            )
            await session.commit()
            return result.rowcount > 0

    async def has_favorite(self, user_id: str, tool_id: str) -> bool:
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(Favorite).where(
                    Favorite.user_id == user_id,
                    Favorite.tool_id == tool_id
                )
            )
            return result.scalar_one_or_none() is not None
    
    async def get_favorites(self, user_id: str) -> List[str]:
        async with self.SessionLocal() as session:
            result = await session.execute(
                select(Favorite.tool_id).where(Favorite.user_id == user_id)
            )
            return [tool_id for (tool_id,) in result.all()]
