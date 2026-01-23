from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
import os
import sys
import asyncio
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import json
from auth import (
    User, UserCreate, UserLogin, Token, Organization, OrganizationCreate,
    ToolConfig, ToolConfigUpdate, get_password_hash, verify_password,
    create_access_token, decode_token, Collection, CollectionCreate,
    Folder, FolderCreate, SavedItem, SavedItemCreate
)
from db_service import get_db
from database import DatabaseBase
import grpc
from google.protobuf import descriptor_pb2
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.message_factory import MessageFactory
from google.protobuf import json_format
import tempfile
import subprocess


ROOT_DIR = Path(__file__).parent

# Load environment files based on mode
env_file = ROOT_DIR / '.env.desktop' if os.environ.get('APP_MODE') == 'desktop' else ROOT_DIR / '.env'
if env_file.exists():
    load_dotenv(env_file)
else:
    # Fallback to default environment variables for desktop mode
    if os.environ.get('APP_MODE') == 'desktop':
        os.environ.setdefault('DATABASE_URL', 'sqlite+aiosqlite:///./devtools.db')
        os.environ.setdefault('CORS_ORIGINS', '*')

# Database will be initialized via dependency injection
db_instance = None

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Security
security = HTTPBearer()

# Dependency to get database instance
async def get_database():
    global db_instance
    if db_instance is None:
        db_instance = await get_db()
    return db_instance

# Dependency to get current user from JWT token
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    db = await get_database()
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    user = await db.get_user_by_id(payload.get("sub"))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user

# Dependency to check if user is admin
async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") not in ["admin", "org_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# Define Models
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Ignore MongoDB's _id field
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str


class JSONBeautifyRequest(BaseModel):
    json_string: str
    indent: int = 2

class JSONBeautifyResponse(BaseModel):
    beautified: str
    valid: bool
    error: Optional[str] = None


class FavoriteToolRequest(BaseModel):
    tool_id: str

class FavoriteTool(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_id: str
    user_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ========== AUTHENTICATION ROUTES ==========

@api_router.post("/auth/register", response_model=Token)
async def register(user_data: UserCreate, db=Depends(get_database)):
    # Check if user already exists
    existing_user = await db.get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # If no organization_id provided, create free tier single-user org
    org_id = user_data.organization_id
    if not org_id:
        free_org = Organization(
            name=f"{user_data.email}'s Workspace",
            license_tier="free",
            max_licenses=1,
            active_licenses=1
        )
        org_doc = free_org.model_dump()
        org_doc['created_at'] = org_doc['created_at'].isoformat()
        await db.create_organization(org_doc)
        org_id = free_org.id
    else:
        # Check if organization exists and has available licenses
        org = await db.get_organization(org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        if org['active_licenses'] >= org['max_licenses']:
            raise HTTPException(status_code=400, detail="No available licenses in organization")
        
        # Increment active licenses
        await db.increment_org_licenses(org_id)
    
    # Create user
    user = User(
        email=user_data.email,
        role=user_data.role,
        organization_id=org_id
    )
    
    user_doc = user.model_dump()
    user_doc['password_hash'] = get_password_hash(user_data.password)
    user_doc['created_at'] = user_doc['created_at'].isoformat()
    
    await db.create_user(user_doc)
    
    # Create access token
    access_token = create_access_token(data={"sub": user.id, "email": user.email})
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user={
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "organization_id": user.organization_id
        }
    )

@api_router.post("/auth/login", response_model=Token)
async def login(credentials: UserLogin, db=Depends(get_database)):
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not verify_password(credentials.password, user['password_hash']):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not user.get('is_active', True):
        raise HTTPException(status_code=403, detail="User account is disabled")
    
    # Create access token
    access_token = create_access_token(data={"sub": user['id'], "email": user['email']})
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user={
            "id": user['id'],
            "email": user['email'],
            "role": user.get('role', 'user'),
            "organization_id": user.get('organization_id')
        }
    )

