# PRD.md: KI-Essensplaner (sourcesavant/ki-essensplaner)

**Repo:** https://github.com/sourcesavant/ki-essensplaner
**Version:** 2.4 (Update: Issue #31 implementiert - Multi-Day Meal Prep (Vorkochen), 03.02.2026)
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

### Phase 6: Wochenplan + Einkaufslisten ✅
- Issue #19 ✅: Wochenplan mit User-Auswahl
  - 5 Vorschläge pro Slot (14 Slots = 7 Tage × 2 Mahlzeiten)
  - `selected_index` für User-Auswahl (Default: Top-Rezept)
  - JSON-Export für HA-Integration vorbereitet
  - Persistenz in `data/local/weekly_plan.json`
- Issue #20 ✅: (kombiniert mit #19)
- Issue #21 ✅: Einkaufsliste aggregieren
  - Gruppierung nach `name_normalized` (spezifisch, nicht generisch)
  - Mengen mit gleicher Einheit werden addiert
  - Verschiedene Einheiten bleiben separat
- Issue #22 ✅: Aufteilen Bioland/Rewe
  - Bioland-Verfügbarkeit über `available_products` Tabelle
  - Matching mit Synonymen und Fuzzy-Match

**Verwendung:**
```python
from src.agents import run_search_agent, load_weekly_plan
from src.shopping import generate_shopping_list

# Wochenplan generieren
plan = run_search_agent()

# Oder gespeicherten Plan laden
plan = load_weekly_plan()

# User wählt Rezept für Slot (Index 0-4)
plan.select_recipe("Montag", "Abendessen", 1)

# Einkaufsliste generieren
shopping_list = generate_shopping_list(plan)
print(shopping_list)

# Nach Store aufteilen
split = shopping_list.split_by_store()
print(split)  # Bioland + Rewe Listen
```

### Phase 7: Integration in HA-Dashboard 🏗️

**Architektur-Entscheidungen:**
- REST API (FastAPI) - MQTT später bei Bedarf
- Lokales Add-on (privates Repo, kein HACS)
- Ein Haushaltsprofil (kein Multi-User)
- Offline-Caching im Custom Component

**Issues:**
- Issue #23 ✅: API-Layer + Add-on Grundgerüst
  - FastAPI mit uvicorn, Token-Auth (Bearer)
  - 11 neue Endpoints: Wochenplan (4), Einkaufsliste (2), Rezepte (5)
  - Lokales Add-on in `/addons/ki_essensplaner/` mit DOCS.md
  - Custom Component in `custom_components/ki_essensplaner/`
  - `sensor.essensplaner_api_status` mit Offline-Caching
  - Background Tasks für async Plan-Generierung (30-120 Sek.)
  - On-Demand Shopping List Generierung

**API Verwendung:**
```bash
# Wochenplan generieren (async)
curl -X POST -H "Authorization: Bearer <TOKEN>" \
  http://localhost:8099/api/weekly-plan/generate

# Wochenplan abrufen
curl -H "Authorization: Bearer <TOKEN>" \
  http://localhost:8099/api/weekly-plan

# Rezept auswählen
curl -X POST -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"weekday":"Montag","slot":"Abendessen","recipe_index":1}' \
  http://localhost:8099/api/weekly-plan/select

# Einkaufsliste (nach Store aufgeteilt)
curl -H "Authorization: Bearer <TOKEN>" \
  http://localhost:8099/api/shopping-list/split

# Rezept bewerten
curl -X POST -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"rating":5}' \
  http://localhost:8099/api/recipes/123/rate

# Zutat ausschließen
curl -X POST -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"ingredient_name":"zwiebeln"}' \
  http://localhost:8099/api/ingredients/exclude
```

- Issue #24 ✅: Onboarding
  - 5 API Endpoints für Setup-Flow
  - Multi-Step Config Flow in Home Assistant
  - Onboarding Status-Check (Azure, OneNote, Import, Profil)
  - OneNote Authentifizierungsstatus
  - Notizbuch-Auswahl und Import
  - Initiale Profil-Generierung
  - Azure App Registration Dokumentation

**Onboarding Flow:**
```bash
# 1. Status prüfen
curl -H "Authorization: Bearer <TOKEN>" \
  http://localhost:8099/api/onboarding/status

# 2. OneNote Auth (via CLI)
python -m src.importers.onenote auth

# 3. Notizbücher auflisten
curl -H "Authorization: Bearer <TOKEN>" \
  http://localhost:8099/api/onboarding/onenote/notebooks

# 4. Daten importieren
curl -X POST -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"notebook_ids": ["<ID>"]}' \
  http://localhost:8099/api/onboarding/import

# 5. Profil generieren
curl -X POST -H "Authorization: Bearer <TOKEN>" \
  http://localhost:8099/api/onboarding/profile/generate
```

- Issue #25 ✅: Konfigurationsmodul
  - 4 Home Assistant Services implementiert
  - 3 neue Sensoren für Profil-Monitoring
  - services.yaml mit vollständiger Dokumentation
  - Vollständige DE-Übersetzungen

**Services:**
```yaml
# Rezept bewerten
service: ki_essensplaner.rate_recipe
data:
  recipe_id: 123
  rating: 5

# Zutat ausschließen
service: ki_essensplaner.exclude_ingredient
data:
  ingredient_name: "zwiebeln"

# Ausschluss entfernen
service: ki_essensplaner.remove_ingredient_exclusion
data:
  ingredient_name: "zwiebeln"

# Profil aktualisieren
service: ki_essensplaner.refresh_profile
```

**Sensoren:**
- `sensor.essensplaner_api_status` - API Status (bereits vorhanden)
- `sensor.essensplaner_profile_status` - Profil-Status (current/outdated/missing)
- `sensor.essensplaner_top_ingredients` - Top 10 Lieblingszutaten
- `sensor.essensplaner_excluded_ingredients` - Ausgeschlossene Zutaten

- Issue #26 ✅: Wochenplanmodul
  - 3 Home Assistant Services für Wochenplan
  - 16 neue Sensoren (1 Status + 14 Slots + 1 Nächste Mahlzeit)
  - Vollständige Wochenplan-Verwaltung über HA
  - Vollständige DE-Übersetzungen

**Services:**
```yaml
# Wochenplan generieren (async, 30-120 Sek.)
service: ki_essensplaner.generate_weekly_plan

# Rezept auswählen
service: ki_essensplaner.select_recipe
data:
  weekday: "Montag"
  slot: "Abendessen"
  recipe_index: 2

# Wochenplan löschen
service: ki_essensplaner.delete_weekly_plan
```

**Sensoren:**
- `sensor.essensplaner_weekly_plan_status` - Plan-Status (active/no_plan)
- `sensor.essensplaner_montag_mittagessen` - Montag Mittagessen
- `sensor.essensplaner_montag_abendessen` - Montag Abendessen
- ... (14 Slot-Sensoren total)
- `sensor.essensplaner_next_meal` - Nächste anstehende Mahlzeit

**Sensor-Attributes:**
- `recipe_id`, `recipe_url`, `prep_time_minutes`, `calories`
- `score`, `is_new`, `alternatives`, `selected_index`
- `ingredients` (Liste)

- Issue #27: Einkaufslistenmodul
  - OneNote-Zugriff konfigurieren
  - Notizbücher auswählen
  - Erste Profilerstellung
- Issue #25: Konfigurationsmodul
  - Rezept-Bewertung Service (`ki_essensplaner.rate_recipe`)
  - Zutaten-Ausschluss Service (`ki_essensplaner.exclude_ingredient`)
  - Profil-Sensoren (Alter, Top-Zutaten, Ausschlüsse)
- Issue #26: Wochenplanmodul
  - Plan generieren/laden Services
  - 14 Slot-Sensoren (Mo-So × Mittag/Abend)
  - `sensor.essensplaner_naechste_mahlzeit`
  - Kalender-Integration (optional)
- Issue #27: Einkaufslistenmodul
  - Einkaufsliste generieren Service
  - Sensoren für Bioland/Rewe Anzahl
  - Todo-Listen Sync
- Issue #28: Automatisierungen & Events
  - Events für HA-Automations (plan_generated, shopping_list_ready, etc.)
  - Automation Blueprints
  - Persistente Notifications
- Issue #29: Lovelace Cards
  - Wochenplan-Card (7×2 Grid, Rezeptauswahl)
  - Einkaufslisten-Card (Tabs Bioland/Rewe, Checkboxen)

### Phase 8: Personalisierung 🏗️

**Features:**
- Haushaltsgröße konfigurierbar
- Automatische Rezept-Skalierung
- Vorkochen für mehrere Tage (Meal Prep)

**Issues:**
- Issue #30 ✅: Portionenanzahl & automatische Rezept-Skalierung
  - Haushaltsgröße konfigurieren (1-10 Personen)
  - `servings`-Feld in Rezepten (via recipe-scrapers)
  - Automatische Mengen-Skalierung in Einkaufsliste
  - Skalierungs-Info für Transparenz (`scale_info`)
  - Rundung auf sinnvolle Werte (10g, ganze Stück, 0.5 EL)
  - API: `GET/PUT /api/config`, `GET /api/config/household-size`
  - HA: `sensor.essensplaner_household_size` + `ki_essensplaner.set_household_size`
  - Config-Persistenz in `data/local/config.json`

- Issue #31 ✅: Vorkochen für mehrere Tage (Meal Prep)
  - Multi-Day Gruppen (primary_weekday/slot + reuse_slots)
  - Slot-Types: Primary Slots (mit prep_days) + Reuse Slots (is_reuse_slot)
  - Automatische Mengen-Multiplikation in Einkaufsliste
  - Transparenz: multi_day_info mit cook_on/eat_on/total_days/multiplier
  - API: `POST/DELETE/GET /api/weekly-plan/multi-day`
  - HA: `ki_essensplaner.set_multi_day` (reuse_days Parameter) + `ki_essensplaner.clear_multi_day`
  - Sensoren: `sensor.essensplaner_multi_day_overview` + dynamische Icons (Leftovers)
  - JSON-Persistenz mit Serialisierung von multi_day_groups

**Beispiel Meal Prep:**
```
Sonntag Abendessen: Lasagne (Kochtag, 3x Menge)
  → Montag Abendessen: [Lasagne von Sonntag]
  → Dienstag Abendessen: [Lasagne von Sonntag]
```

**Verwendung:**
```bash
# Haushaltsgröße setzen
curl -X PUT -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"household_size": 4}' \
  http://localhost:8099/api/config

# Vorkochen konfigurieren
curl -X POST -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "primary_weekday": "Sonntag",
    "primary_slot": "Abendessen",
    "reuse_slots": [
      {"weekday": "Montag", "slot": "Abendessen"},
      {"weekday": "Dienstag", "slot": "Abendessen"}
    ]
  }' \
  http://localhost:8099/api/weekly-plan/multi-day
```

**Installation (privates Repo):**
```bash
# Auf Home Assistant
cd /addons && git clone <repo> ki_essensplaner
# Add-on über UI installieren
# Custom Component nach /config/custom_components/ kopieren
```

## User Stories
- Als User lade ich OneNote-Pläne hoch → Agent leitet Zutaten-Vorlieben + Aufwand-Profile ab.
- Als User sage "Wochenplan mit favorisierten Zutaten" → Suche + Plan mit Neuen von eatsmarter.de.
- Als HA-User sehe ich Pläne im Dashboard.
- Als User konfiguriere ich meine Haushaltsgröße → Einkaufsliste skaliert Mengen automatisch.
- Als User markiere ich Sonntags-Lasagne als "Vorkochen für 3 Tage" → Einkaufsliste enthält 3x Menge, Mo+Di zeigen "Lasagne von Sonntag".

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
