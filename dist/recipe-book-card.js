class RecipeBookCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._filter = 'all';
    this._search = '';
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  setConfig(config) {
    this._config = config;
  }

  getCardSize() {
    return 6;
  }

  _callService(service, data = {}) {
    this._hass.callService('ki_essensplaner', service, data);
  }

  _rateRecipe(recipeId, rating) {
    this._callService('rate_recipe', { recipe_id: recipeId, rating: rating });
  }

  _setFilter(filter) {
    this._filter = filter;
    this.render();
  }

  _setSearch(value) {
    this._search = value.toLowerCase();
    this.render();
  }

  _escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  _safeUrl(rawUrl) {
    if (!rawUrl) return null;
    try {
      const parsed = new URL(rawUrl, window.location.origin);
      if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
        return parsed.href;
      }
    } catch (_) {
      return null;
    }
    return null;
  }

  _formatDate(dateStr) {
    if (!dateStr) return '–';
    try {
      return new Date(dateStr).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
    } catch {
      return dateStr;
    }
  }

  _renderStars(recipeId, currentRating, readOnly = false) {
    const rating = currentRating || 0;
    return `<div class="star-rating">
      ${[1,2,3,4,5].map(s => `
        <span class="star ${s <= rating ? 'filled' : ''}"
              ${readOnly ? '' : `onclick="this.getRootNode().host._rateRecipe(${recipeId}, ${s})"`}
              title="${s} Stern${s !== 1 ? 'e' : ''}">&#9733;</span>
      `).join('')}
    </div>`;
  }

  render() {
    if (!this._hass || !this._config) return;

    const entityId = this._config.entity || 'sensor.essensplaner_recipe_book';
    const state = this._hass.states[entityId];
    const recipes = state ? (state.attributes.recipes || []) : [];

    const search = this._search;
    const filter = this._filter;

    const filtered = recipes.filter(r => {
      if (filter === 'rated' && !r.rating) return false;
      if (filter === 'blocked' && r.rating !== 1) return false;
      const title = (r.title || '').toLowerCase();
      if (search && !title.includes(search)) return false;
      return true;
    });

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        .card {
          padding: 16px;
          background: var(--ha-card-background, var(--card-background-color, white));
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,0.1));
        }
        .card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
          flex-wrap: wrap;
          gap: 8px;
        }
        .card-title {
          font-size: 20px;
          font-weight: 500;
          color: var(--primary-text-color);
        }
        .controls {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
          align-items: center;
          margin-bottom: 12px;
        }
        .filter-btn {
          padding: 4px 12px;
          border-radius: 999px;
          border: 1px solid var(--primary-color);
          background: transparent;
          color: var(--primary-color);
          cursor: pointer;
          font-size: 13px;
        }
        .filter-btn.active {
          background: var(--primary-color);
          color: white;
        }
        .search-input {
          flex: 1;
          min-width: 140px;
          padding: 4px 10px;
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          font-size: 13px;
        }
        .count-label {
          font-size: 12px;
          color: var(--secondary-text-color);
          margin-bottom: 8px;
        }
        table {
          width: 100%;
          border-collapse: collapse;
          font-size: 13px;
        }
        th {
          text-align: left;
          padding: 6px 8px;
          border-bottom: 2px solid var(--divider-color);
          color: var(--secondary-text-color);
          font-weight: 600;
          font-size: 11px;
          text-transform: uppercase;
        }
        td {
          padding: 8px;
          border-bottom: 1px solid var(--divider-color);
          vertical-align: middle;
        }
        tr:last-child td {
          border-bottom: none;
        }
        tr:hover td {
          background: var(--secondary-background-color);
        }
        .recipe-link {
          color: var(--primary-color);
          text-decoration: none;
        }
        .recipe-link:hover {
          text-decoration: underline;
        }
        .badge-blocked {
          display: inline-block;
          padding: 2px 6px;
          border-radius: 3px;
          font-size: 10px;
          background: #ef9a9a;
          color: #b71c1c;
          margin-left: 4px;
        }
        .star-rating {
          display: flex;
          gap: 1px;
        }
        .star {
          font-size: 16px;
          cursor: pointer;
          color: #ccc;
          transition: color 0.1s;
        }
        .star.filled {
          color: #f5a623;
        }
        .star:hover {
          color: #f5a623;
        }
        .cook-count {
          text-align: center;
          font-weight: 600;
        }
        .empty {
          text-align: center;
          padding: 40px;
          color: var(--secondary-text-color);
        }
      </style>
      <ha-card class="card">
        <div class="card-header">
          <div class="card-title">📖 Rezeptbuch</div>
          <span style="font-size:13px;color:var(--secondary-text-color)">${recipes.length} Rezepte gesamt</span>
        </div>
        <div class="controls">
          <button class="filter-btn ${filter === 'all' ? 'active' : ''}"
                  onclick="this.getRootNode().host._setFilter('all')">Alle</button>
          <button class="filter-btn ${filter === 'rated' ? 'active' : ''}"
                  onclick="this.getRootNode().host._setFilter('rated')">Bewertet</button>
          <button class="filter-btn ${filter === 'blocked' ? 'active' : ''}"
                  onclick="this.getRootNode().host._setFilter('blocked')">&#128683; Gesperrt</button>
          <input class="search-input" type="search" placeholder="Suchen…" value="${this._escapeHtml(this._search)}"
                 oninput="this.getRootNode().host._setSearch(this.value)" />
        </div>
        <div class="count-label">${filtered.length} Rezept${filtered.length !== 1 ? 'e' : ''} angezeigt</div>
        ${filtered.length === 0 ? `<div class="empty">Keine Rezepte gefunden.</div>` : `
        <table>
          <thead>
            <tr>
              <th>Rezept</th>
              <th>Bewertung</th>
              <th>Gekocht</th>
              <th>Zuletzt</th>
            </tr>
          </thead>
          <tbody>
            ${filtered.map((r) => {
              const safeTitle = this._escapeHtml(r.title || '');
              const safeUrl = this._safeUrl(r.url);
              const recipeLabel = safeUrl
                ? `<a class="recipe-link" href="${this._escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer">${safeTitle}</a>`
                : safeTitle;
              return `
              <tr>
                <td>
                  ${recipeLabel}
                  ${r.rating === 1 ? '<span class="badge-blocked">&#128683; Gesperrt</span>' : ''}
                </td>
                <td>${this._renderStars(r.id, r.rating)}</td>
                <td class="cook-count">${r.cook_count || 0}×</td>
                <td>${this._formatDate(r.last_cooked)}</td>
              </tr>
            `;
            }).join('')}
          </tbody>
        </table>
        `}
      </ha-card>
    `;
  }
}

customElements.define('recipe-book-card', RecipeBookCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'recipe-book-card',
  name: 'Rezeptbuch',
  description: 'Zeigt alle gekochten und bewerteten Rezepte mit Filteroptionen.',
});

