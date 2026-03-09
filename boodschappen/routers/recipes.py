"""
/api/recipes  —  CRUD + import (foto, tekst, URL) + foto-beheer
"""
import asyncio
import base64
import json
import logging
import pathlib
import re
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from database import get_session
from models import Recipe, RecipeIngredient

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")

router = APIRouter()

# ── Foto-opslag ───────────────────────────────────────────────────
PHOTOS_DIR = pathlib.Path("data/photos")
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

EXT_FROM_MIME = {
    "image/jpeg": ".jpg",
    "image/jpg":  ".jpg",
    "image/png":  ".png",
    "image/webp": ".webp",
    "image/gif":  ".gif",
    "image/heic": ".heic",
    "image/heif": ".heic",
}


def get_photo_path(recipe_id: int) -> Optional[pathlib.Path]:
    """Return path to a recipe's photo file, or None if it doesn't exist."""
    for p in PHOTOS_DIR.glob(f"{recipe_id}.*"):
        return p
    return None


# ── Ollama config ─────────────────────────────────────────────────
OLLAMA_BASE       = "http://localhost:11434"
VISION_MODEL      = "qwen3-vl:8b"     # photo OCR
EXTRACTION_MODEL  = "qwen2.5:7b"      # recipe text → structured JSON (fast, no thinking)
THINKING_MODEL    = "qwen3.5:9b"      # chat, meal planning (reasoning tasks)

# ── Tags taxonomy ──────────────────────────────────────────────────
_AVAILABLE_TAGS = [
    # Maaltijdtype
    "Ontbijt", "Lunch", "Diner", "Snack", "Dessert", "Soep", "Bijgerecht", "Tussendoor",
    # Dieet
    "Vegetarisch", "Veganistisch", "Glutenvrij", "Lactosevrij", "Koolhydraatarm",
    # Keuken
    "Italiaans", "Aziatisch", "Nederlands", "Mexicaans", "Grieks", "Indiaas", "Frans",
    # Bereiding
    "Snel", "Makkelijk", "Oven", "Airfryer", "Slowcooker", "Barbecue", "Eenpan",
]

# ── Prompts ───────────────────────────────────────────────────────
_JSON_SCHEMA = """\
{
  "naam": "naam van het gerecht",
  "bron": "boektitel en/of paginanummer als zichtbaar, anders null",
  "porties": 4,
  "bereidingstijd": 30,
  "tags": ["Diner", "Italiaans"],
  "ingredienten": [
    {"naam": "ingredientnaam", "hoeveelheid": 250, "eenheid": "gr"},
    {"naam": "ingredientnaam", "hoeveelheid": null, "eenheid": null}
  ],
  "stappen": "Stap 1: ...\\nStap 2: ..."
}"""

_TAGS_LIST = ", ".join(_AVAILABLE_TAGS)

_JSON_RULES = f"""\
- hoeveelheid moet een getal zijn of null (nooit tekst zoals "twee"). Breuken als decimaal: 1/2 → 0.5, 3/4 → 0.75
- eenheid is de maateenheid (gr, ml, el, tl, stuks, takjes, snufje, etc.) of null
- Als het recept in een andere taal staat, vertaal naar het Nederlands
- Geef alle ingrediënten die je kunt lezen, ook als hoeveelheid ontbreekt
- porties is een geheel getal of null als niet vermeld
- bereidingstijd is het totaal aantal minuten (voorbereiding + kooktijd), geheel getal of null
- tags is een JSON-lijst met maximaal 5 tags die van toepassing zijn, kies uitsluitend uit: {_TAGS_LIST}
- Geef GEEN markdown code blocks, alleen pure JSON"""

# Two-step photo import: vision model does OCR only, text LLM does structured extraction
PHOTO_OCR_PROMPT = (
    "Lees ALLE tekst op deze foto van een receptpagina. "
    "Geef de volledige tekst terug — titel, ingrediënten, bereidingsstappen, "
    "porties, alles wat je kunt lezen. Gewone platte tekst, geen JSON, geen markdown.\n"
    "Bewaar de originele regelafbrekingen en structuur."
)

# Ask vision model to locate the dish photo for cropping
PHOTO_LOCATE_PROMPT = (
    "Bekijk deze foto van een kookboekpagina. "
    "Is er een foto van het bereide gerecht zichtbaar? "
    "Zo ja, geef de positie als JSON: "
    '{{"has_photo": true, "crop": [x1, y1, x2, y2]}} '
    "waarbij x1,y1 de linkerbovenhoek en x2,y2 de rechteronderhoek zijn, "
    "als percentage (0-100) van de beeldafmetingen. "
    "Zo nee: "
    '{{"has_photo": false}}\n'
    "Geef UITSLUITEND JSON terug, geen uitleg."
)

