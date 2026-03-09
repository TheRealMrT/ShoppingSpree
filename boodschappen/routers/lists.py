import base64
import json
import os
from datetime import date
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from database import get_session
from models import (
    CATEGORIES,
    CATEGORY_ORDER,
    Recipe,
    RecipeIngredient,
    ShoppingList,
    ShoppingListItem,
    StapleItem,
    Supermarket,
)

router = APIRouter()


# ---------- Request schemas ----------

class ListCreate(BaseModel):
    name: str
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    notes: Optional[str] = None


class ListUpdate(BaseModel):
    name: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    notes: Optional[str] = None


class ItemCreate(BaseModel):
    name: str
    amount: Optional[float] = None
    unit: Optional[str] = None
    category: str = "Overig"
    supermarket: Supermarket = Supermarket.beide
    source: Optional[str] = None


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = None
    unit: Optional[str] = None
    category: Optional[str] = None
    supermarket: Optional[Supermarket] = None
    checked: Optional[bool] = None
    source: Optional[str] = None


class BulkItemCreate(BaseModel):
    items: List[ItemCreate]


class AddRecipesRequest(BaseModel):
    recipes: List[dict]  # [{recipe_id, servings}]


# ---------- Helpers ----------

def item_to_dict(item: ShoppingListItem) -> dict:
    return {
        "id": item.id,
        "list_id": item.list_id,
        "name": item.name,
        "amount": item.amount,
        "unit": item.unit,
        "category": item.category,
        "supermarket": item.supermarket,
        "checked": item.checked,
        "source": item.source,
    }


def list_to_dict(lst: ShoppingList, item_count: int = None) -> dict:
    return {
        "id": lst.id,
        "name": lst.name,
        "date_from": lst.date_from.isoformat() if lst.date_from else None,
        "date_to": lst.date_to.isoformat() if lst.date_to else None,
        "notes": lst.notes,
        "published_url": lst.published_url,
        "created_at": lst.created_at.isoformat() if lst.created_at else None,
        "item_count": item_count,
    }


def sort_key(item: dict) -> int:
    return CATEGORY_ORDER.get(item.get("category", "Overig"), len(CATEGORIES))


# ---------- Endpoints ----------

@router.get("/lists")
def list_shopping_lists(session: Session = Depends(get_session)):
    lists = session.exec(select(ShoppingList).order_by(ShoppingList.created_at.desc())).all()
    result = []
    for lst in lists:
        count = len(session.exec(select(ShoppingListItem).where(ShoppingListItem.list_id == lst.id)).all())
        result.append(list_to_dict(lst, item_count=count))
    return result


@router.get("/lists/{list_id}")
def get_shopping_list(list_id: int, session: Session = Depends(get_session)):
    lst = session.get(ShoppingList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="Lijst niet gevonden")
    items = session.exec(select(ShoppingListItem).where(ShoppingListItem.list_id == list_id)).all()
    d = list_to_dict(lst)
    d["items"] = sorted([item_to_dict(i) for i in items], key=sort_key)
    return d


@router.post("/lists", status_code=201)
def create_shopping_list(data: ListCreate, session: Session = Depends(get_session)):
    lst = ShoppingList(
        name=data.name,
        date_from=data.date_from,
        date_to=data.date_to,
        notes=data.notes,
    )
    session.add(lst)
    session.commit()
    session.refresh(lst)
    return list_to_dict(lst, item_count=0)


@router.put("/lists/{list_id}")
def update_shopping_list(list_id: int, data: ListUpdate, session: Session = Depends(get_session)):
    lst = session.get(ShoppingList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="Lijst niet gevonden")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(lst, field, value)
    session.add(lst)
    session.commit()
    session.refresh(lst)
    return list_to_dict(lst)


@router.delete("/lists/{list_id}", status_code=204)
def delete_shopping_list(list_id: int, session: Session = Depends(get_session)):
    lst = session.get(ShoppingList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="Lijst niet gevonden")
    items = session.exec(select(ShoppingListItem).where(ShoppingListItem.list_id == list_id)).all()
    for item in items:
        session.delete(item)
    session.delete(lst)
    session.commit()


# ---------- Item management ----------

@router.get("/lists/{list_id}/items")
def get_list_items(list_id: int, session: Session = Depends(get_session)):
    lst = session.get(ShoppingList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="Lijst niet gevonden")
    items = session.exec(select(ShoppingListItem).where(ShoppingListItem.list_id == list_id)).all()
    return sorted([item_to_dict(i) for i in items], key=sort_key)


