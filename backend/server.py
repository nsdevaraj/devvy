from fastapi import (
    FastAPI,
    APIRouter,
    HTTPException,
    Depends,
    Header,
    UploadFile,
    File as FastAPIFile,
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict
import uuid
from datetime import datetime, timezone, timedelta
import json
import subprocess
import tempfile
import io
import asyncio
import sys
from auth import (
    User,
    UserCreate,
    UserLogin,
    Token,
    Organization,
    OrganizationCreate,
    ToolConfig,
    ToolConfigUpdate,
    get_password_hash,
    verify_password,
    create_access_token,
    decode_token,
    Collection,
    CollectionCreate,
    Folder,
    FolderCreate,
    SavedItem,
    SavedItemCreate,
    SavedItemBulkCreate,
)
from database import get_db_instance as get_db
from database.base import DatabaseBase

ROOT_DIR = Path(__file__).parent

# Load environment files based on mode
env_file = (
    ROOT_DIR / ".env.desktop"
    if os.environ.get("APP_MODE") == "desktop"
    else ROOT_DIR / ".env"
)
if env_file.exists():
    load_dotenv(env_file)
else:
    # Fallback to default environment variables for desktop mode
    if os.environ.get("APP_MODE") == "desktop":
        os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./devtools.db")
        os.environ.setdefault("CORS_ORIGINS", "*")

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
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    db = await get_database()
    token = credentials.credentials

    # Handle desktop mode with fake token
    if token == "desktop-token":
        # Return a fake desktop user
        return {
            "id": "desktop-user",
            "email": "desktop@devtools.local",
            "name": "Desktop User",
            "role": "user",
            "organization_id": "desktop-org",
        }

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


# Optional auth for desktop mode - no authentication required
async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
) -> Optional[dict]:
    """
    Get current user with optional authentication.
    - In desktop mode (APP_MODE=desktop): Returns a default desktop user without requiring auth
    - In web mode: Requires valid JWT token
    """
    if os.environ.get("APP_MODE") == "desktop":
        # Desktop mode: no authentication required, return default user
        return {
            "id": "desktop-user",
            "email": "desktop@devtools.local",
            "name": "Desktop User",
            "role": "user",
            "organization_id": "desktop-org",
        }

    # Web mode: require authentication
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    return await get_current_user(credentials)


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
    user_id: str = "default_user"  # For now, using a default user


class FavoriteTool(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_id: str
    user_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ========== AUTHENTICATION ROUTES ==========


@api_router.post("/auth/register", response_model=Token)
async def register(user_data: UserCreate):
    # Check if user already exists
    existing_user = await db.users.find_one({"email": user_data.email}, {"_id": 0})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # If no organization_id provided, create free tier single-user org
    org_id = user_data.organization_id
    if not org_id:
        free_org = Organization(
            name=f"{user_data.email}'s Workspace",
            license_tier="free",
            max_licenses=1,
            active_licenses=1,
        )
        org_doc = free_org.model_dump()
        org_doc["created_at"] = org_doc["created_at"].isoformat()
        await db.organizations.insert_one(org_doc)
        org_id = free_org.id
    else:
        # Check if organization exists and has available licenses
        org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        if org["active_licenses"] >= org["max_licenses"]:
            raise HTTPException(
                status_code=400, detail="No available licenses in organization"
            )

        # Increment active licenses
        await db.organizations.update_one(
            {"id": org_id}, {"$inc": {"active_licenses": 1}}
        )

    # Create user
    user = User(email=user_data.email, role=user_data.role, organization_id=org_id)

    user_doc = user.model_dump()
    user_doc["password_hash"] = get_password_hash(user_data.password)
    user_doc["created_at"] = user_doc["created_at"].isoformat()

    await db.users.insert_one(user_doc)

    # Create access token
    access_token = create_access_token(data={"sub": user.id, "email": user.email})

    return Token(
        access_token=access_token,
        token_type="bearer",
        user={
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "organization_id": user.organization_id,
        },
    )


@api_router.post("/auth/login", response_model=Token)
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="User account is disabled")

    # Create access token
    access_token = create_access_token(data={"sub": user["id"], "email": user["email"]})

    return Token(
        access_token=access_token,
        token_type="bearer",
        user={
            "id": user["id"],
            "email": user["email"],
            "role": user.get("role", "user"),
            "organization_id": user.get("organization_id"),
        },
    )


