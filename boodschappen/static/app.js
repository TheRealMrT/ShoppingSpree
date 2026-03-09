/* ================================================================
   Boodschappen – app.js
   Plain-JS SPA, no framework. Communicates with FastAPI /api/*
   ================================================================ */

// ── Constants ────────────────────────────────────────────────────

const API = '/api';

const CATEGORIES = [
  'Groente & fruit', 'Vlees vis & vega', 'Zuivel & eieren', 'Kaas',
  'Brood & bakkerij', 'Ontbijt & beleg', 'Pasta rijst & wereldkeuken',
  'Soepen sauzen & conserven', 'Snacks & snoep', 'Dranken', 'Diepvries',
  'Persoonlijke verzorging', 'Huishouden & schoonmaak', 'Overig',
];

const CATEGORY_ORDER = Object.fromEntries(CATEGORIES.map((c, i) => [c, i]));

const SUPERMARKETS = [
  { value: 'beide', label: 'Beide' },
  { value: 'aldi',  label: 'Aldi'  },
  { value: 'jumbo', label: 'Jumbo' },
];

const RECIPE_TAGS = [
  { group: 'Maaltijdtype', tags: ['Ontbijt', 'Lunch', 'Diner', 'Snack', 'Dessert', 'Soep', 'Bijgerecht', 'Tussendoor'] },
  { group: 'Dieet',        tags: ['Vegetarisch', 'Veganistisch', 'Glutenvrij', 'Lactosevrij', 'Koolhydraatarm'] },
  { group: 'Keuken',       tags: ['Italiaans', 'Aziatisch', 'Nederlands', 'Mexicaans', 'Grieks', 'Indiaas', 'Frans'] },
  { group: 'Bereiding',    tags: ['Snel', 'Makkelijk', 'Oven', 'Airfryer', 'Slowcooker', 'Barbecue', 'Eenpan'] },
];
const ALL_TAGS = RECIPE_TAGS.flatMap(g => g.tags);

// ── State ────────────────────────────────────────────────────────

const state = {
  recipes: [],
  staples: [],
  lists:   [],
  familie: [],
  chat: {
    messages: [],   // [{role, content}]
    open: false,
  },
  // "Nieuwe lijst" working state
  newList: {
    id: null,
    selectedRecipes: [],
    items: [],
    addedStaples: false,
  },
  pendingPhoto: null,   // File object to upload after recipe save
  collector: { items: [] },  // [{type:'photo'|'text'|'url', data:File|string, preview:string}]
};

// ── Filter state ─────────────────────────────────────────────────

const filterState = {
  search:      '',
  tags:        new Set(),  // active tag filters
  maxPrepTime: 0,          // 0 = no limit
};

// ── Notification log ──────────────────────────────────────────────

const notificationLog = []; // [{msg, type, ts}]
let notifUnread = 0;

function updateNotifBadge() {
  const badge = $('#notif-badge');
  if (!badge) return;
  if (notifUnread > 0) {
    badge.textContent = notifUnread > 99 ? '99+' : String(notifUnread);
    badge.style.display = 'inline-flex';
  } else {
    badge.style.display = 'none';
  }
}

function openNotifPanel() {
  notifUnread = 0;
  updateNotifBadge();
  renderNotifPanel();
  $('#notif-panel').classList.add('open');
}

function closeNotifPanel() {
  $('#notif-panel').classList.remove('open');
}

function toggleNotifPanel() {
  if ($('#notif-panel').classList.contains('open')) closeNotifPanel();
  else openNotifPanel();
}

function renderNotifPanel() {
  const container = $('#notif-list');
  if (!notificationLog.length) {
    container.innerHTML = '<p style="padding:.75rem;color:var(--text-muted);font-size:.85rem">Nog geen meldingen.</p>';
    return;
  }
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  container.innerHTML = notificationLog.map(n => {
    const timeStr = n.ts.toLocaleTimeString('nl-NL', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    return `<div class="notif-item notif-${esc(n.type)}">
      <span class="notif-icon">${icons[n.type] || 'ℹ️'}</span>
      <div class="notif-body">
        <span class="notif-msg">${esc(n.msg)}</span>
        <span class="notif-time">${timeStr}</span>
      </div>
    </div>`;
  }).join('');
}

function clearNotifLog() {
  notificationLog.length = 0;
  notifUnread = 0;
  updateNotifBadge();
  renderNotifPanel();
}

// ── Markdown renderer ─────────────────────────────────────────────

function renderMarkdown(text) {
  // 1. Escape HTML to prevent XSS
  let s = esc(text);

  // 2. Fenced code blocks (multi-line) — process before inline patterns
  s = s.replace(/```[\s\S]*?```/g, m => {
    const inner = m.replace(/^```[^\n]*\n?/, '').replace(/```$/, '').trim();
    return `<pre><code>${inner}</code></pre>`;
  });

  // 3. Inline code
  s = s.replace(/`([^`\n]+)`/g, '<code>$1</code>');

  // 4. Headings (match only at start of a "line" in the escaped string)
  s = s.replace(/^#{4,} (.+)$/gm, '<strong>$1</strong>');
  s = s.replace(/^### (.+)$/gm,   '<strong>$1</strong>');
  s = s.replace(/^## (.+)$/gm,    '<strong style="font-size:1.02em">$1</strong>');
  s = s.replace(/^# (.+)$/gm,     '<strong style="font-size:1.05em">$1</strong>');

  // 5. Bold & italic
  s = s.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  s = s.replace(/\*\*(.+?)\*\*/g,     '<strong>$1</strong>');
  s = s.replace(/__(.+?)__/g,          '<strong>$1</strong>');
  s = s.replace(/\*(?!\s)(.+?)(?<!\s)\*/g, '<em>$1</em>');
  s = s.replace(/_(?!\s)(.+?)(?<!\s)_/g,   '<em>$1</em>');

  // 6. Horizontal rule
  s = s.replace(/^---+$/gm, '<hr>');

  // 7. Unordered list items
  s = s.replace(/^[•\-\*] (.+)$/gm, '<li>$1</li>');
  // Wrap consecutive <li> in <ul>
  s = s.replace(/(<li>(?:.*?)<\/li>\n?)+/g, m => `<ul>${m}</ul>`);

  // 8. Ordered list items
  s = s.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

  // 9. Line breaks: double newline = paragraph break, single = <br>
  s = s.replace(/\n\n/g, '<br><br>');
  s = s.replace(/\n/g, '<br>');

  return s;
}

// ── Utility ──────────────────────────────────────────────────────

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

function esc(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function fmtAmount(amount, unit) {
  if (amount == null && !unit) return '';
  const parts = [];
  if (amount != null) parts.push(Number.isInteger(amount) ? amount : +parseFloat(amount).toFixed(2));
  if (unit) parts.push(unit);
  return parts.join(' ');
}

function supermarketBadge(sm) {
  const cls = { aldi: 'badge-aldi', jumbo: 'badge-jumbo', beide: 'badge-beide' };
  const lbl = { aldi: 'Aldi', jumbo: 'Jumbo', beide: 'A+J' };
  return `<span class="badge ${cls[sm] || 'badge-beide'}">${lbl[sm] || sm}</span>`;
}

function sortByCategory(items) {
  return [...items].sort((a, b) =>
    (CATEGORY_ORDER[a.category] ?? 99) - (CATEGORY_ORDER[b.category] ?? 99) ||
    (a.name || '').localeCompare(b.name || '')
  );
}

// ── Toast ────────────────────────────────────────────────────────

function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  $('#toast-container').appendChild(el);
  setTimeout(() => el.remove(), 3500);

  // Also log to persistent notification log
  notificationLog.unshift({ msg, type, ts: new Date() });
  if (notificationLog.length > 100) notificationLog.pop();
  notifUnread++;
  updateNotifBadge();
  // If the panel is open, refresh it
  if ($('#notif-panel').classList.contains('open')) renderNotifPanel();
}

// ── API helpers ──────────────────────────────────────────────────

async function api(method, path, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(`${API}${path}`, opts);
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

const get  = (path)       => api('GET',    path);
const post = (path, body) => api('POST',   path, body);
const put  = (path, body) => api('PUT',    path, body);
const del  = (path)       => api('DELETE', path);

// ── Category <select> builder ────────────────────────────────────

function buildCategorySelect(sel, selectedValue) {
  sel.innerHTML = CATEGORIES.map(c =>
    `<option value="${esc(c)}" ${c === selectedValue ? 'selected' : ''}>${esc(c)}</option>`
  ).join('');
}

// ── Tab navigation ────────────────────────────────────────────────

function initTabs() {
  $$('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.tab-btn').forEach(b => b.classList.remove('active'));
      $$('.tab-content').forEach(t => t.classList.remove('active'));
      btn.classList.add('active');
      const tab = $(`#tab-${btn.dataset.tab}`);
      if (tab) tab.classList.add('active');
      onTabActivate(btn.dataset.tab);
    });
  });
}

