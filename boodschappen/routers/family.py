"""
CRUD /api/family  —  Gezinsleden & voorkeuren
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from database import get_session
from models import FamilyMember

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────

class FamilyMemberCreate(BaseModel):
    name: str
    birthdate: Optional[date] = None
    dietary_restrictions: Optional[str] = None
    allergies: Optional[str] = None
    likes: Optional[str] = None
    dislikes: Optional[str] = None
    notes: Optional[str] = None


class FamilyMemberUpdate(BaseModel):
    name: Optional[str] = None
    birthdate: Optional[date] = None
    dietary_restrictions: Optional[str] = None
    allergies: Optional[str] = None
    likes: Optional[str] = None
    dislikes: Optional[str] = None
    notes: Optional[str] = None


# ── Helper ────────────────────────────────────────────────────────

def member_to_dict(m: FamilyMember) -> dict:
    age = None
    if m.birthdate:
        today = date.today()
        age = today.year - m.birthdate.year - (
            (today.month, today.day) < (m.birthdate.month, m.birthdate.day)
        )
    return {
        "id":                   m.id,
        "name":                 m.name,
        "birthdate":            m.birthdate.isoformat() if m.birthdate else None,
        "age":                  age,
        "dietary_restrictions": m.dietary_restrictions,
        "allergies":            m.allergies,
        "likes":                m.likes,
        "dislikes":             m.dislikes,
        "notes":                m.notes,
    }


# ── Endpoints ─────────────────────────────────────────────────────

@router.get("/family")
def list_family(session: Session = Depends(get_session)):
    members = session.exec(select(FamilyMember).order_by(FamilyMember.name)).all()
    return [member_to_dict(m) for m in members]


@router.post("/family", status_code=201)
def create_member(data: FamilyMemberCreate, session: Session = Depends(get_session)):
    member = FamilyMember(**data.model_dump())
    session.add(member)
    session.commit()
    session.refresh(member)
    return member_to_dict(member)


@router.put("/family/{member_id}")
def update_member(member_id: int, data: FamilyMemberUpdate, session: Session = Depends(get_session)):
    member = session.get(FamilyMember, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Gezinslid niet gevonden")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(member, field, value)
    session.add(member)
    session.commit()
    session.refresh(member)
    return member_to_dict(member)


@router.delete("/family/{member_id}", status_code=204)
def delete_member(member_id: int, session: Session = Depends(get_session)):
    member = session.get(FamilyMember, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Gezinslid niet gevonden")
    session.delete(member)
    session.commit()
