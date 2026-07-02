from fastapi import Depends, HTTPException, Request
from typing import Optional
from app.services.auth.auth_service import get_user_permissions_from_redis, get_token_from_request, get_user_from_token
import logging

logger = logging.getLogger(__name__)


async def check_permission(
        request: Request,
        resource: str,
        action: str
) -> bool:
    """
    Проверяет наличие права на ресурс из Redis.

    Args:
        request: HTTP запрос
        resource: Название ресурса (например, "computer", "supplies")
        action: Действие ("read" или "write")

    Returns:
        True если право есть, False если нет
    """
    try:
        token = await get_token_from_request(request)
        user_data = get_user_from_token(token)

        # Получаем права из Redis
        permissions = await get_user_permissions_from_redis(user_data.login)

        if not permissions:
            logger.warning(f"Права не найдены в Redis для пользователя {user_data.login}")
            return False

        # Проверяем наличие права
        resource_perms = permissions.get(resource, {})
        has_permission = resource_perms.get(action, False)

        if not has_permission:
            logger.debug(f"Пользователь {user_data.login} не имеет права {action} на {resource}")

        return has_permission

    except Exception as e:
        logger.error(f"Ошибка проверки прав: {e}")
        return False


def require_permission(resource: str, action: str):
    """
    Зависимость для проверки права на ресурс.

    Пример использования:
        @router_assets.post("/")
        async def create_asset(
            asset_data: AssetCreate,
            current_user = Depends(require_permission("computer", "write"))
        ):
            ...
    """
    async def dependency(request: Request):
        has_perm = await check_permission(request, resource, action)

        if not has_perm:
            raise HTTPException(
                status_code=403,
                detail=f"Нет права '{action}' на ресурс '{resource}'"
            )

        # Возвращаем данные пользователя (можно расширить)
        token = await get_token_from_request(request)
        user_data = get_user_from_token(token)
        return user_data

    return dependency


def require_any_permission(action: str, resources: list[str] = None):
    """
    Проверяет наличие права на ЛЮБОЙ из указанных ресурсов.
    Если resources не указан - проверяет все ресурсы из токена.

    Пример использования:
        @router_assets.get("/")
        async def get_assets(
            current_user = Depends(require_any_permission("read"))
        ):
            ...
    """
    async def dependency(request: Request):
        token = await get_token_from_request(request)
        user_data = get_user_from_token(token)

        # Получаем права из Redis
        permissions = await get_user_permissions_from_redis(user_data.login)

        if not permissions:
            raise HTTPException(status_code=403, detail="Права не найдены")

        # Если ресурсы не указаны - проверяем все
        if resources is None:
            check_resources = list(permissions.keys())
        else:
            check_resources = resources

        # Проверяем через цикл - есть ли право хотя бы на один ресурс
        for resource in check_resources:
            resource_perms = permissions.get(resource, {})
            if resource_perms.get(action, False):
                return user_data  # Нашли право - возвращаем пользователя

        # Не нашли ни одного права
        raise HTTPException(
            status_code=403,
            detail=f"Нет права '{action}' ни на один из ресурсов: {check_resources}"
        )

    return dependency


async def get_accessible_asset_types(request: Request) -> list[str]:
    """
    Возвращает список типов активов, на которые у пользователя есть право read.
    Используется для фильтрации списков активов.
    """
    token = await get_token_from_request(request)
    user_data = get_user_from_token(token)

    permissions = await get_user_permissions_from_redis(user_data.login)

    if not permissions:
        return []

    accessible_types = []
    for resource, perms in permissions.items():
        if perms.get("read", False):
            accessible_types.append(resource)

    return accessible_types