TEXT_IMPORT_PROMPT = (
    "Analyseer de volgende recepttekst en extraheer het recept. "
    "Geef UITSLUITEND een geldig JSON-object terug — geen uitleg, geen markdown, "
    f"alleen pure JSON.\n\nFormaat:\n{_JSON_SCHEMA}\n\nRegels:\n{_JSON_RULES}"
    "\n\nTEKST:\n"
)


# ── Browser-like headers for URL fetching ────────────────────────
URL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}


# ── Shared helpers ────────────────────────────────────────────────

def _parse_recipe_json(raw: str) -> dict:
    """Extract and normalise recipe JSON from a raw model response."""
    logger.info("Raw model response (%d chars): %s…", len(raw), raw[:500])

    # Strip <think>…</think> blocks (qwen3 models emit these before the answer)
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
    if len(cleaned) < len(raw.strip()):
        logger.info("Stripped thinking block (%d → %d chars)", len(raw.strip()), len(cleaned))
    raw = cleaned

    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$",          "", raw.strip())

    # Fix common JSON issues: bare fractions like 3/4 → 0.75
    raw = re.sub(r'(?<=:\s)(\d+)/(\d+)(?=\s*[,}\]])', lambda m: str(round(int(m.group(1))/int(m.group(2)), 4)), raw)

    # Find the first '{' and use raw_decode so trailing content is ignored
    start = raw.find("{")
    if start == -1:
        logger.warning("No JSON object found in model response: %s…", raw[:200])
        raise HTTPException(
            status_code=422,
            detail="Kon geen recept herkennen. Probeer een duidelijkere bron.",
        )
    try:
        data, _ = json.JSONDecoder().raw_decode(raw, start)
    except json.JSONDecodeError as e:
        logger.warning("JSON decode error at pos %d: %s | raw snippet: %s", start, e, raw[start:start+200])
        raise HTTPException(status_code=422, detail=f"Ongeldige JSON van model: {e}")

    if not isinstance(data, dict):
        logger.warning("Model returned JSON but not an object: %s", type(data).__name__)
        raise HTTPException(status_code=422, detail="Model gaf geen JSON-object terug.")

    data.setdefault("naam",        "Onbekend recept")
    data.setdefault("bron",        None)
    data.setdefault("porties",     4)
    data.setdefault("ingredienten", [])
    data.setdefault("stappen",     "")

    for ing in data["ingredienten"]:
        try:
            ing["hoeveelheid"] = (
                float(ing["hoeveelheid"]) if ing.get("hoeveelheid") is not None else None
            )
        except (ValueError, TypeError):
            ing["hoeveelheid"] = None
        # Auto-assign category if not already set
        if not ing.get("categorie") or ing["categorie"] == "Overig":
            ing["categorie"] = _guess_category(ing.get("naam", ""))

    # Normalise bereidingstijd → integer minutes or None
    raw_tijd = data.get("bereidingstijd")
    if isinstance(raw_tijd, (int, float)) and raw_tijd > 0:
        data["bereidingstijd"] = int(raw_tijd)
    elif isinstance(raw_tijd, str):
        m = re.search(r"\d+", raw_tijd)
        data["bereidingstijd"] = int(m.group()) if m else None
    else:
        data["bereidingstijd"] = None

    # Normalise tags → list of known tag strings
    raw_tags = data.get("tags", [])
    if isinstance(raw_tags, str):
        raw_tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    elif not isinstance(raw_tags, list):
        raw_tags = []
    data["tags"] = [str(t).strip() for t in raw_tags if str(t).strip() in _AVAILABLE_TAGS]

    logger.info("Parsed recipe '%s' with %d ingredients, %d tags, %s min",
                data["naam"], len(data["ingredienten"]), len(data["tags"]), data["bereidingstijd"])
    return data


async def _call_ollama_text(prompt: str, model: str = None) -> str:
    """Call Ollama with a plain-text prompt and return raw response content."""
    model = model or EXTRACTION_MODEL
    logger.info("Calling Ollama text model '%s' (prompt length: %d chars)", model, len(prompt))
    try:
        async with httpx.AsyncClient(timeout=600) as client:   # 10-minute timeout (model may need to load)
            resp = await client.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Ollama niet bereikbaar.")
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Ollama timeout (>10 min). Controleer of het model geladen is via: ollama list"
        )

    if resp.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model}' niet gevonden. Controleer: ollama list"
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Ollama fout {resp.status_code}")

    content = resp.json().get("message", {}).get("content", "")
    logger.debug("Ollama response (%d chars): %s…", len(content), content[:200])
    return content


