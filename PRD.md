# PRD.md: KI-Essensplaner (sourcesavant/ki-essensplaner)

**Repo:** https://github.com/sourcesavant/ki-essensplaner
**Version:** 1.6 (Update: Phase 5 abgeschlossen, 01.02.2026)
**Entwickler:** sourcesavant (Windows 11, PyCharm Community, Python 3.12+)

## Projekt-Ziel
Automatisierter KI-Agent für personalisierte Wochenpläne: Lernt aus OneNote-Wochenplänen Vorlieben (Zutaten, Aufwand pro Tag), scrapt eatsmarter.de + andere Sites für passende Neue, generiert Pläne + Einkaufslisten. HA-integrierbar (MQTT/REST).

## Kern-Features (Priorisiert)
1. **Profil-basiertes Lernen (Content-Based Filtering)**: Analysiert OneNote-Pläne → Vorlieben (Zutaten-Frequenz/Häufigkeit, Aufwand-Klassen: quick/normal/long pro Wochentag/Slot).
2. **Intelligentes Rezept-Scouting**:
   - Sucht auf eatsmarter.de nach Matches mittels Playwright-Scraper
   - Scoring-Formel: Zutaten-Affinität (40%) + Zeit-Passung (25%) + Bioland-Verfügbarkeit (20%) + Saisonalität (15%)
   - Verfügbarkeits-Filter: Rezepte werden ausgeschlossen, wenn Hauptzutaten weder bei Bioland noch saisonal verfügbar sind
3. **Hybrider Wochenplaner**:
   - 7-Tage-Mix: 60% Favoriten (bereits gekochte Rezepte aus DB) + 40% Neue (von eatsmarter)
   - Hybrid-Suche: Slots werden gruppiert (schnelle Mittagessen vs. aufwändige Abendessen) für effiziente Suchanfragen
   - Detail-Nachladen: Zutaten-Details nur für Top-Kandidaten laden (Performance-Optimierung)
4. **Lernfunktion** Aktualisiert wöchentlich das Profil.
5. **Rückmeldung** User kann Rezepte bewerten. User kann Zutaten ausschließen. Rezepte mit dieser Zutat werden trotzdem berücksichtigt, wenn Zutat durch ähnliche Zutat ersetzt werden kann.
6. **Einkaufslisten**: Aggregierte Zutaten (Mengen, Kategorien).
7. **Integration**: HA-Dashboard.

## Tech-Stack
- Sprache: Python 3.12 (venv).
- KI: gpt-4o-mini (Scoring/Planung/Normalisierung), gpt-4o (Profil-Ableitung).
- Daten: SQLite (data/local/mealplanner.db), JSON (data/raw/all_recipes.json).
- DB-Tabellen: recipes, meal_plans, meals, parsed_ingredients, available_products, recipe_ratings, excluded_ingredients.
- Scraping: Playwright (eatsmarter.de Suche), recipe-scrapers (Rezept-Details), BeautifulSoup (bioland-huesgen.de).
- Importer: MS Graph API (OneNote).
- Tools: PyCharm, GitHub Projects/Issues, plugged.in MCP.

## Phasen & Issues

### Phase 1: Scrape-Test ✅
- Issue #1: eatsmarter.py Test-Scraper (3 URLs mit recipe-scrapers)

### Phase 2: OneNote-Merge ✅
- Issue #2: OneNote Importer (MS Graph API)

### Phase 3: DB + Profil (Vorlieben) ✅
- Issue #3: Rufe Rezepte von gespeicherten Links ab (Scraping der OneNote-URLs)
- Issue #4: Extrahiere Zutaten und Dauer von Rezepten
- Issue #5: Normalisiere Bezeichnung von Zutaten und Mengen
- Issue #6: Leite Vorlieben-Profil ab (TF-IDF für Zutaten, Aufwand-Klassen pro Wochentag/Slot)

