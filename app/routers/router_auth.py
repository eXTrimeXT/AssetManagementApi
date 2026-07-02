import logging
from typing import Optional

import jwt
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import json
from app.database.connection import get_db
from app.schemas.auth.AuthSchemas import UserInfoResponse, TokenRequest, LoginRequest
from app.services.auth.auth_service import (
    get_user_from_token,
    TokenValidationError,
    JWT_SECRET_KEY
)
from app.models.UserJWTData import UserJWTData
from app.services.redis.redis_client import redis_client
from app.models.zup.employee import Employee
from app.services.auth.external_auth import external_login

logger = logging.getLogger(__name__)

router_auth = APIRouter(tags=["auth"])

async def save_session_to_redis(login: str, token: str, ttl: int) -> None:
    session_key = f"session:{login}"
    session_data = {"token": token, "login": login}
    await redis_client.set(session_key, json.dumps(session_data), ex=ttl)


async def create_session_for_user(db, request, response, login):
    """
    Создаёт сессию для существующего сотрудника из 1С.
    НЕ создаёт новых пользователей - они должны быть синхронизированы из 1С.
    """
    # Проверяем, есть ли сотрудник в БД
    from app.database.crud_zup_employees import get_employee_by_id
    employee = await get_employee_by_id(db, login)

    if not employee:
        logger.warning(f"Сотрудник {login} не найден в БД. Синхронизируйте данные из 1С через /api/zup/sync")
        raise HTTPException(
            status_code=404,
            detail=f"Сотрудник {login} не найден. Обратитесь к администратору для синхронизации из 1С."
        )

    # Проверяем, действующий ли сотрудник
    if not employee.is_active:
        logger.warning(f"Сотрудник {login} уволен")
        raise HTTPException(status_code=403, detail="Учетная запись сотрудника деактивирована")

    now = datetime.now()

    # Генерируем JWT токен
    payload = {
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=12)).timestamp()),
        "login": login,
        "last_ip": request.client.host if request.client else "127.0.0.1",
        "last_time": now.strftime("%H:%M:%S %d.%m.%Y"),
        "user_data": {
            "email": employee.email or f"{login}@hmmr.ru",
            "fullname": employee.full_name_ru,
            "employee_id": employee.employee_id
        }
    }

    token = jwt.encode(
        payload,
        key=JWT_SECRET_KEY if JWT_SECRET_KEY else None,
        algorithm="HS256" if JWT_SECRET_KEY else "none"
    )

    ttl = 12 * 60 * 60
    await save_session_to_redis(login, token, ttl)

    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=ttl,
        path="/"
    )

    return UserInfoResponse(
        login=login,
        email=employee.email or f"{login}@hmmr.ru",
        fullname=employee.full_name_ru,
        distinguished_name=f"CN={login}",
        groups=[],
        permissions={},
        assets_admin=False,
        last_ip=payload["last_ip"],
        last_time=payload["last_time"],
        token=token
    )


@router_auth.post("/login", response_model=UserInfoResponse, status_code=200)
async def login_by_credentials(
        credentials: LoginRequest,
        request: Request,
        response: Response,
        db: AsyncSession = Depends(get_db),
):
    """
    Вход по логину и паролю.
    Если логин == "root" — локальная аутентификация без внешнего сервиса.
    Иначе — аутентификация через внешний сервис с RSA-шифрованием пароля.
    """
    # Удаляем старую сессию перед новым входом
    response.delete_cookie(key="session_token", path="/")

    system_users = ["root", "read", "write", "android", "pc_data"]

    try:
        # === Обработка системных пользователей ===
        if credentials.login in system_users and credentials.login == credentials.password:
            return await create_session_for_user(db, request, response, credentials.login)

        # === Обработка обычных пользователей через внешний сервис ===
        # Получаем токен от внешнего сервиса
        token = external_login(credentials.login, credentials.password)

        # Декодируем токен для извлечения данных пользователя
        user_data: UserJWTData = get_user_from_token(token)
        if user_data.is_expired:
            logger.warning("Срок действия токена истек")
            raise HTTPException(status_code=401, detail="Срок действия токена истек")

        # Сохраняем сессию в Redis
        payload = jwt.decode(
            token,
            key=JWT_SECRET_KEY if JWT_SECRET_KEY else None,
            algorithms=["HS256"],
            options={
                "verify_signature": bool(JWT_SECRET_KEY),
                "verify_exp": False,
                "verify_iat": False
            }
        )
        exp = payload.get("exp")
        ttl = int(exp - datetime.now().timestamp()) if exp else 3600
        ttl = max(ttl, 60)

        await save_session_to_redis(user_data.login, token, ttl)

        # Устанавливаем куки
        response.set_cookie(
            key="session_token",
            value=token,
            httponly=True,
            samesite="lax",
            max_age=ttl,
            path="/"
        )
        logger.info("Авторизация успешна")
        result = user_data.to_dict()
        result["token"] = token
        # result["user_id"] = db_user.user_id
        logger.info("Авторизация успешна")
        return result

    except RuntimeError as e:
        logger.error(f"Ошибка времени выполнения: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Ошибка времени выполнения: {str(e)}")
    except TokenValidationError as e:
        logger.warning(f"Недопустимый токен: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Недопустимый токен: {str(e)}")
    except Exception as e:
        logger.error(f"Внутренняя ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка: {str(e)}")

@router_auth.post("/auth_token", response_model=UserInfoResponse, status_code=200)
async def auth_token(
        request: TokenRequest,
        response: Response,
        db: AsyncSession = Depends(get_db),
):
    # Удаляем старую сессию перед новым входом
    response.delete_cookie(key="session_token", path="/")
    try:
        user_data: UserJWTData = get_user_from_token(request.token)
        if user_data.is_expired:
            logger.warning("Срок действия токена истек")
            raise HTTPException(status_code=401, detail="Срок действия токена истек")

        payload = jwt.decode(
            request.token,
            key=JWT_SECRET_KEY if JWT_SECRET_KEY else None,
            algorithms=["HS256"],
            options={"verify_signature": bool(JWT_SECRET_KEY), "verify_exp": False}
        )
        exp = payload.get("exp")
        ttl = int(exp - datetime.now().timestamp()) if exp else 3600
        ttl = max(ttl, 60)

        await save_session_to_redis(user_data.login, request.token, ttl)

        # === Устанавливаем HTTP-only куки ===
        response.set_cookie(
            key="session_token",
            value=request.token,
            httponly=True,
            # secure=os.getenv("ENV", "dev") == "prod",  # Только HTTPS в продакшене
            samesite="lax",
            max_age=ttl,
            path="/"
        )
        logger.info("Авторизация успешна")
        result = user_data.to_dict()
        result["token"] = request.token  # добавлено
        # result["user_id"] = db_user.user_id
        logger.info("Авторизация успешна")
        return result

    except TokenValidationError as e:
        logger.warning(f"Недопустимый токен: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Недопустимый токен: {str(e)}")
    except Exception as e:
        logger.error(f"Внутренняя ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка: {str(e)}")

@router_auth.post("/logout")
async def logout(
        response: Response,
        token: str = Depends(lambda: None),  # Placeholder, токен берём из куки
):
    """Удаляет сессию из Redis и очищает куки"""
    # Токен берём из куки, которую отправил браузер
    # (обработка будет в auth_service, здесь только очистка куки)
    response.delete_cookie(key="session_token", path="/")
    return {"status": "logged out"}