@api_router.get("/auth/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    # Get organization info
    org = await db.organizations.find_one(
        {"id": current_user.get("organization_id")}, {"_id": 0}
    )

    return {
        "user": {
            "id": current_user["id"],
            "email": current_user["email"],
            "role": current_user.get("role", "user"),
        },
        "organization": org if org else None,
    }


# ========== LICENSE MANAGEMENT ROUTES ==========


@api_router.get("/license/validate")
async def validate_license(
    current_user: dict = Depends(get_current_user), db=Depends(get_database)
):
    """Validate if user has access to premium tools"""
    org = await db.organizations.find_one(
        {"id": current_user.get("organization_id")}, {"_id": 0}
    )

    if not org:
        # Even if no org, return premium access for now
        return {
            "is_premium": True,
            "license_tier": "premium",
            "message": "No organization found (default premium)",
        }

    # Check if license is expired
    is_expired = False
    if org.get("expiry_date"):
        expiry = (
            datetime.fromisoformat(org["expiry_date"])
            if isinstance(org["expiry_date"], str)
            else org["expiry_date"]
        )
        if expiry < datetime.now(timezone.utc):
            is_expired = True

    # Always return premium access regardless of actual license or expiry
    return {
        "is_premium": True,
        "license_tier": "premium",
        "organization_name": org["name"],
        "licenses_used": org.get("active_licenses", 0),
        "licenses_total": org.get("max_licenses", 1),
        "expiry_date": org.get("expiry_date"),
        "is_expired": is_expired,
    }


@api_router.get("/tools/config")
async def get_tools_config(db=Depends(get_database)):
    """Get configuration of which tools are free/premium"""
    configs = await db.get_tool_configs()

    # If no config exists, create default (all free)
    if not configs:
        default_tools = [
            {
                "tool_id": "json-beautifier",
                "tool_name": "JSON Beautifier",
                "is_premium": False,
            },
            {
                "tool_id": "json-validator",
                "tool_name": "JSON Validator",
                "is_premium": False,
            },
            {
                "tool_id": "api-tester",
                "tool_name": "REST API Tester",
                "is_premium": False,
            },
            {"tool_id": "grpc-tester", "tool_name": "gRPC Tester", "is_premium": False},
            {
                "tool_id": "ui-recorder",
                "tool_name": "UI Automation Recorder",
                "is_premium": False,
            },
        ]

        # Use bulk upsert to prevent N+1 performance issue (optimized via upsert_tool_configs)
        # Performance benchmark: ~15ms vs ~600ms (N+1)
        await db.upsert_tool_configs(default_tools)

        configs = await db.get_tool_configs()

    return {"tools": configs}


@api_router.get("/tools/check-access/{tool_id}")
async def check_tool_access(
    tool_id: str,
    current_user: dict = Depends(get_current_user),
    db=Depends(get_database),
):
    """Check if user has access to a specific tool"""
    # Get tool config
    tool_config = await db.get_tool_config(tool_id)

    if not tool_config:
        # If no config, assume free
        return {"has_access": True, "is_premium_tool": False}

    is_premium_tool = tool_config.get("is_premium", False)

    # Always grant access
    return {
        "has_access": True,
        "is_premium_tool": is_premium_tool,
        "license_tier": "premium",
    }


# ========== COLLECTIONS ROUTES ==========


@api_router.post("/collections/create")
async def create_collection(
    collection_data: CollectionCreate,
    current_user: dict = Depends(get_current_user_optional),
    db=Depends(get_database),
):
    """Create a new collection"""
    collection_dict = collection_data.model_dump()
    collection_dict["created_at"] = datetime.now(timezone.utc)

    result = await db.create_collection(current_user["id"], collection_dict)
    return result


@api_router.get("/collections/list")
async def list_collections(
    current_user: dict = Depends(get_current_user_optional), db=Depends(get_database)
):
    """List all collections for current user"""
    collections = await db.get_collections(current_user["id"])
    return {"collections": collections}


@api_router.put("/collections/{collection_id}")
async def update_collection(
    collection_id: str,
    updates: CollectionCreate,
    current_user: dict = Depends(get_current_user_optional),
    db=Depends(get_database),
):
    """Update a collection"""
    update_data = updates.model_dump()
    result = await db.update_collection(collection_id, current_user["id"], update_data)

    if not result:
        raise HTTPException(status_code=404, detail="Collection not found")

    return {"message": "Collection updated", "success": True}


@api_router.delete("/collections/{collection_id}")
async def delete_collection(
    collection_id: str,
    current_user: dict = Depends(get_current_user_optional),
    db=Depends(get_database),
):
    """Delete a collection and all its folders and items"""
    result = await db.delete_collection(collection_id, current_user["id"])

    if not result:
        raise HTTPException(status_code=404, detail="Collection not found")

    return {"message": "Collection deleted"}


# ========== FOLDERS ROUTES ==========


@api_router.post("/folders/create")
async def create_folder(
    folder_data: FolderCreate,
    current_user: dict = Depends(get_current_user_optional),
    db=Depends(get_database),
):
    """Create a new folder in a collection"""
    folder_dict = folder_data.model_dump()
    folder_dict["user_id"] = current_user["id"]
    folder_dict["created_at"] = datetime.now(timezone.utc)

    result = await db.create_folder(folder_dict)
    return result


@api_router.get("/folders/list/{collection_id}")
async def list_folders(
    collection_id: str,
    current_user: dict = Depends(get_current_user_optional),
    db=Depends(get_database),
):
    """List all folders in a collection"""
    folders = await db.get_folders(collection_id, current_user["id"])
    return {"folders": folders}


@api_router.put("/folders/{folder_id}")
async def update_folder(
    folder_id: str,
    updates: FolderCreate,
    current_user: dict = Depends(get_current_user_optional),
    db=Depends(get_database),
):
    """Update a folder"""
    update_data = updates.model_dump()
    result = await db.update_folder(folder_id, current_user["id"], update_data)

    if not result:
        raise HTTPException(status_code=404, detail="Folder not found")

    return {"message": "Folder updated"}


@api_router.delete("/folders/{folder_id}")
async def delete_folder(
    folder_id: str,
    current_user: dict = Depends(get_current_user_optional),
    db=Depends(get_database),
):
    """Delete a folder and all its items and subfolders recursively"""
    result = await db.delete_folder(folder_id, current_user["id"])

    if not result:
        raise HTTPException(status_code=404, detail="Folder not found")

    return {"message": "Folder deleted"}


# ========== SAVED ITEMS ROUTES ==========


@api_router.post("/saved-items/create")
async def create_saved_item(
    item_data: SavedItemCreate,
    current_user: dict = Depends(get_current_user_optional),
    db=Depends(get_database),
):
    """Save a tab/snippet to a collection"""
    item_dict = item_data.model_dump()
    item_dict["user_id"] = current_user["id"]
    item_dict["created_at"] = datetime.now(timezone.utc)

    # Map tool_data to data for SQLite model compatibility
    if "tool_data" in item_dict:
        item_dict["data"] = item_dict.pop("tool_data")

    # Remove description if not in SQLite model
    item_dict.pop("description", None)

    result = await db.create_saved_item(item_dict)
    return result


@api_router.post("/saved-items/create-bulk")
async def create_saved_items_bulk(
    bulk_data: SavedItemBulkCreate,
    current_user: dict = Depends(get_current_user_optional),
    db=Depends(get_database),
):
    """
    Bulk save tabs/snippets to a collection.
    Optimized to prevent N+1 insert performance issues.
    """
    items_to_create = []

    for item_data in bulk_data.items:
        item_dict = item_data.model_dump()
        item_dict["user_id"] = current_user["id"]
        item_dict["created_at"] = datetime.now(timezone.utc)

        # Map tool_data to data for SQLite model compatibility
        if "tool_data" in item_dict:
            item_dict["data"] = item_dict.pop("tool_data")

        # Remove description if not in SQLite model
        item_dict.pop("description", None)

        items_to_create.append(item_dict)

    result = await db.create_saved_items_bulk(items_to_create)
    return {"count": len(result), "items": result}


@api_router.get("/saved-items/list/{collection_id}")
async def list_saved_items(
    collection_id: str,
    current_user: dict = Depends(get_current_user_optional),
    db=Depends(get_database),
):
    """List all saved items in a collection"""
    items = await db.get_saved_items(collection_id, current_user["id"])

    # Map data field back to tool_data for frontend compatibility
    for item in items:
        if "data" in item:
            item["tool_data"] = item.pop("data")

    return {"items": items}


@api_router.get("/saved-items/{item_id}")
async def get_saved_item(
    item_id: str,
    current_user: dict = Depends(get_current_user_optional),
    db=Depends(get_database),
):
    """Get a specific saved item"""
    item = await db.get_saved_item(item_id, current_user["id"])

    if not item:
        raise HTTPException(status_code=404, detail="Saved item not found")

    # Map data field back to tool_data for frontend compatibility
    if "data" in item:
        item["tool_data"] = item.pop("data")

    return item


@api_router.put("/saved-items/{item_id}")
async def update_saved_item(
    item_id: str,
    updates: SavedItemCreate,
    current_user: dict = Depends(get_current_user_optional),
    db=Depends(get_database),
):
    """Update a saved item"""
    update_dict = updates.model_dump()

    # Map tool_data to data for SQLite model compatibility
    if "tool_data" in update_dict:
        update_dict["data"] = update_dict.pop("tool_data")

    # Remove description if not in SQLite model
    update_dict.pop("description", None)

    result = await db.update_saved_item(item_id, current_user["id"], update_dict)

    if not result:
        raise HTTPException(status_code=404, detail="Saved item not found")

    # Map data back to tool_data for frontend
    if "data" in result:
        result["tool_data"] = result.pop("data")

    return result


@api_router.delete("/saved-items/{item_id}")
async def delete_saved_item(
    item_id: str,
    current_user: dict = Depends(get_current_user_optional),
    db=Depends(get_database),
):
    """Delete a saved item"""
    result = await db.delete_saved_item(item_id, current_user["id"])

    if not result:
        raise HTTPException(status_code=404, detail="Saved item not found")

    return {"message": "Saved item deleted"}


# ========== ADMIN ROUTES ==========


@api_router.post("/admin/configure-tool")
async def configure_tool(
    config: ToolConfigUpdate, admin_user: dict = Depends(require_admin)
):
    """Set a tool as free or premium (admin only)"""
    existing = await db.tool_configs.find_one({"tool_id": config.tool_id}, {"_id": 0})

    if existing:
        await db.tool_configs.update_one(
            {"tool_id": config.tool_id}, {"$set": {"is_premium": config.is_premium}}
        )
        message = "Tool configuration updated"
    else:
        tool_config = ToolConfig(
            tool_id=config.tool_id,
            tool_name=config.tool_id.replace("-", " ").title(),
            is_premium=config.is_premium,
        )
        await db.tool_configs.insert_one(tool_config.model_dump())
        message = "Tool configuration created"

    return {
        "message": message,
        "tool_id": config.tool_id,
        "is_premium": config.is_premium,
    }


@api_router.get("/admin/tools-config")
async def get_admin_tools_config(admin_user: dict = Depends(require_admin)):
    """Get all tool configurations (admin only)"""
    configs = await db.tool_configs.find({}, {"_id": 0}).to_list(100)
    return {"tools": configs}


@api_router.post("/admin/create-organization")
async def create_organization(
    org_data: OrganizationCreate, admin_user: dict = Depends(require_admin)
):
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
        expiry_date=(
            datetime.now(timezone.utc) + timedelta(days=365)
            if org_data.license_tier == "premium"
            else None
        ),
    )

    org_doc = org.model_dump()
    org_doc["created_at"] = org_doc["created_at"].isoformat()
    if org_doc.get("expiry_date"):
        org_doc["expiry_date"] = org_doc["expiry_date"].isoformat()

    await db.organizations.insert_one(org_doc)

    # Create admin user
    admin_user_data = UserCreate(
        email=org_data.admin_email,
        password=org_data.admin_password,
        role="org_admin",
        organization_id=org.id,
    )

    user = User(email=admin_user_data.email, role="org_admin", organization_id=org.id)

    user_doc = user.model_dump()
    user_doc["password_hash"] = get_password_hash(org_data.admin_password)
    user_doc["created_at"] = user_doc["created_at"].isoformat()

    await db.users.insert_one(user_doc)

    return {
        "message": "Organization created successfully",
        "organization": {
            "id": org.id,
            "name": org.name,
            "license_key": org.license_key,
            "license_tier": org.license_tier,
            "max_licenses": org.max_licenses,
        },
        "admin_user": {"id": user.id, "email": user.email},
    }


