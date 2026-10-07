import os
from contextlib import asynccontextmanager
from enum import Enum
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    Enum as SqlEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
    select,
)
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


class ContractStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Mercenary(Base):
    __tablename__ = "mercenaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    nickname: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    reputation: Mapped[int] = mapped_column(Integer, default=0)
    balance: Mapped[float] = mapped_column(Float, default=0.0)


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(String(500))
    difficulty: Mapped[int] = mapped_column(Integer, index=True)
    reward: Mapped[float] = mapped_column(Float)
    district: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[ContractStatus] = mapped_column(
        SqlEnum(ContractStatus),
        default=ContractStatus.OPEN,
        index=True,
    )
    mercenary_id: Mapped[int | None] = mapped_column(
        ForeignKey("mercenaries.id"),
        default=None,
        index=True,
    )


class MercenaryCreate(BaseModel):
    nickname: str = Field(min_length=2, max_length=80)
    level: int = Field(default=1, ge=1, le=10)
    reputation: int = Field(default=0, ge=0)
    balance: float = Field(default=0.0, ge=0)


class MercenaryUpdate(BaseModel):
    nickname: str | None = Field(default=None, min_length=2, max_length=80)
    level: int | None = Field(default=None, ge=1, le=10)
    reputation: int | None = Field(default=None, ge=0)
    balance: float | None = Field(default=None, ge=0)


class MercenaryRead(BaseModel):
    id: int
    nickname: str
    level: int
    reputation: int
    balance: float

    model_config = ConfigDict(from_attributes=True)


class ContractCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=2, max_length=500)
    difficulty: int = Field(ge=1, le=10)
    reward: float = Field(gt=0)
    district: str = Field(min_length=2, max_length=80)


class ContractUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, min_length=2, max_length=500)
    difficulty: int | None = Field(default=None, ge=1, le=10)
    reward: float | None = Field(default=None, gt=0)
    district: str | None = Field(default=None, min_length=2, max_length=80)


class ContractRead(BaseModel):
    id: int
    name: str
    description: str
    difficulty: int
    reward: float
    district: str
    status: ContractStatus
    mercenary_id: int | None

    model_config = ConfigDict(from_attributes=True)


class TakeContract(BaseModel):
    mercenary_id: int


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
    title="MERCNET",
    lifespan=lifespan,
)


@app.get("/")
def root():
    return {
        "message": "MERCNET API is running",
        "storage": "PostgreSQL via SQLAlchemy ORM",
    }


@app.get("/mercenaries", response_model=list[MercenaryRead])
def get_mercenaries(db: DbSession):
    return db.scalars(select(Mercenary)).all()


@app.get("/mercenaries/{mercenary_id}", response_model=MercenaryRead)
def get_mercenary(mercenary_id: int, db: DbSession):
    mercenary = db.get(Mercenary, mercenary_id)

    if mercenary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mercenary not found",
        )

    return mercenary


@app.post(
    "/mercenaries",
    response_model=MercenaryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_mercenary(data: MercenaryCreate, db: DbSession):
    mercenary = Mercenary(**data.model_dump())

    db.add(mercenary)
    db.commit()
    db.refresh(mercenary)

    return mercenary


@app.patch("/mercenaries/{mercenary_id}", response_model=MercenaryRead)
def update_mercenary(mercenary_id: int, data: MercenaryUpdate, db: DbSession):
    mercenary = db.get(Mercenary, mercenary_id)

    if mercenary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mercenary not found",
        )

    changes = data.model_dump(exclude_unset=True)

    for field_name, value in changes.items():
        setattr(mercenary, field_name, value)

    db.commit()
    db.refresh(mercenary)

    return mercenary


@app.delete(
    "/mercenaries/{mercenary_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_mercenary(mercenary_id: int, db: DbSession):
    mercenary = db.get(Mercenary, mercenary_id)

    if mercenary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mercenary not found",
        )

    db.delete(mercenary)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/contracts", response_model=list[ContractRead])