function onTabActivate(tab) {
  if (tab === 'recepten')        loadRecipes();
  if (tab === 'nieuwe-lijst')    loadNewListTab();
  if (tab === 'lijsten')         loadLists();
  if (tab === 'vaste-artikelen') loadStaples();
  if (tab === 'familie')         loadFamilie();
}

function switchTab(tabName) {
  $$('.tab-btn').forEach(b => b.classList.remove('active'));
  $$('.tab-content').forEach(t => t.classList.remove('active'));
  const btn = $(`.tab-btn[data-tab="${tabName}"]`);
  const content = $(`#tab-${tabName}`);
  if (btn) btn.classList.add('active');
  if (content) content.classList.add('active');
  onTabActivate(tabName);
}

// ════════════════════════════════════════════════════════════════
// TAB 1 – RECEPTEN
// ════════════════════════════════════════════════════════════════

async function loadRecipes() {
  state.recipes = await get('/recipes');
  buildFilterTagRow();
  applyRecipeFilter();
  populateRecipeSelect();
}

// ── Tag picker (recipe form) ──────────────────────────────────────

function buildTagPicker(container, selectedTags = []) {
  const active = new Set(selectedTags.map(t => t.trim()).filter(Boolean));
  container.innerHTML = RECIPE_TAGS.map(group => `
    <div class="tag-group">
      <span class="tag-group-label">${esc(group.group)}</span>
      <div class="tag-options">
        ${group.tags.map(tag => `
          <button type="button" class="tag-option ${active.has(tag) ? 'active' : ''}"
            onclick="this.classList.toggle('active')" data-tag="${esc(tag)}">${esc(tag)}</button>
        `).join('')}
      </div>
    </div>
  `).join('');
}

function getSelectedTags(container) {
  return $$('.tag-option.active', container).map(btn => btn.dataset.tag);
}

// ── Filter bar ────────────────────────────────────────────────────

function buildFilterTagRow() {
  const container = $('#filter-tag-row');
  if (!container) return;
  container.innerHTML = ALL_TAGS.map(tag => `
    <button type="button" class="filter-tag-chip ${filterState.tags.has(tag) ? 'active' : ''}"
      data-tag="${esc(tag)}">${esc(tag)}</button>
  `).join('');
  // Attach click handlers
  $$('.filter-tag-chip', container).forEach(btn => {
    btn.addEventListener('click', () => {
      const tag = btn.dataset.tag;
      if (filterState.tags.has(tag)) {
        filterState.tags.delete(tag);
        btn.classList.remove('active');
      } else {
        filterState.tags.add(tag);
        btn.classList.add('active');
      }
      applyRecipeFilter();
    });
  });
}

function resetFilter() {
  filterState.search = '';
  filterState.tags.clear();
  filterState.maxPrepTime = 0;
  const searchEl = $('#filter-search');
  if (searchEl) searchEl.value = '';
  const prepEl = $('#filter-prep-time');
  if (prepEl) prepEl.value = '0';
  $$('.filter-tag-chip').forEach(c => c.classList.remove('active'));
  applyRecipeFilter();
}

function applyRecipeFilter() {
  const search  = filterState.search.toLowerCase();
  const tags    = filterState.tags;
  const maxTime = filterState.maxPrepTime;

  let filtered = state.recipes;

  if (search) {
    filtered = filtered.filter(r => r.name.toLowerCase().includes(search));
  }
  if (tags.size > 0) {
    filtered = filtered.filter(r => {
      if (!r.tags) return false;
      const rTags = r.tags.split(',').map(t => t.trim());
      return [...tags].some(t => rTags.includes(t));
    });
  }
  if (maxTime > 0) {
    filtered = filtered.filter(r => r.prep_time != null && r.prep_time <= maxTime);
  }

  renderRecipeListFiltered(filtered);
}

function renderRecipeList() {
  applyRecipeFilter();
}

function renderRecipeListFiltered(recipes) {
  const container = $('#recipe-list');
  if (!state.recipes.length) {
    container.innerHTML = `<div class="empty-state"><div class="icon">📖</div><p>Nog geen recepten. Voeg er een toe!</p></div>`;
    return;
  }
  if (!recipes.length) {
    container.innerHTML = `<div class="empty-state"><div class="icon">🔍</div><p>Geen recepten gevonden voor dit filter.</p></div>`;
    return;
  }
  container.innerHTML = recipes.map(r => {
    const prepBadge = r.prep_time
      ? `<span class="prep-time-badge">⏱ ${r.prep_time} min</span>`
      : '';
    return `
    <div class="card" id="recipe-card-${r.id}">
      <div class="card-header" style="align-items:center">
        ${r.has_photo ? `<img src="/api/recipes/${r.id}/photo" class="recipe-thumb" onerror="this.style.display='none'" loading="lazy">` : ''}
        <div style="flex:1;min-width:0">
          <div class="card-title">${esc(r.name)}${prepBadge}</div>
          <div class="card-meta">
            ${r.source ? `<span>${esc(r.source)}</span> · ` : ''}
            ${r.default_servings} porties
          </div>
          ${r.tags ? `<div class="tags">${r.tags.split(',').map(t => `<span class="tag">${esc(t.trim())}</span>`).join('')}</div>` : ''}
        </div>
        <div style="display:flex;gap:.35rem;flex-shrink:0">
          <button class="btn btn-secondary btn-sm" onclick="editRecipe(${r.id})">✏️ Bewerk</button>
          <button class="btn btn-danger btn-sm" onclick="deleteRecipe(${r.id})">🗑</button>
        </div>
      </div>
    </div>`;
  }).join('');
}

function showRecipeForm(recipe = null) {
  const card = $('#recipe-form-card');
  card.style.display = 'block';
  card.scrollIntoView({ behavior: 'smooth', block: 'start' });

  $('#recipe-form-title').textContent = recipe ? 'Recept bewerken' : 'Nieuw recept';
  $('#recipe-id').value        = recipe?.id || '';
  $('#recipe-name').value      = recipe?.name || '';
  $('#recipe-source').value    = recipe?.source || '';
  $('#recipe-servings').value  = recipe?.default_servings || 4;
  $('#recipe-prep-time').value = recipe?.prep_time ?? '';
  buildTagPicker($('#recipe-tag-picker'), recipe?.tags ? recipe.tags.split(',').map(t => t.trim()) : []);
  $('#recipe-steps').value     = recipe?.steps || '';
  $('#recipe-notes').value     = recipe?.notes || '';

  // Show existing photo if editing
  const preview = $('#recipe-photo-preview');
  const img     = $('#recipe-photo-img');
  if (recipe?.has_photo) {
    img.src = `/api/recipes/${recipe.id}/photo?t=${Date.now()}`;
    preview.style.display = 'flex';
  } else {
    preview.style.display = 'none';
    img.src = '';
  }
  $('#recipe-photo-file').value = '';

  renderIngRows(recipe?.ingredients || []);
}

// ── fillRecipeForm – shared helper for all import modes ──────────

function fillRecipeForm(data) {
  showRecipeForm();
  $('#recipe-name').value      = data.naam     || '';
  $('#recipe-source').value    = data.bron     || '';
  $('#recipe-servings').value  = parseInt(data.porties) || 4;
  $('#recipe-prep-time').value = data.bereidingstijd ?? '';

  const tagList = Array.isArray(data.tags) ? data.tags : (data.tags ? data.tags.split(',').map(t => t.trim()) : []);
  buildTagPicker($('#recipe-tag-picker'), tagList);

  $('#recipe-steps').value     = data.stappen  || '';
  $('#recipe-notes').value     = '';

  const ings = (data.ingredienten || []).map(ing => ({
    name:     ing.naam        || '',
    amount:   ing.hoeveelheid ?? null,
    unit:     ing.eenheid     || null,
    category: ing.categorie   || 'Overig',
  }));
  renderIngRows(ings.length ? ings : [{}]);
  return ings.length;
}

