/**
 * KI-Essensplaner Weekly Plan Card
 *
 * Custom Lovelace card for displaying the weekly meal plan.
 * Shows 7 days × 2 slots (Mittagessen, Abendessen) with recipe selection.
 */

class WeeklyPlanCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hass = null;
    this._config = null;
    this._isGenerating = false;
    this._lastGeneratedAt = null;
    this._isScrolling = false;
    this._pendingRender = false;
    this._scrollListenerAttached = false;
    this._scrollTimeout = null;
    this._savedScrollPosition = 0;
    this._isRestoringScroll = false;
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error('Please define an entity (sensor.essensplaner_weekly_plan_status)');
    }
    this._entityPrefix = this._deriveEntityPrefix(config.entity);
    this._config = {
      multi_day_preferences_entity: `${this._entityPrefix}meal_prep_preferences`,
      skipped_slots_entity: `${this._entityPrefix}skipped_slots`,
      ...config,
    };
    this.render();
  }

  set hass(hass) {
    const oldHass = this._hass;
    this._hass = hass;

    // Check if relevant entities changed
    if (oldHass && !this._hasRelevantChanges(oldHass, hass)) {
      return; // Nothing changed, no need to render
    }

    // Don't render while scrolling
    if (this._isScrolling) {
      this._pendingRender = true;
      return;
    }

    this.render();
  }

  _hasRelevantChanges(oldHass, newHass) {
    if (!this._config?.entity) return true;

    // Check if status entity changed
    const oldStatus = oldHass.states[this._config.entity];
    const newStatus = newHass.states[this._config.entity];
    if (JSON.stringify(oldStatus) !== JSON.stringify(newStatus)) {
      return true;
    }

    // Check if any meal slot entities changed
    const weekdays = ['samstag', 'sonntag', 'montag', 'dienstag', 'mittwoch', 'donnerstag', 'freitag'];
    const slots = ['mittagessen', 'abendessen'];

    for (const day of weekdays) {
      for (const slot of slots) {
        const entityId = `${this._entityPrefix}${day}_${slot}`;
        const oldState = oldHass.states[entityId];
        const newState = newHass.states[entityId];
        if (JSON.stringify(oldState) !== JSON.stringify(newState)) {
          return true;
        }
      }
    }

    const extraEntities = [
      this._config.multi_day_preferences_entity,
      this._config.skipped_slots_entity,
    ];
    for (const entityId of extraEntities) {
      const oldState = oldHass.states[entityId];
      const newState = newHass.states[entityId];
      if (JSON.stringify(oldState) !== JSON.stringify(newState)) {
        return true;
      }
    }

    return false; // No relevant changes
  }

  getCardSize() {
    return 8;
  }

  _callService(service, data = {}) {
    this._hass.callService('ki_essensplaner', service, data);
  }

  _rateRecipe(recipeId, recipeUrlEncoded, recipeTitleEncoded, rating) {
    const payload = { rating: rating };
    if (recipeId) {
      payload.recipe_id = recipeId;
    } else {
      const recipeUrl = decodeURIComponent(recipeUrlEncoded || '');
      const recipeTitle = decodeURIComponent(recipeTitleEncoded || '');
      if (!recipeUrl) return;
      payload.recipe_url = recipeUrl;
      payload.recipe_title = recipeTitle;
    }
    this._callService('rate_recipe', payload);
  }

  _selectRecipe(weekday, slot, recipeIndex) {
    this._callService('select_recipe', {
      weekday: weekday,
      slot: slot,
      recipe_index: recipeIndex
    });
  }

  _setRecipeUrl(weekday, slot, recipeUrl) {
    const url = (recipeUrl || '').trim();
    if (!url) return false;
    this._callService('set_recipe_url', {
      weekday: weekday,
      slot: slot,
      recipe_url: url
    });
    return true;
  }

  _isValidUrl(value) {
    try {
      const parsed = new URL(value);
      return parsed.protocol === 'http:' || parsed.protocol === 'https:';
    } catch (e) {
      return false;
    }
  }

  _setFeedback(container, message, isError = false) {
    if (!container) return;
    container.textContent = message;
    container.classList.toggle('error', isError);
    container.classList.toggle('success', !isError);
    container.style.display = message ? 'block' : 'none';
  }

  _handleCustomUrlClick(buttonEl, weekday, slot) {
    const inputEl = buttonEl?.previousElementSibling;
    const feedbackEl = buttonEl?.nextElementSibling;
    const value = (inputEl?.value || '').trim();

    if (!value) {
      this._setFeedback(feedbackEl, 'Bitte eine URL eingeben.', true);
      return;
    }
    if (!this._isValidUrl(value)) {
      this._setFeedback(feedbackEl, 'Ungueltige URL. Nur http/https.', true);
      return;
    }

    const sent = this._setRecipeUrl(weekday, slot, value);
    if (sent) {
      this._setFeedback(feedbackEl, 'URL gesendet. Wird gescraped ...', false);
      inputEl.value = '';
      setTimeout(() => this._setFeedback(feedbackEl, ''), 3000);
    }
  }

  _generatePlan() {
    const planStatus = this._hass?.states?.[this._config?.entity];
    this._lastGeneratedAt = planStatus?.attributes?.generated_at || null;
    this._isGenerating = true;
    this._callService('generate_weekly_plan');
  }

  _completeWeek(generateNext = true) {
    if (generateNext) {
      const planStatus = this._hass?.states?.[this._config?.entity];
      this._lastGeneratedAt = planStatus?.attributes?.generated_at || null;
      this._isGenerating = true;
    }
    this._callService('complete_week', {
      generate_next: generateNext
    });
  }

  _setDisplayedWeek(weekStart) {
    if (!weekStart || weekStart === 'current') {
      this._callService('set_displayed_week', {});
      return;
    }
    this._callService('set_displayed_week', { week_start: weekStart });
  }

  _changeDisplayedWeek(direction) {
    const planStatus = this._hass?.states?.[this._config?.entity];
    const weeks = planStatus?.attributes?.available_weeks || [];
    const historyKeys = weeks.map((w) => w.week_start).filter(Boolean);
    const displayMode = planStatus?.attributes?.display_mode || 'current';
    const displayedWeekStart = planStatus?.attributes?.displayed_week_start || null;
    if (!historyKeys.length || direction === 0) {
      return;
    }
    const isHistoryMode = displayMode === 'history' && displayedWeekStart;

    // Navigation model:
    // current -> newest history -> older history (left)
    // older history -> newer history -> current (right)
    if (!isHistoryMode) {
      if (direction < 0) {
        this._setDisplayedWeek(historyKeys[0]);
      }
      return;
    }

    const currentIndex = historyKeys.indexOf(displayedWeekStart);
    if (currentIndex === -1) {
      this._setDisplayedWeek('current');
      return;
    }

    if (direction < 0) {
      const olderIndex = currentIndex + 1;
      if (olderIndex < historyKeys.length) {
        this._setDisplayedWeek(historyKeys[olderIndex]);
      }
      return;
    }

    const newerIndex = currentIndex - 1;
    if (newerIndex >= 0) {
      this._setDisplayedWeek(historyKeys[newerIndex]);
      return;
    }

    this._setDisplayedWeek('current');
  }

  _getRuleSelection(prefix) {
    const day = this.shadowRoot?.querySelector(`#${prefix}-day`)?.value;
    const slot = this.shadowRoot?.querySelector(`#${prefix}-slot`)?.value;
    return { day, slot };
  }

  _addPrepPreference() {
    const { day, slot } = this._getRuleSelection('prep');
    const reuseDays = Number(this.shadowRoot?.querySelector('#prep-days')?.value || 1);
    if (!day || !slot || !Number.isFinite(reuseDays) || reuseDays < 1) return;
    this._callService('set_multi_day_preferences', {
      primary_weekday: day,
      primary_slot: slot,
      reuse_days: reuseDays,
    });
  }

  _removePrepPreference() {
    const { day, slot } = this._getRuleSelection('prep');
    if (!day || !slot) return;
    this._callService('clear_multi_day_preferences', {
      primary_weekday: day,
      primary_slot: slot,
    });
  }

  _clearAllPrepPreferences() {
    this._callService('clear_multi_day_preferences', {});
  }

  _addSkippedSlot() {
    const { day, slot } = this._getRuleSelection('skip');
    if (!day || !slot) return;
    this._callService('set_skip_slot', {
      weekday: day,
      slot: slot,
    });
  }

  _removeSkippedSlot() {
    const { day, slot } = this._getRuleSelection('skip');
    if (!day || !slot) return;
    this._callService('clear_skip_slots', {
      weekday: day,
      slot: slot,
    });
  }

  _clearAllSkippedSlots() {
    this._callService('clear_skip_slots', {});
  }

  _formatDate(value) {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString('de-DE');
  }

  _getSlotEntity(weekday, slot) {
    const weekdayMap = {
      'Montag': 'montag',
      'Dienstag': 'dienstag',
      'Mittwoch': 'mittwoch',
      'Donnerstag': 'donnerstag',
      'Freitag': 'freitag',
      'Samstag': 'samstag',
      'Sonntag': 'sonntag'
    };
    const slotMap = {
      'Mittagessen': 'mittagessen',
      'Abendessen': 'abendessen'
    };

    const day = weekdayMap[weekday];
    const meal = slotMap[slot];

    return `${this._entityPrefix}${day}_${meal}`;
  }

  _deriveEntityPrefix(entityId) {
    if (!entityId) return 'sensor.essensplaner_';
    if (entityId.endsWith('_weekly_plan_status')) {
      return entityId.slice(0, -'weekly_plan_status'.length);
    }
    return 'sensor.essensplaner_';
  }

  _getEffortColor(prepTime) {
    if (!prepTime) return '#808080';
    if (prepTime <= 30) return '#4caf50'; // Green - quick
    if (prepTime <= 60) return '#ff9800'; // Orange - normal
    return '#f44336'; // Red - elaborate
  }

  _renderSlot(weekday, slot, readOnly = false) {
    const entityId = this._getSlotEntity(weekday, slot);
    const state = this._hass.states[entityId];

    if (!state) {
      return `
        <div class="slot empty">
          <div class="slot-header">${slot}</div>
          <div class="slot-content">Kein Rezept</div>
        </div>
      `;
    }

    const attributes = state.attributes;
    const recipeTitle = attributes.recipe_title || 'Kein Rezept';
    const recipeUrl = attributes.recipe_url;
    const prepTime = attributes.prep_time_minutes;
    const isNew = attributes.is_new || false;
    const isReuseSlot = attributes.is_reuse_slot || false;
    const alternatives = attributes.alternatives || [];
    const selectedIndex = Number.isInteger(attributes.selected_index) ? attributes.selected_index : 0;

    const effortColor = this._getEffortColor(prepTime);
    const newBadge = isNew ? '<span class="badge new">NEU</span>' : '';
    const reuseBadge = isReuseSlot ? '<span class="badge reuse">♻️ Reste</span>' : '';

    const recipeId = attributes.recipe_id;
    const encodedRecipeUrl = encodeURIComponent(recipeUrl || '');
    const encodedRecipeTitle = encodeURIComponent(recipeTitle || '');
    const currentRating = attributes.rating || 0;
    const starsHtml = (recipeId || recipeUrl) && !readOnly ? `
      <div class="star-rating">
        ${[1,2,3,4,5].map(s => `
          <span class="star ${s <= currentRating ? 'filled' : ''}"
                onclick="this.getRootNode().host._rateRecipe(${recipeId || 'null'}, '${encodedRecipeUrl}', '${encodedRecipeTitle}', ${s})">&#9733;</span>
        `).join('')}
      </div>
    ` : '';

    const alternativesHtml = !isReuseSlot ? `
      <select class="alternatives" onchange="this.getRootNode().host._selectRecipe('${weekday}', '${slot}', this.value)" ${readOnly ? 'disabled' : ''}>
        <option value="-1" ${selectedIndex === -1 ? 'selected' : ''}>Kein Rezept</option>
        ${alternatives.map((alt, index) => `
          <option value="${index}" ${index === selectedIndex ? 'selected' : ''}>
            ${alt.title}${alt.is_new ? ' 🆕' : ''}
          </option>
        `).join('')}
      </select>
      <div class="custom-url">
        <input class="custom-url-input" type="url" placeholder="Rezept-Link einfuegen" ${readOnly ? 'disabled' : ''} />
        <button class="custom-url-button" onclick="this.getRootNode().host._handleCustomUrlClick(this, '${weekday}', '${slot}')" ${readOnly ? 'disabled' : ''}>
          Hinzufuegen
        </button>
        <div class="custom-url-feedback" aria-live="polite"></div>
      </div>
    ` : '';

    return `
      <div class="slot" style="border-left: 4px solid ${effortColor}">
        <div class="slot-header">
          ${slot}
          ${prepTime ? `<span class="prep-time">${prepTime} min</span>` : ''}
        </div>
        <div class="slot-content">
          <div class="recipe-title">
            ${recipeUrl ? `<a href="${recipeUrl}" target="_blank">${recipeTitle}</a>` : recipeTitle}
          </div>
          <div class="badges">
            ${newBadge}
            ${reuseBadge}
          </div>
          ${starsHtml}
          ${alternativesHtml}
        </div>
      </div>
    `;
  }

  render() {
    if (!this._hass || !this._config) return;

    // Save current scroll position before re-rendering
    const weekGrid = this.shadowRoot.querySelector('.week-grid');
    if (weekGrid) {
      this._savedScrollPosition = weekGrid.scrollLeft;
    }

    const weekdays = ['Samstag', 'Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag'];
    const slots = ['Mittagessen', 'Abendessen'];

    const planStatus = this._hass.states[this._config.entity];
    const hasPlan = planStatus && planStatus.state !== 'no_plan';
    const completedAt = planStatus?.attributes?.completed_at;
    const isCompleted = Boolean(completedAt);
    const completedLabel = completedAt ? this._formatDate(completedAt) : '';
    const generatedAt = planStatus?.attributes?.generated_at || null;
    const displayMode = planStatus?.attributes?.display_mode || 'current';
    const isHistoryMode = displayMode === 'history';
    const displayedWeekStart = planStatus?.attributes?.displayed_week_start || null;
    const availableWeeks = planStatus?.attributes?.available_weeks || [];
    const prepPrefsState = this._hass.states[this._config.multi_day_preferences_entity];
    const skippedState = this._hass.states[this._config.skipped_slots_entity];
    const prepGroups = prepPrefsState?.attributes?.groups || [];
    const skippedSlots = skippedState?.attributes?.slots || [];

    if (this._isGenerating && this._lastGeneratedAt && generatedAt && generatedAt !== this._lastGeneratedAt) {
      this._isGenerating = false;
      this._lastGeneratedAt = generatedAt;
    }
    if (this._isGenerating && !this._lastGeneratedAt && generatedAt) {
      this._isGenerating = false;
      this._lastGeneratedAt = generatedAt;
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }
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
          gap: 12px;
        }
        .card-title {
          font-size: 24px;
          font-weight: 500;
          color: var(--primary-text-color);
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .action-buttons {
          display: flex;
          gap: 8px;
          align-items: center;
          flex-wrap: wrap;
        }
        .week-selector {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          margin-right: 8px;
        }
        .week-select {
          min-width: 180px;
          padding: 6px;
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          font-size: 12px;
        }
        .action-button {
          padding: 8px 16px;
          border-radius: 4px;
          cursor: pointer;
          font-size: 14px;
          border: none;
        }
        .action-button.primary {
          background: var(--primary-color);
          color: white;
        }
        .action-button.secondary {
          background: transparent;
          color: var(--primary-color);
          border: 1px solid var(--primary-color);
        }
        .action-button:hover {
          opacity: 0.9;
        }
        .action-button[disabled] {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .status-badge {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          padding: 2px 8px;
          border-radius: 999px;
          font-size: 11px;
          background: #e0f2f1;
          color: #00695c;
        }
        .status-note {
          margin: 0 0 12px;
          font-size: 12px;
          color: var(--secondary-text-color);
        }
        .rules-panel {
          border: 1px solid var(--divider-color);
          border-radius: 8px;
          padding: 10px;
          margin: 0 0 12px;
          background: var(--secondary-background-color);
        }
        .rules-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 12px;
        }
        .rules-block-title {
          margin: 0 0 8px;
          font-size: 12px;
          font-weight: 600;
          color: var(--primary-text-color);
          text-transform: uppercase;
        }
        .rules-controls {
          display: flex;
          gap: 6px;
          flex-wrap: wrap;
          align-items: center;
        }
        .rules-controls select {
          min-width: 110px;
          padding: 4px;
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          font-size: 12px;
        }
        .rules-list {
          margin-top: 8px;
          font-size: 12px;
          color: var(--secondary-text-color);
        }
        .rules-list .empty {
          font-style: italic;
        }
        .week-grid {
          display: grid;
          grid-template-columns: repeat(7, minmax(160px, 1fr));
          gap: 8px;
          overflow-x: auto;
          overscroll-behavior-x: contain;
          scroll-behavior: auto;
          -webkit-overflow-scrolling: touch;
          padding-bottom: 4px;
          will-change: scroll-position;
        }
        .day-column {
          display: flex;
          flex-direction: column;
          gap: 8px;
          min-width: 160px;
        }
        .day-header {
          font-weight: 600;
          font-size: 14px;
          text-align: center;
          padding: 8px;
          background: var(--secondary-background-color);
          border-radius: 4px;
          color: var(--primary-text-color);
        }
        .slot {
          background: var(--card-background-color, white);
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          padding: 8px;
          min-height: 120px;
        }
        .slot.empty {
          opacity: 0.5;
        }
        .slot-header {
          font-size: 12px;
          font-weight: 500;
          color: var(--secondary-text-color);
          margin-bottom: 4px;
          display: flex;
          justify-content: space-between;
        }
        .prep-time {
          font-size: 11px;
          color: var(--secondary-text-color);
        }
        .slot-content {
          font-size: 13px;
        }
        .recipe-title {
          margin-bottom: 4px;
          line-height: 1.3;
        }
        .recipe-title a {
          color: var(--primary-color);
          text-decoration: none;
        }
        .recipe-title a:hover {
          text-decoration: underline;
        }
        .badges {
          display: flex;
          gap: 4px;
          margin-bottom: 8px;
        }
        .badge {
          display: inline-block;
          padding: 2px 6px;
          border-radius: 3px;
          font-size: 10px;
          font-weight: 500;
        }
        .badge.new {
          background: #4caf50;
          color: white;
        }
        .badge.reuse {
          background: #ff9800;
          color: white;
        }
        .alternatives {
          width: 100%;
          padding: 4px;
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          font-size: 12px;
        }
        .custom-url {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 6px;
          margin-top: 6px;
          align-items: center;
        }
        .custom-url-input {
          flex: 1;
          padding: 4px 6px;
          border: 1px solid var(--divider-color);
          border-radius: 4px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          font-size: 12px;
        }
        .custom-url-button {
          padding: 4px 8px;
          border: none;
          border-radius: 4px;
          background: var(--primary-color);
          color: white;
          cursor: pointer;
          font-size: 12px;
        }
        .custom-url-button:hover {
          opacity: 0.9;
        }
        .custom-url-feedback {
          display: none;
          grid-column: 1 / -1;
          font-size: 11px;
          color: var(--secondary-text-color);
        }
        .custom-url-feedback.success {
          color: #2e7d32;
        }
        .custom-url-feedback.error {
          color: #c62828;
        }
        .star-rating {
          display: flex;
          gap: 2px;
          margin-top: 4px;
        }
        .star {
          font-size: 16px;
          cursor: pointer;
          color: #ccc;
          line-height: 1;
          transition: color 0.1s;
        }
        .star.filled {
          color: #f5a623;
        }
        .star:hover {
          color: #f5a623;
        }
        .no-plan {
          text-align: center;
          padding: 40px;
          color: var(--secondary-text-color);
        }
        @media (max-width: 768px) {
          .rules-grid {
            grid-template-columns: 1fr;
          }
          .week-grid {
            grid-template-columns: 1fr;
          }
          .day-column {
            flex-direction: row;
          }
          .day-header {
            min-width: 100px;
          }
        }
      </style>
      <ha-card class="card">
        <div class="card-header">
          <div class="card-title">
            🍽️ Wochenplan
            ${isCompleted ? `<span class="status-badge">Abgeschlossen am ${completedLabel}</span>` : ''}
          </div>
          <div class="week-selector">
            <button class="action-button secondary" onclick="this.getRootNode().host._changeDisplayedWeek(-1)">&larr;</button>
            <select class="week-select" onchange="this.getRootNode().host._setDisplayedWeek(this.value)">
              <option value="current" ${!isHistoryMode ? 'selected' : ''}>Aktuelle Woche</option>
              ${availableWeeks.map((week) => `
                <option value="${week.week_start}" ${(isHistoryMode && displayedWeekStart === week.week_start) ? 'selected' : ''}>
                  Woche ab ${this._formatDate(week.week_start)}
                </option>
              `).join('')}
            </select>
            <button class="action-button secondary" onclick="this.getRootNode().host._changeDisplayedWeek(1)">&rarr;</button>
          </div>
          ${hasPlan && !isHistoryMode ? `
            <div class="action-buttons">
              ${isCompleted ? `
                <button class="action-button primary" ${this._isGenerating ? 'disabled' : ''} onclick="this.getRootNode().host._generatePlan()">
                  Neuen Plan generieren
                </button>
              ` : `
                <button class="action-button primary" ${this._isGenerating ? 'disabled' : ''} onclick="this.getRootNode().host._completeWeek(true)">
                  Woche abschliessen
                </button>
                <button class="action-button secondary" ${this._isGenerating ? 'disabled' : ''} onclick="this.getRootNode().host._generatePlan()">
                  Neu generieren
                </button>
              `}
            </div>
          ` : ''}
        </div>
        ${isHistoryMode ? `<div class="status-note">Historische Woche (${this._formatDate(displayedWeekStart)}) - nur Anzeige.</div>` : ''}
        ${this._isGenerating ? `<div class="status-note">Generierung laeuft ...</div>` : ''}
        ${!isHistoryMode ? `
          <div class="rules-panel">
            <div class="rules-grid">
              <div>
                <p class="rules-block-title">Vorkochen (fuer naechste Generierung)</p>
                <div class="rules-controls">
                  <select id="prep-day">
                    ${weekdays.map((day) => `<option value="${day}">${day}</option>`).join('')}
                  </select>
                  <select id="prep-slot">
                    ${slots.map((slot) => `<option value="${slot}">${slot}</option>`).join('')}
                  </select>
                  <select id="prep-days">
                    ${[1,2,3,4,5,6].map((d) => `<option value="${d}">${d} Tag${d > 1 ? 'e' : ''}</option>`).join('')}
                  </select>
                  <button class="action-button secondary" onclick="this.getRootNode().host._addPrepPreference()">Setzen</button>
                  <button class="action-button secondary" onclick="this.getRootNode().host._removePrepPreference()">Entfernen</button>
                  <button class="action-button secondary" onclick="this.getRootNode().host._clearAllPrepPreferences()">Alle loeschen</button>
                </div>
                <div class="rules-list">
                  ${prepGroups.length
                    ? prepGroups.map((g) => {
                        const reuseCount = (g.reuse_slots || []).length;
                        return `<div>${g.primary_weekday} ${g.primary_slot} -> +${reuseCount} Tag${reuseCount !== 1 ? 'e' : ''}</div>`;
                      }).join('')
                    : '<div class="empty">Keine Vorkoch-Regeln gesetzt.</div>'}
                </div>
              </div>
              <div>
                <p class="rules-block-title">Kein Rezept fuer Slots</p>
                <div class="rules-controls">
                  <select id="skip-day">
                    ${weekdays.map((day) => `<option value="${day}">${day}</option>`).join('')}
                  </select>
                  <select id="skip-slot">
                    ${slots.map((slot) => `<option value="${slot}">${slot}</option>`).join('')}
                  </select>
                  <button class="action-button secondary" onclick="this.getRootNode().host._addSkippedSlot()">Hinzufuegen</button>
                  <button class="action-button secondary" onclick="this.getRootNode().host._removeSkippedSlot()">Entfernen</button>
                  <button class="action-button secondary" onclick="this.getRootNode().host._clearAllSkippedSlots()">Alle loeschen</button>
                </div>
                <div class="rules-list">
                  ${skippedSlots.length
                    ? skippedSlots.map((s) => `<div>${s.weekday} ${s.slot}</div>`).join('')
                    : '<div class="empty">Keine Skip-Slots gesetzt.</div>'}
                </div>
              </div>
            </div>
          </div>
        ` : ''}
        ${hasPlan ? `
          <div class="week-grid">
            ${weekdays.map(weekday => `
              <div class="day-column">
                <div class="day-header">${weekday}</div>
                ${slots.map(slot => this._renderSlot(weekday, slot, isHistoryMode)).join('')}
              </div>
            `).join('')}
          </div>
        ` : `
          <div class="no-plan">
            <p>Kein Wochenplan vorhanden</p>
            <button class="action-button primary" ${this._isGenerating ? 'disabled' : ''} onclick="this.getRootNode().host._generatePlan()">
              Wochenplan generieren
            </button>
          </div>
        `}
      </ha-card>
    `;

    // Attach scroll listener to the new element (re-attached on each render)
    setTimeout(() => {
      const weekGrid = this.shadowRoot.querySelector('.week-grid');
      if (weekGrid) {
        // Remove old listener if exists (cleanup)
        if (this._scrollHandler) {
          weekGrid.removeEventListener('scroll', this._scrollHandler);
        }

        // Create new scroll handler
        this._scrollHandler = () => {
          // Ignore programmatic scrolls (from restoring position)
          if (this._isRestoringScroll) {
            return;
          }

          this._isScrolling = true;

          // Clear previous timeout
          if (this._scrollTimeout) {
            clearTimeout(this._scrollTimeout);
          }

          // Set a new timeout to detect when scrolling stops
          this._scrollTimeout = setTimeout(() => {
            this._isScrolling = false;

            // Render if there was a pending render
            if (this._pendingRender) {
              this._pendingRender = false;
              this.render();
            }
          }, 3000); // Wait 3 seconds after last scroll event to allow user to scroll again
        };

        // Attach to new element
        weekGrid.addEventListener('scroll', this._scrollHandler, { passive: true });

        // Restore saved scroll position (set flag to ignore the scroll event)
        if (this._savedScrollPosition > 0) {
          this._isRestoringScroll = true;
          weekGrid.scrollLeft = this._savedScrollPosition;
          // Reset flag after a short delay to allow the scroll event to be ignored
          setTimeout(() => {
            this._isRestoringScroll = false;
          }, 50);
        }
      }
    }, 0);
  }
}

customElements.define('weekly-plan-card', WeeklyPlanCard);

// Register the card with Home Assistant
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'weekly-plan-card',
  name: 'KI-Essensplaner Wochenplan',
  description: 'Zeigt den wöchentlichen Essensplan mit Rezeptauswahl',
  preview: false,
  documentationURL: 'https://github.com/sourcesavant/ki-essensplaner',
});

console.info(
  '%c KI-ESSENSPLANER-CARD %c Weekly Plan Card loaded ',
  'color: white; background: #4caf50; font-weight: 700;',
  'color: #4caf50; background: white; font-weight: 700;'
);










