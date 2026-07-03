import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.database.connection import get_db
from app.database.assets.asset_type import (
    create_asset_type, get_asset_type_by_id, get_asset_types_list,
    update_asset_type, delete_asset_type
)
from app.schemas.assets.asset_type import AssetTypeCreate, AssetTypeUpdate, AssetTypeResponse
from app.services.auth.auth_service import require_authorized_user
from app.services.auth.permission_checker import require_permission, require_any_permission

logger = logging.getLogger(__name__)
router_asset_types = APIRouter(prefix="/asset-types", tags=["Asset Types"])


@router_asset_types.post("/", response_model=AssetTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_asset_type_endpoint(
        data: AssetTypeCreate,
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_any_permission("write"))
):
    return await create_asset_type(db, data, current_user.employee_id)


@router_asset_types.get("/", response_model=List[AssetTypeResponse])
async def get_asset_types(
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        name: Optional[str] = Query(None),
        en_name: Optional[str] = Query(None),
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("asset_types", "read"))
):
    return await get_asset_types_list(db, skip, limit, name, en_name)


@router_asset_types.get("/{asset_type_id}", response_model=AssetTypeResponse)
async def get_asset_type(
        asset_type_id: int,
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("asset_types", "read"))
):
    obj = await get_asset_type_by_id(db, asset_type_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Тип актива не найден")
    return obj


@router_asset_types.patch("/{asset_type_id}", response_model=AssetTypeResponse)
async def update_asset_type_endpoint(
        asset_type_id: int,
        data: AssetTypeUpdate,
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("asset_types", "write"))
):
    updated = await update_asset_type(db, asset_type_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Тип актива не найден")
    return updated


@router_asset_types.delete("/{asset_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset_type_endpoint(
        asset_type_id: int,
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("asset_types", "write"))
):
    success = await delete_asset_type(db, asset_type_id)
    if not success:
        raise HTTPException(status_code=404, detail="Тип актива не найден")