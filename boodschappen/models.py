from sqlmodel import Field, SQLModel, Relationship
from typing import Optional, List
from datetime import datetime, date
from enum import Enum

CATEGORIES = [
    "Groente & fruit",
    "Vlees vis & vega",
    "Zuivel & eieren",
    "Kaas",
    "Brood & bakkerij",
    "Ontbijt & beleg",
    "Pasta rijst & wereldkeuken",
    "Soepen sauzen & conserven",
    "Snacks & snoep",
    "Dranken",
    "Diepvries",
    "Persoonlijke verzorging",
    "Huishouden & schoonmaak",
    "Overig",
]

CATEGORY_ORDER = {cat: i for i, cat in enumerate(CATEGORIES)}


class Supermarket(str, Enum):
    aldi = "aldi"
    jumbo = "jumbo"
    beide = "beide"


class Recipe(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    source: Optional[str] = None
    default_servings: int = Field(default=4)
    steps: Optional[str] = None
    tags: Optional[str] = None
    prep_time: Optional[int] = None  # bereidingstijd in minuten
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    ingredients: List["RecipeIngredient"] = Relationship(
        back_populates="recipe",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class RecipeIngredient(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    recipe_id: int = Field(foreign_key="recipe.id")
    name: str
    amount: Optional[float] = None
    unit: Optional[str] = None
    category: str = Field(default="Overig")

    recipe: Optional[Recipe] = Relationship(back_populates="ingredients")


class ShoppingList(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    notes: Optional[str] = None
    published_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    items: List["ShoppingListItem"] = Relationship(
        back_populates="shopping_list",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class ShoppingListItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    list_id: int = Field(foreign_key="shoppinglist.id")
    name: str
    amount: Optional[float] = None
    unit: Optional[str] = None
    category: str = Field(default="Overig")
    supermarket: Supermarket = Field(default=Supermarket.beide)
    checked: bool = Field(default=False)
    source: Optional[str] = None

    shopping_list: Optional[ShoppingList] = Relationship(back_populates="items")


class StapleItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    amount: Optional[float] = None
    unit: Optional[str] = None
    category: str = Field(default="Overig")
    supermarket: Supermarket = Field(default=Supermarket.beide)
    notes: Optional[str] = None


class FamilyMember(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    birthdate: Optional[date] = None
    dietary_restrictions: Optional[str] = None  # kommagescheiden bijv. "vegetarisch,lactosevrij"
    allergies: Optional[str] = None              # bijv. "noten,gluten"
    likes: Optional[str] = None                  # bijv. "pasta,Aziatisch"
    dislikes: Optional[str] = None               # bijv. "spruitjes,champignons"
    notes: Optional[str] = None
