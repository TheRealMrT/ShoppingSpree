from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database import create_db_and_tables
from routers import items, lists, recipes, chat, family


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    from seed import seed_database
    seed_database()
    yield


app = FastAPI(
    title="Boodschappen",
    description="Lokale boodschappenplanner",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(recipes.router, prefix="/api", tags=["recepten"])
app.include_router(lists.router, prefix="/api", tags=["lijsten"])
app.include_router(items.router, prefix="/api", tags=["artikelen"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(family.router, prefix="/api", tags=["familie"])

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def read_root():
    return FileResponse("static/index.html")
