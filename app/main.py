from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

from app.database.connection import engine
from app.models.Base import Base

# Менеджер контекста для асинхронного управления жизненным циклом приложения
from contextlib import asynccontextmanager

# Middleware's
# Импорт класса логирования в middleware
from app.middleware.LoggingMiddleware import LoggingMiddleware
# Middleware для автоматической авторизации
# from app.middleware.AuthTokenMiddleware import AuthTokenMiddleware

# Импорт роутеров

# Redis
from app.services.redis.redis_client import router_redis

# Роутеры для данных о ПК и андроид устройств
from app.routers.router_pc_data import router_pc_data
from app.routers.router_android_data import router_android_data
from app.routers.router_zup import router_zup


# --- Управление жизненным циклом (Lifespan) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Функция, выполняемая при запуске и завершении работы приложения.

    STARTUP:
    1. engine.begin() открывает транзакцию с БД.
    2. conn.run_sync(Base.metadata.create_all) синхронно создает все таблицы,
       описанные в моделях (классы, наследующие Base), если они еще не существуют в БД.
    """

    # Инициализация дефолтного конфига карты
    # await MapConfigService.init_default_config()

    # Для разработки раскомментировать
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

# --- Создание экземпляра приложения ---
app = FastAPI(
    lifespan=lifespan,
    title="IT Assets API",
    description="API для управления IT-активами компании",
    version="1.0.0",
)

# --- Подключение MiddleWare ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене укажи конкретные домены
    allow_credentials=True,
    allow_methods=["*"],  # Разрешить все HTTP методы
    allow_headers=["*"],  # Разрешить все заголовки
)

app.add_middleware(LoggingMiddleware)
# app.add_middleware(AuthTokenMiddleware)

# --- Подключение API Маршрутов ---
app.include_router(router_redis, prefix="/api")             # Only DEV: check redis storage
app.include_router(router_pc_data, prefix="/api")           # PC DATA
app.include_router(router_android_data, prefix="/api")      # Android DATA
app.include_router(router_zup, prefix="/api")               # 1С ЗУП


router_root = APIRouter(tags=["/"])
@router_root.get("/")
async def root():
    host = "localhost"
    port = "8800"
    return {
        "docs": f"http://{host}:{port}/docs",
        "api": f"http://{host}:{port}/api"
    }

app.include_router(router_root)                             # корень веб-приложения