@api_router.get("/auth/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    # Get organization info
    org = await db.organizations.find_one({"id": current_user.get('organization_id')}, {"_id": 0})
    
    return {
        "user": {
            "id": current_user['id'],
            "email": current_user['email'],
            "role": current_user.get('role', 'user')
        },
        "organization": org if org else None
    }


# ========== LICENSE MANAGEMENT ROUTES ==========

@api_router.get("/license/validate")
async def validate_license(current_user: dict = Depends(get_current_user)):
    """Validate if user has access to premium tools"""
    org = await db.organizations.find_one({"id": current_user.get('organization_id')}, {"_id": 0})
    
    if not org:
        return {
            "is_premium": False,
            "license_tier": "free",
            "message": "No organization found"
        }
    
    # Check if license is expired
    is_expired = False
    if org.get('expiry_date'):
        expiry = datetime.fromisoformat(org['expiry_date']) if isinstance(org['expiry_date'], str) else org['expiry_date']
        if expiry < datetime.now(timezone.utc):
            is_expired = True
    
    return {
        "is_premium": org['license_tier'] == 'premium' and not is_expired,
        "license_tier": org['license_tier'],
        "organization_name": org['name'],
        "licenses_used": org.get('active_licenses', 0),
        "licenses_total": org.get('max_licenses', 1),
        "expiry_date": org.get('expiry_date'),
        "is_expired": is_expired
    }

@api_router.get("/tools/config")
async def get_tools_config(db=Depends(get_database)):
    """Get configuration of which tools are free/premium"""
    configs = await db.tool_configs.find({}, {"_id": 0}).to_list(100)
    
    # If no config exists, create default (all free)
    if not configs:
        default_tools = [
            {"tool_id": "json-beautifier", "tool_name": "JSON Beautifier", "is_premium": False},
            {"tool_id": "json-validator", "tool_name": "JSON Validator", "is_premium": False},
            {"tool_id": "api-tester", "tool_name": "REST API Tester", "is_premium": False},
            {"tool_id": "grpc-tester", "tool_name": "gRPC Tester", "is_premium": False},
            {"tool_id": "ui-recorder", "tool_name": "UI Automation Recorder", "is_premium": False},
        ]
        
        docs = []
        for tool_data in default_tools:
            tool_config = ToolConfig(**tool_data)
            docs.append(tool_config.model_dump())

        if docs:
            await db.tool_configs.insert_many(docs)
        
        configs = await db.tool_configs.find({}, {"_id": 0}).to_list(100)
    
    return {"tools": configs}

@api_router.get("/tools/check-access/{tool_id}")
async def check_tool_access(tool_id: str, current_user: dict = Depends(get_current_user)):
    """Check if user has access to a specific tool"""
    # Get tool config
    tool_config = await db.tool_configs.find_one({"tool_id": tool_id}, {"_id": 0})
    
    if not tool_config:
        # If no config, assume free
        return {"has_access": True, "is_premium_tool": False}
    
    if not tool_config.get('is_premium', False):
        # Free tool, everyone has access
        return {"has_access": True, "is_premium_tool": False}
    
    # Premium tool - check license
    license_info = await validate_license(current_user)
    
    return {
        "has_access": license_info['is_premium'],
        "is_premium_tool": True,
        "license_tier": license_info['license_tier']
    }


# ========== COLLECTIONS ROUTES ==========

@api_router.post("/collections/create", response_model=Collection)
async def create_collection(collection_data: CollectionCreate, current_user: dict = Depends(get_current_user)):
    """Create a new collection"""
    collection = Collection(**collection_data.model_dump(), user_id=current_user['id'])
    
    doc = collection.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.collections.insert_one(doc)
    return collection

@api_router.get("/collections/list")
async def list_collections(current_user: dict = Depends(get_current_user)):
    """List all collections for current user"""
    collections = await db.collections.find(
        {"user_id": current_user['id']},
        {"_id": 0}
    ).to_list(1000)
    
    return {"collections": collections}

@api_router.put("/collections/{collection_id}")
async def update_collection(collection_id: str, updates: CollectionCreate, current_user: dict = Depends(get_current_user)):
    """Update a collection"""
    result = await db.collections.update_one(
        {"id": collection_id, "user_id": current_user['id']},
        {"$set": updates.model_dump()}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    return {"message": "Collection updated"}

@api_router.delete("/collections/{collection_id}")
async def delete_collection(collection_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a collection and all its folders and items"""
    # Delete all saved items in this collection
    await db.saved_items.delete_many({"collection_id": collection_id, "user_id": current_user['id']})
    
    # Delete all folders in this collection
    await db.folders.delete_many({"collection_id": collection_id, "user_id": current_user['id']})
    
    # Delete the collection
    result = await db.collections.delete_one({"id": collection_id, "user_id": current_user['id']})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    return {"message": "Collection deleted"}


# ========== FOLDERS ROUTES ==========

@api_router.post("/folders/create", response_model=Folder)
async def create_folder(folder_data: FolderCreate, current_user: dict = Depends(get_current_user)):
    """Create a new folder in a collection"""
    folder = Folder(**folder_data.model_dump(), user_id=current_user['id'])
    
    doc = folder.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.folders.insert_one(doc)
    return folder

@api_router.get("/folders/list/{collection_id}")
async def list_folders(collection_id: str, current_user: dict = Depends(get_current_user)):
    """List all folders in a collection"""
    folders = await db.folders.find(
        {"collection_id": collection_id, "user_id": current_user['id']},
        {"_id": 0}
    ).to_list(1000)
    
    return {"folders": folders}

@api_router.put("/folders/{folder_id}")
async def update_folder(folder_id: str, updates: FolderCreate, current_user: dict = Depends(get_current_user)):
    """Update a folder"""
    result = await db.folders.update_one(
        {"id": folder_id, "user_id": current_user['id']},
        {"$set": updates.model_dump()}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    return {"message": "Folder updated"}

@api_router.delete("/folders/{folder_id}")
async def delete_folder(
    folder_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database)
):
    """Delete a folder and all its items and subfolders recursively"""
    
    user_id = current_user['id']

    # Check if folder exists and get details
    folder = await db.folders.find_one({"id": folder_id, "user_id": user_id}, {"_id": 0})
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    collection_id = folder.get('collection_id')

    # Fetch all folders in this collection to build the tree
    all_folders = await db.folders.find(
        {"collection_id": collection_id, "user_id": user_id},
        {"_id": 0}
    ).to_list(10000)

    # Build parent -> children map
    children_map = {}
    for f in all_folders:
        pid = f.get('parent_folder_id')
        if pid:
            if pid not in children_map:
                children_map[pid] = []
            children_map[pid].append(f['id'])

    # BFS to find all descendants
    ids_to_delete = [folder_id]
    queue = [folder_id]

    while queue:
        current_id = queue.pop(0)
        if current_id in children_map:
            children = children_map[current_id]
            ids_to_delete.extend(children)
            queue.extend(children)

    # Delete all saved items in these folders
    await db.saved_items.delete_many({
        "folder_id": {"$in": ids_to_delete},
        "user_id": user_id
    })

    # Delete the folders
    await db.folders.delete_many({
        "id": {"$in": ids_to_delete},
        "user_id": user_id
    })
    
    return {"message": "Folder deleted"}


# ========== SAVED ITEMS ROUTES ==========

@api_router.post("/saved-items/create", response_model=SavedItem)
async def create_saved_item(item_data: SavedItemCreate, current_user: dict = Depends(get_current_user)):
    """Save a tab/snippet to a collection"""
    saved_item = SavedItem(**item_data.model_dump(), user_id=current_user['id'])
    
    doc = saved_item.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.saved_items.insert_one(doc)
    return saved_item

@api_router.get("/saved-items/list/{collection_id}")
async def list_saved_items(collection_id: str, current_user: dict = Depends(get_current_user)):
    """List all saved items in a collection"""
    items = await db.saved_items.find(
        {"collection_id": collection_id, "user_id": current_user['id']},
        {"_id": 0}
    ).to_list(1000)
    
    return {"items": items}

@api_router.get("/saved-items/{item_id}")
async def get_saved_item(item_id: str, current_user: dict = Depends(get_current_user)):
    """Get a specific saved item"""
    item = await db.saved_items.find_one(
        {"id": item_id, "user_id": current_user['id']},
        {"_id": 0}
    )
    
    if not item:
        raise HTTPException(status_code=404, detail="Saved item not found")
    
    return item

@api_router.put("/saved-items/{item_id}")
async def update_saved_item(item_id: str, updates: SavedItemCreate, current_user: dict = Depends(get_current_user)):
    """Update a saved item"""
    result = await db.saved_items.update_one(
        {"id": item_id, "user_id": current_user['id']},
        {"$set": updates.model_dump()}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Saved item not found")
    
    return {"message": "Saved item updated"}

@api_router.delete("/saved-items/{item_id}")
async def delete_saved_item(item_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a saved item"""
    result = await db.saved_items.delete_one({"id": item_id, "user_id": current_user['id']})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Saved item not found")
    
    return {"message": "Saved item deleted"}


# ========== ADMIN ROUTES ==========

@api_router.post("/admin/configure-tool")
async def configure_tool(config: ToolConfigUpdate, admin_user: dict = Depends(require_admin)):
    """Set a tool as free or premium (admin only)"""
    existing = await db.tool_configs.find_one({"tool_id": config.tool_id}, {"_id": 0})
    
    if existing:
        await db.tool_configs.update_one(
            {"tool_id": config.tool_id},
            {"$set": {"is_premium": config.is_premium}}
        )
        message = "Tool configuration updated"
    else:
        tool_config = ToolConfig(
            tool_id=config.tool_id,
            tool_name=config.tool_id.replace('-', ' ').title(),
            is_premium=config.is_premium
        )
        await db.tool_configs.insert_one(tool_config.model_dump())
        message = "Tool configuration created"
    
    return {"message": message, "tool_id": config.tool_id, "is_premium": config.is_premium}

@api_router.get("/admin/tools-config")
async def get_admin_tools_config(admin_user: dict = Depends(require_admin)):
    """Get all tool configurations (admin only)"""
    configs = await db.tool_configs.find({}, {"_id": 0}).to_list(100)
    return {"tools": configs}

@api_router.post("/admin/create-organization")
async def create_organization(org_data: OrganizationCreate, admin_user: dict = Depends(require_admin)):
    """Create a new organization with licenses (admin only)"""
    # Check if admin email already exists
    existing_user = await db.users.find_one({"email": org_data.admin_email}, {"_id": 0})
    if existing_user:
        raise HTTPException(status_code=400, detail="Admin email already registered")
    
    # Create organization
    org = Organization(
        name=org_data.name,
        license_tier=org_data.license_tier,
        max_licenses=org_data.max_licenses,
        active_licenses=1,  # Admin counts as first license
        expiry_date=datetime.now(timezone.utc) + timedelta(days=365) if org_data.license_tier == 'premium' else None
    )
    
    org_doc = org.model_dump()
    org_doc['created_at'] = org_doc['created_at'].isoformat()
    if org_doc.get('expiry_date'):
        org_doc['expiry_date'] = org_doc['expiry_date'].isoformat()
    
    await db.organizations.insert_one(org_doc)
    
    # Create admin user
    admin_user_data = UserCreate(
        email=org_data.admin_email,
        password=org_data.admin_password,
        role="org_admin",
        organization_id=org.id
    )
    
    user = User(
        email=admin_user_data.email,
        role="org_admin",
        organization_id=org.id
    )
    
    user_doc = user.model_dump()
    user_doc['password_hash'] = get_password_hash(org_data.admin_password)
    user_doc['created_at'] = user_doc['created_at'].isoformat()
    
    await db.users.insert_one(user_doc)
    
    return {
        "message": "Organization created successfully",
        "organization": {
            "id": org.id,
            "name": org.name,
            "license_key": org.license_key,
            "license_tier": org.license_tier,
            "max_licenses": org.max_licenses
        },
        "admin_user": {
            "id": user.id,
            "email": user.email
        }
    }

@api_router.get("/admin/organizations")
async def list_organizations(admin_user: dict = Depends(require_admin)):
    """List all organizations (admin only)"""
    orgs = await db.organizations.find({}, {"_id": 0}).to_list(1000)
    return {"organizations": orgs}

@api_router.get("/admin/organization/{org_id}/users")
async def list_organization_users(org_id: str, admin_user: dict = Depends(require_admin)):
    """List all users in an organization (admin only)"""
    users = await db.users.find(
        {"organization_id": org_id},
        {"_id": 0, "password_hash": 0}
    ).to_list(1000)
    
    return {"users": users}


# ========== ORIGINAL ROUTES ==========

@api_router.get("/")
async def root():
    return {"message": "Developer Productivity Suite API"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate, db: DatabaseBase = Depends(get_database)):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    # Convert to dict and store datetime natively
    doc = status_obj.model_dump()
    # No need to convert timestamp to isoformat string, store as native Date
    
    _ = await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks(db: DatabaseBase = Depends(get_database)):
    # Exclude MongoDB's _id field from the query results
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    
    # Pydantic V2 will automatically handle parsing of strings to datetime if necessary
    # (legacy data support), and pass through native datetime objects efficiently.
    # The manual conversion loop is removed for performance.
    
    return status_checks


# JSON Beautifier Tool
@api_router.post("/tools/json-beautifier", response_model=JSONBeautifyResponse)
async def beautify_json(request: JSONBeautifyRequest):
    try:
        # Parse JSON to validate
        parsed = json.loads(request.json_string)
        
        # Beautify with specified indent
        beautified = json.dumps(parsed, indent=request.indent, sort_keys=False)
        
        return JSONBeautifyResponse(
            beautified=beautified,
            valid=True,
            error=None
        )
    except json.JSONDecodeError as e:
        return JSONBeautifyResponse(
            beautified=request.json_string,
            valid=False,
            error=f"Invalid JSON: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Favorites Management
@api_router.post("/favorites/add")
async def add_favorite(
    request: FavoriteToolRequest,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    user_id = current_user['id']
    
    # Check if already exists
    if await db.has_favorite(user_id, request.tool_id):
        return {"message": "Already in favorites", "favorite_id": "unknown"}
    
    await db.add_favorite(user_id, request.tool_id)
    return {"message": "Added to favorites", "favorite_id": "new"}

@api_router.post("/favorites/remove")
async def remove_favorite(
    request: FavoriteToolRequest,
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    user_id = current_user['id']

    result = await db.remove_favorite(user_id, request.tool_id)
    
    if result:
        return {"message": "Removed from favorites"}
    else:
        return {"message": "Not found in favorites"}

@api_router.get("/favorites/list")
async def list_favorites(
    current_user: dict = Depends(get_current_user),
    db = Depends(get_database)
):
    user_id = current_user['id']

    favorites = await db.get_favorites(user_id)
    
    return {"favorites": favorites}


# ========== gRPC PROXY ENDPOINT ==========

class GrpcCallRequest(BaseModel):
    server_url: str
    service: str
    method: str
    request: dict
    metadata: dict = {}
    proto_content: str


@api_router.post("/grpc/call")
async def grpc_call(request: GrpcCallRequest, current_user: dict = Depends(get_current_user)):
    """
    Proxy endpoint for making gRPC calls.
    This endpoint receives proto file content, parses it, and makes a gRPC call.
    """
    # Validate proto content
    if not request.proto_content or not request.proto_content.strip():
        raise HTTPException(status_code=400, detail="Proto content is required")
    
    try:
        import grpc
        from google.protobuf import descriptor_pb2
        from google.protobuf.descriptor_pool import DescriptorPool
        from google.protobuf import message_factory
        from google.protobuf import json_format
        import tempfile
        import os as os_module
        
        # Save proto content to a temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.proto', delete=False) as proto_file:
            proto_file.write(request.proto_content)
            proto_file_path = proto_file.name
        
        # Compile the proto file to get descriptor
        descriptor_set_file = proto_file_path + '.desc'
        proto_dir = os_module.path.dirname(proto_file_path)
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-m', 'grpc_tools.protoc',
            f'--proto_path={proto_dir}',
            f'--descriptor_set_out={descriptor_set_file}',
            '--include_imports',
            proto_file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to compile proto file: {stderr.decode()}"
            )
        
        # Load the descriptor
        def load_descriptor_set():
            with open(descriptor_set_file, 'rb') as f:
                descriptor_set = descriptor_pb2.FileDescriptorSet()
                descriptor_set.ParseFromString(f.read())
            return descriptor_set

        descriptor_set = await run_in_threadpool(load_descriptor_set)
        
        # Create a descriptor pool and register the descriptors
        pool = DescriptorPool()
        for file_descriptor_proto in descriptor_set.file:
            pool.Add(file_descriptor_proto)
        
        # Find the service and method descriptors
        service_descriptor = None
        package_name = ""
        for file_descriptor_proto in descriptor_set.file:
            for service in file_descriptor_proto.service:
                if service.name == request.service:
                    service_descriptor = service
                    package_name = file_descriptor_proto.package
                    break
            if service_descriptor:
                break
        
        if not service_descriptor:
            raise HTTPException(status_code=400, detail=f"Service '{request.service}' not found")
        
        # Find the method
        method_descriptor = None
        for method in service_descriptor.method:
            if method.name == request.method:
                method_descriptor = method
                break
        
        if not method_descriptor:
            raise HTTPException(status_code=400, detail=f"Method '{request.method}' not found")
        
        # Get the request and response message types
        request_type = pool.FindMessageTypeByName(method_descriptor.input_type.lstrip('.'))
        response_type = pool.FindMessageTypeByName(method_descriptor.output_type.lstrip('.'))
        
        # Create message instances
        request_message_class = message_factory.GetMessageClass(request_type)
        response_message_class = message_factory.GetMessageClass(response_type)
        
        # Convert JSON request to protobuf message
        request_message = json_format.ParseDict(request.request, request_message_class())
        
        # Create gRPC channel and make the call
        async with grpc.aio.insecure_channel(request.server_url) as channel:
            # Prepare metadata
            metadata_list = [(k, v) for k, v in request.metadata.items()]

            # Make the unary-unary call
            full_service_name = f"{package_name}.{service_descriptor.name}" if package_name else service_descriptor.name
            method_full_name = f'/{full_service_name}/{request.method}'

            response = await channel.unary_unary(
                method_full_name,
                request_serializer=lambda x: x.SerializeToString(),
                response_deserializer=response_message_class.FromString,
            )(request_message, metadata=metadata_list, timeout=30)

            # Convert response to dict
            response_dict = json_format.MessageToDict(response, preserving_proto_field_name=True)
        
        # Clean up temporary files
        os.unlink(proto_file_path)
        os.unlink(descriptor_set_file)
        
        return {
            "response": response_dict,
            "metadata": {}
        }
        
    except HTTPException:
        # Re-raise HTTPExceptions (like 400 errors) as-is
        raise
    except grpc.RpcError as e:
        raise HTTPException(
            status_code=500,
            detail=f"gRPC Error: {e.code()}: {e.details()}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error making gRPC call: {str(e)}"
        )


# ========== UI AUTOMATION RECORDER ENDPOINTS ==========

# In-memory storage for recording sessions
recording_sessions = {}

class RecorderSession(BaseModel):
    language: str
    target_url: str

class RecorderEvents(BaseModel):
    events: List[dict]

@api_router.post("/recorder/session")
async def create_recorder_session(session: RecorderSession, current_user: dict = Depends(get_current_user)):
    """Create a new recording session"""
    session_id = str(uuid.uuid4())
    recording_sessions[session_id] = {
        'user_id': current_user['id'],
        'language': session.language,
        'target_url': session.target_url,
        'events': [],
        'created_at': datetime.now(timezone.utc)
    }
    return {"session_id": session_id, "message": "Recording session created"}

@api_router.post("/recorder/events/{session_id}")
async def add_recorder_events(session_id: str, events: RecorderEvents, current_user: dict = Depends(get_current_user)):
    """Add recorded events to a session"""
    if session_id not in recording_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = recording_sessions[session_id]
    if session['user_id'] != current_user['id']:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    session['events'].extend(events.events)
    return {"message": "Events recorded", "total_events": len(session['events'])}

@api_router.post("/recorder/generate/{session_id}")
async def generate_recorder_code(session_id: str, request: dict, current_user: dict = Depends(get_current_user)):
    """Generate Playwright code from recorded events"""
    if session_id not in recording_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = recording_sessions[session_id]
    if session['user_id'] != current_user['id']:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    language = request.get('language', session['language'])
    events = session['events']
    
    # Generate code based on language
    if language == 'python':
        code = generate_python_code(events, session['target_url'])
    elif language == 'javascript':
        code = generate_javascript_code(events, session['target_url'])
    elif language == 'typescript':
        code = generate_typescript_code(events, session['target_url'])
    else:
        code = generate_python_code(events, session['target_url'])
    
    return {"code": code, "total_events": len(events)}

def generate_python_code(events, target_url):
    """Generate Python Playwright code from events"""
    lines = [
        "from playwright.sync_api import sync_playwright",
        "",
        "def run(playwright):",
        "    browser = playwright.chromium.launch(headless=False)",
        "    context = browser.new_context()",
        "    page = context.new_page()",
        ""
    ]
    
    # Add initial navigation
    if events and events[0]['type'] != 'navigation':
        lines.append(f"    page.goto('{target_url}')")
    
    # Process events
    for event in events:
        if event['type'] == 'navigation':
            lines.append(f"    page.goto('{event['url']}')")
        elif event['type'] == 'click':
            lines.append(f"    page.click('{event['selector']}')")
        elif event['type'] == 'input':
            value = event.get('value', '').replace("'", "\\'")
            lines.append(f"    page.fill('{event['selector']}', '{value}')")
    
    lines.extend([
        "",
        "    # Close the browser",
        "    context.close()",
        "    browser.close()",
        "",
        "with sync_playwright() as playwright:",
        "    run(playwright)"
    ])
    
    return "\n".join(lines)

def generate_javascript_code(events, target_url):
    """Generate JavaScript Playwright code from events"""
    lines = [
        "const { chromium } = require('playwright');",
        "",
        "(async () => {",
        "  const browser = await chromium.launch({ headless: false });",
        "  const context = await browser.newContext();",
        "  const page = await context.newPage();",
        ""
    ]
    
    # Add initial navigation
    if events and events[0]['type'] != 'navigation':
        lines.append(f"  await page.goto('{target_url}');")
    
    # Process events
    for event in events:
        if event['type'] == 'navigation':
            lines.append(f"  await page.goto('{event['url']}');")
        elif event['type'] == 'click':
            lines.append(f"  await page.click('{event['selector']}');")
        elif event['type'] == 'input':
            value = event.get('value', '').replace("'", "\\'")
            lines.append(f"  await page.fill('{event['selector']}', '{value}');")
    
    lines.extend([
        "",
        "  // Close the browser",
        "  await context.close();",
        "  await browser.close();",
        "})();"
    ])
    
    return "\n".join(lines)

def generate_typescript_code(events, target_url):
    """Generate TypeScript Playwright code from events"""
    lines = [
        "import { chromium, Browser, BrowserContext, Page } from 'playwright';",
        "",
        "(async () => {",
        "  const browser: Browser = await chromium.launch({ headless: false });",
        "  const context: BrowserContext = await browser.newContext();",
        "  const page: Page = await context.newPage();",
        ""
    ]
    
    # Add initial navigation
    if events and events[0]['type'] != 'navigation':
        lines.append(f"  await page.goto('{target_url}');")
    
    # Process events
    for event in events:
        if event['type'] == 'navigation':
            lines.append(f"  await page.goto('{event['url']}');")
        elif event['type'] == 'click':
            lines.append(f"  await page.click('{event['selector']}');")
        elif event['type'] == 'input':
            value = event.get('value', '').replace("'", "\\'")
            lines.append(f"  await page.fill('{event['selector']}', '{value}');")
    
    lines.extend([
        "",
        "  // Close the browser",
        "  await context.close();",
        "  await browser.close();",
        "})();"
    ])
    
    return "\n".join(lines)


# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    global db_instance
    if db_instance:
        await db_instance.disconnect()
        db_instance = None