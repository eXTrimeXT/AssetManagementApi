import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.database.connection import get_db
from app.database.assets.asset_class import (
    create_asset_class, get_asset_class_by_id, get_asset_classes_list,
    update_asset_class, delete_asset_class
)
from app.schemas.assets.asset_class import AssetClassCreate, AssetClassUpdate, AssetClassResponse
from app.services.auth.auth_service import require_authorized_user
from app.services.auth.permission_checker import require_permission

logger = logging.getLogger(__name__)
router_asset_classes = APIRouter(prefix="/asset-classes", tags=["Asset Classes"])


@router_asset_classes.post("/", response_model=AssetClassResponse, status_code=status.HTTP_201_CREATED)
async def create_asset_class_endpoint(
        data: AssetClassCreate,
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("asset_classes", "write"))
):
    return await create_asset_class(db, data, current_user.employee_id)


@router_asset_classes.get("/", response_model=List[AssetClassResponse])
async def get_asset_classes(
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        class_name: Optional[str] = Query(None),
        asset_type_id: Optional[int] = Query(None),
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("asset_classes", "read"))
):
    return await get_asset_classes_list(db, skip, limit, class_name, asset_type_id)


@router_asset_classes.get("/{class_id}", response_model=AssetClassResponse)
async def get_asset_class(
        class_id: int,
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("asset_classes", "read"))
):
    obj = await get_asset_class_by_id(db, class_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Класс актива не найден")
    return obj


@router_asset_classes.patch("/{class_id}", response_model=AssetClassResponse)
async def update_asset_class_endpoint(
        class_id: int,
        data: AssetClassUpdate,
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("asset_classes", "write"))
):
    updated = await update_asset_class(db, class_id, data, current_user.employee_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Класс актива не найден")
    return updated


@router_asset_classes.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset_class_endpoint(
        class_id: int,
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("asset_classes", "write"))
):
    success = await delete_asset_class(db, class_id)
    if not success:
        raise HTTPException(status_code=404, detail="Класс актива не найден")