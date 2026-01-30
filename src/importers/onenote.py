"""OneNote importer using MS Graph API with MSAL device code flow."""

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import msal
import requests

from src.core.config import AzureConfig, RAW_DIR, ensure_directories
from src.core.database import init_db, upsert_meal_plan
from src.models.meal_plan import DayOfWeek, MealCreate, MealPlanCreate, MealSlot

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"

# Token cache file path
TOKEN_CACHE_PATH = Path.home() / ".ki-essensplaner" / "token_cache.json"


class OneNoteClient:
    """MS Graph API client for OneNote operations."""

    def __init__(self):
        if not AzureConfig.is_configured():
            raise ValueError(
                "Azure credentials not configured. "
                "Please set AZURE_CLIENT_ID and AZURE_TENANT_ID in .env file."
            )

        self._token_cache = msal.SerializableTokenCache()
        self._load_token_cache()

        self._app = msal.PublicClientApplication(
            AzureConfig.CLIENT_ID,
            authority=AzureConfig.AUTHORITY,
            token_cache=self._token_cache,
        )
        self._access_token: str | None = None

    def _load_token_cache(self) -> None:
        """Load token cache from file."""
        TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        if TOKEN_CACHE_PATH.exists():
            self._token_cache.deserialize(TOKEN_CACHE_PATH.read_text())

    def _save_token_cache(self) -> None:
        """Save token cache to file."""
        if self._token_cache.has_state_changed:
            TOKEN_CACHE_PATH.write_text(self._token_cache.serialize())

    def authenticate(self) -> bool:
        """Authenticate using device code flow."""
        # Try to get token from cache first
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(AzureConfig.SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self._access_token = result["access_token"]
                self._save_token_cache()
                print("Authenticated using cached token.")
                return True

        # Device code flow
        flow = self._app.initiate_device_flow(scopes=AzureConfig.SCOPES)
        if "user_code" not in flow:
            print(f"Authentication failed: {flow.get('error_description', 'Unknown error')}")
            return False

        print(f"\n{flow['message']}\n")

        result = self._app.acquire_token_by_device_flow(flow)

        if "access_token" in result:
            self._access_token = result["access_token"]
            self._save_token_cache()
            print("Authentication successful!")
            return True

        print(f"Authentication failed: {result.get('error_description', 'Unknown error')}")
        return False

    def _get_headers(self) -> dict[str, str]:
        """Get authorization headers."""
        if not self._access_token:
            raise ValueError("Not authenticated. Call authenticate() first.")
        return {"Authorization": f"Bearer {self._access_token}"}

    def get_notebooks(self) -> list[dict]:
        """Get all notebooks."""
        response = requests.get(
            f"{GRAPH_API_BASE}/me/onenote/notebooks",
            headers=self._get_headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("value", [])

    def get_sections(self, notebook_id: str) -> list[dict]:
        """Get all sections in a notebook."""
        response = requests.get(
            f"{GRAPH_API_BASE}/me/onenote/notebooks/{notebook_id}/sections",
            headers=self._get_headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("value", [])

    def get_pages(self, section_id: str) -> list[dict]:
        """Get all pages in a section."""
        response = requests.get(
            f"{GRAPH_API_BASE}/me/onenote/sections/{section_id}/pages",
            headers=self._get_headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("value", [])

    def get_page_content(self, page_id: str) -> str:
        """Get the HTML content of a page."""
        response = requests.get(
            f"{GRAPH_API_BASE}/me/onenote/pages/{page_id}/content",
            headers=self._get_headers(),
            timeout=30,
        )
        response.raise_for_status()
        return response.text

    def search_pages(self, query: str = "Wochenplan") -> list[dict]:
        """Search for pages by title."""
        all_pages = []
        notebooks = self.get_notebooks()

        for notebook in notebooks:
            sections = self.get_sections(notebook["id"])
            for section in sections:
                pages = self.get_pages(section["id"])
                for page in pages:
                    if query.lower() in page.get("title", "").lower():
                        page["notebook_name"] = notebook.get("displayName", "")
                        page["section_name"] = section.get("displayName", "")
                        all_pages.append(page)

        return all_pages


class MealPlanParser:
    """Parse OneNote HTML content into structured meal plans."""

    # German day names mapping
    DAY_MAPPING = {
        "montag": DayOfWeek.MONDAY,
        "dienstag": DayOfWeek.TUESDAY,
        "mittwoch": DayOfWeek.WEDNESDAY,
        "donnerstag": DayOfWeek.THURSDAY,
        "freitag": DayOfWeek.FRIDAY,
        "samstag": DayOfWeek.SATURDAY,
        "sonntag": DayOfWeek.SUNDAY,
        "mo": DayOfWeek.MONDAY,
        "di": DayOfWeek.TUESDAY,
        "mi": DayOfWeek.WEDNESDAY,
        "do": DayOfWeek.THURSDAY,
        "fr": DayOfWeek.FRIDAY,
        "sa": DayOfWeek.SATURDAY,
        "so": DayOfWeek.SUNDAY,
    }

    # Slot patterns
    SLOT_MAPPING = {
        "mittag": MealSlot.LUNCH,
        "lunch": MealSlot.LUNCH,
        "abend": MealSlot.DINNER,
        "dinner": MealSlot.DINNER,
        "abends": MealSlot.DINNER,
        "mittags": MealSlot.LUNCH,
    }

    def parse(self, html_content: str, page_id: str) -> MealPlanCreate:
        """Parse HTML content into a MealPlanCreate."""
        # Extract text from HTML
        text = self._strip_html(html_content)
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        meals = []
        current_day = None
        week_start = self._extract_week_start(lines)

        for line in lines:
            # Try to detect day
            day = self._detect_day(line)
            if day is not None:
                current_day = day
                continue

            # Try to detect meal
            if current_day is not None:
                meal = self._parse_meal_line(line, current_day)
                if meal:
                    meals.append(meal)

        return MealPlanCreate(
            onenote_page_id=page_id,
            week_start=week_start,
            raw_content=html_content,
            meals=meals,
        )

    def _strip_html(self, html: str) -> str:
        """Remove HTML tags and decode entities."""
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "\n", html)
        # Decode common HTML entities
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        return text

    def _detect_day(self, line: str) -> DayOfWeek | None:
        """Detect day of week from a line."""
        line_lower = line.lower()
        for pattern, day in self.DAY_MAPPING.items():
            if pattern in line_lower:
                # Check if this is a day header (not just a word containing the day)
                if re.search(rf"\b{pattern}\b", line_lower):
                    return day
        return None

    def _parse_meal_line(self, line: str, day: DayOfWeek) -> MealCreate | None:
        """Parse a meal line and return MealCreate if valid."""
        line_lower = line.lower()

        # Detect slot
        slot = MealSlot.DINNER  # Default to dinner
        for pattern, meal_slot in self.SLOT_MAPPING.items():
            if pattern in line_lower:
                slot = meal_slot
                # Remove slot indicator from title
                line = re.sub(rf"\b{pattern}\b:?\s*", "", line, flags=re.IGNORECASE)
                break

        # Clean up the line
        line = line.strip()
        if not line or len(line) < 3:
            return None

        # Skip common non-meal lines
        skip_patterns = ["wochenplan", "woche", "kw", "datum", "---", "==="]
        if any(p in line_lower for p in skip_patterns):
            return None

        return MealCreate(
            day_of_week=day,
            slot=slot,
            recipe_title=line,
        )

    def _extract_week_start(self, lines: list[str]) -> date | None:
        """Try to extract week start date from content."""
        for line in lines[:10]:  # Check first 10 lines
            # Look for date patterns like "KW 5" or "05.02" or "5.2.2024"
            date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.?(\d{2,4})?", line)
            if date_match:
                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = int(date_match.group(3)) if date_match.group(3) else datetime.now().year
                if year < 100:
                    year += 2000
                try:
                    return date(year, month, day)
                except ValueError:
                    continue
        return None


def test_auth():
    """Test Azure authentication."""
    print("Testing Azure AD authentication...")
    client = OneNoteClient()
    if client.authenticate():
        print("Authentication test passed!")
        return True
    return False


def list_notebooks():
    """List all available notebooks."""
    client = OneNoteClient()
    if not client.authenticate():
        return

    print("\nAvailable OneNote notebooks:\n")
    notebooks = client.get_notebooks()

    if not notebooks:
        print("No notebooks found.")
        return

    for notebook in notebooks:
        print(f"  - {notebook.get('displayName', 'Unnamed')}")
        print(f"    ID: {notebook['id']}")

        sections = client.get_sections(notebook["id"])
        for section in sections:
            print(f"      Section: {section.get('displayName', 'Unnamed')}")
            pages = client.get_pages(section["id"])
            for page in pages:
                print(f"        - {page.get('title', 'Untitled')}")
        print()


def import_meal_plans(search_term: str = "Wochenplan", export_raw: bool = False):
    """Import meal plans from OneNote."""
    ensure_directories()
    init_db()

    client = OneNoteClient()
    if not client.authenticate():
        return

    print(f"\nSearching for pages containing '{search_term}'...\n")
    pages = client.search_pages(search_term)

    if not pages:
        print("No matching pages found.")
        return

    print(f"Found {len(pages)} matching pages.\n")

    parser = MealPlanParser()
    imported_count = 0

    for page in pages:
        page_id = page["id"]
        title = page.get("title", "Untitled")
        notebook = page.get("notebook_name", "")
        section = page.get("section_name", "")

        print(f"Processing: {title}")
        print(f"  Location: {notebook} > {section}")

        try:
            content = client.get_page_content(page_id)

            # Export raw content if requested
            if export_raw:
                raw_path = RAW_DIR / f"{page_id}.html"
                raw_path.write_text(content, encoding="utf-8")
                print(f"  Raw content saved to: {raw_path}")

            # Parse and save
            meal_plan = parser.parse(content, page_id)
            saved_plan = upsert_meal_plan(meal_plan)

            print(f"  Parsed {len(meal_plan.meals)} meals")
            print(f"  Saved as meal plan ID: {saved_plan.id}")
            imported_count += 1

        except requests.HTTPError as e:
            print(f"  Error fetching content: {e}")
        except Exception as e:
            print(f"  Error processing: {e}")

        print()

    print(f"\nImported {imported_count} meal plans.")


def export_page_content(page_id: str):
    """Export a specific page's content for debugging."""
    ensure_directories()

    client = OneNoteClient()
    if not client.authenticate():
        return

    print(f"Fetching page content for: {page_id}")
    content = client.get_page_content(page_id)

    # Save HTML
    html_path = RAW_DIR / f"{page_id}.html"
    html_path.write_text(content, encoding="utf-8")
    print(f"HTML saved to: {html_path}")

    # Parse and show result
    parser = MealPlanParser()
    meal_plan = parser.parse(content, page_id)

    print(f"\nParsed meal plan:")
    print(f"  Week start: {meal_plan.week_start}")
    print(f"  Meals found: {len(meal_plan.meals)}")
    for meal in meal_plan.meals:
        day_name = DayOfWeek(meal.day_of_week).name
        print(f"    {day_name} {meal.slot}: {meal.recipe_title}")

    # Save JSON
    json_path = RAW_DIR / f"{page_id}.json"
    json_path.write_text(
        json.dumps(meal_plan.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nJSON saved to: {json_path}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="OneNote meal plan importer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Test auth command
    subparsers.add_parser("test-auth", help="Test Azure AD authentication")

    # List notebooks command
    subparsers.add_parser("list-notebooks", help="List all available notebooks")

    # Import command
    import_parser = subparsers.add_parser("import", help="Import meal plans from OneNote")
    import_parser.add_argument(
        "--search",
        default="Wochenplan",
        help="Search term for page titles (default: Wochenplan)",
    )
    import_parser.add_argument(
        "--export-raw",
        action="store_true",
        help="Export raw HTML content to data/raw/",
    )

    # Export single page command
    export_parser = subparsers.add_parser("export-page", help="Export a specific page for debugging")
    export_parser.add_argument("page_id", help="OneNote page ID")

    args = parser.parse_args()

    if args.command == "test-auth":
        success = test_auth()
        sys.exit(0 if success else 1)
    elif args.command == "list-notebooks":
        list_notebooks()
    elif args.command == "import":
        import_meal_plans(args.search, args.export_raw)
    elif args.command == "export-page":
        export_page_content(args.page_id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