def _parse_iso_duration(duration) -> Optional[int]:
    """Parse ISO 8601 duration (PT30M, PT1H30M, P0DT45M) → total minutes or None."""
    if not duration:
        return None
    s = str(duration).strip()
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?", s, re.IGNORECASE)
    if not m:
        return None
    days, hours, mins = (int(x or 0) for x in m.groups())
    total = days * 24 * 60 + hours * 60 + mins
    return total if total > 0 else None


def _is_recipe_type(t) -> bool:
    """Check if @type field (str or list) includes 'Recipe'."""
    if isinstance(t, list):
        return any("Recipe" in str(item) for item in t)
    return "Recipe" in str(t)


# ── Category auto-detection ──────────────────────────────────────
# Keyword → category mapping for Dutch grocery ingredients.
# Checked against lowercase ingredient name using word boundaries for
# short words (≤3 chars) and substring match for longer words.

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Groente & fruit": [
        "ui", "uien", "ajuin", "knoflook", "teen knoflook", "tomaat", "tomaten",
        "tomatjes", "paprika", "wortel", "wortelen", "peen", "aardappel",
        "aardappelen", "aardappels", "krieltjes", "sla", "spinazie",
        "broccoli", "bloemkool", "courgette", "aubergine", "champignon",
        "champignons", "prei", "prij", "prijen", "knolselderij", "selderij",
        "bieslook", "peterselie", "basilicum", "koriander", "munt", "dille",
        "rozemarijn", "tijm", "laurier", "gember", "citroen", "limoen",
        "sinaasappel", "appel", "banaan", "avocado", "komkommer", "radijs",
        "biet", "bieten", "mais", "doperwt", "doperwten", "sperzieboon",
        "sperziebonen", "snijboon", "snijbonen", "boontjes", "lente-ui",
        "bosui", "rode kool", "witte kool", "spitskool", "andijvie", "witlof",
        "venkel", "pastinaak", "rabarber", "aardbei", "aardbeien", "frambozen",
        "blauwe bessen", "druiven", "peer", "peren", "mango", "ananas",
        "pompoen", "rode peper", "groene peper", "chilipeper",
    ],
    "Vlees vis & vega": [
        "kip", "kipfilet", "kippenpoot", "kippenpoten", "kippenbouten",
        "kippendij", "gehakt", "rundergehakt", "half-om-half", "spek",
        "spekjes", "bacon", "ham", "hamschijf", "worst", "rookworst",
        "braadworst", "varkensvlees", "varkenshaas", "varkenspoot",
        "karbonades", "karbonade", "biefstuk", "entrecote", "spare ribs",
        "riblappen", "stoofvlees", "sucadelapjes", "ossenstaart",
        "zalm", "vis", "visfilet", "garnaal", "garnalen", "tonijn",
        "kabeljauw", "pangasius", "forel", "makreel", "haring", "mosselen",
        "tofu", "tempeh", "vegetarisch gehakt",
    ],
    "Zuivel & eieren": [
        "melk", "halfvolle melk", "volle melk", "room", "slagroom", "kookroom",
        "yoghurt", "kwark", "boter", "roomboter", "margarine", "ei", "eieren",
        "crème fraîche", "creme fraiche", "mascarpone", "ricotta", "zure room",
    ],
    "Kaas": [
        "kaas", "parmezaan", "parmezaanse", "mozzarella", "cheddar",
        "geitenkaas", "feta", "brie", "gruyère", "gruyere",
    ],
    "Brood & bakkerij": [
        "brood", "broodjes", "tortilla", "pita", "naan", "wraps",
        "croissant", "stokbrood", "pannenkoek",
    ],
    "Ontbijt & beleg": [
        "hagelslag", "pindakaas", "jam", "honing", "nutella",
        "muesli", "havermout", "cornflakes",
    ],
    "Pasta rijst & wereldkeuken": [
        "pasta", "spaghetti", "penne", "macaroni", "fusilli", "tagliatelle",
        "lasagne", "noedels", "noodles", "rijst", "couscous", "bulgur",
        "quinoa", "linzen", "spliterwten", "kikkererwten", "bonen",
        "kidneybonen", "witte bonen", "sojasaus", "ketjap", "sambal",
        "curry", "currypasta", "kokosmelk",
    ],
    "Soepen sauzen & conserven": [
        "bouillon", "bouillonblokje", "bouillonblokjes", "tomatenpuree",
        "passata", "gepelde tomaten", "saus", "ketchup", "mayonaise",
        "mosterd", "azijn", "olijfolie", "zonnebloemolie", "olie",
        "pesto",
    ],
    "Snacks & snoep": [
        "chips", "nootjes", "chocolade", "koek", "koekjes", "snoep", "drop",
    ],
    "Dranken": [
        "sap", "sinaasappelsap", "appelsap", "cola", "bier", "wijn",
        "koffie", "thee", "fris", "limonade",
    ],
}

