# Codebase Overview

Last reviewed: 2026-06-28
Repository: `ki-essensplaner`
Branch state at review: `master` tracking `origin/master`, latest seen commit `6d6609a`

## Purpose

This project is a Python/FastAPI meal-planning backend plus a Home Assistant custom integration/add-on. It imports meal history from OneNote, builds a preference profile, scrapes and scores recipes, generates weekly meal plans, and exposes Home Assistant sensors/services plus Lovelace cards for plan selection, shopping lists, and recipe history.

## Top-Level Layout

- `src/`: Python application code.
- `src/api/`: FastAPI app, auth, schemas, routers.
- `src/agents/`: weekly recommendation model and recipe search orchestration.
- `src/core/`: config, SQLite database access, user config persistence.
- `src/importers/`: OneNote import via Microsoft Graph/MSAL.
- `src/profile/`: ingredient parsing, categorization, pseudo-recipes, preference profile generation.
- `src/scoring/`: recipe scoring, availability, seasonality rules.
- `src/scrapers/`: recipe and shop scrapers, especially EatSmarter and Bioland Huesgen.
- `src/shopping/`: shopping-list generation and Bioland/Rewe splitting.
- `custom_components/ki_essensplaner/`: Home Assistant integration.
- `dist/`: built JS cards/assets for Home Assistant/Lovelace and backend-served UI.
- `ki_essensplaner/`: Home Assistant add-on packaging (`Dockerfile`, `run.sh`, docs, requirements).
- `tests/`: pytest tests focused on config and recipe rotation.
- `scripts/`: older/manual issue test scripts and migrations.

## Runtime Entry Points

- API server: `python -m src.api`
- FastAPI app: `src/api/main.py`
  - Startup lifespan runs `migrate_db_if_needed()` then `init_db()`.
  - Routers are mounted directly; config router is included both without and with `/api` prefix.
- Add-on image: `ki_essensplaner/Dockerfile`
  - Installs Python/Chromium/git.
  - Installs `ki_essensplaner/requirements.txt`.
  - Clones this GitHub repo into `/app/app` during image build.
  - `run.sh` starts the app in the add-on environment.
- HA integration: `custom_components/ki_essensplaner/__init__.py`
  - Creates `EssensplanerCoordinator`.
  - Registers sensors and services.

## Configuration And Data

- Core filesystem config: `src/core/config.py`
  - `DATA_DIR` comes from env or defaults to repo `data/`.
  - SQLite path is `DATA_DIR/local/mealplanner.db`.
  - `.env` is loaded from repo root.
  - Azure config uses `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` default `consumers`, scopes `Notes.Read`, `User.Read`.
- API config: `src/api/config.py`
  - Defaults: host `0.0.0.0`, port `8099`, bearer token from `API_TOKEN`.
- User config: `src/core/user_config.py`
  - Stored in `DATA_DIR/local/config.json`.
  - Holds household size, rotation policy, multi-day preferences, skipped slots.

## Database

SQLite schema lives in `src/core/database.py`. Main tables:

- `recipes`: scraped/imported recipe metadata and ingredients JSON.
- `meal_plans`: imported or HA-completed weeks.
- `meals`: individual slots tied to meal plans and recipes.
- `parsed_ingredients`: normalized recipe ingredients.
- `available_products`: shop availability from Bioland.
- `recipe_ratings`: 1-5 star ratings, with 1-star used as blacklist.
- `excluded_ingredients`: global ingredient exclusions.
- `shopping_checked_items`: persistent checked state for shopping list rows.

Important behavior:

- `migrate_db_if_needed()` copies legacy `data/local/mealplanner.db` to `DATA_DIR` if target has no meaningful data.
- Many CRUD helpers return Pydantic/domain models.
- Recipe history for rotation uses completed HA weeks (`ha-week-*`) and `week_start`.

## API Routers

Core endpoints:

- `/api/health`, `/api/db-status`: health and DB diagnostics.
- `/api/profile`, `/api/profile/refresh`: preference profile.
- `/api/config`, `/api/config/household-size`: household and rotation config.
- `/api/onboarding/*`: Azure/OneNote device auth, notebook listing, import, profile generation.
- `/api/weekly-plan`: get/delete current plan.
- `/api/weekly-plan/generate`: background plan generation.
- `/api/weekly-plan/complete`: persist selected meals, optionally generate next plan.
- `/api/weekly-plan/select`: select an alternative by index.
- `/api/weekly-plan/select-url`: scrape/select a custom recipe URL.
- `/api/weekly-plan/history`: completed week history.
- `/api/weekly-plan/multi-day*`: meal-prep/reuse configuration.
- `/api/weekly-plan/skip-slots`: persisted slot exclusions for generation.
- `/api/shopping-list`, `/api/shopping-list/split`, `/api/shopping-list/checked`: shopping list and checked-state API.
- `/api/recipes/*`: ratings, recipe book, recipe fetching.
- `/api/ingredients/*`: excluded ingredient management.
- `/api/bioland/products`: available shop products.
- `/api/seasonality/{month}`: seasonal ingredient info.
- `/recipe-book`: backend-served HTML UI from `src/api/routers/ui.py`.

Auth:

- Protected routes use `verify_token` from `src/api/auth.py` and expect `Authorization: Bearer <API_TOKEN>`.

## Weekly Plan Flow

Main model file: `src/agents/models.py`

- `ScoredRecipe`: recommendation candidate with score, URL, DB id, ingredients, servings.
- `SlotRecommendation`: one weekday/meal slot, recommendations, selected index, multi-day metadata.
- `MultiDayGroup`: primary slot plus reuse slots.
- `WeeklyRecommendation`: full plan, serialization, selection, multi-day helpers.
- Saved plan JSON path is managed in this module.

Generation orchestration: `src/agents/recipe_search_agent.py`

High-level flow in `run_search_agent()`:

1. Load or refresh preference profile.
2. Load or refresh Bioland availability.
3. Load ratings, blacklist, excluded ingredients.
4. Load recent completed-week history for rotation.
5. Build scoring context.
6. Determine slots, respecting skipped slots.
7. Score favorites from DB.
8. Build EatSmarter search queries from profile, seasonality, cuisine rotation.
9. Search new recipes and load details for top candidates.
10. Filter by rotation and banned URLs.
11. Assign recipes to slots, avoid duplicates, top up alternatives.
12. Apply multi-day preferences.
13. Save `WeeklyRecommendation`.

Rotation defaults:

- `no_repeat_weeks`: 1
- `favorite_min_return_weeks`: 3
- `favorite_return_bonus_per_week`: 2.0
- `favorite_return_bonus_max`: 10.0

Note: tests currently expect only selected last-plan recipes to be banned, but `_get_last_plan_recipe_keys()` in current code comments/logic appears to collect all recommendations. Re-check before changing rotation behavior.

## Scoring And Profile

- `src/profile/preference_profile.py` builds profile from meal history and parsed ingredients.
- `src/profile/ingredient_parser.py` parses quantity/unit/name from ingredient strings.
- `src/profile/ingredient_categorizer.py` has cached ingredient normalization/categorization.
- `src/profile/pseudo_recipes.py` provides pseudo ingredients for meals without full recipes.
- `src/scoring/recipe_scorer.py` combines:
  - ingredient affinity,
  - prep-time compatibility,
  - Bioland availability,
  - seasonality,
  - ratings/blacklist,
  - excluded ingredients and replacement checks.
- `src/scoring/seasonality.py` provides seasonal calendars and scoring.

## Scraping

- `src/scrapers/eatsmarter_search.py`
  - Uses Playwright and cache.
  - Batch search is used by the agent.
  - Parses search result title, URL, time, calories, rating.
- `src/scrapers/recipe_fetcher.py`
  - Uses `recipe-scrapers` for detailed recipe extraction.
  - Links meals to recipes after scraping.
- `src/scrapers/bioland_huesgen.py`
  - Scrapes available shop products.
  - Normalizes products and persists to `available_products`.
- `src/scrapers/familienkost.py` and `bioland_huesgen.py` add source-specific support.

## Shopping Lists

Main file: `src/shopping/shopping_list.py`

- Builds list from selected plan recipes.
- Reads parsed ingredients where possible.
- Scales quantities by household size and recipe servings.
- Applies multi-day prep multiplier.
- Aggregates compatible units.
- Splits items into Bioland/Rewe based on current availability.
- API checked state is keyed by ingredient/unit via `shopping_checked_items`.

## Home Assistant Integration

Manifest: `custom_components/ki_essensplaner/manifest.json`

