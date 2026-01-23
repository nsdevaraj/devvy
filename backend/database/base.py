"""
Abstract base class for database operations.
Provides interface for both MongoDB (web) and SQLite (desktop) implementations.
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any


class DatabaseBase(ABC):
    """Abstract database interface"""
    
    @abstractmethod
    async def connect(self):
        """Initialize database connection"""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Close database connection"""
        pass
    
    # User operations
    @abstractmethod
    async def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        pass
    
    # Organization operations
    @abstractmethod
    async def create_organization(self, org_data: Dict[str, Any]) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def get_organization(self, org_id: str) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def increment_org_licenses(self, org_id: str) -> bool:
        pass

    @abstractmethod
    async def get_organizations(self) -> List[Dict[str, Any]]:
        pass
    
    # Tool configuration operations
    @abstractmethod
    async def get_tool_configs(self) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def get_tool_config(self, tool_id: str) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def upsert_tool_config(self, tool_id: str, config_data: Dict[str, Any]) -> Dict[str, Any]:
        pass
    
    # Collection operations
    @abstractmethod
    async def create_collection(self, user_id: str, collection_data: Dict[str, Any]) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def get_collections(self, user_id: str) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def delete_collection(self, collection_id: str, user_id: str) -> bool:
        pass
    
    # Folder operations
    @abstractmethod
    async def create_folder(self, folder_data: Dict[str, Any]) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def get_folders(self, collection_id: str, user_id: str) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def update_folder(self, folder_id: str, user_id: str, update_data: Dict[str, Any]) -> bool:
        pass
    
    @abstractmethod
    async def delete_folder(self, folder_id: str, user_id: str) -> bool:
        pass
    
    @abstractmethod
    async def get_folder(self, folder_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        pass
    
    # Saved items operations
    @abstractmethod
    async def create_saved_item(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def get_saved_items(self, collection_id: str, user_id: str) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def get_saved_item(self, item_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def delete_saved_items_by_folder(self, folder_id: str, user_id: str) -> int:
        pass
    
    @abstractmethod
    async def delete_saved_items_by_collection(self, collection_id: str, user_id: str) -> int:
        pass
    
    # Favorites operations
    @abstractmethod
    async def add_favorite(self, user_id: str, tool_id: str) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def remove_favorite(self, user_id: str, tool_id: str) -> bool:
        pass
    
    @abstractmethod
    async def has_favorite(self, user_id: str, tool_id: str) -> bool:
        pass

    @abstractmethod
    async def get_favorites(self, user_id: str) -> List[str]:
        pass