@router.post("/lists/{list_id}/items", status_code=201)
def add_item(list_id: int, data: ItemCreate, session: Session = Depends(get_session)):
    lst = session.get(ShoppingList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="Lijst niet gevonden")
    item = ShoppingListItem(
        list_id=list_id,
        name=data.name,
        amount=data.amount,
        unit=data.unit,
        category=data.category,
        supermarket=data.supermarket,
        source=data.source,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item_to_dict(item)


@router.post("/lists/{list_id}/items/bulk", status_code=201)
def bulk_add_items(list_id: int, data: BulkItemCreate, session: Session = Depends(get_session)):
    lst = session.get(ShoppingList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="Lijst niet gevonden")
    created = []
    for item_data in data.items:
        item = ShoppingListItem(
            list_id=list_id,
            name=item_data.name,
            amount=item_data.amount,
            unit=item_data.unit,
            category=item_data.category,
            supermarket=item_data.supermarket,
            source=item_data.source,
        )
        session.add(item)
        session.flush()
        created.append(item_to_dict(item))
    session.commit()
    return created


@router.put("/lists/{list_id}/items/{item_id}")
def update_item(list_id: int, item_id: int, data: ItemUpdate, session: Session = Depends(get_session)):
    item = session.get(ShoppingListItem, item_id)
    if not item or item.list_id != list_id:
        raise HTTPException(status_code=404, detail="Item niet gevonden")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item_to_dict(item)


@router.delete("/lists/{list_id}/items/{item_id}", status_code=204)
def delete_item(list_id: int, item_id: int, session: Session = Depends(get_session)):
    item = session.get(ShoppingListItem, item_id)
    if not item or item.list_id != list_id:
        raise HTTPException(status_code=404, detail="Item niet gevonden")
    session.delete(item)
    session.commit()


@router.post("/lists/{list_id}/items/{item_id}/toggle")
def toggle_item(list_id: int, item_id: int, session: Session = Depends(get_session)):
    item = session.get(ShoppingListItem, item_id)
    if not item or item.list_id != list_id:
        raise HTTPException(status_code=404, detail="Item niet gevonden")
    item.checked = not item.checked
    session.add(item)
    session.commit()
    session.refresh(item)
    return item_to_dict(item)


# ---------- Add recipes / staples ----------

@router.post("/lists/{list_id}/add-recipes")
def add_recipes_to_list(list_id: int, data: AddRecipesRequest, session: Session = Depends(get_session)):
    lst = session.get(ShoppingList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="Lijst niet gevonden")

    created = []
    for entry in data.recipes:
        recipe_id = entry.get("recipe_id")
        servings = entry.get("servings", 4)
        recipe = session.get(Recipe, recipe_id)
        if not recipe:
            continue

        scale = servings / recipe.default_servings if recipe.default_servings else 1
        ings = session.exec(
            select(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe_id)
        ).all()

        for ing in ings:
            scaled_amount = round(ing.amount * scale, 2) if ing.amount is not None else None
            item = ShoppingListItem(
                list_id=list_id,
                name=ing.name,
                amount=scaled_amount,
                unit=ing.unit,
                category=ing.category,
                supermarket=Supermarket.beide,
                source=recipe.name,
            )
            session.add(item)
            session.flush()
            created.append(item_to_dict(item))

    session.commit()
    return created


@router.post("/lists/{list_id}/add-staples")
def add_staples_to_list(list_id: int, session: Session = Depends(get_session)):
    lst = session.get(ShoppingList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="Lijst niet gevonden")

    staples = session.exec(select(StapleItem)).all()
    created = []
    for staple in staples:
        item = ShoppingListItem(
            list_id=list_id,
            name=staple.name,
            amount=staple.amount,
            unit=staple.unit,
            category=staple.category,
            supermarket=staple.supermarket,
            source="vast",
        )
        session.add(item)
        session.flush()
        created.append(item_to_dict(item))

    session.commit()
    return created


# ---------- Publish to GitHub Pages ----------

def _generate_html(lst: ShoppingList, items: List[ShoppingListItem]) -> str:
    date_str = ""
    if lst.date_from and lst.date_to:
        date_str = f"{lst.date_from.strftime('%d %b')} – {lst.date_to.strftime('%d %b %Y')}"
    elif lst.date_from:
        date_str = lst.date_from.strftime("%d %b %Y")

    # Group items by category (in canonical order)
    by_cat: dict = {cat: [] for cat in CATEGORIES}
    for item in items:
        cat = item.category if item.category in by_cat else "Overig"
        by_cat[cat].append(item)

    def supermarket_badge(sm: str) -> str:
        if sm == "aldi":
            return '<span class="badge badge-aldi">Aldi</span>'
        elif sm == "jumbo":
            return '<span class="badge badge-jumbo">Jumbo</span>'
        return '<span class="badge badge-beide">A+J</span>'

    def fmt_amount(amount, unit) -> str:
        if amount is None and unit is None:
            return ""
        parts = []
        if amount is not None:
            parts.append(str(int(amount) if amount == int(amount) else amount))
        if unit:
            parts.append(unit)
        return " ".join(parts)

    categories_html = ""
    for cat in CATEGORIES:
        cat_items = by_cat.get(cat, [])
        if not cat_items:
            continue
        items_html = ""
        for item in sorted(cat_items, key=lambda i: (i.supermarket, i.name)):
            amt = fmt_amount(item.amount, item.unit)
            label = f"{amt} {item.name}".strip() if amt else item.name
            badge = supermarket_badge(item.supermarket)
            source_note = f'<span class="source">{item.source}</span>' if item.source and item.source != "vast" else ""
            items_html += f"""
        <label class="item-label" for="item-{item.id}">
          <input type="checkbox" id="item-{item.id}" class="item-check">
          <span class="item-text">{label} {badge} {source_note}</span>
        </label>"""
        categories_html += f"""
    <section class="category">
      <h2>{cat}</h2>
      <div class="items">{items_html}
      </div>
    </section>"""

    return f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>🛒 {lst.name}</title>
  <style>
    :root {{
      --green: #2d6a4f;
      --green-light: #52b788;
      --aldi: #e63946;
      --jumbo: #f4a261;
      --bg: #f8f9fa;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: #222; }}
    header {{ background: var(--green); color: white; padding: 1rem 1.25rem; position: sticky; top: 0; z-index: 10; }}
    header h1 {{ font-size: 1.4rem; }}
    header p {{ font-size: 0.85rem; opacity: 0.85; margin-top: 0.2rem; }}
    main {{ max-width: 600px; margin: 0 auto; padding: 0.75rem; }}
    .category {{ background: white; border-radius: 10px; margin-bottom: 0.75rem; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
    .category h2 {{ background: var(--green-light); color: white; padding: 0.55rem 1rem; font-size: 0.95rem; font-weight: 600; }}
    .items {{ padding: 0.25rem 0; }}
    .item-label {{ display: flex; align-items: center; gap: 0.6rem; padding: 0.65rem 1rem; cursor: pointer; border-bottom: 1px solid #f0f0f0; }}
    .item-label:last-child {{ border-bottom: none; }}
    .item-check {{ width: 1.25rem; height: 1.25rem; accent-color: var(--green); flex-shrink: 0; cursor: pointer; }}
    .item-text {{ font-size: 1rem; transition: all 0.2s; }}
    .item-check:checked + .item-text {{ text-decoration: line-through; color: #aaa; }}
    .badge {{ display: inline-block; font-size: 0.65rem; font-weight: 700; padding: 0.1rem 0.35rem; border-radius: 4px; vertical-align: middle; margin-left: 0.25rem; }}
    .badge-aldi {{ background: var(--aldi); color: white; }}
    .badge-jumbo {{ background: var(--jumbo); color: white; }}
    .badge-beide {{ background: #6c757d; color: white; }}
    .source {{ font-size: 0.75rem; color: #888; font-style: italic; }}
    footer {{ text-align: center; padding: 1.5rem; font-size: 0.8rem; color: #aaa; }}
  </style>
</head>
<body>
  <header>
    <h1>🛒 {lst.name}</h1>
    {'<p>' + date_str + '</p>' if date_str else ''}
  </header>
  <main>{categories_html}
  </main>
  <footer>Boodschappen app</footer>
  <script>
    // Persist checkbox state in localStorage
    const KEY = 'boodschappen-{lst.id}';
    const saved = JSON.parse(localStorage.getItem(KEY) || '{{}}');
    document.querySelectorAll('.item-check').forEach(cb => {{
      if (saved[cb.id]) cb.checked = true;
      cb.addEventListener('change', () => {{
        saved[cb.id] = cb.checked;
        localStorage.setItem(KEY, JSON.stringify(saved));
      }});
    }});
  </script>
</body>
</html>"""


@router.post("/lists/{list_id}/publish")
async def publish_list(list_id: int, session: Session = Depends(get_session)):
    lst = session.get(ShoppingList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="Lijst niet gevonden")

    # Load config
    config_path = "config.json"
    if not os.path.exists(config_path):
        raise HTTPException(
            status_code=400,
            detail="config.json niet gevonden. Stel GitHub-configuratie in.",
        )
    with open(config_path) as f:
        config = json.load(f)

    token = config.get("github_token", "")
    owner = config.get("repo_owner", "")
    repo = config.get("repo_name", "")
    file_path = config.get("file_path", "boodschappen.html")

    if not all([token, owner, repo]):
        raise HTTPException(
            status_code=400,
            detail="GitHub configuratie onvolledig (token, owner, repo).",
        )

    # Generate HTML
    items = session.exec(
        select(ShoppingListItem).where(ShoppingListItem.list_id == list_id)
    ).all()
    html_content = _generate_html(lst, items)
    encoded = base64.b64encode(html_content.encode("utf-8")).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"

    async with httpx.AsyncClient(timeout=15) as client:
        # Check if file already exists (to get SHA for update)
        get_resp = await client.get(api_url, headers=headers)
        sha = None
        if get_resp.status_code == 200:
            sha = get_resp.json().get("sha")

        payload = {
            "message": f"Boodschappenlijst: {lst.name}",
            "content": encoded,
        }
        if sha:
            payload["sha"] = sha

        put_resp = await client.put(api_url, headers=headers, json=payload)

    if put_resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=502,
            detail=f"GitHub API fout: {put_resp.status_code} – {put_resp.text[:200]}",
        )

    # Build GitHub Pages URL
    pages_url = f"https://{owner}.github.io/{repo}/{file_path}"

    # Update published_url in DB
    lst.published_url = pages_url
    session.add(lst)
    session.commit()

    return {"url": pages_url}
