import os
import jwt
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.UserJWTData import UserJWTData
from app.models.zup.employee import Employee  # ← Изменено
from app.database.crud_zup_employees import get_employee_by_id  # ← Изменено
from app.database.connection import get_db
from app.services.redis.redis_client import redis_client
from app.services.zup_integration import sync_all_data  # ← Добавлено для автосинхронизации

logger = logging.getLogger(__name__)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")


class TokenValidationError(Exception):
    pass


security = HTTPBearer(auto_error=False)


async def get_token_from_request(request: Request) -> str:
    """
    Получает токен из:
    1. Заголовка Authorization: Bearer <token>
    2. Куки session_token
    """
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    token = request.cookies.get("session_token")
    if token:
        return token.strip()

    logger.warning("Токен не предоставлен")
    raise HTTPException(status_code=401, detail="Токен не предоставлен")


async def require_authorized_user(
        request: Request,
        db: AsyncSession = Depends(get_db)
) -> Employee:
    """
    Проверяет авторизацию и возвращает сотрудника из ZUP по employee_id.
    Если сотрудник не найден в БД, пытается синхронизировать данные из 1С.
    """
    try:
        token = await get_token_from_request(request)
        user_data = get_user_from_token(token)

        if user_data.is_expired:
            logger.warning("Срок действия токена истек")
            raise HTTPException(status_code=401, detail="Срок действия токена истек")

        session = await get_session_from_redis(user_data.login)
        if not session or session.get("token") != token:
            logger.warning("Недействительный или просроченный сеанс")
            raise HTTPException(status_code=401, detail="Недействительный или просроченный сеанс")

        # === Ищем сотрудника в ZUP по employee_id (login) ===
        employee = await get_employee_by_id(db, user_data.login)

        if not employee:
            logger.info(f"Сотрудник {user_data.login} не найден в БД. Попытка синхронизации из 1С...")
            # Пытаемся синхронизировать данные из 1С
            try:
                await sync_all_data(db)
                # Повторно ищем сотрудника после синхронизации
                employee = await get_employee_by_id(db, user_data.login)
            except Exception as e:
                logger.error(f"Ошибка синхронизации из 1С: {e}")
                raise HTTPException(status_code=404, detail=f"Сотрудник {user_data.login} не найден и синхронизация не удалась")

        if not employee:
            logger.warning(f"Сотрудник {user_data.login} не найден после синхронизации")
            raise HTTPException(status_code=404, detail=f"Сотрудник {user_data.login} не найден в системе")

        # Проверяем, действующий ли сотрудник
        if not employee.is_active:
            logger.warning(f"Сотрудник {user_data.login} уволен")
            raise HTTPException(status_code=403, detail="Учетная запись сотрудника деактивирована")

        return employee

    except TokenValidationError as e:
        logger.warning(f"Недопустимый токен: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Недопустимый токен: {str(e)}")


async def get_current_user_id(
        current_user: Employee = Depends(require_authorized_user)
) -> str:
    """
    Зависимость для получения employee_id текущего авторизованного сотрудника.
    """
    return current_user.employee_id


def decode_token(token: str, secret_key: Optional[str] = None) -> Dict[str, Any]:
    key = secret_key or JWT_SECRET_KEY
    try:
        if key:
            payload = jwt.decode(
                token,
                key=key,
                algorithms=["HS256"],
                options={"verify_exp": True}
            )
        else:
            logger.warning(
                "Секретный ключ JWT не настроен. Токен декодирования без проверки подписи!"
                "Установите JWT_SECRET_KEY для работы."
            )
            payload = jwt.decode(
                token,
                options={"verify_signature": False, "verify_exp": True}
            )
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Срок действия токена истек")
        raise TokenValidationError("Срок действия токена истек")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Недопустимый токен: {str(e)}")
        raise TokenValidationError(f"Недопустимый токен: {str(e)}")

def get_user_from_token(token: str, secret_key: Optional[str] = None) -> UserJWTData:
    key = secret_key or JWT_SECRET_KEY
    payload = decode_token(token, key)
    return UserJWTData(payload)

def is_token_valid(token: str, secret_key: Optional[str] = None) -> bool:
    key = secret_key or JWT_SECRET_KEY
    try:
        decode_token(token, key)
        return True
    except TokenValidationError:
        logger.error("Исключение: TokenValidationError")
        return False

async def create_or_update_user_from_token(
        db: AsyncSession,
        user_data: UserJWTData
) -> User:
    # === Получаем иерархию по аббревиатуре отдела ===
    group_id = None
    division_id = None
    department_id = None
    if user_data.department:
        hierarchy = await get_hierarchy_by_group_params(db, abbreviation=user_data.department)
        if hierarchy:
            first = hierarchy[0]
            group_id = first.get("group_id")
            division_id = first.get("division_id")
            department_id = first.get("department_id")

    existing_user = await get_user_by_tab_id(db, user_data.login)
    if existing_user:
        existing_user.user_en_name = user_data.fullname
        existing_user.owner = user_data.fullname
        existing_user.email = user_data.email
        existing_user.assets_admin = user_data.assets_admin
        existing_user.permissions = user_data.permissions
        existing_user.group_id = group_id
        existing_user.division_id = division_id
        existing_user.department_id = department_id
        existing_user.updated_at = datetime.now()
        await db.commit()
        await db.refresh(existing_user)
        return existing_user
    else:
        new_user = User(
            user_tab_id=user_data.login,
            user_en_name=user_data.fullname,
            owner=user_data.fullname,
            email=user_data.email,
            permissions=user_data.permissions,
            group_id=group_id,
            division_id=division_id,
            department_id=department_id,
            is_active=True,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        return new_user