"""
MongoDB implementation for web app mode.
"""
from motor.motor_asyncio import AsyncIOMotorClient
from typing import List, Optional, Dict, Any
from .base import DatabaseBase
import uuid


class MongoDBDatabase(DatabaseBase):
    def __init__(self, mongo_url: str, db_name: str):
        self.mongo_url = mongo_url
        self.db_name = db_name
        self.client = None
        self.db = None
    
    async def connect(self):
        """Initialize MongoDB connection"""
        self.client = AsyncIOMotorClient(self.mongo_url)
        self.db = self.client[self.db_name]
    
    async def disconnect(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
    
    # User operations
    async def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        await self.db.users.insert_one(user_data)
        return user_data
    
    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        return await self.db.users.find_one({"email": email}, {"_id": 0})
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.users.find_one({"id": user_id}, {"_id": 0})
    
    # Organization operations
    async def create_organization(self, org_data: Dict[str, Any]) -> Dict[str, Any]:
        await self.db.organizations.insert_one(org_data)
        return org_data
    
    async def get_organization(self, org_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.organizations.find_one({"id": org_id}, {"_id": 0})
    
    async def increment_org_licenses(self, org_id: str) -> bool:
        result = await self.db.organizations.update_one(
            {"id": org_id},
            {"$inc": {"active_licenses": 1}}
        )
        return result.modified_count > 0

    async def get_organizations(self) -> List[Dict[str, Any]]:
        return await self.db.organizations.find({}, {"_id": 0}).to_list(1000)
    
    # Tool configuration operations
    async def get_tool_configs(self) -> List[Dict[str, Any]]:
        return await self.db.tool_configs.find({}, {"_id": 0}).to_list(100)
    
    async def get_tool_config(self, tool_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.tool_configs.find_one({"tool_id": tool_id}, {"_id": 0})
    
    async def upsert_tool_config(self, tool_id: str, config_data: Dict[str, Any]) -> Dict[str, Any]:
        await self.db.tool_configs.update_one(
            {"tool_id": tool_id},
            {"$set": config_data},
            upsert=True
        )
        return config_data
    
    # Collection operations
    async def create_collection(self, user_id: str, collection_data: Dict[str, Any]) -> Dict[str, Any]:
        if 'id' not in collection_data:
            collection_data['id'] = str(uuid.uuid4())
        collection_data['user_id'] = user_id
        await self.db.collections.insert_one(collection_data)
        return collection_data
    
    async def get_collections(self, user_id: str) -> List[Dict[str, Any]]:
        return await self.db.collections.find({"user_id": user_id}, {"_id": 0}).to_list(1000)
    
    async def delete_collection(self, collection_id: str, user_id: str) -> bool:
        result = await self.db.collections.delete_one({"id": collection_id, "user_id": user_id})
        return result.deleted_count > 0
    
    # Folder operations
    async def create_folder(self, folder_data: Dict[str, Any]) -> Dict[str, Any]:
        if 'id' not in folder_data:
            folder_data['id'] = str(uuid.uuid4())
        await self.db.folders.insert_one(folder_data)
        return folder_data
    
    async def get_folders(self, collection_id: str, user_id: str) -> List[Dict[str, Any]]:
        return await self.db.folders.find(
            {"collection_id": collection_id, "user_id": user_id},
            {"_id": 0}
        ).to_list(1000)
    
    async def update_folder(self, folder_id: str, user_id: str, update_data: Dict[str, Any]) -> bool:
        result = await self.db.folders.update_one(
            {"id": folder_id, "user_id": user_id},
            {"$set": update_data}
        )
        return result.modified_count > 0
    
    async def delete_folder(self, folder_id: str, user_id: str) -> bool:
        result = await self.db.folders.delete_one({"id": folder_id, "user_id": user_id})
        return result.deleted_count > 0
    
    async def get_folder(self, folder_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.folders.find_one({"id": folder_id, "user_id": user_id}, {"_id": 0})
    
    # Saved items operations
    async def create_saved_item(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        if 'id' not in item_data:
            item_data['id'] = str(uuid.uuid4())
        await self.db.saved_items.insert_one(item_data)
        return item_data
    
    async def get_saved_items(self, collection_id: str, user_id: str) -> List[Dict[str, Any]]:
        return await self.db.saved_items.find(
            {"collection_id": collection_id, "user_id": user_id},
            {"_id": 0}
        ).to_list(1000)
    
    async def get_saved_item(self, item_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        return await self.db.saved_items.find_one({"id": item_id, "user_id": user_id}, {"_id": 0})
    
    async def delete_saved_items_by_folder(self, folder_id: str, user_id: str) -> int:
        result = await self.db.saved_items.delete_many({"folder_id": folder_id, "user_id": user_id})
        return result.deleted_count
    
    async def delete_saved_items_by_collection(self, collection_id: str, user_id: str) -> int:
        result = await self.db.saved_items.delete_many({"collection_id": collection_id, "user_id": user_id})
        return result.deleted_count
    
    # Favorites operations
    async def add_favorite(self, user_id: str, tool_id: str) -> Dict[str, Any]:
        favorite = {"user_id": user_id, "tool_id": tool_id}
        await self.db.favorites.insert_one(favorite)
        return favorite
    
    async def remove_favorite(self, user_id: str, tool_id: str) -> bool:
        result = await self.db.favorites.delete_one({"user_id": user_id, "tool_id": tool_id})
        return result.deleted_count > 0
    
    async def has_favorite(self, user_id: str, tool_id: str) -> bool:
        result = await self.db.favorites.find_one({"user_id": user_id, "tool_id": tool_id}, {"_id": 1})
        return result is not None

    async def get_favorites(self, user_id: str) -> List[str]:
        favorites = await self.db.favorites.find({"user_id": user_id}, {"_id": 0}).to_list(1000)
        return [fav["tool_id"] for fav in favorites]