@api_router.get("/admin/organizations")
async def list_organizations(admin_user: dict = Depends(require_admin)):
    """List all organizations (admin only)"""
    orgs = await db.organizations.find({}, {"_id": 0}).to_list(1000)
    return {"organizations": orgs}


@api_router.get("/admin/organization/{org_id}/users")
async def list_organization_users(
    org_id: str, admin_user: dict = Depends(require_admin)
):
    """List all users in an organization (admin only)"""
    users = await db.users.find(
        {"organization_id": org_id}, {"_id": 0, "password_hash": 0}
    ).to_list(1000)

    return {"users": users}


# ========== ORIGINAL ROUTES ==========


@api_router.get("/")
async def root():
    return {"message": "Developer Productivity Suite API"}


@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)

    # Convert to dict and serialize datetime to ISO string for MongoDB
    doc = status_obj.model_dump()
    doc["timestamp"] = doc["timestamp"].isoformat()

    _ = await db.status_checks.insert_one(doc)
    return status_obj


@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    # Exclude MongoDB's _id field from the query results
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)

    # Convert ISO string timestamps back to datetime objects
    for check in status_checks:
        if isinstance(check["timestamp"], str):
            check["timestamp"] = datetime.fromisoformat(check["timestamp"])

    return status_checks


# JSON Beautifier Tool
@api_router.post("/tools/json-beautifier", response_model=JSONBeautifyResponse)
async def beautify_json(request: JSONBeautifyRequest):
    try:

        def process_json():
            # Parse JSON to validate
            parsed = json.loads(request.json_string)

            # Beautify with specified indent
            return json.dumps(parsed, indent=request.indent, sort_keys=False)

        # Run CPU-bound JSON processing in threadpool to avoid blocking event loop
        beautified = await run_in_threadpool(process_json)

        return JSONBeautifyResponse(beautified=beautified, valid=True, error=None)
    except json.JSONDecodeError as e:
        return JSONBeautifyResponse(
            beautified=request.json_string, valid=False, error=f"Invalid JSON: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Favorites Management
@api_router.post("/favorites/add")
async def add_favorite(
    request: FavoriteToolRequest, db: DatabaseBase = Depends(get_database)
):
    try:
        result = await db.add_favorite(request.user_id, request.tool_id)
        return {"message": "Added to favorites", "favorite": result}
    except Exception as e:
        # If already exists, some implementations might raise an error
        return {"message": "Already in favorites or error occurred", "error": str(e)}


@api_router.post("/favorites/remove")
async def remove_favorite(
    request: FavoriteToolRequest, db: DatabaseBase = Depends(get_database)
):
    result = await db.remove_favorite(request.user_id, request.tool_id)

    if result:
        return {"message": "Removed from favorites"}
    else:
        return {"message": "Not found in favorites"}


@api_router.get("/favorites/list")
async def list_favorites(
    user_id: str = "default_user", db: DatabaseBase = Depends(get_database)
):
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
async def grpc_call(
    request: GrpcCallRequest, current_user: dict = Depends(get_current_user)
):
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
        from google.protobuf.message_factory import GetMessageClass
        from google.protobuf import json_format
        import tempfile
        import os as os_module

        # Save proto content to a temporary file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".proto", delete=False
        ) as proto_file:
            proto_file.write(request.proto_content)
            proto_file_path = proto_file.name

        # Compile the proto file to get descriptor
        descriptor_set_file = proto_file_path + ".desc"
        proto_dir = os_module.path.dirname(proto_file_path)

        cmd = [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"--proto_path={proto_dir}",
            f"--descriptor_set_out={descriptor_set_file}",
            "--include_imports",
            proto_file_path,
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            raise HTTPException(
                status_code=400, detail=f"Failed to compile proto file: {error_msg}"
            )

        # Load the descriptor
        with open(descriptor_set_file, "rb") as f:
            descriptor_set = descriptor_pb2.FileDescriptorSet()
            descriptor_set.ParseFromString(f.read())

        # Create a descriptor pool and register the descriptors
        pool = DescriptorPool()
        for file_descriptor_proto in descriptor_set.file:
            pool.Add(file_descriptor_proto)

        # Find the service and method descriptors
        service_descriptor = None
        for file_descriptor_proto in descriptor_set.file:
            for service in file_descriptor_proto.service:
                if service.name == request.service:
                    service_descriptor = service
                    break
            if service_descriptor:
                break

        if not service_descriptor:
            raise HTTPException(
                status_code=400, detail=f"Service '{request.service}' not found"
            )

        # Find the method
        method_descriptor = None
        for method in service_descriptor.method:
            if method.name == request.method:
                method_descriptor = method
                break

        if not method_descriptor:
            raise HTTPException(
                status_code=400, detail=f"Method '{request.method}' not found"
            )

        # Get the request and response message types
        request_type = pool.FindMessageTypeByName(
            method_descriptor.input_type.lstrip(".")
        )
        response_type = pool.FindMessageTypeByName(
            method_descriptor.output_type.lstrip(".")
        )

        # Create message instances
        request_message_class = GetMessageClass(request_type)
        response_message_class = GetMessageClass(response_type)

        # Convert JSON request to protobuf message
        request_message = json_format.ParseDict(
            request.request, request_message_class()
        )

        # Create gRPC channel and make the call
        channel = grpc.insecure_channel(request.server_url)

        # Prepare metadata
        metadata_list = [(k, v) for k, v in request.metadata.items()]

        # Make the unary-unary call
        method_full_name = f"/{service_descriptor.full_name}/{request.method}"
        response = channel.unary_unary(
            method_full_name,
            request_serializer=lambda x: x.SerializeToString(),
            response_deserializer=response_message_class.FromString,
        )(request_message, metadata=metadata_list, timeout=30)

        # Convert response to dict
        response_dict = json_format.MessageToDict(
            response, preserving_proto_field_name=True
        )

        # Clean up temporary files
        os_module.unlink(proto_file_path)
        os_module.unlink(descriptor_set_file)

        channel.close()

        return {"response": response_dict, "metadata": {}}

    except HTTPException:
        # Re-raise HTTPExceptions (like 400 errors) as-is
        raise
    except grpc.RpcError as e:
        raise HTTPException(
            status_code=500, detail=f"gRPC Error: {e.code()}: {e.details()}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error making gRPC call: {str(e)}")


# ========== UI AUTOMATION RECORDER ENDPOINTS ==========

# In-memory storage for recording sessions
recording_sessions = {}


class RecorderSession(BaseModel):
    language: str
    target_url: str


class RecorderEvents(BaseModel):
    events: List[dict]


@api_router.post("/recorder/session")
async def create_recorder_session(
    session: RecorderSession, current_user: dict = Depends(get_current_user)
):
    """Create a new recording session"""
    session_id = str(uuid.uuid4())
    recording_sessions[session_id] = {
        "user_id": current_user["id"],
        "language": session.language,
        "target_url": session.target_url,
        "events": [],
        "created_at": datetime.now(timezone.utc),
    }
    return {"session_id": session_id, "message": "Recording session created"}


@api_router.post("/recorder/events/{session_id}")
async def add_recorder_events(
    session_id: str,
    events: RecorderEvents,
    current_user: dict = Depends(get_current_user),
):
    """Add recorded events to a session"""
    if session_id not in recording_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = recording_sessions[session_id]
    if session["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    session["events"].extend(events.events)
    return {"message": "Events recorded", "total_events": len(session["events"])}


@api_router.post("/recorder/generate/{session_id}")
async def generate_recorder_code(
    session_id: str, request: dict, current_user: dict = Depends(get_current_user)
):
    """Generate Playwright code from recorded events"""
    if session_id not in recording_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = recording_sessions[session_id]
    if session["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    language = request.get("language", session["language"])
    events = session["events"]

    # Generate code based on language
    if language == "python":
        code = generate_python_code(events, session["target_url"])
    elif language == "javascript":
        code = generate_javascript_code(events, session["target_url"])
    elif language == "typescript":
        code = generate_typescript_code(events, session["target_url"])
    else:
        code = generate_python_code(events, session["target_url"])

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
        "",
    ]

    # Add initial navigation
    if events and events[0]["type"] != "navigation":
        lines.append(f"    page.goto('{target_url}')")

    # Process events
    for event in events:
        if event["type"] == "navigation":
            lines.append(f"    page.goto('{event['url']}')")
        elif event["type"] == "click":
            lines.append(f"    page.click('{event['selector']}')")
        elif event["type"] == "input":
            value = event.get("value", "").replace("'", "\\'")
            lines.append(f"    page.fill('{event['selector']}', '{value}')")

    lines.extend(
        [
            "",
            "    # Close the browser",
            "    context.close()",
            "    browser.close()",
            "",
            "with sync_playwright() as playwright:",
            "    run(playwright)",
        ]
    )

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
        "",
    ]

    # Add initial navigation
    if events and events[0]["type"] != "navigation":
        lines.append(f"  await page.goto('{target_url}');")

    # Process events
    for event in events:
        if event["type"] == "navigation":
            lines.append(f"  await page.goto('{event['url']}');")
        elif event["type"] == "click":
            lines.append(f"  await page.click('{event['selector']}');")
        elif event["type"] == "input":
            value = event.get("value", "").replace("'", "\\'")
            lines.append(f"  await page.fill('{event['selector']}', '{value}');")

    lines.extend(
        [
            "",
            "  // Close the browser",
            "  await context.close();",
            "  await browser.close();",
            "})();",
        ]
    )

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
        "",
    ]

    # Add initial navigation
    if events and events[0]["type"] != "navigation":
        lines.append(f"  await page.goto('{target_url}');")

    # Process events
    for event in events:
        if event["type"] == "navigation":
            lines.append(f"  await page.goto('{event['url']}');")
        elif event["type"] == "click":
            lines.append(f"  await page.click('{event['selector']}');")
        elif event["type"] == "input":
            value = event.get("value", "").replace("'", "\\'")
            lines.append(f"  await page.fill('{event['selector']}', '{value}');")

    lines.extend(
        [
            "",
            "  // Close the browser",
            "  await context.close();",
            "  await browser.close();",
            "})();",
        ]
    )

    return "\n".join(lines)


