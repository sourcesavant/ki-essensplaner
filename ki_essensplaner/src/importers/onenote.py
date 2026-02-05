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

# Token cache file path - use DATA_DIR if set (Home Assistant), otherwise home directory
import os
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
_data_dir = os.environ.get("DATA_DIR")
if _data_dir:
    TOKEN_CACHE_PATH = Path(_data_dir) / "token_cache.json"
    DEVICE_FLOW_CACHE_PATH = Path(_data_dir) / "device_flow_cache.json"
else:
    TOKEN_CACHE_PATH = Path.home() / ".ki-essensplaner" / "token_cache.json"
    DEVICE_FLOW_CACHE_PATH = Path.home() / ".ki-essensplaner" / "device_flow_cache.json"


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
        self._timeout = int(os.getenv("GRAPH_TIMEOUT", "120"))
        self._session = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        self._session.mount("https://", HTTPAdapter(max_retries=retries))

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

    def try_authenticate_from_cache(self) -> bool:
        """Try to authenticate using cached token only.

        Returns:
            True if authenticated from cache, False if interactive auth needed.
        """
        import logging
        logger = logging.getLogger(__name__)
        accounts = self._app.get_accounts()
        logger.info(
            "OneNote cache check: path=%s exists=%s accounts=%s",
            str(TOKEN_CACHE_PATH),
            TOKEN_CACHE_PATH.exists(),
            len(accounts),
        )
        if accounts:
            result = self._app.acquire_token_silent(AzureConfig.SCOPES, account=accounts[0])
            if result and "access_token" in result:
                self._access_token = result["access_token"]
                self._save_token_cache()
                return True
        return False

    def start_device_flow(self) -> dict | None:
        """Start the device code flow and return flow data.

        Returns:
            Dict with user_code, verification_uri, message, expires_in
            or None if failed.
        """
        flow = self._app.initiate_device_flow(scopes=AzureConfig.SCOPES)
        if "user_code" not in flow:
            return None

        # Save flow to file for persistence across API requests
        DEVICE_FLOW_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEVICE_FLOW_CACHE_PATH.write_text(json.dumps(flow))

        return {
            "user_code": flow["user_code"],
            "verification_uri": flow["verification_uri"],
            "message": flow["message"],
            "expires_in": flow.get("expires_in", 900),
        }

    def complete_device_flow(self, timeout: int = 300) -> bool:
        """Complete the device code flow after user has authenticated.

        Args:
            timeout: Max seconds to wait for user to authenticate.

        Returns:
            True if authenticated successfully.
        """
        # Load flow from file
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            "Completing device flow: cache_path=%s exists=%s",
            str(DEVICE_FLOW_CACHE_PATH),
            DEVICE_FLOW_CACHE_PATH.exists(),
        )
        if not DEVICE_FLOW_CACHE_PATH.exists():
            return False

        try:
            flow = json.loads(DEVICE_FLOW_CACHE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return False

        # This will block until user completes auth or timeout
        result = self._app.acquire_token_by_device_flow(flow)

        # Clean up the flow cache
        if DEVICE_FLOW_CACHE_PATH.exists():
            DEVICE_FLOW_CACHE_PATH.unlink()

        if "access_token" in result:
            self._access_token = result["access_token"]
            self._save_token_cache()
            logger.info("Device flow complete: token cached=%s", TOKEN_CACHE_PATH.exists())
            return True

        return False

    def _get_headers(self) -> dict[str, str]:
        """Get authorization headers."""
        if not self._access_token:
            # Attempt to load from cache on demand
            if not self.try_authenticate_from_cache():
                raise ValueError("Not authenticated. Call authenticate() first.")
        return {"Authorization": f"Bearer {self._access_token}"}

    def get_notebooks(self) -> list[dict]:
        """Get all notebooks."""
        response = self._session.get(
            f"{GRAPH_API_BASE}/me/onenote/notebooks",
            headers=self._get_headers(),
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json().get("value", [])

    def get_sections(self, notebook_id: str) -> list[dict]:
        """Get all sections in a notebook."""
        response = self._session.get(
            f"{GRAPH_API_BASE}/me/onenote/notebooks/{notebook_id}/sections",
            headers=self._get_headers(),
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json().get("value", [])

    def get_pages(self, section_id: str) -> list[dict]:
        """Get all pages in a section."""
        response = self._session.get(
            f"{GRAPH_API_BASE}/me/onenote/sections/{section_id}/pages",
            headers=self._get_headers(),
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json().get("value", [])

    def get_page_content(self, page_id: str) -> str:
        """Get the HTML content of a page."""
        response = self._session.get(
            f"{GRAPH_API_BASE}/me/onenote/pages/{page_id}/content",
            headers=self._get_headers(),
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.text

    def search_pages(self, query: str = "", notebooks_filter: list[str] | None = None) -> list[dict]:
        """Search for pages, optionally filtered by notebook names."""
        all_pages = []
        notebooks = self.get_notebooks()

        for notebook in notebooks:
            notebook_name = notebook.get("displayName", "")

            # Filter by notebook name if specified
            if notebooks_filter:
                if not any(f.lower() in notebook_name.lower() for f in notebooks_filter):
                    continue

            sections = self.get_sections(notebook["id"])
            for section in sections:
                pages = self.get_pages(section["id"])
                for page in pages:
                    title = page.get("title", "")
                    # Filter by query if specified
                    if query and query.lower() not in title.lower():
                        continue
                    page["notebook_name"] = notebook_name
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
    }

    def parse(self, html_content: str, page_id: str) -> MealPlanCreate:
        """Parse HTML content into a MealPlanCreate."""
        week_start = self._extract_week_start_from_html(html_content)
        meals = self._parse_meal_blocks(html_content)

        return MealPlanCreate(
            onenote_page_id=page_id,
            week_start=week_start,
            raw_content=html_content,
            meals=meals,
        )

    def _parse_meal_blocks(self, html: str) -> list[MealCreate]:
        """Parse meal blocks from HTML divs."""
        meals = []

        # Find all div blocks
        div_pattern = re.compile(r"<div[^>]*>(.*?)</div>", re.DOTALL | re.IGNORECASE)

        for div_match in div_pattern.finditer(html):
            div_content = div_match.group(1)

            # Extract paragraphs from this div
            p_pattern = re.compile(r"<p[^>]*>(.*?)</p>", re.DOTALL | re.IGNORECASE)
            paragraphs = [self._strip_html(p.group(1)).strip() for p in p_pattern.finditer(div_content)]
            paragraphs = [p for p in paragraphs if p]  # Remove empty

            if len(paragraphs) >= 2:
                header = paragraphs[0]  # e.g., "Sonntag + Montag Abendessen"
                recipe = paragraphs[1]  # e.g., URL or recipe name

                # Extract URL if present
                url_match = re.search(r'href="([^"]+)"', div_content)
                if url_match:
                    recipe = url_match.group(1)

                # Parse header for days and slot
                parsed_meals = self._parse_header(header, recipe)
                meals.extend(parsed_meals)

        return meals

    def _parse_header(self, header: str, recipe: str) -> list[MealCreate]:
        """Parse header like 'Sonntag + Montag Abendessen' into meals."""
        meals = []
        header_lower = header.lower()

        # Detect slot
        if "mittagessen" in header_lower or "mittag" in header_lower:
            slot = MealSlot.LUNCH
        else:
            slot = MealSlot.DINNER  # Default

        # Find all days mentioned
        days_found = []
        for day_name, day_enum in self.DAY_MAPPING.items():
            if day_name in header_lower:
                days_found.append(day_enum)

        # Create a meal for each day
        for day in days_found:
            meals.append(MealCreate(
                day_of_week=day,
                slot=slot,
                recipe_title=recipe,
            ))

        return meals

    def _strip_html(self, html: str) -> str:
        """Remove HTML tags and decode entities."""
        text = re.sub(r"<[^>]+>", " ", html)
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        return " ".join(text.split())  # Normalize whitespace

    def _extract_week_start_from_html(self, html: str) -> date | None:
        """Extract week start date from title tag."""
        title_match = re.search(r"<title>([^<]+)</title>", html)
        if title_match:
            title = title_match.group(1)
            # Parse date like "24.1.-30.1." or "17.1-23.1."
            date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.?-", title)
            if date_match:
                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = datetime.now().year
                try:
                    return date(year, month, day)
                except ValueError:
                    pass
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


def import_meal_plans(
    search_term: str = "",
    notebooks: list[str] | None = None,
    export_raw: bool = False,
):
    """Import meal plans from OneNote."""
    ensure_directories()
    init_db()

    client = OneNoteClient()
    if not client.authenticate():
        return

    filter_desc = []
    if notebooks:
        filter_desc.append(f"notebooks: {', '.join(notebooks)}")
    if search_term:
        filter_desc.append(f"search: '{search_term}'")
    print(f"\nSearching for pages ({', '.join(filter_desc) or 'all'})...\n")

    pages = client.search_pages(search_term, notebooks)

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


def import_meal_plans_cached(
    client: OneNoteClient,
    notebooks_filter: list[str] | None = None,
    export_raw: bool = False,
) -> dict:
    """Import meal plans using an already authenticated client (no interactive auth).

    Returns a dict with pages_found and meal_plans_imported.
    """
    ensure_directories()
    init_db()

    pages = client.search_pages("", notebooks_filter)
    if not pages:
        return {"pages_found": 0, "meal_plans_imported": 0}

    parser = MealPlanParser()
    imported_count = 0

    for page in pages:
        page_id = page["id"]
        try:
            content = client.get_page_content(page_id)

            if export_raw:
                raw_path = RAW_DIR / f"{page_id}.html"
                raw_path.write_text(content, encoding="utf-8")

            meal_plan = parser.parse(content, page_id)
            upsert_meal_plan(meal_plan)
            imported_count += 1
        except requests.HTTPError:
            continue
        except Exception:
            continue

    return {"pages_found": len(pages), "meal_plans_imported": imported_count}


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
        default="",
        help="Search term for page titles (optional)",
    )
    import_parser.add_argument(
        "--notebooks",
        nargs="+",
        help="Filter by notebook names (e.g., --notebooks 'Essen 2025' 'Essensplanung')",
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
        import_meal_plans(args.search, args.notebooks, args.export_raw)
    elif args.command == "export-page":
        export_page_content(args.page_id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