# Pre-compile: split into short-word (regex boundary) and long-word (substring) lookups
_CAT_RULES: list[tuple[str, re.Pattern, list[str]]] = []
for _cat, _words in _CATEGORY_KEYWORDS.items():
    _short = [w for w in _words if len(w) <= 3]
    _long  = [w for w in _words if len(w) > 3]
    _pat = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in _short) + r")\b") if _short else None
    _CAT_RULES.append((_cat, _pat, _long))


def _guess_category(ingredient_name: str) -> str:
    """Guess a supermarket category from a Dutch ingredient name."""
    low = ingredient_name.lower().strip()
    for cat, short_pat, long_words in _CAT_RULES:
        if short_pat and short_pat.search(low):
            return cat
        for w in long_words:
            if w in low:
                return cat
    return "Overig"



def _parse_ingredient_string(s: str) -> dict:
    """Parse '250 gr bloem' or '3 eieren' into structured dict."""
    s = s.strip()
    num  = r"(\d+(?:[,.]\d+)?(?:\s*/\s*\d+)?)"
    unit = (
        r"(gr|gram|kg|ml|cl|dl|liter|l\b|el|eetlepels?|tl|theelepels?|"
        r"stuks?|stukken|takjes?|teentjes?|blikjes?|blik|pakjes?|pak|"
        r"snufjes?|scheutjes?|bosjes?|handjes?|plakjes?|plak|cups?|"
        r"ons|pond|el\.|tl\.)"
    )
    m = re.match(fr"^{num}\s*{unit}?\s+(.+)$", s, re.IGNORECASE)
    if m:
        amount_str, unit_str, name = m.groups()
        amount_str = amount_str.replace(",", ".").replace(" ", "")
        if "/" in amount_str:
            try:
                p = amount_str.split("/")
                amount = float(p[0]) / float(p[1])
            except Exception:
                amount = None
        else:
            try:
                amount = float(amount_str)
            except ValueError:
                amount = None
        return {
            "naam":        name.strip(),
            "hoeveelheid": amount,
            "eenheid":     unit_str.lower().rstrip(".") if unit_str else None,
        }
    return {"naam": s, "hoeveelheid": None, "eenheid": None}


def _extract_jsonld(html: str) -> Optional[dict]:
    """Try to extract a Recipe from JSON-LD embedded in the HTML page."""
    scripts = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>',
        html, re.IGNORECASE,
    )
    logger.info("Found %d JSON-LD script block(s)", len(scripts))

    for i, script in enumerate(scripts):
        try:
            data = json.loads(script.strip())
        except Exception as e:
            logger.debug("JSON-LD block %d parse error: %s", i, e)
            continue

        logger.debug("JSON-LD block %d type: %s", i, type(data).__name__)

        # Unwrap @graph or plain list
        if isinstance(data, dict) and "@graph" in data:
            data = data["@graph"]
        if isinstance(data, list):
            logger.debug("JSON-LD block %d is a list with %d items", i, len(data))
            data = next(
                (d for d in data if isinstance(d, dict) and _is_recipe_type(d.get("@type", ""))),
                None,
            )

        if isinstance(data, dict) and _is_recipe_type(data.get("@type", "")):
            logger.info("JSON-LD Recipe found: '%s'", data.get("name", "?"))
            result = _jsonld_to_recipe(data)
            logger.info("Extracted %d ingredients from JSON-LD", len(result.get("ingredienten", [])))
            return result

        logger.debug("JSON-LD block %d: @type = %s (not Recipe)", i, data.get("@type") if isinstance(data, dict) else "N/A")

    logger.info("No JSON-LD Recipe found in page")
    return None


