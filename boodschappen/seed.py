from sqlmodel import Session, select
from database import engine
from models import Recipe, RecipeIngredient, StapleItem, Supermarket


def seed_database():
    with Session(engine) as session:
        # Only seed if DB is empty
        existing = session.exec(select(StapleItem)).first()
        if existing:
            return

        # --- Staple items ---
        staples = [
            StapleItem(
                name="Volle melk",
                amount=2,
                unit="liter",
                category="Zuivel & eieren",
                supermarket=Supermarket.jumbo,
                notes="Altijd nodig",
            ),
            StapleItem(
                name="Brood",
                amount=1,
                unit="stuks",
                category="Brood & bakkerij",
                supermarket=Supermarket.beide,
            ),
            StapleItem(
                name="Eieren",
                amount=10,
                unit="stuks",
                category="Zuivel & eieren",
                supermarket=Supermarket.aldi,
            ),
            StapleItem(
                name="Boter",
                amount=250,
                unit="gr",
                category="Zuivel & eieren",
                supermarket=Supermarket.jumbo,
            ),
            StapleItem(
                name="Sinaasappelsap",
                amount=1,
                unit="liter",
                category="Dranken",
                supermarket=Supermarket.aldi,
            ),
        ]
        for item in staples:
            session.add(item)

        # --- Example recipe ---
        recipe = Recipe(
            name="Spaghetti bolognese",
            source="Allerhande",
            default_servings=4,
            steps=(
                "1. Snipper de ui fijn en hak de knoflook.\n"
                "2. Bak in olijfolie op middelhoog vuur tot glazig.\n"
                "3. Voeg rundergehakt toe en bak rul en bruin.\n"
                "4. Voeg tomatenpuree toe en roer 1 minuut mee.\n"
                "5. Voeg gepelde tomaten, oregano en laurierblad toe.\n"
                "6. Laat 30 minuten sudderen op laag vuur. Breng op smaak.\n"
                "7. Kook spaghetti al dente.\n"
                "8. Serveer met versgeraspte Parmezaanse kaas."
            ),
            tags="pasta,vlees,italiaans",
            notes="Lekker met een glas rode wijn. Saus kan van tevoren gemaakt worden en is de volgende dag nog beter.",
        )
        session.add(recipe)
        session.flush()  # assigns recipe.id

        ingredients = [
            RecipeIngredient(recipe_id=recipe.id, name="Spaghetti", amount=400, unit="gr", category="Pasta rijst & wereldkeuken"),
            RecipeIngredient(recipe_id=recipe.id, name="Rundergehakt", amount=500, unit="gr", category="Vlees vis & vega"),
            RecipeIngredient(recipe_id=recipe.id, name="Ui", amount=2, unit="stuks", category="Groente & fruit"),
            RecipeIngredient(recipe_id=recipe.id, name="Knoflook", amount=3, unit="teentjes", category="Groente & fruit"),
            RecipeIngredient(recipe_id=recipe.id, name="Tomatenpuree", amount=2, unit="el", category="Soepen sauzen & conserven"),
            RecipeIngredient(recipe_id=recipe.id, name="Gepelde tomaten (blik)", amount=400, unit="gr", category="Soepen sauzen & conserven"),
            RecipeIngredient(recipe_id=recipe.id, name="Gedroogde oregano", amount=1, unit="tl", category="Soepen sauzen & conserven"),
            RecipeIngredient(recipe_id=recipe.id, name="Laurierblad", amount=2, unit="stuks", category="Soepen sauzen & conserven"),
            RecipeIngredient(recipe_id=recipe.id, name="Parmezaanse kaas", amount=50, unit="gr", category="Kaas"),
            RecipeIngredient(recipe_id=recipe.id, name="Olijfolie", amount=2, unit="el", category="Overig"),
        ]
        for ing in ingredients:
            session.add(ing)

        session.commit()
        print("Database seeded with sample data.")
