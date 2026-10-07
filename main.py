import os
from contextlib import asynccontextmanager
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, Float, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Create a .env file from .env.example "
        "and paste your Neon connection string there."
    )


if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://", "postgresql+psycopg://", 1
    )
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://", "postgresql+psycopg://", 1
    )


engine_options: dict = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
else:
    engine_options["pool_recycle"] = 300

engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    price: Mapped[float] = mapped_column(Float)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    category: str = Field(min_length=2, max_length=80)
    price: float = Field(gt=0)
    in_stock: bool = True


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    category: str | None = Field(default=None, min_length=2, max_length=80)
    price: float | None = Field(default=None, gt=0)
    in_stock: bool | None = None


class ProductRead(BaseModel):
    id: int
    name: str
    category: str
    price: float
    in_stock: bool

    model_config = ConfigDict(from_attributes=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Mini Store API - Neon PostgreSQL",
    description=(
        "Lesson example: FastAPI + SQLAlchemy ORM + cloud PostgreSQL in Neon"
    ),
    version="3.0.0",
    lifespan=lifespan,
)


@app.get("/")
def root():
    return {
        "message": "Mini Store API is running",
        "storage": "PostgreSQL via SQLAlchemy ORM",
    }


@app.get("/products", response_model=list[ProductRead])
def get_products(
    db: DbSession,
    category: str | None = None,
    in_stock: bool | None = None,
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
):
    statement = select(Product)

    if category is not None:
        statement = statement.where(Product.category == category)

    if in_stock is not None:
        statement = statement.where(Product.in_stock == in_stock)

    if min_price is not None:
        statement = statement.where(Product.price >= min_price)

    if max_price is not None:
        statement = statement.where(Product.price <= max_price)

    return db.scalars(statement).all()


@app.get("/products/{product_id}", response_model=ProductRead)
def get_product(product_id: int, db: DbSession):
    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    return product


@app.post(
    "/products",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
)
def create_product(data: ProductCreate, db: DbSession):
    product = Product(**data.model_dump())

    db.add(product)
    db.commit()
    db.refresh(product)

    return product


@app.patch("/products/{product_id}", response_model=ProductRead)
def update_product(product_id: int, data: ProductUpdate, db: DbSession):
    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    changes = data.model_dump(exclude_unset=True)

    for field_name, value in changes.items():
        setattr(product, field_name, value)

    db.commit()
    db.refresh(product)

    return product


@app.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_product(product_id: int, db: DbSession):
    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    db.delete(product)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