def _jsonld_to_recipe(data: dict) -> dict:
    """Convert a JSON-LD Recipe object to our internal structure."""
    # Servings
    yield_val = data.get("recipeYield", "4")
    if isinstance(yield_val, list):
        yield_val = yield_val[0] if yield_val else "4"
    try:
        porties = int(re.search(r"\d+", str(yield_val)).group())
    except Exception:
        porties = 4

    # Ingredients
    raw_ings = data.get("recipeIngredient", [])
    logger.debug("JSON-LD recipeIngredient list (%d items): %s", len(raw_ings), raw_ings[:5])
    ings = [_parse_ingredient_string(s) for s in raw_ings]
    for ing in ings:
        ing["categorie"] = _guess_category(ing.get("naam", ""))

    # Steps
    instr = data.get("recipeInstructions", [])
    if isinstance(instr, str):
        stappen = instr
    elif isinstance(instr, list):
        parts = []
        for i, step in enumerate(instr):
            text = step.get("text", step) if isinstance(step, dict) else str(step)
            parts.append(f"Stap {i + 1}: {text.strip()}")
        stappen = "\n".join(parts)
    else:
        stappen = ""

    # Prep time: totalTime preferred, then cookTime + prepTime
    prep_time = None
    for field in ("totalTime", "cookTime", "prepTime"):
        val = data.get(field)
        if val:
            if isinstance(val, list):
                val = val[0]
            prep_time = _parse_iso_duration(val)
            if field == "totalTime" and prep_time:
                break
            elif field == "cookTime":
                # try to add prepTime
                pt = _parse_iso_duration(data.get("prepTime"))
                if pt:
                    prep_time = (prep_time or 0) + pt
                break
            elif prep_time:
                break

    return {
        "naam":           data.get("name", "Onbekend recept"),
        "bron":           data.get("url") or data.get("mainEntityOfPage") or None,
        "porties":        porties,
        "bereidingstijd": prep_time,
        "tags":           [],
        "ingredienten":   ings,
        "stappen":        stappen,
    }


def _clean_html(html: str) -> str:
    """Strip HTML to readable text for model analysis (fallback)."""
    # Remove tags with whole blocks of useless content
    for tag in ("script", "style", "nav", "footer", "header", "aside", "noscript",
                "svg", "iframe", "template", "link", "meta"):
        html = re.sub(fr"<{tag}[\s\S]*?</{tag}>", "", html, flags=re.IGNORECASE)
    # Remove self-closing script/link/meta
    html = re.sub(r"<(script|link|meta)[^>]*/?>", "", html, flags=re.IGNORECASE)
    # Convert structure to readable text
    html = re.sub(r"<br\s*/?>",     "\n",   html, flags=re.IGNORECASE)
    html = re.sub(r"<li[^>]*>",     "\n• ", html, flags=re.IGNORECASE)
    html = re.sub(r"<p[^>]*>",      "\n",   html, flags=re.IGNORECASE)
    html = re.sub(r"<h[1-6][^>]*>", "\n## ", html, flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>",       "",     html)
    # Collapse whitespace
    html = re.sub(r"\n{3,}",        "\n\n", html)
    html = re.sub(r"[ \t]+",        " ",    html)
    return html.strip()


_SPA_WARNING = (
    "⚠️ De website lijkt een JavaScript SPA te zijn zonder zichtbare recepttekst "
    "(minder dan 500 tekens na opschonen). Probeer de receptpagina te kopiëren en "
    "de tekst te plakken via 'Tekst plakken'."
)


# ── Pydantic schemas ──────────────────────────────────────────────

class IngredientCreate(BaseModel):
    name: str
    amount: Optional[float] = None
    unit: Optional[str] = None
    category: str = "Overig"


class RecipeCreate(BaseModel):
    name: str
    source: Optional[str] = None
    default_servings: int = 4
    steps: Optional[str] = None
    tags: Optional[str] = None
    prep_time: Optional[int] = None
    notes: Optional[str] = None
    ingredients: Optional[List[IngredientCreate]] = None


class RecipeUpdate(BaseModel):
    name: Optional[str] = None
    source: Optional[str] = None
    default_servings: Optional[int] = None
    steps: Optional[str] = None
    tags: Optional[str] = None
    prep_time: Optional[int] = None
    notes: Optional[str] = None


class TextImportRequest(BaseModel):
    text: str


class UrlImportRequest(BaseModel):
    url: str


# ── Dict helper ───────────────────────────────────────────────────

def recipe_to_dict(r: Recipe, include_ingredients: bool = False, session: Session = None):
    d = {
        "id":               r.id,
        "name":             r.name,
        "source":           r.source,
        "default_servings": r.default_servings,
        "steps":            r.steps,
        "tags":             r.tags,
        "prep_time":        r.prep_time,
        "notes":            r.notes,
        "created_at":       r.created_at.isoformat() if r.created_at else None,
        "has_photo":        get_photo_path(r.id) is not None,
    }
    if include_ingredients and session:
        ings = session.exec(
            select(RecipeIngredient).where(RecipeIngredient.recipe_id == r.id)
        ).all()
        d["ingredients"] = [
            {"id": i.id, "name": i.name, "amount": i.amount, "unit": i.unit, "category": i.category}
            for i in ings
        ]
    return d


# ── Endpoints ─────────────────────────────────────────────────────

@router.get("/recipes")
def list_recipes(session: Session = Depends(get_session)):
    recipes = session.exec(select(Recipe).order_by(Recipe.name)).all()
    return [recipe_to_dict(r) for r in recipes]


# NOTE: literal paths must come before /{recipe_id}

async def _call_ollama_vision(prompt: str, image_b64: str) -> str:
    """Call Ollama vision model with an image and return raw response content."""
    logger.info("Calling Ollama vision model '%s' (prompt: %d chars)", VISION_MODEL, len(prompt))
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model": VISION_MODEL,
                    "stream": False,
                    "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
                },
            )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Ollama niet bereikbaar. Start Ollama en zorg dat qwen3-vl:8b gedownload is.",
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Ollama timeout — probeer een kleinere afbeelding.")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Ollama fout {resp.status_code}: {resp.text[:200]}")

    content = resp.json().get("message", {}).get("content", "")
    # Strip thinking blocks
    content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
    logger.info("Vision response (%d chars): %s…", len(content), content[:300])
    return content


