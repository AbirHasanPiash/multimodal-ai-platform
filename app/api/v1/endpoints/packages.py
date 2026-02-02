from typing import List, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.security import get_current_user, get_current_admin
from app.core.database import get_db
from app.models.package import Package
from app.schemas.package import PackageCreate, PackageUpdate, PackageResponse
from app.models.user import User

router = APIRouter()

# Public/User Routes

@router.get("/", response_model=List[PackageResponse])
async def read_packages(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Retrieve active packages for purchase.
    """
    stmt = (
        select(Package)
        .order_by(Package.is_active.desc(), Package.price.asc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    packages = result.scalars().all()
    return packages


# Admin Only Routes

@router.post("/", response_model=PackageResponse, status_code=status.HTTP_201_CREATED)
async def create_package(
    *,
    db: AsyncSession = Depends(get_db),
    package_in: PackageCreate,
    current_user: User = Depends(get_current_admin),
) -> Any:
    """
    Create a new package. Only for admin users.
    """
    # Check if name already exists
    stmt = select(Package).where(Package.name == package_in.name)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="A package with this name already exists."
        )

    package = Package(
        name=package_in.name,
        description=package_in.description,
        price=package_in.price,
        credits=package_in.credits,
        is_active=package_in.is_active,
        is_featured=package_in.is_featured,
    )
    db.add(package)
    await db.commit()
    await db.refresh(package)
    return package

@router.put("/{package_id}", response_model=PackageResponse)
async def update_package(
    *,
    db: AsyncSession = Depends(get_db),
    package_id: UUID,
    package_in: PackageUpdate,
    current_user: User = Depends(get_current_admin),
) -> Any:
    """
    Update a package. Only for Superusers.
    """
    package = await db.get(Package, package_id)
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    update_data = package_in.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(package, field, value)

    db.add(package)
    await db.commit()
    await db.refresh(package)
    return package

@router.delete("/{package_id}", response_model=PackageResponse)
async def delete_package(
    *,
    db: AsyncSession = Depends(get_db),
    package_id: UUID,
    current_user: User = Depends(get_current_admin),
) -> Any:
    """
    Soft delete a package.
    """
    package = await db.get(Package, package_id)
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    package.is_active = False
    db.add(package)
    await db.commit()
    await db.refresh(package)
    return package