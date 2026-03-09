import json
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from database import get_session
from models import CATEGORIES, StapleItem, Supermarket

router = APIRouter()

CONFIG_PATH = "config.json"
DEFAULT_CONFIG = {
    "github_token": "",
    "repo_owner": "",
    "repo_name": "",
    "file_path": "boodschappen.html",
}


# ---------- Request schemas ----------

class StapleCreate(BaseModel):
    name: str
    amount: Optional[float] = None
    unit: Optional[str] = None
    category: str = "Overig"
    supermarket: Supermarket = Supermarket.beide
    notes: Optional[str] = None


class StapleUpdate(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = None
    unit: Optional[str] = None
    category: Optional[str] = None
    supermarket: Optional[Supermarket] = None
    notes: Optional[str] = None


class GithubConfig(BaseModel):
    github_token: str = ""
    repo_owner: str = ""
    repo_name: str = ""
    file_path: str = "boodschappen.html"


# ---------- Helpers ----------

def staple_to_dict(s: StapleItem) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "amount": s.amount,
        "unit": s.unit,
        "category": s.category,
        "supermarket": s.supermarket,
        "notes": s.notes,
    }


# ---------- Staple item endpoints ----------

@router.get("/staples")
def list_staples(session: Session = Depends(get_session)):
    staples = session.exec(select(StapleItem).order_by(StapleItem.name)).all()
    return [staple_to_dict(s) for s in staples]


@router.post("/staples", status_code=201)
def create_staple(data: StapleCreate, session: Session = Depends(get_session)):
    staple = StapleItem(
        name=data.name,
        amount=data.amount,
        unit=data.unit,
        category=data.category,
        supermarket=data.supermarket,
        notes=data.notes,
    )
    session.add(staple)
    session.commit()
    session.refresh(staple)
    return staple_to_dict(staple)


@router.put("/staples/{staple_id}")
def update_staple(staple_id: int, data: StapleUpdate, session: Session = Depends(get_session)):
    staple = session.get(StapleItem, staple_id)
    if not staple:
        raise HTTPException(status_code=404, detail="Artikel niet gevonden")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(staple, field, value)
    session.add(staple)
    session.commit()
    session.refresh(staple)
    return staple_to_dict(staple)


@router.delete("/staples/{staple_id}", status_code=204)
def delete_staple(staple_id: int, session: Session = Depends(get_session)):
    staple = session.get(StapleItem, staple_id)
    if not staple:
        raise HTTPException(status_code=404, detail="Artikel niet gevonden")
    session.delete(staple)
    session.commit()


# ---------- Config endpoints ----------

@router.get("/config")
def get_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            data = json.load(f)
        return {**DEFAULT_CONFIG, **data}
    return DEFAULT_CONFIG


@router.post("/config")
def save_config(data: GithubConfig):
    config = data.model_dump()
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
    return {"ok": True}


# ---------- Misc ----------

@router.get("/categories")
def get_categories():
    return CATEGORIES