- Domain: `ki_essensplaner`
- Version seen: `1.1.0`
- Config flow enabled.
- Requires `aiohttp`.

Coordinator: `custom_components/ki_essensplaner/coordinator.py`

- Polls API on configured interval.
- Caches last valid data and per-endpoint payloads.
- Fetches health, profile, excluded ingredients, weekly plan, history, config, multi-day data, skipped slots, shopping lists, ratings, recipe book.
- Exposes actions for rating, exclusion, profile refresh, plan generation/selection/deletion/completion, config changes, shopping item toggles.
- Polls after plan generation to refresh once plan appears.

Services: `custom_components/ki_essensplaner/__init__.py`

- `rate_recipe`
- `exclude_ingredient`
- `remove_ingredient_exclusion`
- `refresh_profile`
- `generate_weekly_plan`
- `select_recipe`
- `set_recipe_url`
- `delete_weekly_plan`
- `set_rotation_policy`
- `set_household_size`
- `set_multi_day`
- `set_multi_day_preferences`
- `clear_multi_day_preferences`
- `set_skip_slot`
- `clear_skip_slots`
- `clear_multi_day`
- `fetch_recipes`
- `complete_week`
- `set_displayed_week`
- `toggle_shopping_item`
- `clear_checked_items`

Sensors: `custom_components/ki_essensplaner/sensor.py`

- API status, profile status, top ingredients, excluded ingredients.
- Household size.
- Weekly plan status and 14 slot sensors.
- Multi-day overview/preferences, skipped slots.
- Next meal.
- Shopping counts for total/Bioland/Rewe.
- Recipe book count.

Cards/assets:

- `dist/weekly-plan-card.js`
- `dist/shopping-list-card.js`
- `dist/recipe-book-card.js`
- `dist/ki-essensplaner.js`

## Tests

Current pytest files:

- `tests/test_recipe_rotation.py`
  - rotation filtering/boosting,
  - banned recommendation filtering,
  - unique selection logic.
- `tests/test_user_config_rotation.py`
  - rotation policy normalization/persistence.
- `tests/test_config_api_models.py`
  - config update request validation.

Manual/older issue scripts:

- `scripts/test_issue_27.py` through `scripts/test_issue_31_wip.py`
- `scripts/test_issue_31.py` covers multi-day model serialization and shopping scaling.

Likely command:

```powershell
pytest
```

Dev dependencies in `pyproject.toml`: `pytest`, `ruff`.

## Known Practical Notes

- Python requirement is `>=3.12`.
- Network/scraping-dependent code may require Chromium/Playwright and internet.
- Generated weekly plans are JSON files under the app data area, while cooked/completed history is also persisted in SQLite.
- Home Assistant card state size limits were recently addressed by moving full recipe book UI to backend `/recipe-book` and limiting sensor attributes.
- `dist/` contains built artifacts, not source modules; edit carefully unless the project intentionally keeps source unavailable.
- Many files contain mojibake in comments/docs/output strings (`fÃ¼r`, `GrÃ¶ÃŸe`), likely due to earlier encoding display or file encoding issues. Avoid broad encoding churn unless explicitly fixing text.

## Fast Orientation For Future Work

When changing plan generation:

- Start in `src/agents/recipe_search_agent.py`.
- Check `src/agents/models.py` serialization compatibility.
- Update weekly-plan schemas/router if API shape changes.
- Verify `tests/test_recipe_rotation.py` and consider adding focused tests.

When changing shopping lists:

- Start in `src/shopping/shopping_list.py`.
- Check `src/api/routers/shopping.py` and HA shopping sensors/card expectations.
- Pay attention to quantity scaling, multi-day multipliers, and checked item keys.

When changing HA services/sensors:

- Start in `custom_components/ki_essensplaner/__init__.py`, `coordinator.py`, `sensor.py`.
- Mirror API path/payload changes in coordinator methods.
- Update `custom_components/ki_essensplaner/services.yaml`, `strings.json`, and translations if service schema/user-facing names change.

When changing API config:

- Start in `src/api/routers/config.py` and `src/core/user_config.py`.
- Keep add-on docs and HA services aligned.

When changing onboarding/OneNote:

- Start in `src/api/routers/onboarding.py` and `src/importers/onenote.py`.
- Azure/MSAL env config is in `src/core/config.py`.