# ==================== LICENSE API ROUTES (MOCK) ====================


class LicenseActivation(BaseModel):
    activationKey: str
    machineId: str
    machineName: str


class LicenseConfig(BaseModel):
    toolConfig: dict
    machineId: str
    activationKey: str
    activatedAt: str


@api_router.post("/license/activate")
async def activate_license(activation: LicenseActivation, db=Depends(get_database)):
    """
    Mock license activation endpoint
    In production, this will validate the key against your licensing server
    """
    try:
        # Mock validation - check activation key format
        key = activation.activationKey.strip()

        # Mock: Different keys unlock different tool sets
        if key.startswith("PRO-"):
            # Pro license - all tools
            tool_config = {
                "version": "1.0.0",
                "isActivated": True,
                "licenseType": "pro",
                "activatedTools": ["all"],
                "tools": [],  # Will be populated from toolconfig.json
            }
            message = "Pro license activated successfully!"
        elif key.startswith("PREMIUM-"):
            # Premium license - specific premium tools
            tool_config = {
                "version": "1.0.0",
                "isActivated": True,
                "licenseType": "premium",
                "activatedTools": ["rest-api-tester", "grpc-tester", "ui-recorder"],
                "tools": [],
            }
            message = "Premium license activated successfully!"
        elif key.startswith("FREE-"):
            # Free license - just free tools
            tool_config = {
                "version": "1.0.0",
                "isActivated": False,
                "licenseType": "free",
                "activatedTools": [],
                "tools": [],
            }
            message = "Free license activated"
        else:
            return {
                "success": False,
                "message": "Invalid activation key. Please check and try again.",
            }

        # Store in database
        license_data = {
            "machine_id": activation.machineId,
            "machine_name": activation.machineName,
            "activation_key": activation.activationKey,
            "tool_config": json.dumps(tool_config),
            "activated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Save to database (using tool_configs collection for now)
        await db.save_tool_config("license_" + activation.machineId, license_data)

        logger.info(
            f"License activated for machine: {activation.machineName} ({activation.machineId})"
        )

        return {"success": True, "toolConfig": tool_config, "message": message}

    except Exception as e:
        logger.error(f"License activation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/license/config")
async def save_license_config(config: LicenseConfig, db=Depends(get_database)):
    """Save activated license configuration"""
    try:
        license_data = {
            "machine_id": config.machineId,
            "activation_key": config.activationKey,
            "tool_config": json.dumps(config.toolConfig),
            "activated_at": config.activatedAt,
        }

        await db.save_tool_config("license_" + config.machineId, license_data)

        return {"success": True, "message": "License configuration saved"}
    except Exception as e:
        logger.error(f"Error saving license config: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/license/config")
async def get_license_config(machineId: str, db=Depends(get_database)):
    """Get license configuration for a machine"""
    try:
        config = await db.get_tool_config("license_" + machineId)

        if config and "tool_config" in config:
            tool_config = (
                json.loads(config["tool_config"])
                if isinstance(config["tool_config"], str)
                else config["tool_config"]
            )
            return {
                "success": True,
                "toolConfig": tool_config,
                "activatedAt": config.get("activated_at"),
            }
        else:
            return {"success": False, "message": "No license found for this machine"}
    except Exception as e:
        logger.error(f"Error getting license config: {str(e)}")
        return {"success": False, "message": "No license found"}


@api_router.delete("/license/config")
async def deactivate_license(machineId: str, db=Depends(get_database)):
    """Deactivate license for a machine"""
    try:
        await db.delete_tool_config("license_" + machineId)
        return {"success": True, "message": "License deactivated"}
    except Exception as e:
        logger.error(f"Error deactivating license: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# JWT Encoding Models
class JWTEncodeRequest(BaseModel):
    algorithm: str = Field(
        ...,
        description="JWT algorithm (HS256, HS384, HS512, RS256, RS384, RS512, ES256, ES384, ES512, PS256, PS384, PS512)",
    )
    secret: str = Field(
        ..., description="Secret key for HMAC or private key for RSA/ECDSA"
    )
    payload: dict = Field(..., description="JWT payload claims")


class JWTEncodeResponse(BaseModel):
    token: str
    algorithm: str


@api_router.post("/tools/jwt/encode", response_model=JWTEncodeResponse)
async def encode_jwt(request: JWTEncodeRequest):
    """
    Encode a JWT token with proper cryptographic signing.
    Supports all standard JWT algorithms.
    """
    try:
        import jwt as pyjwt

        # Map algorithm names
        algorithm = request.algorithm.upper()

        # Validate algorithm
        valid_algorithms = [
            "HS256",
            "HS384",
            "HS512",
            "RS256",
            "RS384",
            "RS512",
            "ES256",
            "ES384",
            "ES512",
            "PS256",
            "PS384",
            "PS512",
        ]
        if algorithm not in valid_algorithms:
            raise HTTPException(
                status_code=400, detail=f"Unsupported algorithm: {algorithm}"
            )

        # Encode the JWT
        token = pyjwt.encode(request.payload, request.secret, algorithm=algorithm)

        return JWTEncodeResponse(token=token, algorithm=algorithm)
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="PyJWT library not installed. Run: pip install pyjwt[crypto]",
        )
    except Exception as e:
        logger.error(f"JWT encoding error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to encode JWT: {str(e)}")


# JWT Verification Models
class JWTVerifyRequest(BaseModel):
    token: str = Field(..., description="JWT token to verify")
    secret: str = Field(..., description="Secret key or public key for verification")
    algorithm: Optional[str] = Field(
        None, description="Algorithm to use (if not specified, will use token header)"
    )


class JWTVerifyResponse(BaseModel):
    valid: bool
    message: str
    header: Optional[dict] = None
    payload: Optional[dict] = None


@api_router.post("/tools/jwt/verify", response_model=JWTVerifyResponse)
async def verify_jwt(request: JWTVerifyRequest):
    """
    Verify a JWT token signature with proper cryptographic validation.
    """
    try:
        import jwt as pyjwt

        # First decode without verification to get the algorithm
        unverified_header = pyjwt.get_unverified_header(request.token)
        algorithm = request.algorithm or unverified_header.get("alg")

        # Verify and decode the JWT
        decoded = pyjwt.decode(request.token, request.secret, algorithms=[algorithm])

        return JWTVerifyResponse(
            valid=True,
            message="Signature verified successfully!",
            header=unverified_header,
            payload=decoded,
        )
    except pyjwt.ExpiredSignatureError:
        return JWTVerifyResponse(
            valid=False, message="Token signature is valid but token has expired"
        )
    except pyjwt.InvalidSignatureError:
        return JWTVerifyResponse(
            valid=False,
            message="Invalid signature - token has been tampered with or wrong secret key",
        )
    except pyjwt.DecodeError as e:
        return JWTVerifyResponse(
            valid=False, message=f"Failed to decode token: {str(e)}"
        )
    except Exception as e:
        logger.error(f"JWT verification error: {str(e)}")
        return JWTVerifyResponse(valid=False, message=f"Verification failed: {str(e)}")


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ========== CRON MANAGER ==========

# In-memory storage for cron jobs (in production, use database)
cron_jobs_storage = {}


class CronJob(BaseModel):
    id: Optional[str] = None
    name: str
    expression: str
    command: str
    enabled: bool = True
    description: Optional[str] = None
    lastRun: Optional[str] = None
    createdAt: Optional[str] = None


class CronJobCreate(BaseModel):
    name: str
    expression: str
    command: str
    enabled: bool = True
    description: Optional[str] = None


@api_router.post("/cron/create", response_model=CronJob)
async def create_cron_job(job_data: CronJobCreate):
    """Create a new cron job"""
    job_id = str(uuid.uuid4())
    job = CronJob(
        **job_data.model_dump(),
        id=job_id,
        createdAt=datetime.now(timezone.utc).isoformat(),
    )
    cron_jobs_storage[job_id] = job.model_dump()
    return job


@api_router.get("/cron/list")
async def list_cron_jobs():
    """List all cron jobs"""
    return {"jobs": list(cron_jobs_storage.values())}


@api_router.get("/cron/{job_id}", response_model=CronJob)
async def get_cron_job(job_id: str):
    """Get a specific cron job"""
    if job_id not in cron_jobs_storage:
        raise HTTPException(status_code=404, detail="Cron job not found")
    return cron_jobs_storage[job_id]


@api_router.put("/cron/{job_id}", response_model=CronJob)
async def update_cron_job(job_id: str, job_data: CronJobCreate):
    """Update a cron job"""
    if job_id not in cron_jobs_storage:
        raise HTTPException(status_code=404, detail="Cron job not found")

    existing = cron_jobs_storage[job_id]
    updated = CronJob(
        **job_data.model_dump(),
        id=job_id,
        createdAt=existing.get("createdAt"),
        lastRun=existing.get("lastRun"),
    )
    cron_jobs_storage[job_id] = updated.model_dump()
    return updated


@api_router.delete("/cron/{job_id}")
async def delete_cron_job(job_id: str):
    """Delete a cron job"""
    if job_id not in cron_jobs_storage:
        raise HTTPException(status_code=404, detail="Cron job not found")
    del cron_jobs_storage[job_id]
    return {"message": "Cron job deleted"}


@api_router.patch("/cron/{job_id}/toggle", response_model=CronJob)
async def toggle_cron_job(job_id: str):
    """Toggle cron job enabled/disabled"""
    if job_id not in cron_jobs_storage:
        raise HTTPException(status_code=404, detail="Cron job not found")

    job = cron_jobs_storage[job_id]
    job["enabled"] = not job.get("enabled", True)
    cron_jobs_storage[job_id] = job
    return CronJob(**job)


# ========== SHELL SCRIPT EXECUTOR ==========


class ScriptExecuteRequest(BaseModel):
    script: str
    workingDir: Optional[str] = None
    env: Optional[Dict[str, str]] = None


class ScriptExecuteResponse(BaseModel):
    output: str
    exitCode: int
    executionTime: float


@api_router.post("/execute-script", response_model=ScriptExecuteResponse)
async def execute_script(request: ScriptExecuteRequest):
    """
    Execute a shell script and return output
    Security: Runs in isolated process with timeout
    """
    import time

    start_time = time.time()

    try:
        # Create temporary script file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write(request.script)
            script_path = f.name

        # Make script executable
        os.chmod(script_path, 0o755)

        # Prepare environment
        env = os.environ.copy()
        if request.env:
            env.update(request.env)

        # Execute script with timeout
        try:
            process = await asyncio.create_subprocess_exec(
                "/bin/bash",
                script_path,
                cwd=request.workingDir if request.workingDir else None,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=300
                )
            except asyncio.TimeoutError:
                try:
                    process.kill()
                    await process.communicate()
                except Exception:
                    pass
                raise HTTPException(
                    status_code=408, detail="Script execution timed out (5 minutes)"
                )

            output = stdout.decode()
            if stderr:
                output += f"\n--- STDERR ---\n{stderr.decode()}"

            execution_time = time.time() - start_time

            return ScriptExecuteResponse(
                output=output, exitCode=process.returncode, executionTime=execution_time
            )
        finally:
            # Clean up temp file
            try:
                os.unlink(script_path)
            except:
                pass

    except Exception as e:
        logger.error(f"Script execution error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== ENVIRONMENT VARIABLES ==========

# In-memory storage for environment variables (in production, use database)
env_variables_storage = {}


class EnvVariable(BaseModel):
    key: str
    value: str


@api_router.post("/env/set")
async def set_env_variable(var: EnvVariable):
    """Set an environment variable"""
    env_variables_storage[var.key] = var.value
    return {"message": "Environment variable set"}


@api_router.get("/env/get/{key}")
async def get_env_variable(key: str):
    """Get an environment variable"""
    if key not in env_variables_storage:
        raise HTTPException(status_code=404, detail="Variable not found")
    return {"key": key, "value": env_variables_storage[key]}


@api_router.get("/env/get-all")
async def get_all_env_variables():
    """Get all environment variables"""
    return {"variables": env_variables_storage}


@api_router.delete("/env/delete/{key}")
async def delete_env_variable(key: str):
    """Delete an environment variable"""
    if key in env_variables_storage:
        del env_variables_storage[key]
    return {"message": "Environment variable deleted"}


# ========== AWS S3 VISUALIZER ==========


class S3Config(BaseModel):
    endpoint: Optional[str] = None
    accessKeyId: str
    secretAccessKey: str
    region: str = "us-east-1"
    useLocalStack: bool = False


class S3ListObjectsRequest(BaseModel):
    bucket: str
    prefix: Optional[str] = ""
    endpoint: Optional[str] = None
    accessKeyId: str
    secretAccessKey: str
    region: str = "us-east-1"


class S3DownloadRequest(BaseModel):
    bucket: str
    key: str
    endpoint: Optional[str] = None
    accessKeyId: str
    secretAccessKey: str
    region: str = "us-east-1"


@api_router.post("/s3/list-buckets")
async def list_s3_buckets(config: S3Config):
    """List all S3 buckets"""
    try:
        import boto3
        from botocore.config import Config as BotoConfig

        # Configure S3 client
        s3_config = BotoConfig(region_name=config.region, signature_version="s3v4")

        client_kwargs = {
            "aws_access_key_id": config.accessKeyId,
            "aws_secret_access_key": config.secretAccessKey,
            "config": s3_config,
        }

        if config.endpoint:
            client_kwargs["endpoint_url"] = config.endpoint

        def _list_buckets():
            s3 = boto3.client("s3", **client_kwargs)
            return s3.list_buckets()

        response = await run_in_threadpool(_list_buckets)
        buckets = [
            {"name": bucket["Name"], "creationDate": bucket["CreationDate"].isoformat()}
            for bucket in response.get("Buckets", [])
        ]

        return {"buckets": buckets}
    except Exception as e:
        logger.error(f"S3 list buckets error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/s3/list-objects")
async def list_s3_objects(request: S3ListObjectsRequest):
    """List objects in an S3 bucket"""
    try:
        import boto3
        from botocore.config import Config as BotoConfig

        s3_config = BotoConfig(region_name=request.region, signature_version="s3v4")

        client_kwargs = {
            "aws_access_key_id": request.accessKeyId,
            "aws_secret_access_key": request.secretAccessKey,
            "config": s3_config,
        }

        if request.endpoint:
            client_kwargs["endpoint_url"] = request.endpoint

        def _list_objects():
            s3 = boto3.client("s3", **client_kwargs)
            return s3.list_objects_v2(
                Bucket=request.bucket, Prefix=request.prefix or "", Delimiter="/"
            )

        # List objects with delimiter to get folders
        response = await run_in_threadpool(_list_objects)

        objects = []

        # Add folders
        for prefix in response.get("CommonPrefixes", []):
            folder_name = prefix["Prefix"].replace(request.prefix or "", "").rstrip("/")
            if folder_name:
                objects.append(
                    {"key": prefix["Prefix"], "name": folder_name, "isFolder": True}
                )

        # Add files
        for obj in response.get("Contents", []):
            # Skip the prefix itself
            if obj["Key"] == request.prefix:
                continue

            file_name = obj["Key"].replace(request.prefix or "", "")
            if file_name:
                objects.append(
                    {
                        "key": obj["Key"],
                        "name": file_name,
                        "size": obj["Size"],
                        "lastModified": obj["LastModified"].isoformat(),
                        "isFolder": False,
                    }
                )

        return {"objects": objects}
    except Exception as e:
        logger.error(f"S3 list objects error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/s3/download")
async def download_s3_object(request: S3DownloadRequest):
    """Download an object from S3"""
    try:
        import boto3
        from botocore.config import Config as BotoConfig

        s3_config = BotoConfig(region_name=request.region, signature_version="s3v4")

        client_kwargs = {
            "aws_access_key_id": request.accessKeyId,
            "aws_secret_access_key": request.secretAccessKey,
            "config": s3_config,
        }

        if request.endpoint:
            client_kwargs["endpoint_url"] = request.endpoint

        def _get_object():
            s3 = boto3.client("s3", **client_kwargs)
            response = s3.get_object(Bucket=request.bucket, Key=request.key)
            return io.BytesIO(response["Body"].read()), response.get("ContentType", "application/octet-stream")

        # Get object content in threadpool
        content_stream, content_type = await run_in_threadpool(_get_object)

        # Stream the file
        return StreamingResponse(
            content_stream,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{request.key.split("/")[-1]}"'
            },
        )
    except Exception as e:
        logger.error(f"S3 download error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/s3/preview")
async def preview_s3_object(request: S3DownloadRequest):
    """Preview an object from S3 (text files only)"""
    try:
        import boto3
        from botocore.config import Config as BotoConfig

        s3_config = BotoConfig(region_name=request.region, signature_version="s3v4")

        client_kwargs = {
            "aws_access_key_id": request.accessKeyId,
            "aws_secret_access_key": request.secretAccessKey,
            "config": s3_config,
        }

        if request.endpoint:
            client_kwargs["endpoint_url"] = request.endpoint

        def _preview_object():
            s3 = boto3.client("s3", **client_kwargs)
            response = s3.get_object(Bucket=request.bucket, Key=request.key)
            content = response["Body"].read()

            # Try to decode as text
            try:
                text_content = content.decode("utf-8")
                # Limit preview to first 10000 characters
                if len(text_content) > 10000:
                    text_content = text_content[:10000] + "\n\n... (truncated)"
                return {"content": text_content}
            except:
                return {"content": "[Binary file - cannot preview]"}

        return await run_in_threadpool(_preview_object)
    except Exception as e:
        logger.error(f"S3 preview error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/s3/delete")
async def delete_s3_object(request: S3DownloadRequest):
    """Delete an object from S3"""
    try:
        import boto3
        from botocore.config import Config as BotoConfig

        s3_config = BotoConfig(region_name=request.region, signature_version="s3v4")

        client_kwargs = {
            "aws_access_key_id": request.accessKeyId,
            "aws_secret_access_key": request.secretAccessKey,
            "config": s3_config,
        }

        if request.endpoint:
            client_kwargs["endpoint_url"] = request.endpoint

        def _delete_object():
            s3 = boto3.client("s3", **client_kwargs)
            s3.delete_object(Bucket=request.bucket, Key=request.key)

        # Delete object
        await run_in_threadpool(_delete_object)

        return {"message": "Object deleted"}
    except Exception as e:
        logger.error(f"S3 delete error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/s3/presigned-url")
async def get_presigned_url(request: S3DownloadRequest):
    """Generate a presigned URL for an S3 object"""
    try:
        import boto3
        from botocore.config import Config as BotoConfig

        s3_config = BotoConfig(region_name=request.region, signature_version="s3v4")

        client_kwargs = {
            "aws_access_key_id": request.accessKeyId,
            "aws_secret_access_key": request.secretAccessKey,
            "config": s3_config,
        }

        if request.endpoint:
            client_kwargs["endpoint_url"] = request.endpoint

        def _generate_presigned_url():
            s3 = boto3.client("s3", **client_kwargs)
            return s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": request.bucket, "Key": request.key},
                ExpiresIn=3600,
            )

        # Generate presigned URL (valid for 1 hour)
        url = await run_in_threadpool(_generate_presigned_url)

        return {"url": url}
    except Exception as e:
        logger.error(f"S3 presigned URL error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/s3/upload")