async def _try_extract_dish_photo(image_bytes: bytes, image_b64: str) -> Optional[tuple]:
    """Ask vision model to locate the dish photo; returns (cropped_bytes, ext) or None."""
    try:
        raw = await _call_ollama_vision(PHOTO_LOCATE_PROMPT, image_b64)
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())
        start = cleaned.find("{")
        if start == -1:
            return None
        data, _ = json.JSONDecoder().raw_decode(cleaned, start)
        if not data.get("has_photo") or not data.get("crop"):
            logger.info("No dish photo detected in image")
            return None

        crop = data["crop"]
        if len(crop) != 4:
            return None

        # Convert percentage coords to pixels and crop
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        x1 = int(crop[0] / 100 * w)
        y1 = int(crop[1] / 100 * h)
        x2 = int(crop[2] / 100 * w)
        y2 = int(crop[3] / 100 * h)
        logger.info("Cropping dish photo: (%d,%d)-(%d,%d) from %dx%d", x1, y1, x2, y2, w, h)

        cropped = img.crop((x1, y1, x2, y2))
        buf = io.BytesIO()
        cropped.save(buf, format="JPEG", quality=85)
        return buf.getvalue(), ".jpg"
    except ImportError:
        logger.warning("Pillow not installed — cannot crop dish photo")
        return None
    except Exception as e:
        logger.warning("Dish photo extraction failed (non-fatal): %s", e)
        return None


@router.post("/recipes/import-photo")
async def import_recipe_photo(file: UploadFile = File(...)):
    """Upload a recipe photo → vision OCR → text LLM extraction → dish photo crop."""
    logger.info("Photo import: filename=%s, content_type=%s", file.filename, file.content_type)
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Leeg bestand ontvangen.")
    logger.info("Photo size: %d bytes", len(image_bytes))

    b64 = base64.b64encode(image_bytes).decode()

    # Step 1: Vision model (qwen3-vl) does OCR — just reads the text
    ocr_text = await _call_ollama_vision(PHOTO_OCR_PROMPT, b64)
    if not ocr_text or len(ocr_text) < 20:
        raise HTTPException(status_code=422, detail="Kon geen tekst lezen op de foto.")
    logger.info("OCR extracted %d chars of text", len(ocr_text))

    # Step 2: Text model (qwen3.5) does full structured extraction
    #   OCR text is messy (titles, page numbers, sentences mixed in)
    #   — the text LLM understands context and can separate them properly
    prompt = TEXT_IMPORT_PROMPT + ocr_text[:8000]
    raw = await _call_ollama_text(prompt)
    result = _parse_recipe_json(raw)

    # Step 3: Try to extract dish photo from the cookbook page
    dish_photo = await _try_extract_dish_photo(image_bytes, b64)
    if dish_photo:
        result["_dish_photo"] = base64.b64encode(dish_photo[0]).decode()
        result["_dish_photo_ext"] = dish_photo[1]
        logger.info("Dish photo extracted (%d bytes)", len(dish_photo[0]))

    return result