function renderIngRows(ings) {
  const container = $('#ing-rows-container');
  container.innerHTML = '';
  ings.forEach(ing => addIngRow(ing));
  if (!ings.length) addIngRow();
}

function addIngRow(ing = {}) {
  const container = $('#ing-rows-container');
  const row = document.createElement('div');
  row.className = 'ing-row';

  const catOptions = CATEGORIES.map(c =>
    `<option value="${esc(c)}" ${c === (ing.category || 'Overig') ? 'selected' : ''}>${esc(c)}</option>`
  ).join('');

  row.innerHTML = `
    <input type="text" class="ing-name" placeholder="Naam" value="${esc(ing.name || '')}" required>
    <input type="number" class="ing-amount" placeholder="bijv. 200" value="${ing.amount ?? ''}" step="any">
    <input type="text" class="ing-unit" placeholder="gr, el, stuks" value="${esc(ing.unit || '')}">
    <select class="ing-category">${catOptions}</select>
    <button type="button" class="btn-icon del-btn" title="Verwijder rij" onclick="this.closest('.ing-row').remove()">✕</button>
  `;
  if (ing.id) row.dataset.ingId = ing.id;
  container.appendChild(row);
}

async function editRecipe(id) {
  try {
    const recipe = await get(`/recipes/${id}`);
    showRecipeForm(recipe);
  } catch (e) {
    toast('Fout bij laden recept: ' + e.message, 'error');
  }
}

async function deleteRecipe(id) {
  if (!confirm('Recept verwijderen?')) return;
  try {
    await del(`/recipes/${id}`);
    toast('Recept verwijderd', 'success');
    await loadRecipes();
  } catch (e) {
    toast('Fout: ' + e.message, 'error');
  }
}

async function saveRecipe(e) {
  e.preventDefault();
  const id = $('#recipe-id').value;
  const ingredients = $$('.ing-row').map(row => ({
    name:     $('.ing-name', row).value.trim(),
    amount:   $('.ing-amount', row).value ? parseFloat($('.ing-amount', row).value) : null,
    unit:     $('.ing-unit', row).value.trim() || null,
    category: $('.ing-category', row).value,
  })).filter(i => i.name);

  const selectedTags = getSelectedTags($('#recipe-tag-picker'));
  const prepTimeVal  = $('#recipe-prep-time').value;
  const payload = {
    name:             $('#recipe-name').value.trim(),
    source:           $('#recipe-source').value.trim() || null,
    default_servings: parseInt($('#recipe-servings').value) || 4,
    tags:             selectedTags.length ? selectedTags.join(', ') : null,
    prep_time:        prepTimeVal ? parseInt(prepTimeVal) : null,
    steps:            $('#recipe-steps').value.trim() || null,
    notes:            $('#recipe-notes').value.trim() || null,
    ingredients,
  };

  try {
    let recipeId;
    if (id) {
      await put(`/recipes/${id}`, {
        name: payload.name, source: payload.source,
        default_servings: payload.default_servings,
        tags: payload.tags, prep_time: payload.prep_time,
        steps: payload.steps, notes: payload.notes,
      });
      const existing = await get(`/recipes/${id}`);
      for (const ing of existing.ingredients) {
        await del(`/recipes/${id}/ingredients/${ing.id}`);
      }
      for (const ing of ingredients) {
        await post(`/recipes/${id}/ingredients`, ing);
      }
      recipeId = parseInt(id);
      toast('Recept bijgewerkt', 'success');
    } else {
      const created = await post('/recipes', payload);
      recipeId = created.id;
      toast('Recept aangemaakt', 'success');
    }

    // Upload photo: newly selected file in form takes priority, then pending photo
    const formPhotoFile = $('#recipe-photo-file').files[0];
    const photoFile = formPhotoFile || state.pendingPhoto;
    if (photoFile && recipeId) {
      await uploadRecipePhoto(recipeId, photoFile);
    }
    state.pendingPhoto = null;

    hideRecipeForm();
    await loadRecipes();
  } catch (e) {
    toast('Fout bij opslaan: ' + e.message, 'error');
  }
}

function hideRecipeForm() {
  $('#recipe-form-card').style.display = 'none';
  $('#recipe-form').reset();
  $('#recipe-id').value = '';
  $('#recipe-photo-preview').style.display = 'none';
  // Clear tag picker
  const picker = $('#recipe-tag-picker');
  if (picker) picker.innerHTML = '';
  state.pendingPhoto = null;
}

async function uploadRecipePhoto(recipeId, file) {
  try {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch(`${API}/recipes/${recipeId}/photo`, { method: 'POST', body: fd });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
  } catch (e) {
    console.warn('Foto upload mislukt:', e.message);
    toast('Foto opslaan mislukt: ' + e.message, 'error');
  }
}

async function removeRecipePhoto(recipeId) {
  if (!confirm('Foto verwijderen?')) return;
  try {
    await del(`/recipes/${recipeId}/photo`);
    $('#recipe-photo-preview').style.display = 'none';
    toast('Foto verwijderd', 'success');
  } catch (e) {
    toast('Verwijderen mislukt: ' + e.message, 'error');
  }
}

// ── Import overlay ────────────────────────────────────────────────

let _importTimerInterval = null;
let _importTimerStart    = null;

function showImportLoader(
  msg = 'Recept inlezen…',
  sub = 'Recept wordt geanalyseerd…'
) {
  let overlay = $('#import-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'import-overlay';
    overlay.style.cssText =
      'position:fixed;inset:0;z-index:9998;background:rgba(0,0,0,.55);' +
      'display:flex;align-items:center;justify-content:center;';
    document.body.appendChild(overlay);
  }
  overlay.innerHTML = `
    <div style="background:white;border-radius:14px;padding:2rem 2.5rem;text-align:center;
                box-shadow:0 8px 40px rgba(0,0,0,.25);max-width:300px">
      <div class="import-spinner"></div>
      <p style="font-weight:700;color:var(--green);margin-top:1rem;font-size:1rem">${esc(msg)}</p>
      <p id="import-loader-sub" style="font-size:.82rem;color:var(--text-muted);margin-top:.3rem">${esc(sub)}</p>
      <p id="import-loader-timer" style="font-size:.78rem;color:var(--text-muted);margin-top:.5rem;font-variant-numeric:tabular-nums;letter-spacing:.01em">0s</p>
    </div>`;
  overlay.style.display = 'flex';

  // Start live elapsed-time counter
  clearInterval(_importTimerInterval);
  _importTimerStart = Date.now();
  _importTimerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - _importTimerStart) / 1000);
    const timerEl = $('#import-loader-timer');
    if (timerEl) {
      const mins = Math.floor(elapsed / 60);
      const secs = elapsed % 60;
      timerEl.textContent = mins > 0
        ? `${mins}m ${String(secs).padStart(2, '0')}s`
        : `${elapsed}s`;
    }
    // Contextual hint after 45 seconds — model is probably still loading
    const subEl = $('#import-loader-sub');
    if (subEl && elapsed === 45) {
      subEl.textContent = 'Model wordt geladen, even geduld…';
    }
    if (subEl && elapsed === 120) {
      subEl.textContent = 'Bijna klaar, nog even geduld…';
    }
  }, 1000);
}

function hideImportLoader() {
  clearInterval(_importTimerInterval);
  _importTimerInterval = null;
  const overlay = $('#import-overlay');
  if (overlay) overlay.style.display = 'none';
}

// ── Collector / staging area ──────────────────────────────────────

