import requests
from recipe_scrapers import scrape_me  # Global Funktionen
urls = [
    "https://eatsmarter.de/rezepte/spaghetti-bolognese",
    "https://eatsmarter.de/rezepte/ofengemuese-mit-blumenkohl-und-kichererbsen-0",
    "https://eatsmarter.de/rezepte/bulgur-mit-gebratenem-gemuse"
]
for url in urls:
    try:
        scraper = scrape_me(url)  # Automatische Site-Erkennung
        data = {
            "url": url,
            "title": scraper.title(),
            "total_time": scraper.total_time(),
            "yields": scraper.yields(),
            "ingredients": scraper.ingredients(),
            "instructions": scraper.instructions()
        }
        print(data)
        print("=" * 50)
    except Exception as e:
        print(f"Fehler bei {url}: {e}")