@router.post("/recipes/import-text")
async def import_recipe_text(data: TextImportRequest):
    """Paste recipe text → text LLM does full extraction."""
    logger.info("Text import: %d chars", len(data.text))
    if not data.text.strip():
        raise HTTPException(status_code=400, detail="Lege tekst ontvangen.")

    prompt = TEXT_IMPORT_PROMPT + data.text[:8000]
    raw = await _call_ollama_text(prompt)
    return _parse_recipe_json(raw)


@router.post("/recipes/import-url")
async def import_recipe_url(data: UrlImportRequest):
    """Fetch recipe URL politely → JSON-LD → or model fallback."""
    url = data.url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    logger.info("URL import: %s", url)

    # Polite delay — don't look like a bot
    await asyncio.sleep(1.5)

    try:
        async with httpx.AsyncClient(
            timeout=20, follow_redirects=True, headers=URL_HEADERS
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.warning("HTTP error fetching %s: %s", url, e)
        raise HTTPException(status_code=502, detail=f"Website fout {e.response.status_code}")
    except httpx.ConnectError as e:
        logger.warning("Connect error fetching %s: %s", url, e)
        raise HTTPException(status_code=502, detail="Kan de website niet bereiken.")
    except httpx.TimeoutException:
        logger.warning("Timeout fetching %s", url)
        raise HTTPException(status_code=504, detail="Website reageert te traag.")

    html = resp.text
    logger.info("Fetched %d bytes from %s (final URL: %s)", len(html), url, str(resp.url))

    # 1) Try JSON-LD first — fast, no model needed
    recipe = _extract_jsonld(html)
    if recipe:
        logger.info("JSON-LD extraction succeeded: '%s', %d ingredients",
                    recipe.get("naam"), len(recipe.get("ingredienten", [])))
        return recipe

    # 2) Fallback: send cleaned text to model
    clean = _clean_html(html)
    logger.info("JSON-LD failed, falling back to model. Cleaned text: %d chars", len(clean))
    logger.debug("Cleaned text snippet: %s", clean[:500])

    # If the page has almost no content, it's likely a JS SPA — reject early
    if len(clean) < 500:
        logger.warning("Cleaned text too short (%d chars) — likely a JS SPA", len(clean))
        raise HTTPException(
            status_code=422,
            detail=_SPA_WARNING,
        )

    raw = await _call_ollama_text(TEXT_IMPORT_PROMPT + clean[:6000])
    result = _parse_recipe_json(raw)
    if not result.get("bron"):
        result["bron"] = url
    logger.info("Model fallback result: '%s', %d ingredients",
                result.get("naam"), len(result.get("ingredienten", [])))
    return result


@router.get("/recipes/{recipe_id}")
def get_recipe(recipe_id: int, session: Session = Depends(get_session)):
    recipe = session.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recept niet gevonden")
    return recipe_to_dict(recipe, include_ingredients=True, session=session)


@router.post("/recipes", status_code=201)
def create_recipe(data: RecipeCreate, session: Session = Depends(get_session)):
    recipe = Recipe(
        name=data.name, source=data.source,
        default_servings=data.default_servings,
        steps=data.steps, tags=data.tags, prep_time=data.prep_time, notes=data.notes,
    )
    session.add(recipe)
    session.flush()

    for ing_data in (data.ingredients or []):
        session.add(RecipeIngredient(
            recipe_id=recipe.id, name=ing_data.name,
            amount=ing_data.amount, unit=ing_data.unit, category=ing_data.category,
        ))

    session.commit()
    session.refresh(recipe)
    return recipe_to_dict(recipe, include_ingredients=True, session=session)


@router.put("/recipes/{recipe_id}")
def update_recipe(recipe_id: int, data: RecipeUpdate, session: Session = Depends(get_session)):
    recipe = session.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recept niet gevonden")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(recipe, field, value)
    session.add(recipe)
    session.commit()
    session.refresh(recipe)
    return recipe_to_dict(recipe, include_ingredients=True, session=session)


@router.delete("/recipes/{recipe_id}", status_code=204)
def delete_recipe(recipe_id: int, session: Session = Depends(get_session)):
    recipe = session.get(Recipe, recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recept niet gevonden")
    for ing in session.exec(select(RecipeIngredient).where(RecipeIngredient.recipe_id == recipe_id)).all():
        session.delete(ing)
    session.delete(recipe)
    session.commit()
    # Remove photo if present
    photo = get_photo_path(recipe_id)
    if photo:
        photo.unlink(missing_ok=True)
        logger.info("Deleted photo for recipe %d: %s", recipe_id, photo)


# ── Photo endpoints ───────────────────────────────────────────────

@router.post("/recipes/{recipe_id}/photo")
async def upload_recipe_photo(recipe_id: int, file: UploadFile = File(...),
                               session: Session = Depends(get_session)):
    """Upload or replace the photo for a recipe."""
    if not session.get(Recipe, recipe_id):
        raise HTTPException(status_code=404, detail="Recept niet gevonden")

    photo_bytes = await file.read()
    if not photo_bytes:
        raise HTTPException(status_code=400, detail="Leeg bestand ontvangen.")

    # Remove old photo (any extension)
    for old in PHOTOS_DIR.glob(f"{recipe_id}.*"):
        old.unlink(missing_ok=True)

    # Determine extension from content-type
    content_type = file.content_type or "image/jpeg"
    ext = EXT_FROM_MIME.get(content_type, ".jpg")
    photo_path = PHOTOS_DIR / f"{recipe_id}{ext}"
    photo_path.write_bytes(photo_bytes)

    logger.info("Saved photo for recipe %d: %s (%d bytes)", recipe_id, photo_path, len(photo_bytes))
    return {"ok": True, "has_photo": True}


@router.get("/recipes/{recipe_id}/photo")
def get_recipe_photo(recipe_id: int, session: Session = Depends(get_session)):
    """Serve the photo for a recipe."""
    if not session.get(Recipe, recipe_id):
        raise HTTPException(status_code=404, detail="Recept niet gevonden")

    photo = get_photo_path(recipe_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Geen foto voor dit recept.")

    mime_map = {
        ".jpg": "image/jpeg", ".png": "image/png",
        ".webp": "image/webp", ".gif": "image/gif", ".heic": "image/heic",
    }
    media_type = mime_map.get(photo.suffix.lower(), "image/jpeg")
    return FileResponse(photo, media_type=media_type)


@router.delete("/recipes/{recipe_id}/photo", status_code=204)
def delete_recipe_photo(recipe_id: int, session: Session = Depends(get_session)):
    """Delete the photo for a recipe."""
    if not session.get(Recipe, recipe_id):
        raise HTTPException(status_code=404, detail="Recept niet gevonden")
    photo = get_photo_path(recipe_id)
    if photo:
        photo.unlink(missing_ok=True)
        logger.info("Deleted photo for recipe %d", recipe_id)


@router.post("/recipes/{recipe_id}/ingredients", status_code=201)
def add_ingredient(recipe_id: int, data: IngredientCreate, session: Session = Depends(get_session)):
    if not session.get(Recipe, recipe_id):
        raise HTTPException(status_code=404, detail="Recept niet gevonden")
    ing = RecipeIngredient(recipe_id=recipe_id, **data.model_dump())
    session.add(ing)
    session.commit()
    session.refresh(ing)
    return {"id": ing.id, "name": ing.name, "amount": ing.amount, "unit": ing.unit, "category": ing.category}


@router.put("/recipes/{recipe_id}/ingredients/{ing_id}")
def update_ingredient(recipe_id: int, ing_id: int, data: IngredientCreate, session: Session = Depends(get_session)):
    ing = session.get(RecipeIngredient, ing_id)
    if not ing or ing.recipe_id != recipe_id:
        raise HTTPException(status_code=404, detail="Ingrediënt niet gevonden")
    for field, value in data.model_dump().items():
        setattr(ing, field, value)
    session.add(ing)
    session.commit()
    session.refresh(ing)
    return {"id": ing.id, "name": ing.name, "amount": ing.amount, "unit": ing.unit, "category": ing.category}


@router.delete("/recipes/{recipe_id}/ingredients/{ing_id}", status_code=204)
def delete_ingredient(recipe_id: int, ing_id: int, session: Session = Depends(get_session)):
    ing = session.get(RecipeIngredient, ing_id)
    if not ing or ing.recipe_id != recipe_id:
        raise HTTPException(status_code=404, detail="Ingrediënt niet gevonden")
    session.delete(ing)
    session.commit()