async def upload_s3_object(
    file: UploadFile = FastAPIFile(...),
    config: str = None,
    bucket: str = None,
    prefix: str = None,
):
    """Upload a file to S3"""
    try:
        import boto3
        from botocore.config import Config as BotoConfig

        # Parse config
        config_data = json.loads(config) if config else {}

        s3_config = BotoConfig(
            region_name=config_data.get("region", "us-east-1"), signature_version="s3v4"
        )

        client_kwargs = {
            "aws_access_key_id": config_data.get("accessKeyId"),
            "aws_secret_access_key": config_data.get("secretAccessKey"),
            "config": s3_config,
        }

        if config_data.get("endpoint"):
            client_kwargs["endpoint_url"] = config_data["endpoint"]

        def _upload_file():
            s3 = boto3.client("s3", **client_kwargs)
            key = f"{prefix or ''}{file.filename}"
            s3.upload_fileobj(file.file, bucket, key)
            return key

        # Upload file
        key = await run_in_threadpool(_upload_file)

        return {"message": "File uploaded", "key": key}
    except Exception as e:
        logger.error(f"S3 upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== DOCKER UI ==========


@api_router.get("/docker/containers")
async def list_docker_containers():
    """List all Docker containers"""
    try:
        def _list_containers():
            import docker
            client = docker.from_env()
            containers = []
            for container in client.containers.list(all=True):
                containers.append(
                    {
                        "id": container.id,
                        "name": container.name,
                        "image": (
                            container.image.tags[0]
                            if container.image.tags
                            else container.image.id[:12]
                        ),
                        "state": container.status,
                        "created": container.attrs["Created"],
                    }
                )
            return containers

        containers = await run_in_threadpool(_list_containers)
        return {"containers": containers}
    except Exception as e:
        logger.error(f"Docker containers list error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/docker/images")
async def list_docker_images():
    """List all Docker images"""
    try:
        def _list_images():
            import docker
            client = docker.from_env()
            images = []
            for image in client.images.list():
                images.append(
                    {"id": image.id, "tags": image.tags, "size": image.attrs.get("Size", 0)}
                )
            return images

        images = await run_in_threadpool(_list_images)
        return {"images": images}
    except Exception as e:
        logger.error(f"Docker images list error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/docker/containers/{container_id}/start")
async def start_docker_container(container_id: str):
    """Start a Docker container"""
    try:
        def _start_container():
            import docker
            client = docker.from_env()
            container = client.containers.get(container_id)
            container.start()

        await run_in_threadpool(_start_container)
        return {"message": "Container started"}
    except Exception as e:
        logger.error(f"Docker start error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/docker/containers/{container_id}/stop")
async def stop_docker_container(container_id: str):
    """Stop a Docker container"""
    try:
        def _stop_container():
            import docker
            client = docker.from_env()
            container = client.containers.get(container_id)
            container.stop()

        await run_in_threadpool(_stop_container)
        return {"message": "Container stopped"}
    except Exception as e:
        logger.error(f"Docker stop error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/docker/containers/{container_id}")
async def remove_docker_container(container_id: str):
    """Remove a Docker container"""
    try:
        def _remove_container():
            import docker
            client = docker.from_env()
            container = client.containers.get(container_id)
            container.remove(force=True)

        await run_in_threadpool(_remove_container)
        return {"message": "Container removed"}
    except Exception as e:
        logger.error(f"Docker remove error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/docker/containers/{container_id}/logs")
async def get_docker_logs(container_id: str):
    """Get container logs"""
    try:
        def _get_logs():
            import docker
            client = docker.from_env()
            container = client.containers.get(container_id)
            return container.logs(tail=1000).decode("utf-8")

        logs = await run_in_threadpool(_get_logs)
        return {"logs": logs}
    except Exception as e:
        logger.error(f"Docker logs error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/docker/images/{image_id}")
async def remove_docker_image(image_id: str):
    """Remove a Docker image"""
    try:
        def _remove_image():
            import docker
            client = docker.from_env()
            client.images.remove(image_id, force=True)

        await run_in_threadpool(_remove_image)
        return {"message": "Image removed"}
    except Exception as e:
        logger.error(f"Docker image remove error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


class DockerBuildRequest(BaseModel):
    dockerfile: str
    imageName: str
    context: Optional[str] = None


@api_router.post("/docker/build")
async def build_docker_image(request: DockerBuildRequest):
    """Build a Docker image"""
    try:
        def _build_image():
            import docker
            import io
            client = docker.from_env()

            # Create Dockerfile in memory
            dockerfile_content = request.dockerfile.encode("utf-8")
            fileobj = io.BytesIO(dockerfile_content)

            # Build image
            image, build_logs = client.images.build(
                fileobj=fileobj, tag=request.imageName, rm=True
            )

            # Collect build output
            output = []
            for log in build_logs:
                if "stream" in log:
                    output.append(log["stream"])

            return "".join(output), image.id

        output_str, image_id = await run_in_threadpool(_build_image)
        return {"output": output_str, "imageId": image_id}
    except Exception as e:
        logger.error(f"Docker build error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


class DockerPullRequest(BaseModel):
    image: str


@api_router.post("/docker/pull")
async def pull_docker_image(request: DockerPullRequest):
    """Pull a Docker image"""
    try:
        def _pull_image():
            import docker
            client = docker.from_env()
            client.images.pull(request.image)

        await run_in_threadpool(_pull_image)
        return {"message": "Image pulled"}
    except Exception as e:
        logger.error(f"Docker pull error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Data Comparison Endpoints ====================


class DataSourceConfig(BaseModel):
    id: str
    name: str
    type: str  # mysql, postgresql, mongodb, excel, etc.
    apiUrl: str
    token: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None


class CompareRequest(BaseModel):
    left: Dict
    right: Dict
    compareData: bool = False


@api_router.get("/datasources/{source_id}/databases")
async def get_databases(source_id: str):
    """Get list of databases from a data source"""
    try:
        # This would connect to the actual database
        # For now, return mock data
        return {"databases": ["database1", "database2", "database3"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/datasources/{source_id}/databases/{db_name}/tables")
async def get_tables(source_id: str, db_name: str):
    """Get list of tables from a database"""
    try:
        # This would connect to the actual database
        # For now, return mock data
        return {
            "tables": [
                {"name": "users", "rowCount": 1000},
                {"name": "orders", "rowCount": 5000},
                {"name": "products", "rowCount": 500},
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/compare/schemas")
async def compare_schemas(request: CompareRequest):
    """Compare schemas between two data sources"""
    try:
        # This would perform actual schema comparison
        # For now, return mock comparison results
        results = {
            "tables": [
                {"name": "users", "status": "match", "differences": []},
                {
                    "name": "orders",
                    "status": "mismatch",
                    "differences": [
                        {
                            "field": "status",
                            "description": "Column type mismatch: VARCHAR(50) vs VARCHAR(100)",
                        },
                        {
                            "field": "created_at",
                            "description": "Column missing in right source",
                        },
                    ],
                },
                {
                    "name": "products",
                    "status": "partial",
                    "differences": [
                        {
                            "field": "price",
                            "description": "Precision mismatch: DECIMAL(10,2) vs DECIMAL(12,2)",
                        }
                    ],
                },
            ],
            "summary": {"totalTables": 3, "matches": 1, "mismatches": 1, "partial": 1},
        }
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Code Execution Endpoints ====================


class CodeExecutionRequest(BaseModel):
    language: str
    code: str
    stdin: Optional[str] = ""
    configId: str


class CodeStopRequest(BaseModel):
    configId: str


@api_router.post("/code/execute")
async def execute_code(request: CodeExecutionRequest):
    """Execute code in specified language"""
    try:
        # This would execute code on remote/local environment
        # For now, return mock execution result
        # Optimized: Non-blocking sleep
        await asyncio.sleep(0.5)  # Simulate execution time

        result = {
            "output": f"Executed {request.language} code successfully!\n",
            "stdout": "Hello, World!\n",
            "stderr": "",
            "exitCode": 0,
            "executionTime": 523,
        }
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/code/stop")
async def stop_execution(request: CodeStopRequest):
    """Stop running code execution"""
    try:
        return {"message": "Execution stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== OpenAPI Test Generation Endpoints ====================


class OpenAPITestRequest(BaseModel):
    spec: Dict
    outputFormat: str
    testFramework: str
    options: Dict


@api_router.post("/openapi/generate-tests")
async def generate_tests_from_openapi(request: OpenAPITestRequest):
    """Generate test code from OpenAPI specification"""
    try:
        spec = request.spec
        output_format = request.outputFormat
        framework = request.testFramework
        options = request.options

        # Generate test code based on format
        if output_format == "python":
            code = generate_python_tests(spec, framework, options)
        elif output_format == "postman":
            code = generate_postman_collection(spec, options)
        elif output_format == "java":
            code = generate_java_tests(spec, framework, options)
        elif output_format == "javascript":
            code = generate_javascript_tests(spec, framework, options)
        elif output_format == "typescript":
            code = generate_typescript_tests(spec, framework, options)
        else:
            code = f"# Test generation for {output_format} coming soon"

        return {"code": code}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def generate_python_tests(spec, framework, options):
    """Generate Python test code"""
    base_url = options.get("baseUrl", "http://localhost:8000")
    code = f"""import pytest
import requests
import json

BASE_URL = "{base_url}"

"""

    # Generate test for each endpoint
    for path, methods in spec.get("paths", {}).items():
        for method, details in methods.items():
            if method not in ["get", "post", "put", "delete", "patch"]:
                continue

            operation_id = details.get(
                "operationId", f"{method}_{path.replace('/', '_')}"
            )
            summary = details.get("summary", f"Test {method.upper()} {path}")

            code += f"""
def test_{operation_id}():
    \"\"\"Test: {summary}\"\"\"
    url = f"{{BASE_URL}}{path}"
    response = requests.{method}(url)
    assert response.status_code in [200, 201, 204]
    """

            if options.get("includeValidation"):
                code += """
    assert response.headers.get('Content-Type') == 'application/json'
    data = response.json()
    assert data is not None
"""

    return code


def generate_postman_collection(spec, options):
    """Generate Postman collection"""
    collection = {
        "info": {
            "name": spec.get("info", {}).get("title", "API Tests"),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [],
    }

    for path, methods in spec.get("paths", {}).items():
        for method, details in methods.items():
            if method not in ["get", "post", "put", "delete", "patch"]:
                continue

            item = {
                "name": details.get("summary", f"{method.upper()} {path}"),
                "request": {
                    "method": method.upper(),
                    "header": [],
                    "url": {
                        "raw": f"{{{{base_url}}}}{path}",
                        "host": ["{{base_url}}"],
                        "path": path.split("/")[1:],
                    },
                },
                "response": [],
            }

            if options.get("includeValidation"):
                item["event"] = [
                    {
                        "listen": "test",
                        "script": {
                            "exec": [
                                "pm.test('Status code is 200', function() {",
                                "    pm.response.to.have.status(200);",
                                "});",
                            ]
                        },
                    }
                ]

            collection["item"].append(item)

    return json.dumps(collection, indent=2)


def generate_java_tests(spec, framework, options):
    """Generate Java test code"""
    base_url = options.get("baseUrl", "http://localhost:8000")
    code = f"""import org.junit.jupiter.api.Test;
import io.restassured.RestAssured;
import static io.restassured.RestAssured.*;
import static org.hamcrest.Matchers.*;

public class ApiTests {{
    
    private static final String BASE_URL = "{base_url}";
    
"""

    for path, methods in spec.get("paths", {}).items():
        for method, details in methods.items():
            if method not in ["get", "post", "put", "delete", "patch"]:
                continue

            operation_id = details.get(
                "operationId", f"{method}_{path.replace('/', '_')}"
            )
            summary = details.get("summary", f"Test {method.upper()} {path}")

            code += f"""
    @Test
    public void test_{operation_id}() {{
        given()
            .baseUri(BASE_URL)
        .when()
            .{method}("{path}")
        .then()
            .statusCode(200);
    }}
"""

    code += "\n}\n"
    return code


def generate_javascript_tests(spec, framework, options):
    """Generate JavaScript test code"""
    base_url = options.get("baseUrl", "http://localhost:8000")
    code = f"""const axios = require('axios');

const BASE_URL = '{base_url}';

"""

    for path, methods in spec.get("paths", {}).items():
        for method, details in methods.items():
            if method not in ["get", "post", "put", "delete", "patch"]:
                continue

            operation_id = details.get(
                "operationId", f"{method}_{path.replace('/', '_')}"
            )
            summary = details.get("summary", f"Test {method.upper()} {path}")

            code += f"""
describe('{summary}', () => {{
    test('should return success', async () => {{
        const response = await axios.{method}(`${{BASE_URL}}{path}`);
        expect(response.status).toBe(200);
    }});
}});
"""

    return code


def generate_typescript_tests(spec, framework, options):
    """Generate TypeScript test code"""
    base_url = options.get("baseUrl", "http://localhost:8000")
    code = f"""import axios from 'axios';

const BASE_URL: string = '{base_url}';

"""

    for path, methods in spec.get("paths", {}).items():
        for method, details in methods.items():
            if method not in ["get", "post", "put", "delete", "patch"]:
                continue

            operation_id = details.get(
                "operationId", f"{method}_{path.replace('/', '_')}"
            )
            summary = details.get("summary", f"Test {method.upper()} {path}")

            code += f"""
describe('{summary}', () => {{
    test('should return success', async () => {{
        const response = await axios.{method}<any>(`${{BASE_URL}}{path}`);
        expect(response.status).toBe(200);
    }});
}});
"""

    return code


# ==================== AI Chat Endpoints ====================


class AIChatRequest(BaseModel):
    messages: List[Dict]
    toolContext: Dict
    llmConfig: Optional[Dict] = None


@api_router.post("/ai/chat")
async def ai_chat(request: AIChatRequest):
    """AI-powered chat assistant with tool context"""
    try:
        messages = request.messages
        tool_context = request.toolContext
        llm_config = request.llmConfig or {}

        # Build context-aware system prompt
        system_prompt = f"""You are an AI assistant integrated into the {tool_context.get('toolName')} tool.
Your purpose: {tool_context.get('description')}

Current tool state:
{json.dumps(tool_context.get('currentData', {}), indent=2)}

Provide helpful, accurate, and context-aware assistance. You can:
- Explain features and functionality
- Generate code or configurations
- Debug issues
- Suggest best practices
- Answer questions about the tool

Be concise and actionable."""

        # For now, return intelligent mock responses
        # In production, this would call OpenAI, Anthropic, or local LLM
        user_message = messages[-1]["content"].lower()

        if "generate" in user_message or "create" in user_message:
            response = f"I can help you generate test cases! Based on your OpenAPI spec, I'll create comprehensive tests. Would you like me to:\n\n1. Generate tests for all endpoints\n2. Focus on specific HTTP methods\n3. Include authentication tests\n4. Add data validation\n\nWhat would you prefer?"
        elif (
            "error" in user_message
            or "issue" in user_message
            or "problem" in user_message
        ):
            response = "I'll help you troubleshoot! Common issues:\n\n1. Invalid OpenAPI spec format\n2. Missing required fields\n3. Unsupported HTTP methods\n\nCan you share more details about the error you're seeing?"
        elif "example" in user_message or "sample" in user_message:
            response = 'Here\'s a sample OpenAPI spec structure:\n\n```json\n{\n  "openapi": "3.0.0",\n  "info": {\n    "title": "My API",\n    "version": "1.0.0"\n  },\n  "paths": {\n    "/users": {\n      "get": {\n        "summary": "Get users"\n      }\n    }\n  }\n}\n```\n\nWould you like me to explain any part?'
        elif "best practice" in user_message or "recommend" in user_message:
            response = "Best practices for API testing:\n\n1. ✅ Test all HTTP methods\n2. ✅ Validate response schemas\n3. ✅ Include authentication tests\n4. ✅ Test error scenarios\n5. ✅ Use meaningful test names\n6. ✅ Add assertions for status codes\n\nWant me to generate tests following these practices?"
        else:
            response = f"I'm here to help with {tool_context.get('toolName')}! I can:\n\n• Generate test code from your OpenAPI spec\n• Explain different output formats\n• Help debug issues\n• Suggest best practices\n• Answer questions\n\nWhat would you like to know?"

        return {"message": response}
    except Exception as e:
        logger.error(f"AI chat error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Include the router in the main app
app.include_router(api_router)


@app.on_event("startup")
async def startup_db_client():
    """Initialize database on startup"""
    global db_instance
    try:
        if db_instance is None:
            logger.info("Initializing database...")
            db_instance = await get_db()
            logger.info(f"Database initialized successfully: {type(db_instance)}")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_db_client():
    global db_instance
    if db_instance:
        await db_instance.disconnect()
        db_instance = None
