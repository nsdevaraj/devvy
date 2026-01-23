from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field, ConfigDict
import os
import uuid
import logging

logger = logging.getLogger(__name__)

# JWT Settings
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours

_secret_key = None


def get_secret_key():
    global _secret_key
    if _secret_key:
        return _secret_key

    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        logger.warning(
            "JWT_SECRET_KEY is not set. Using insecure default key. "
            "THIS IS NOT SAFE FOR PRODUCTION."
        )
        secret = "your-secret-key-change-in-production"

    _secret_key = secret
    return secret


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Models
class UserBase(BaseModel):
    email: EmailStr
    role: str = "user"  # user, admin, org_admin

class UserCreate(UserBase):
    password: str
    organization_id: Optional[str] = None

class User(UserBase):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    organization_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict

class OrganizationBase(BaseModel):
    name: str
    license_tier: str = "free"  # free, premium
    max_licenses: int = 1
    
class OrganizationCreate(OrganizationBase):
    admin_email: EmailStr
    admin_password: str

class Organization(OrganizationBase):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    license_key: str = Field(default_factory=lambda: str(uuid.uuid4()))
    active_licenses: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expiry_date: Optional[datetime] = None
    is_active: bool = True

class ToolConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_id: str
    tool_name: str
    is_premium: bool = False
    description: str = ""

class ToolConfigUpdate(BaseModel):
    tool_id: str
    is_premium: bool


# Collections Models
class CollectionBase(BaseModel):
    name: str
    description: str = ""

class CollectionCreate(CollectionBase):
    pass

class Collection(CollectionBase):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class FolderBase(BaseModel):
    name: str
    collection_id: str
    parent_folder_id: Optional[str] = None

class FolderCreate(FolderBase):
    pass

class Folder(FolderBase):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SavedItemBase(BaseModel):
    name: str
    description: str = ""
    tool_id: str
    tool_data: dict
    collection_id: str
    folder_id: Optional[str] = None

class SavedItemCreate(SavedItemBase):
    pass

class SavedItem(SavedItemBase):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Password utilities
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

# JWT utilities
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, get_secret_key(), algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
