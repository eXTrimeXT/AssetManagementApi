import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.database.connection import get_db
from app.database.assets.asset import (
    create_asset, get_asset_by_id, get_assets_list,
    get_assets_list_with_permissions, update_asset, delete_asset,
    get_asset_children, get_asset_children_with_permissions
)
from app.schemas.assets.asset import AssetCreate, AssetUpdate, AssetResponse, AssetShortResponse
from app.services.auth.auth_service import require_authorized_user
from app.services.auth.permission_checker import require_permission

logger = logging.getLogger(__name__)
router_assets = APIRouter(prefix="/assets", tags=["Assets"])


@router_assets.post("/", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def create_asset_endpoint(
        data: AssetCreate,
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("assets", "write"))
):
    return await create_asset(db, data, current_user.employee_id)


@router_assets.get("/", response_model=List[AssetShortResponse])
async def get_assets(
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        name: Optional[str] = Query(None),
        inventory_id: Optional[str] = Query(None),
        serial_number: Optional[str] = Query(None),
        asset_status: Optional[str] = Query(None),
        model_id: Optional[int] = Query(None),
        parent_id: Optional[int] = Query(None),
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("assets", "read"))
):
    # Вариант 2: фильтрация списка по правам
    return await get_assets_list_with_permissions(
        db, current_user.employee_id, skip, limit,
        name, inventory_id, serial_number, asset_status, model_id, parent_id
    )


@router_assets.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(
        asset_id: int,
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("assets", "read"))
):
    obj = await get_asset_by_id(db, asset_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Актив не найден")
    return obj


@router_assets.patch("/{asset_id}", response_model=AssetResponse)
async def update_asset_endpoint(
        asset_id: int,
        data: AssetUpdate,
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("assets", "write"))
):
    updated = await update_asset(db, asset_id, data, current_user.employee_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Актив не найден")
    return updated


@router_assets.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset_endpoint(
        asset_id: int,
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("assets", "write"))
):
    success = await delete_asset(db, asset_id)
    if not success:
        raise HTTPException(status_code=404, detail="Актив не найден")


@router_assets.get("/{asset_id}/children", response_model=List[AssetShortResponse])
async def get_asset_children_endpoint(
        asset_id: int,
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("assets", "read"))
):
    # Вариант 3: проверка прав при получении детей
    children = await get_asset_children_with_permissions(db, asset_id, current_user.employee_id)
    return children