function openCollector() {
  $('#collector-panel').style.display = 'block';
  $('#collector-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
  renderCollectorItems();
}

function closeCollector() {
  $('#collector-panel').style.display = 'none';
}

function addCollectorPhotos(files) {
  for (const file of files) {
    const preview = URL.createObjectURL(file);
    state.collector.items.push({ type: 'photo', data: file, preview });
  }
  renderCollectorItems();
}

function addCollectorText(text) {
  if (!text.trim()) return;
  state.collector.items.push({
    type: 'text',
    data: text.trim(),
    preview: text.trim().slice(0, 80) + (text.trim().length > 80 ? '…' : ''),
  });
  renderCollectorItems();
}

function addCollectorUrl(url) {
  if (!url.trim()) return;
  // Only allow one URL at a time — replace existing
  const existing = state.collector.items.findIndex(i => i.type === 'url');
  if (existing >= 0) {
    state.collector.items[existing].data = url.trim();
    state.collector.items[existing].preview = url.trim();
  } else {
    state.collector.items.push({ type: 'url', data: url.trim(), preview: url.trim() });
  }
  renderCollectorItems();
}

function removeCollectorItem(index) {
  const item = state.collector.items[index];
  if (item && item.type === 'photo' && item.preview) {
    URL.revokeObjectURL(item.preview);
  }
  state.collector.items.splice(index, 1);
  renderCollectorItems();
}

function clearCollector() {
  state.collector.items.forEach(item => {
    if (item.type === 'photo' && item.preview) URL.revokeObjectURL(item.preview);
  });
  state.collector.items = [];
  renderCollectorItems();
}

function renderCollectorItems() {
  const container = $('#collector-items');
  const items = state.collector.items;
  const hasItems = items.length > 0;
  const photoCount = items.filter(i => i.type === 'photo').length;
  const hasNonPhoto = items.some(i => i.type !== 'photo');

  // Show/hide empty message, footer, batch option
  $('#collector-empty-msg').style.display = hasItems ? 'none' : '';
  $('#collector-footer').style.display = hasItems ? 'flex' : 'none';
  $('#collector-options').style.display = (photoCount >= 2 && !hasNonPhoto) ? '' : 'none';
  // Uncheck batch when hidden
  if (photoCount < 2 || hasNonPhoto) {
    const cb = $('#collector-batch-mode');
    if (cb) cb.checked = false;
  }

  // Build items HTML
  const html = items.map((item, i) => {
    let icon, content;
    if (item.type === 'photo') {
      icon = `<img src="${item.preview}" class="collector-thumb" alt="Foto">`;
      content = `<span class="collector-item-name">${esc(item.data.name)}</span>`;
    } else if (item.type === 'text') {
      icon = '<span class="collector-item-icon">📝</span>';
      content = `<span class="collector-item-preview">${esc(item.preview)}</span>`;
    } else {
      icon = '<span class="collector-item-icon">🔗</span>';
      content = `<span class="collector-item-preview">${esc(item.preview)}</span>`;
    }
    return `
      <div class="collector-item">
        ${icon}
        ${content}
        <button class="btn-icon collector-remove" data-idx="${i}" title="Verwijderen">✕</button>
      </div>`;
  }).join('');

  // Replace only item nodes (keep the empty msg)
  container.querySelectorAll('.collector-item').forEach(el => el.remove());
  container.insertAdjacentHTML('beforeend', html);

  // Bind remove buttons via delegation
  container.querySelectorAll('.collector-remove').forEach(btn => {
    btn.onclick = () => removeCollectorItem(parseInt(btn.dataset.idx));
  });
}

async function processCollector() {
  const items = state.collector.items;
  if (!items.length) { toast('Voeg eerst iets toe', 'error'); return; }

  // Check for batch mode
  const batchCb = $('#collector-batch-mode');
  const batchMode = batchCb && batchCb.checked
    && items.every(i => i.type === 'photo')
    && items.filter(i => i.type === 'photo').length >= 2;

  if (batchMode) {
    const files = items.filter(i => i.type === 'photo').map(i => i.data);
    clearCollector();
    closeCollector();
    startBatchImport(files);
    return;
  }

  // Unified processing
  const formData = new FormData();

  // Append photos
  const photos = items.filter(i => i.type === 'photo');
  photos.forEach(p => formData.append('photos', p.data));

  // Append text snippets as JSON array
  const texts = items.filter(i => i.type === 'text').map(i => i.data);
  formData.append('texts', JSON.stringify(texts));

  // Append URL (at most one)
  const urlItem = items.find(i => i.type === 'url');
  if (urlItem) formData.append('url', urlItem.data);

  showImportLoader('Recept verwerken…', 'Alle bronnen worden gecombineerd…');
  try {
    const res = await fetch(`${API}/recipes/import-unified`, {
      method: 'POST',
      body: formData,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

    const n = fillRecipeForm(data);

    // Handle dish photo if extracted from cookbook page
    if (data._dish_photo) {
      const byteStr = atob(data._dish_photo);
      const bytes = new Uint8Array(byteStr.length);
      for (let i = 0; i < byteStr.length; i++) bytes[i] = byteStr.charCodeAt(i);
      const ext = data._dish_photo_ext || '.jpg';
      const mime = ext === '.png' ? 'image/png' : 'image/jpeg';
      state.pendingPhoto = new File([bytes], `dish${ext}`, { type: mime });
      const preview = $('#recipe-photo-preview');
      const img = $('#recipe-photo-img');
      img.src = URL.createObjectURL(state.pendingPhoto);
      preview.style.display = 'flex';
    } else if (photos.length === 1) {
      // Use original photo as recipe photo
      state.pendingPhoto = photos[0].data;
    }

    toast(`✅ ${n} ingrediënten ingelezen — controleer en sla op`, 'success');
    clearCollector();
    closeCollector();
    $('#recipe-form-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) {
    toast('Importeren mislukt: ' + e.message, 'error');
  } finally {
    hideImportLoader();
  }
}

// ── Batch import ──────────────────────────────────────────────────

let batchCancelled = false;

async function startBatchImport(files) {
  batchCancelled = false;
  const total = files.length;
  if (!total) return;

  const panel = $('#batch-panel');
  panel.style.display = 'block';
  panel.scrollIntoView({ behavior: 'smooth', block: 'start' });

  $('#batch-status').textContent = `Verwerkt: 0 / ${total}`;
  $('#batch-progress-bar').style.width = '0%';
  $('#batch-file-list').innerHTML = '';
  $('#btn-stop-batch').style.display = 'inline-flex';

  let saved = 0, failed = 0;

  for (let i = 0; i < total; i++) {
    if (batchCancelled) break;

    const file = files[i];
    const row = document.createElement('div');
    row.className = 'batch-file-item';
    row.innerHTML = `<span class="batch-icon">⏳</span><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(file.name)}</span>`;
    $('#batch-file-list').appendChild(row);
    row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${API}/recipes/import-photo`, { method: 'POST', body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

      // Auto-save
      const ingredients = (data.ingredienten || []).map(ing => ({
        name:     ing.naam        || '',
        amount:   ing.hoeveelheid ?? null,
        unit:     ing.eenheid     || null,
        category: 'Overig',
      })).filter(i => i.name);

      const batchTagList = Array.isArray(data.tags) ? data.tags : (data.tags ? String(data.tags).split(',').map(t => t.trim()) : []);
      const created = await post('/recipes', {
        name:             data.naam || file.name.replace(/\.[^.]+$/, ''),
        source:           data.bron || null,
        default_servings: parseInt(data.porties) || 4,
        tags:             batchTagList.length ? batchTagList.join(', ') : null,
        prep_time:        data.bereidingstijd || null,
        steps:            data.stappen || null,
        notes:            null,
        ingredients,
      });

      // Also save the photo
      if (created?.id) {
        await uploadRecipePhoto(created.id, file);
      }

      row.querySelector('.batch-icon').textContent = '✅';
      saved++;
    } catch (e) {
      row.querySelector('.batch-icon').textContent = '❌';
      failed++;
    }

    const pct = Math.round((i + 1) / total * 100);
    $('#batch-progress-bar').style.width = `${pct}%`;
    $('#batch-status').textContent = `Verwerkt: ${i + 1} / ${total}`;
  }

  $('#btn-stop-batch').style.display = 'none';
  $('#collector-photo-input').value = '';

  const summary = batchCancelled
    ? `Gestopt. ${saved} opgeslagen, ${failed} mislukt.`
    : `Klaar! ${saved} opgeslagen, ${failed} mislukt.`;
  toast(summary, failed > 0 ? 'error' : 'success');
  await loadRecipes();
}

// (Old importText / importUrl removed — replaced by collector)

// ════════════════════════════════════════════════════════════════
// TAB 2 – NIEUWE LIJST
// ════════════════════════════════════════════════════════════════

function loadNewListTab() {
  populateRecipeSelect();
  buildCategorySelect($('#extra-category'), 'Overig');
  if (!state.newList.id) renderListItemsPreview();
}

function populateRecipeSelect() {
  const sel = $('#recipe-select');
  if (!sel) return;
  sel.innerHTML = state.recipes.length
    ? state.recipes.map(r => `<option value="${r.id}">${esc(r.name)}</option>`).join('')
    : '<option value="">– geen recepten –</option>';
}

function resetNewList() {
  state.newList = { id: null, selectedRecipes: [], items: [], addedStaples: false };
  $('#lijst-name').value = '';
  $('#lijst-datefrom').value = '';
  $('#lijst-dateto').value = '';
  $('#lijst-notes').value = '';
  $('#editing-list-id').value = '';
  $('#nieuw-lijst-title').textContent = 'Nieuwe lijst';
  $('#btn-cancel-lijst').style.display = 'none';
  renderSelectedRecipes();
  renderListItemsPreview();
}

function addRecipeToList() {
  const sel = $('#recipe-select');
  if (!sel || !sel.value) return;
  const recipeId = parseInt(sel.value);
  const servings = parseInt($('#recipe-portions').value) || 4;
  const recipe = state.recipes.find(r => r.id === recipeId);
  if (!recipe) return;

  const existing = state.newList.selectedRecipes.find(sr => sr.recipe.id === recipeId);
  if (existing) {
    existing.servings = servings;
  } else {
    state.newList.selectedRecipes.push({ recipe, servings });
  }
  renderSelectedRecipes();
}

function renderSelectedRecipes() {
  const container = $('#selected-recipes-list');
  if (!state.newList.selectedRecipes.length) {
    container.innerHTML = '<p style="font-size:.85rem;color:var(--text-muted)">Geen recepten geselecteerd.</p>';
    return;
  }
  container.innerHTML = state.newList.selectedRecipes.map((sr, i) => `
    <div class="selected-recipe-chip">
      <span>${esc(sr.recipe.name)}</span>
      <input type="number" value="${sr.servings}" min="1" max="30"
        style="width:60px;padding:.2rem .4rem;font-size:.85rem"
        onchange="updateRecipeServings(${i}, this.value)">
      <span style="font-size:.8rem;color:var(--text-muted)">porties</span>
      <button class="btn-icon" onclick="removeSelectedRecipe(${i})" title="Verwijder">✕</button>
    </div>
  `).join('');
}

function updateRecipeServings(idx, val) {
  state.newList.selectedRecipes[idx].servings = parseInt(val) || 4;
}

function removeSelectedRecipe(idx) {
  state.newList.selectedRecipes.splice(idx, 1);
  renderSelectedRecipes();
}

async function generateListItems() {
  const items = [];

  for (const sr of state.newList.selectedRecipes) {
    try {
      const recipe = await get(`/recipes/${sr.recipe.id}`);
      const scale = sr.servings / (recipe.default_servings || 1);
      for (const ing of recipe.ingredients) {
        items.push({
          name:        ing.name,
          amount:      ing.amount != null ? +(ing.amount * scale).toFixed(2) : null,
          unit:        ing.unit,
          category:    ing.category,
          supermarket: 'beide',
          source:      recipe.name,
          _tmpId:      Math.random(),
        });
      }
    } catch (e) {
      toast('Fout bij laden recept: ' + e.message, 'error');
    }
  }

  if (state.newList.addedStaples) {
    for (const s of state.staples) {
      items.push({
        name:        s.name,
        amount:      s.amount,
        unit:        s.unit,
        category:    s.category,
        supermarket: s.supermarket,
        source:      'vast',
        _tmpId:      Math.random(),
      });
    }
  }

  state.newList.items = items;
  renderListItemsPreview();
}

async function addStaplesToList() {
  if (!state.staples.length) {
    state.staples = await get('/staples');
  }
  state.newList.addedStaples = true;
  await generateListItems();
  toast('Vaste artikelen toegevoegd', 'success');
}

function renderListItemsPreview() {
  const container = $('#lijst-items-preview');
  if (!state.newList.items.length) {
    container.innerHTML = '<p style="font-size:.85rem;color:var(--text-muted);padding:.5rem 0">Voeg recepten toe en klik "Ververs items".</p>';
    return;
  }

  const grouped = {};
  for (const cat of CATEGORIES) grouped[cat] = [];
  for (const item of state.newList.items) {
    const cat = CATEGORIES.includes(item.category) ? item.category : 'Overig';
    grouped[cat].push(item);
  }

  let html = '';
  for (const cat of CATEGORIES) {
    if (!grouped[cat].length) continue;
    html += `
      <div class="cat-section">
        <div class="cat-header">${esc(cat)}</div>
        <div class="cat-items">
          ${grouped[cat].map(item => previewItemRow(item)).join('')}
        </div>
      </div>`;
  }
  container.innerHTML = html;
}

function previewItemRow(item) {
  const tmpId = item._tmpId || item.id || Math.random();
  const smOptions = SUPERMARKETS.map(sm =>
    `<option value="${sm.value}" ${sm.value === item.supermarket ? 'selected' : ''}>${sm.label}</option>`
  ).join('');
  const srcBadge = item.source && item.source !== 'vast'
    ? `<span class="badge badge-vast item-source-badge" data-source="${esc(item.source)}" title="${esc(item.source)}" style="font-size:.65rem;max-width:70px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(item.source)}</span>`
    : item.source === 'vast' ? `<span class="badge badge-vast">⭐</span>` : '';

  return `
    <div class="list-item" data-tmp-id="${tmpId}">
      <input type="text" value="${esc(item.name)}" style="font-size:.85rem"
        onchange="updatePreviewItem('${tmpId}', 'name', this.value)">
      <input type="number" value="${item.amount ?? ''}" step="any" placeholder="–" style="font-size:.85rem"
        onchange="updatePreviewItem('${tmpId}', 'amount', this.value)">
      <input type="text" value="${esc(item.unit || '')}" placeholder="–" style="font-size:.85rem"
        onchange="updatePreviewItem('${tmpId}', 'unit', this.value)">
      <select style="font-size:.8rem" onchange="updatePreviewItem('${tmpId}', 'supermarket', this.value)">
        ${smOptions}
      </select>
      <div style="display:flex;align-items:center;gap:.25rem">
        ${srcBadge}
        <button class="btn-icon" onclick="removePreviewItem('${tmpId}')" title="Verwijder">✕</button>
      </div>
    </div>`;
}

function updatePreviewItem(tmpId, field, value) {
  const item = state.newList.items.find(i => String(i._tmpId || i.id) === String(tmpId));
  if (!item) return;
  if (field === 'amount') item.amount = value ? parseFloat(value) : null;
  else item[field] = value || null;
}

function removePreviewItem(tmpId) {
  state.newList.items = state.newList.items.filter(i => String(i._tmpId || i.id) !== String(tmpId));
  renderListItemsPreview();
}

function addExtraItem() {
  const name = $('#extra-name').value.trim();
  if (!name) { toast('Voer een naam in', 'error'); return; }
  state.newList.items.push({
    name,
    amount:      $('#extra-amount').value ? parseFloat($('#extra-amount').value) : null,
    unit:        $('#extra-unit').value.trim() || null,
    category:    $('#extra-category').value,
    supermarket: $('#extra-supermarket').value,
    source:      null,
    _tmpId:      Math.random(),
  });
  $('#extra-name').value = '';
  $('#extra-amount').value = '';
  $('#extra-unit').value = '';
  renderListItemsPreview();
}

async function saveList() {
  const name = $('#lijst-name').value.trim();
  if (!name) { toast('Voer een lijstnaam in', 'error'); return; }

  const payload = {
    name,
    date_from: $('#lijst-datefrom').value || null,
    date_to:   $('#lijst-dateto').value   || null,
    notes:     $('#lijst-notes').value.trim() || null,
  };

  try {
    let listId = state.newList.id;

    if (listId) {
      await put(`/lists/${listId}`, payload);
      const existing = await get(`/lists/${listId}`);
      for (const item of existing.items) {
        await del(`/lists/${listId}/items/${item.id}`);
      }
    } else {
      const created = await post('/lists', payload);
      listId = created.id;
    }

    if (state.newList.items.length) {
      const items = state.newList.items.map(item => ({
        name:        item.name,
        amount:      item.amount,
        unit:        item.unit || null,
        category:    item.category || 'Overig',
        supermarket: item.supermarket || 'beide',
        source:      item.source || null,
      }));
      await post(`/lists/${listId}/items/bulk`, { items });
    }

    toast('Lijst opgeslagen!', 'success');
    resetNewList();
    switchTab('lijsten');
  } catch (e) {
    toast('Fout bij opslaan: ' + e.message, 'error');
  }
}

// ════════════════════════════════════════════════════════════════
// TAB 3 – LIJSTEN
// ════════════════════════════════════════════════════════════════

async function loadLists() {
  state.lists = await get('/lists');
  renderLists();
  loadConfig();
}

function renderLists() {
  const container = $('#lists-overview');
  if (!state.lists.length) {
    container.innerHTML = `<div class="empty-state"><div class="icon">📋</div><p>Nog geen lijsten aangemaakt.</p></div>`;
    return;
  }

  container.innerHTML = state.lists.map(lst => {
    const dateRange = [lst.date_from, lst.date_to].filter(Boolean).join(' – ');
    return `
      <div class="card">
        <div class="list-card">
          <div>
            <div class="card-title">${esc(lst.name)}</div>
            <div class="card-meta">
              ${dateRange ? `${esc(dateRange)} · ` : ''}${lst.item_count} artikelen
              ${lst.published_url ? `· <a href="${esc(lst.published_url)}" target="_blank" style="color:var(--green)">🔗 Gepubliceerd</a>` : ''}
            </div>
          </div>
          <div class="list-card-actions">
            <button class="btn btn-secondary btn-sm" onclick="openList(${lst.id})">✏️ Bewerk</button>
            <button class="btn btn-outline btn-sm" onclick="publishList(${lst.id})">📤 Publiceer</button>
            <button class="btn btn-danger btn-sm" onclick="deleteList(${lst.id})">🗑</button>
          </div>
        </div>
      </div>`;
  }).join('');
}

async function openList(id) {
  try {
    const lst = await get(`/lists/${id}`);
    state.newList.id = id;
    state.newList.selectedRecipes = [];
    state.newList.addedStaples = false;
    state.newList.items = lst.items.map(item => ({ ...item, _tmpId: item.id }));

    $('#lijst-name').value = lst.name || '';
    $('#lijst-datefrom').value = lst.date_from || '';
    $('#lijst-dateto').value = lst.date_to || '';
    $('#lijst-notes').value = lst.notes || '';
    $('#editing-list-id').value = id;
    $('#nieuw-lijst-title').textContent = `Bewerken: ${lst.name}`;
    $('#btn-cancel-lijst').style.display = 'inline-flex';

    buildCategorySelect($('#extra-category'), 'Overig');
    renderSelectedRecipes();
    renderListItemsPreview();
    switchTab('nieuwe-lijst');
  } catch (e) {
    toast('Fout bij laden: ' + e.message, 'error');
  }
}

async function deleteList(id) {
  if (!confirm('Lijst verwijderen?')) return;
  try {
    await del(`/lists/${id}`);
    toast('Lijst verwijderd', 'success');
    await loadLists();
  } catch (e) {
    toast('Fout: ' + e.message, 'error');
  }
}

async function publishList(id) {
  try {
    toast('Publiceren…', 'info');
    const result = await post(`/lists/${id}/publish`);
    toast('Gepubliceerd!', 'success');
    const url = result.url;
    if (url) {
      setTimeout(() => {
        if (confirm(`Gepubliceerd naar:\n${url}\n\nOpenen in browser?`)) {
          window.open(url, '_blank');
        }
      }, 100);
    }
    await loadLists();
  } catch (e) {
    toast('Publiceren mislukt: ' + e.message, 'error');
  }
}

// ── GitHub config ─────────────────────────────────────────────────

async function loadConfig() {
  try {
    const cfg = await get('/config');
    $('#cfg-token').value    = cfg.github_token || '';
    $('#cfg-owner').value    = cfg.repo_owner   || '';
    $('#cfg-repo').value     = cfg.repo_name    || '';
    $('#cfg-filepath').value = cfg.file_path    || 'boodschappen.html';
  } catch (_) {}
}

async function saveConfig() {
  try {
    await post('/config', {
      github_token: $('#cfg-token').value.trim(),
      repo_owner:   $('#cfg-owner').value.trim(),
      repo_name:    $('#cfg-repo').value.trim(),
      file_path:    $('#cfg-filepath').value.trim() || 'boodschappen.html',
    });
    toast('Configuratie opgeslagen', 'success');
  } catch (e) {
    toast('Fout: ' + e.message, 'error');
  }
}

// ════════════════════════════════════════════════════════════════
// TAB 4 – VASTE ARTIKELEN
// ════════════════════════════════════════════════════════════════

async function loadStaples() {
  state.staples = await get('/staples');
  renderStapleList();
}

function renderStapleList() {
  const container = $('#staple-list');
  if (!state.staples.length) {
    container.innerHTML = `<div class="empty-state"><div class="icon">⭐</div><p>Nog geen vaste artikelen.</p></div>`;
    return;
  }

  const sorted = sortByCategory(state.staples);
  const grouped = {};
  for (const cat of CATEGORIES) grouped[cat] = [];
  for (const s of sorted) {
    const cat = CATEGORIES.includes(s.category) ? s.category : 'Overig';
    grouped[cat].push(s);
  }

  let html = '';
  for (const cat of CATEGORIES) {
    if (!grouped[cat].length) continue;
    html += `
      <div class="cat-section">
        <div class="cat-header">${esc(cat)}</div>
        <div class="cat-items">
          ${grouped[cat].map(s => stapleRow(s)).join('')}
        </div>
      </div>`;
  }
  container.innerHTML = html;
}

function stapleRow(s) {
  return `
    <div class="staple-row" id="staple-row-${s.id}">
      <span style="font-size:.9rem">${esc(s.name)}</span>
      <span style="font-size:.85rem;color:var(--text-muted)">${fmtAmount(s.amount, s.unit) || '–'}</span>
      <span>${supermarketBadge(s.supermarket)}</span>
      <span style="font-size:.8rem;color:var(--text-muted)">${esc(s.notes || '')}</span>
      <button class="btn btn-secondary btn-sm" onclick="editStaple(${s.id})">✏️</button>
      <button class="btn btn-danger btn-sm" onclick="deleteStaple(${s.id})">🗑</button>
    </div>`;
}

function showStapleForm(staple = null) {
  const card = $('#staple-form-card');
  card.style.display = 'block';
  card.scrollIntoView({ behavior: 'smooth', block: 'start' });
  $('#staple-form-title').textContent = staple ? 'Artikel bewerken' : 'Nieuw artikel';
  $('#staple-id').value         = staple?.id || '';
  $('#staple-name').value       = staple?.name || '';
  $('#staple-amount').value     = staple?.amount ?? '';
  $('#staple-unit').value       = staple?.unit || '';
  buildCategorySelect($('#staple-category'), staple?.category || 'Overig');
  $('#staple-supermarket').value = staple?.supermarket || 'beide';
  $('#staple-notes').value      = staple?.notes || '';
}

async function editStaple(id) {
  const staple = state.staples.find(s => s.id === id);
  if (staple) showStapleForm(staple);
}

async function deleteStaple(id) {
  if (!confirm('Artikel verwijderen?')) return;
  try {
    await del(`/staples/${id}`);
    toast('Artikel verwijderd', 'success');
    await loadStaples();
  } catch (e) {
    toast('Fout: ' + e.message, 'error');
  }
}

async function saveStaple(e) {
  e.preventDefault();
  const id = $('#staple-id').value;
  const payload = {
    name:        $('#staple-name').value.trim(),
    amount:      $('#staple-amount').value ? parseFloat($('#staple-amount').value) : null,
    unit:        $('#staple-unit').value.trim() || null,
    category:    $('#staple-category').value,
    supermarket: $('#staple-supermarket').value,
    notes:       $('#staple-notes').value.trim() || null,
  };
  try {
    if (id) {
      await put(`/staples/${id}`, payload);
      toast('Artikel bijgewerkt', 'success');
    } else {
      await post('/staples', payload);
      toast('Artikel aangemaakt', 'success');
    }
    hideStapleForm();
    await loadStaples();
  } catch (e) {
    toast('Fout bij opslaan: ' + e.message, 'error');
  }
}

function hideStapleForm() {
  $('#staple-form-card').style.display = 'none';
  $('#staple-form').reset();
  $('#staple-id').value = '';
}

// ════════════════════════════════════════════════════════════════
// TAB 5 – FAMILIE
// ════════════════════════════════════════════════════════════════

async function loadFamilie() {
  state.familie = await get('/family');
  renderFamilieList();
}

function renderFamilieList() {
  const container = $('#familie-list');
  if (!state.familie.length) {
    container.innerHTML = `<div class="empty-state"><div class="icon">👨‍👩‍👧</div><p>Nog geen gezinsleden. Voeg er een toe!</p></div>`;
    return;
  }
  container.innerHTML = state.familie.map(m => {
    const chips = [];
    if (m.dietary_restrictions) {
      m.dietary_restrictions.split(',').forEach(d =>
        chips.push(`<span class="chip">${esc(d.trim())}</span>`)
      );
    }
    if (m.allergies) {
      m.allergies.split(',').forEach(a =>
        chips.push(`<span class="chip chip-danger">⚠ ${esc(a.trim())}</span>`)
      );
    }
    if (m.likes) {
      m.likes.split(',').forEach(l =>
        chips.push(`<span class="chip">❤ ${esc(l.trim())}</span>`)
      );
    }
    return `
      <div class="card">
        <div class="familie-card">
          <div class="familie-avatar">👤</div>
          <div class="familie-info">
            <div class="card-header" style="align-items:flex-start">
              <div style="min-width:0">
                <div class="card-title">${esc(m.name)}</div>
                ${m.age != null ? `<div class="card-meta">${m.age} jaar</div>` : ''}
                <div style="margin-top:.35rem;display:flex;flex-wrap:wrap">${chips.join('')}</div>
                ${m.dislikes ? `<div class="card-meta" style="margin-top:.3rem">Niet van: ${esc(m.dislikes)}</div>` : ''}
                ${m.notes   ? `<div class="card-meta" style="margin-top:.2rem">${esc(m.notes)}</div>` : ''}
              </div>
              <div style="display:flex;gap:.35rem;flex-shrink:0">
                <button class="btn btn-secondary btn-sm" onclick="editFamilieLid(${m.id})">✏️</button>
                <button class="btn btn-danger btn-sm" onclick="deleteFamilieLid(${m.id})">🗑</button>
              </div>
            </div>
          </div>
        </div>
      </div>`;
  }).join('');
}

function showFamilieForm(member = null) {
  const card = $('#familie-form-card');
  card.style.display = 'block';
  card.scrollIntoView({ behavior: 'smooth', block: 'start' });

  $('#familie-form-title').textContent = member ? 'Gezinslid bewerken' : 'Nieuw gezinslid';
  $('#familie-id').value        = member?.id || '';
  $('#familie-name').value      = member?.name || '';
  $('#familie-birthdate').value = member?.birthdate || '';
  $('#familie-dietary').value   = member?.dietary_restrictions || '';
  $('#familie-allergies').value = member?.allergies || '';
  $('#familie-likes').value     = member?.likes || '';
  $('#familie-dislikes').value  = member?.dislikes || '';
  $('#familie-notes').value     = member?.notes || '';
}

function hideFamilieForm() {
  $('#familie-form-card').style.display = 'none';
  $('#familie-form').reset();
  $('#familie-id').value = '';
}

async function editFamilieLid(id) {
  const member = state.familie.find(m => m.id === id);
  if (member) showFamilieForm(member);
}

async function deleteFamilieLid(id) {
  if (!confirm('Gezinslid verwijderen?')) return;
  try {
    await del(`/family/${id}`);
    toast('Gezinslid verwijderd', 'success');
    await loadFamilie();
  } catch (e) {
    toast('Fout: ' + e.message, 'error');
  }
}

async function saveFamilieLid(e) {
  e.preventDefault();
  const id = $('#familie-id').value;
  const payload = {
    name:                 $('#familie-name').value.trim(),
    birthdate:            $('#familie-birthdate').value || null,
    dietary_restrictions: $('#familie-dietary').value.trim() || null,
    allergies:            $('#familie-allergies').value.trim() || null,
    likes:                $('#familie-likes').value.trim() || null,
    dislikes:             $('#familie-dislikes').value.trim() || null,
    notes:                $('#familie-notes').value.trim() || null,
  };
  try {
    if (id) {
      await put(`/family/${id}`, payload);
      toast('Gezinslid bijgewerkt', 'success');
    } else {
      await post('/family', payload);
      toast('Gezinslid aangemaakt', 'success');
    }
    hideFamilieForm();
    await loadFamilie();
  } catch (e) {
    toast('Fout bij opslaan: ' + e.message, 'error');
  }
}

// ════════════════════════════════════════════════════════════════
// CHAT
// ════════════════════════════════════════════════════════════════

function toggleChat() {
  state.chat.open = !state.chat.open;
  $('#chat-panel').classList.toggle('open', state.chat.open);
  $('#chat-fab').textContent = state.chat.open ? '✕' : '💬';
  if (state.chat.open) {
    updateChatContext();
    setTimeout(() => $('#chat-input').focus(), 100);
    $('#chat-messages').scrollTop = $('#chat-messages').scrollHeight;
  }
}

function buildChatContext() {
  const parts = [];

  if (state.familie.length) {
    const lines = state.familie.map(m => {
      const details = [];
      if (m.dietary_restrictions) details.push(`dieet: ${m.dietary_restrictions}`);
      if (m.allergies)            details.push(`allergieën: ${m.allergies}`);
      if (m.likes)                details.push(`houdt van: ${m.likes}`);
      if (m.dislikes)             details.push(`niet van: ${m.dislikes}`);
      return `- ${m.name}${m.age != null ? ` (${m.age} jaar)` : ''}: ${details.join(', ') || 'geen bijzonderheden'}`;
    });
    parts.push(`Gezinsleden:\n${lines.join('\n')}`);
  }

  const recipeCard = $('#recipe-form-card');
  const recipeName = $('#recipe-name').value.trim();
  if (recipeName && recipeCard && recipeCard.style.display !== 'none') {
    const ings = $$('.ing-row').map(row => {
      const nm = $('.ing-name', row).value.trim();
      const am = $('.ing-amount', row).value;
      const un = $('.ing-unit', row).value.trim();
      return [am, un, nm].filter(Boolean).join(' ');
    }).filter(Boolean);
    if (ings.length) {
      parts.push(`Huidig recept: ${recipeName}\nIngrediënten: ${ings.join(', ')}`);
    } else {
      parts.push(`Huidig recept: ${recipeName}`);
    }
  }

  return parts.length ? parts.join('\n\n') : null;
}

function updateChatContext() {
  const ctx = buildChatContext();
  const bar = $('#chat-context-bar');
  if (ctx) {
    bar.classList.add('active');
    const names = state.familie.map(m => m.name).join(', ');
    const recName = $('#recipe-name').value.trim();
    const parts = [names, recName].filter(Boolean);
    bar.textContent = `Context: ${parts.join(' · ') || 'actief'}`;
  } else {
    bar.classList.remove('active');
  }
}

function addChatBubble(role, content) {
  const messages = $('#chat-messages');
  const bubble = document.createElement('div');
  bubble.className = `chat-bubble ${role}`;
  // Assistant messages render markdown; user messages are plain text
  if (role === 'assistant') {
    bubble.innerHTML = renderMarkdown(content);
  } else {
    bubble.textContent = content;
  }
  messages.appendChild(bubble);
  messages.scrollTop = messages.scrollHeight;
}

function showThinking() {
  const messages = $('#chat-messages');
  const el = document.createElement('div');
  el.id = 'chat-thinking';
  el.className = 'chat-thinking';
  el.innerHTML = '<span></span><span></span><span></span>';
  messages.appendChild(el);
  messages.scrollTop = messages.scrollHeight;
}

function hideThinking() {
  const el = $('#chat-thinking');
  if (el) el.remove();
}

async function sendChatMessage() {
  const input = $('#chat-input');
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  input.disabled = true;
  $('#btn-chat-send').disabled = true;

  state.chat.messages.push({ role: 'user', content: text });
  addChatBubble('user', text);
  showThinking();

  try {
    const context = buildChatContext();
    const result = await post('/chat', {
      messages: state.chat.messages,
      context,
    });
    hideThinking();
    const reply = result.response || '';
    state.chat.messages.push({ role: 'assistant', content: reply });
    addChatBubble('assistant', reply);
  } catch (e) {
    hideThinking();
    const errMsg = e.message.includes('503')
      ? 'Ollama is niet bereikbaar. Start Ollama eerst.'
      : e.message.includes('504')
      ? 'Model reageert niet (timeout). Probeer opnieuw.'
      : `Fout: ${e.message}`;
    addChatBubble('assistant', `❌ ${errMsg}`);
  } finally {
    input.disabled = false;
    $('#btn-chat-send').disabled = false;
    input.focus();
  }
}

// ════════════════════════════════════════════════════════════════
// EVENT LISTENERS
// ════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', async () => {
  initTabs();

  // ── Notification log ─────────────────────────────────────────

  $('#btn-notif').addEventListener('click', e => {
    e.stopPropagation();
    toggleNotifPanel();
  });
  $('#btn-close-notif').addEventListener('click', closeNotifPanel);
  $('#btn-clear-notif').addEventListener('click', clearNotifLog);
  // Close notification panel when clicking elsewhere
  document.addEventListener('click', e => {
    if (!e.target.closest('#notif-panel') && !e.target.closest('#btn-notif')) {
      closeNotifPanel();
    }
  });

  // ── Tab 1 – Recepten ──────────────────────────────────────────

  // Filter bar
  $('#filter-search').addEventListener('input', e => {
    filterState.search = e.target.value.trim();
    applyRecipeFilter();
  });
  $('#filter-prep-time').addEventListener('change', e => {
    filterState.maxPrepTime = parseInt(e.target.value) || 0;
    applyRecipeFilter();
  });
  $('#btn-reset-filter').addEventListener('click', resetFilter);

  $('#btn-nieuw-recept').addEventListener('click', () => showRecipeForm());
  $('#btn-cancel-recipe').addEventListener('click', hideRecipeForm);
  $('#recipe-form').addEventListener('submit', saveRecipe);
  $('#btn-add-ing-row').addEventListener('click', () => addIngRow());

  // Recipe photo in form
  $('#recipe-photo-file').addEventListener('change', e => {
    const file = e.target.files[0];
    if (file) {
      // Show a preview of the newly selected file
      const url = URL.createObjectURL(file);
      $('#recipe-photo-img').src = url;
      $('#recipe-photo-preview').style.display = 'flex';
    }
  });
  $('#btn-remove-photo').addEventListener('click', () => {
    const id = $('#recipe-id').value;
    if (id) {
      removeRecipePhoto(parseInt(id));
    } else {
      // Just clear pending
      state.pendingPhoto = null;
      $('#recipe-photo-preview').style.display = 'none';
      $('#recipe-photo-file').value = '';
    }
  });

  // ── Collector (unified import) ──────────────────────────────────
  $('#btn-open-collector').addEventListener('click', openCollector);
  $('#btn-close-collector').addEventListener('click', closeCollector);

  // Add photos
  $('#btn-collector-add-photo').addEventListener('click', () => {
    $('#collector-photo-input').click();
  });
  $('#collector-photo-input').addEventListener('change', e => {
    addCollectorPhotos(Array.from(e.target.files));
    e.target.value = '';
  });

  // Add text
  $('#btn-collector-add-text').addEventListener('click', () => {
    const el = $('#collector-text-input');
    el.style.display = el.style.display === 'none' ? 'block' : 'none';
    if (el.style.display === 'block') $('#collector-text-area').focus();
  });
  $('#btn-collector-confirm-text').addEventListener('click', () => {
    addCollectorText($('#collector-text-area').value);
    $('#collector-text-area').value = '';
    $('#collector-text-input').style.display = 'none';
  });
  $('#collector-text-area').addEventListener('keydown', e => {
    if (e.key === 'Enter' && e.ctrlKey) {
      addCollectorText($('#collector-text-area').value);
      $('#collector-text-area').value = '';
      $('#collector-text-input').style.display = 'none';
    }
  });

  // Add URL
  $('#btn-collector-add-url').addEventListener('click', () => {
    const el = $('#collector-url-input');
    el.style.display = el.style.display === 'none' ? 'block' : 'none';
    if (el.style.display === 'block') $('#collector-url-field').focus();
  });
  $('#btn-collector-confirm-url').addEventListener('click', () => {
    addCollectorUrl($('#collector-url-field').value);
    $('#collector-url-field').value = '';
    $('#collector-url-input').style.display = 'none';
  });
  $('#collector-url-field').addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      addCollectorUrl($('#collector-url-field').value);
      $('#collector-url-field').value = '';
      $('#collector-url-input').style.display = 'none';
    }
  });

  // Process & clear
  $('#btn-collector-process').addEventListener('click', processCollector);
  $('#btn-collector-clear').addEventListener('click', clearCollector);

  // Batch panel (still used for batch mode)
  $('#btn-stop-batch').addEventListener('click', () => {
    batchCancelled = true;
    toast('Batch gestopt', 'info');
  });
  $('#btn-close-batch-panel').addEventListener('click', () => {
    $('#batch-panel').style.display = 'none';
  });

  // ── Tab 2 – Nieuwe lijst ─────────────────────────────────────

  $('#btn-add-recipe-to-list').addEventListener('click', addRecipeToList);
  $('#btn-voeg-standaard-toe').addEventListener('click', addStaplesToList);
  $('#btn-genereer-lijst').addEventListener('click', async () => {
    await generateListItems();
    toast('Items bijgewerkt', 'success');
  });
  $('#btn-add-extra').addEventListener('click', addExtraItem);
  $('#btn-save-lijst').addEventListener('click', saveList);
  $('#btn-reset-lijst').addEventListener('click', () => {
    if (confirm('Weet je zeker dat je de lijst wilt leegmaken?')) resetNewList();
  });
  $('#btn-cancel-lijst').addEventListener('click', () => {
    resetNewList();
    switchTab('lijsten');
  });
  $('#extra-name').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); addExtraItem(); }
  });

  // ── Tab 3 – Lijsten ──────────────────────────────────────────

  $('#btn-save-config').addEventListener('click', saveConfig);
  $('#settings-toggle').addEventListener('click', () => {
    $('#settings-body').classList.toggle('open');
    $('#settings-toggle').classList.toggle('open');
  });

  // ── Tab 4 – Vaste artikelen ──────────────────────────────────

  $('#btn-nieuw-staple').addEventListener('click', () => showStapleForm());
  $('#btn-cancel-staple').addEventListener('click', hideStapleForm);
  $('#staple-form').addEventListener('submit', saveStaple);

  // ── Tab 5 – Familie ──────────────────────────────────────────

  $('#btn-nieuw-lid').addEventListener('click', () => showFamilieForm());
  $('#btn-cancel-lid').addEventListener('click', hideFamilieForm);
  $('#familie-form').addEventListener('submit', saveFamilieLid);

  // ── Chat ─────────────────────────────────────────────────────

  $('#chat-fab').addEventListener('click', toggleChat);
  $('#btn-close-chat').addEventListener('click', toggleChat);
  $('#btn-chat-send').addEventListener('click', sendChatMessage);
  $('#chat-input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendChatMessage();
    }
  });

  // ── Initial data load ─────────────────────────────────────────

  await loadRecipes();
  loadNewListTab();
  // Pre-load familie so chat context is available immediately
  try { state.familie = await get('/family'); } catch (_) {}
});

// ── Window exports (for inline onclick handlers) ──────────────────

window.editRecipe           = editRecipe;
window.deleteRecipe         = deleteRecipe;
window.updateRecipeServings = updateRecipeServings;
window.removeSelectedRecipe = removeSelectedRecipe;
window.updatePreviewItem    = updatePreviewItem;
window.removePreviewItem    = removePreviewItem;
window.openList             = openList;
window.deleteList           = deleteList;
window.publishList          = publishList;
window.editStaple           = editStaple;
window.deleteStaple         = deleteStaple;
window.editFamilieLid       = editFamilieLid;
window.deleteFamilieLid     = deleteFamilieLid;
window.removeRecipePhoto    = removeRecipePhoto;
