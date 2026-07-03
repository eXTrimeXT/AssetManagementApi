import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.database.connection import get_db
from app.database.assets.asset_model import (
    create_asset_model, get_asset_model_by_id, get_asset_models_list,
    update_asset_model, delete_asset_model
)
from app.schemas.assets.asset_model import AssetModelCreate, AssetModelUpdate, AssetModelResponse
from app.services.auth.auth_service import require_authorized_user
from app.services.auth.permission_checker import require_permission

logger = logging.getLogger(__name__)
router_asset_models = APIRouter(prefix="/asset-models", tags=["Asset Models"])


@router_asset_models.post("/", response_model=AssetModelResponse, status_code=status.HTTP_201_CREATED)
async def create_asset_model_endpoint(
        data: AssetModelCreate,
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("asset_models", "write"))
):
    return await create_asset_model(db, data, current_user.employee_id)


@router_asset_models.get("/", response_model=List[AssetModelResponse])
async def get_asset_models(
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        model_name: Optional[str] = Query(None),
        class_id: Optional[int] = Query(None),
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("asset_models", "read"))
):
    return await get_asset_models_list(db, skip, limit, model_name, class_id)


@router_asset_models.get("/{model_id}", response_model=AssetModelResponse)
async def get_asset_model(
        model_id: int,
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("asset_models", "read"))
):
    obj = await get_asset_model_by_id(db, model_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Модель актива не найдена")
    return obj


@router_asset_models.patch("/{model_id}", response_model=AssetModelResponse)
async def update_asset_model_endpoint(
        model_id: int,
        data: AssetModelUpdate,
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("asset_models", "write"))
):
    updated = await update_asset_model(db, model_id, data, current_user.employee_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Модель актива не найдена")
    return updated


@router_asset_models.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset_model_endpoint(
        model_id: int,
        db: AsyncSession = Depends(get_db),
        current_user=Depends(require_permission("asset_models", "write"))
):
    success = await delete_asset_model(db, model_id)
    if not success:
        raise HTTPException(status_code=404, detail="Модель актива не найдена")