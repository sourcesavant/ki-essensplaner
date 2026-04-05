"""Simple web UI views served by the FastAPI backend."""

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from src.api.config import config

router = APIRouter(prefix="/ui", tags=["ui"])

_RECIPE_BOOK_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Rezeptbuch</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, -apple-system, sans-serif; background: #f5f5f5; color: #333; }
  header { background: #1976d2; color: #fff; padding: 14px 16px; display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 1.1rem; font-weight: 600; }
  #count { font-size: 0.85rem; opacity: 0.8; margin-left: auto; }
  #controls { padding: 10px 16px; background: #fff; border-bottom: 1px solid #e0e0e0; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  #search { flex: 1; min-width: 160px; padding: 7px 10px; border: 1px solid #ccc; border-radius: 6px; font-size: 0.9rem; }
  select { padding: 7px 10px; border: 1px solid #ccc; border-radius: 6px; font-size: 0.9rem; background: #fff; }
  #list { padding: 8px; display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 8px; }
  .card { background: #fff; border-radius: 8px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,.08); display: flex; flex-direction: column; gap: 6px; }
  .card-title { font-size: 0.95rem; font-weight: 600; line-height: 1.3; }
  .card-title a { color: #1976d2; text-decoration: none; }
  .card-title a:hover { text-decoration: underline; }
  .card-meta { font-size: 0.8rem; color: #666; display: flex; gap: 10px; flex-wrap: wrap; }
  .stars { color: #f5a623; font-size: 0.9rem; }
  .tag { background: #e3f2fd; color: #1565c0; border-radius: 4px; padding: 1px 5px; font-size: 0.75rem; }
  .tag.cooked { background: #e8f5e9; color: #2e7d32; }
  .empty { text-align: center; padding: 40px; color: #888; grid-column: 1/-1; }
  #error { background: #ffebee; color: #c62828; padding: 12px 16px; margin: 8px; border-radius: 6px; display: none; }
</style>
</head>
<body>
<header>
  <span>📖</span>
  <h1>Rezeptbuch</h1>
  <span id="count"></span>
</header>
<div id="controls">
  <input id="search" type="search" placeholder="Rezept suchen…" oninput="render()">
  <select id="sort" onchange="render()">
    <option value="cook">Meist gekocht</option>
    <option value="rating">Bewertung</option>
    <option value="title">Name</option>
    <option value="recent">Zuletzt gekocht</option>
  </select>
  <select id="filter" onchange="render()">
    <option value="all">Alle</option>
    <option value="rated">Bewertet</option>
    <option value="cooked">Gekocht</option>
    <option value="new">Neu (unbewertet)</option>
  </select>
</div>
<div id="error"></div>
<div id="list"></div>

<script>
const TOKEN = new URLSearchParams(location.search).get('token') || '';
let allRecipes = [];

async function load() {
  try {
    const r = await fetch('/api/recipes/book', {
      headers: { 'Authorization': 'Bearer ' + TOKEN }
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const data = await r.json();
    allRecipes = data.recipes || [];
    document.getElementById('count').textContent = allRecipes.length + ' Rezepte';
    render();
  } catch(e) {
    const el = document.getElementById('error');
    el.style.display = 'block';
    el.textContent = 'Fehler beim Laden: ' + e.message + (TOKEN ? '' : ' – kein Token angegeben');
  }
}

function stars(rating) {
  if (!rating) return '';
  return '★'.repeat(rating) + '☆'.repeat(5 - rating);
}

function render() {
  const q = document.getElementById('search').value.toLowerCase();
  const sort = document.getElementById('sort').value;
  const filter = document.getElementById('filter').value;

  let list = allRecipes.filter(r => {
    if (q && !(r.title || '').toLowerCase().includes(q)) return false;
    if (filter === 'rated' && !r.rating) return false;
    if (filter === 'cooked' && !(r.cook_count > 0)) return false;
    if (filter === 'new' && r.rating) return false;
    return true;
  });

  list.sort((a, b) => {
    if (sort === 'cook') return (b.cook_count || 0) - (a.cook_count || 0);
    if (sort === 'rating') return (b.rating || 0) - (a.rating || 0);
    if (sort === 'title') return (a.title || '').localeCompare(b.title || '', 'de');
    if (sort === 'recent') return (b.last_cooked || '').localeCompare(a.last_cooked || '');
    return 0;
  });

  const container = document.getElementById('list');
  if (!list.length) {
    container.innerHTML = '<p class="empty">Keine Rezepte gefunden.</p>';
    return;
  }

  container.innerHTML = list.map(r => {
    const title = r.url
      ? `<a href="#" data-url="${esc(r.url)}" class="recipe-link">${esc(r.title || '?')}</a>`
      : esc(r.title || '?');
    const meta = [];
    if (r.rating) meta.push(`<span class="stars">${stars(r.rating)}</span>`);
    if (r.cook_count > 0) meta.push(`<span class="tag cooked">🍳 ${r.cook_count}×</span>`);
    if (r.prep_time_minutes) meta.push(`<span>⏱ ${r.prep_time_minutes} Min</span>`);
    if (r.calories) meta.push(`<span>${r.calories} kcal</span>`);
    if (r.last_cooked) meta.push(`<span>zuletzt ${r.last_cooked}</span>`);
    return `<div class="card">
      <div class="card-title">${title}</div>
      ${meta.length ? `<div class="card-meta">${meta.join('')}</div>` : ''}
    </div>`;
  }).join('');
}

function esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Open recipe links via window.open to work inside HA iframe sandbox
document.getElementById('list').addEventListener('click', function(e) {
  const a = e.target.closest('a.recipe-link');
  if (!a) return;
  e.preventDefault();
  const url = a.dataset.url;
  if (url) window.open(url, '_blank');
});

load();
</script>
</body>
</html>"""


@router.get("/recipe-book", response_class=HTMLResponse, include_in_schema=False)
def recipe_book_ui(token: str = Query(default="")) -> HTMLResponse:
    """Serve the recipe book web UI.

    The token query parameter is forwarded to the JS fetch call.
    Example: /ui/recipe-book?token=YOURTOKEN
    """
    # Validate token before serving the page (avoids serving the UI to strangers).
    if config.api_token and token != config.api_token:
        return HTMLResponse("<h3>401 Unauthorized</h3>", status_code=401)
    return HTMLResponse(_RECIPE_BOOK_HTML)