### Phase 4: Planner + Search ✅
- Issue #10 ✅: Bioland Hüsgen Scraper (Verfügbarkeit saisonaler Produkte)
- Issue #12 ✅: Saisonalitäts-Modul (Kalender für deutsche Produkte)
- Issue #13 ✅: Eatsmarter Playwright Scraper (Rezeptsuche mit Zutaten-Filter)
- Issue #14 ✅: Rezept-Scoring-System
  - Gewichtete Formel: Zutaten-Affinität (40%) + Zeit-Passung (25%) + Bioland (20%) + Saison (15%)
  - Verfügbarkeits-Filter: Rezepte mit nicht-beschaffbaren Hauptzutaten werden ausgeschlossen
- Issue #15 ✅: Such-Agent für Rezept-Empfehlungen
  - **Hybrid-Suche**: 3 gruppierte Suchanfragen (quick/normal/elaborate)
  - **60/40-Mix**: 60% Favoriten aus DB + 40% neue von eatsmarter
  - **Detail-Nachladen**: Zutaten nur für Top-10 Kandidaten laden via recipe-scrapers

**Verwendung:**
```python
from src.agents import run_search_agent

result = run_search_agent()  # Volle Woche
result = run_search_agent(target_day="Mittwoch")  # Ein Tag
result = run_search_agent(target_day="Mittwoch", target_slot="Abendessen")  # Ein Slot

print(result.summary())
```

### Phase 5: Lernfunktion + Interaktion ✅
- Issue #16 ✅: Wöchentliche Profil-Aktualisierung (auto-update beim Agent-Start wenn >7 Tage alt)
- Issue #17 ✅: Rezept-Bewertungen (1-5 Sterne)
  - 1 Stern: Blacklist (Rezept ausgeschlossen)
  - 2 Sterne: -15% Score-Multiplikator
  - 3 Sterne: Neutral
  - 4 Sterne: +10% Score-Multiplikator
  - 5 Sterne: +20% Score-Multiplikator
- Issue #18 ✅: Zutaten-Ausschluss mit GPT-basierter Ersetzbarkeit
  - GPT-4o-mini prüft ob Zutat ersetzbar ist (Haupt- vs. Nebenzutat)
  - Nebenzutat: Rezept bleibt, Alternativen werden vorgeschlagen
  - Hauptzutat: Rezept wird ausgeschlossen
  - Ergebnisse werden gecached
- Bioland Auto-Update: Wöchentliche Aktualisierung der Produktverfügbarkeit beim Agent-Start

### Phase 6: Wochenplan + Einkaufslisten 🔜
- Issue #19: Erstelle Wochenplan
- Issue #20: Mache mehrere Vorschläge pro Slot für den Wochenplan
- Issue #21: Aggregiere Zutaten aus Wochenplan für Einkaufsliste (spezifisch, nicht generisch)
- Issue #22: Teile Einkauflisten auf für Bioland Hüsgen und Rewe

### Phase 7: Integration in HA-Dashboard 🔜
- User Interface (MQTT/REST API)

## User Stories
- Als User lade ich OneNote-Pläne hoch → Agent leitet Zutaten-Vorlieben + Aufwand-Profile ab.
- Als User sage "Wochenplan mit favorisierten Zutaten" → Suche + Plan mit Neuen von eatsmarter.de.
- Als HA-User sehe ich Pläne im Dashboard.

## AI-Instructions (für Claude/Cursor)
- Granular: Ein File pro Feature (src/profile/preferences.py).
- Output: Vollständige Python-Dateien + pip-Requirements + Tests.
- Profil: TF-IDF/Cosine für Zutaten, Counts für Aufwand pro Slot.
- Idempotent: UPSERT, Error-Handling.
- Libs: recipe-scrapers, pandas, msal, openai, scikit-learn (Similarity).

## Milestones (GitHub Projects)
- Week 1: Setup + Phase 1-2.
- Week 2: Phase 3 (Profil + Vorlieben-Ableitung).
- Week 3: Phase 4 (Search + Planner).

## Risiken & Constraints
- Azure Permissions (Notes.Read.All).
- Scraping-Limits: sleep(0.5), Multi-Site-Fallback.
- Budget: gpt-4o-mini (~0.15$/1M Tokens).