def get_contracts(
    db: DbSession,
    contract_status: ContractStatus | None = Query(default=None, alias="status"),
    district: str | None = None,
    min_reward: float | None = Query(default=None, ge=0),
    max_difficulty: int | None = Query(default=None, ge=1, le=10),
):
    statement = select(Contract)

    if contract_status is not None:
        statement = statement.where(Contract.status == contract_status)

    if district is not None:
        statement = statement.where(Contract.district == district)

    if min_reward is not None:
        statement = statement.where(Contract.reward >= min_reward)

    if max_difficulty is not None:
        statement = statement.where(Contract.difficulty <= max_difficulty)

    return db.scalars(statement).all()


@app.get("/contracts/best", response_model=ContractRead)
def get_best_contract(db: DbSession):
    statement = select(Contract).where(Contract.status == ContractStatus.OPEN)
    contracts = db.scalars(statement).all()

    if not contracts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No open contracts available",
        )

    best = max(contracts, key=lambda contract: contract.reward / contract.difficulty)

    return best


@app.get("/contracts/{contract_id}", response_model=ContractRead)
def get_contract(contract_id: int, db: DbSession):
    contract = db.get(Contract, contract_id)

    if contract is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found",
        )

    return contract


@app.post(
    "/contracts",
    response_model=ContractRead,
    status_code=status.HTTP_201_CREATED,
)
def create_contract(data: ContractCreate, db: DbSession):
    contract = Contract(**data.model_dump())

    db.add(contract)
    db.commit()
    db.refresh(contract)

    return contract


@app.patch("/contracts/{contract_id}", response_model=ContractRead)
def update_contract(contract_id: int, data: ContractUpdate, db: DbSession):
    contract = db.get(Contract, contract_id)

    if contract is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found",
        )

    changes = data.model_dump(exclude_unset=True)

    for field_name, value in changes.items():
        setattr(contract, field_name, value)

    db.commit()
    db.refresh(contract)

    return contract


@app.delete(
    "/contracts/{contract_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_contract(contract_id: int, db: DbSession):
    contract = db.get(Contract, contract_id)

    if contract is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found",
        )

    db.delete(contract)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/contracts/{contract_id}/take", response_model=ContractRead)
def take_contract(contract_id: int, data: TakeContract, db: DbSession):
    contract = db.get(Contract, contract_id)

    if contract is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found",
        )

    mercenary = db.get(Mercenary, data.mercenary_id)

    if mercenary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mercenary not found",
        )

    if contract.status != ContractStatus.OPEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Contract is not OPEN and cannot be taken",
        )

    if contract.difficulty > mercenary.level:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contract difficulty is higher than mercenary level",
        )

    contract.status = ContractStatus.IN_PROGRESS
    contract.mercenary_id = mercenary.id

    db.commit()
    db.refresh(contract)

    return contract


@app.post("/contracts/{contract_id}/complete", response_model=ContractRead)
def complete_contract(contract_id: int, db: DbSession):
    contract = db.get(Contract, contract_id)

    if contract is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found",
        )

    if contract.status != ContractStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only IN_PROGRESS contracts can be completed",
        )

    contract.status = ContractStatus.COMPLETED

    if contract.mercenary_id is not None:
        mercenary = db.get(Mercenary, contract.mercenary_id)

        if mercenary is not None:
            mercenary.balance += contract.reward
            mercenary.reputation += 1

    db.commit()
    db.refresh(contract)

    return contract


@app.post("/contracts/{contract_id}/fail", response_model=ContractRead)
def fail_contract(contract_id: int, db: DbSession):
    contract = db.get(Contract, contract_id)

    if contract is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contract not found",
        )

    if contract.status != ContractStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only IN_PROGRESS contracts can be failed",
        )

    contract.status = ContractStatus.FAILED

    db.commit()
    db.refresh(contract)

    return contract
