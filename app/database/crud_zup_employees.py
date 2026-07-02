from typing import Optional, Sequence, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.zup.employee import Employee
from app.schemas.zup.employee_schemas import EmployeeCreate, EmployeeUpdate


async def get_employee_by_guid(db: AsyncSession, guid: str) -> Optional[Employee]:
    """Получить сотрудника по GUID"""
    result = await db.execute(
        select(Employee).where(Employee.guid == guid)
    )
    return result.scalar_one_or_none()


async def get_employee_by_id(db: AsyncSession, employee_id: str) -> Optional[Employee]:
    """Получить сотрудника по табельному номеру"""
    result = await db.execute(
        select(Employee).where(Employee.employee_id == employee_id)
    )
    return result.scalar_one_or_none()


async def create_employee(db: AsyncSession, employee_in: EmployeeCreate) -> Employee:
    """Создать нового сотрудника"""
    db_employee = Employee(**employee_in.model_dump())
    db.add(db_employee)
    await db.commit()
    await db.refresh(db_employee)
    return db_employee


async def update_employee(db: AsyncSession, guid: str, employee_in: EmployeeUpdate) -> Optional[Employee]:
    """Обновить данные сотрудника"""
    employee = await get_employee_by_guid(db, guid)
    if not employee:
        return None

    update_data = employee_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(employee, key, value)

    await db.commit()
    await db.refresh(employee)
    return employee


async def get_employees_list(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 50,
        employee_id: Optional[str] = None,
        last_name: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name_en: Optional[str] = None,
        first_name_en: Optional[str] = None,
        department_guid: Optional[str] = None,
        position_guid: Optional[str] = None,
        is_active: Optional[bool] = None
) -> Sequence[Employee]:
    """Получить список сотрудников с фильтрацией"""
    query = select(Employee)

    if employee_id:
        query = query.where(Employee.employee_id == employee_id)
    if last_name:
        query = query.where(Employee.last_name.ilike(f"%{last_name}%"))
    if first_name:
        query = query.where(Employee.first_name.ilike(f"%{first_name}%"))
    if last_name_en:
        query = query.where(Employee.last_name_en.ilike(f"%{last_name_en}%"))
    if first_name_en:
        query = query.where(Employee.first_name_en.ilike(f"%{first_name_en}%"))
    if department_guid:
        query = query.where(Employee.department_guid == department_guid)
    if position_guid:
        query = query.where(Employee.position_guid == position_guid)
    if is_active is not None:
        if is_active:
            query = query.where(Employee.dismissal_date.is_(None))
        else:
            query = query.where(Employee.dismissal_date.isnot(None))

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


async def upsert_employee(db: AsyncSession, employee_data: dict) -> Employee:
    """Создать или обновить сотрудника (для интеграции с 1С)"""
    employee = await get_employee_by_guid(db, employee_data["guid"])

    if employee:
        # Обновление
        for key, value in employee_data.items():
            if hasattr(employee, key):
                setattr(employee, key, value)
    else:
        # Создание
        employee = Employee(**employee_data)
        db.add(employee)

    await db.commit()
    await db.refresh(employee)
    return employee