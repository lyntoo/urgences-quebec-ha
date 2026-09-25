// Urgences Québec — panneau dashboard optionnel (activable via la config
// de l'intégration, toggle "show_dashboard"). Vanilla JS, aucune dépendance
// externe (pas de Mushroom/card-mod), aucune étape de build — pour rester
// portable pour n'importe quel utilisateur qui installe cette intégration,
// pas seulement ceux qui ont les mêmes cartes HACS installées.
//
// Lecture des entités : via config/entity_registry/list + device_registry/list
// (pattern repris de config_map, seule methode fiable trouvee dans ce
// contexte panel_custom — hass.entities/hass.devices ne sont pas garantis
// peuples ici).

const DOMAIN = "urgences_quebec";

const SORTS = [
  { key: "temps_attente", label: "Temps d'attente", unit: "h", icon: "⏱" },
  { key: "occupation", label: "Occupation", unit: "%", icon: "🏥" },
  { key: "patients_24h", label: "Patients 24h+", unit: "", icon: "👤" },
];

// Seuils de couleur par metrique (vert/jaune/rouge)
const THRESHOLDS = {
  temps_attente: { yellow: 3, red: 6 }, // heures
  occupation: { yellow: 90, red: 100 }, // %
  patients_24h: { yellow: 1, red: 5 }, // nb patients
};

function colorFor(metric, value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "#9e9e9e";
  const t = THRESHOLDS[metric];
  if (value >= t.red) return "#d32f2f";
  if (value >= t.yellow) return "#f9a825";
  return "#2e7d32";
}

class UrgencesQuebecPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._loaded = false;
    this._loading = false;
    this._error = null;
    this._installations = []; // [{name, address, values: {temps_attente, occupation, patients_24h}, lastUpdated}]
    this._activeSort = "temps_attente";
    this._sortAsc = true; // defaut : plus petit nombre en premier (ex: moins de patients/temps/occupation = ce que la majorite veut voir en premier)
    this.attachShadow({ mode: "open" });

    // Delegation d'evenements sur shadowRoot (stable, jamais recree) plutot
    // que d'attacher un listener par bouton a chaque _render() - hass est
    // pousse tres frequemment par HA (tout changement d'etat systeme, pas
    // seulement nos entites), donc _render() reconstruit le DOM souvent ;
    // des listeners attaches sur des boutons recrees en plein milieu d'un
    // clic causaient des clics perdus/a repeter (bug rapporte 2026-09-25).
    //
    // pointerdown plutot que click (2026-09-25) : rapporte "double-clic
    // fiable, simple clic pas fiable" - symptome classique d'un premier
    // clic consomme par l'acquisition du focus du panneau plutot que par
    // le bouton lui-meme. click() exige que mousedown ET mouseup landent
    // tous les deux sur le meme element pour se declencher ; pointerdown
    // se declenche des l'appui, sans cette contrainte.
    this.shadowRoot.addEventListener("pointerdown", (ev) => {
      const btn = ev.target.closest(".tab");
      if (btn) this._setSort(btn.dataset.sort);
    });
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loaded && !this._loading) {
      this._loading = true;
      this._load().finally(() => {
        this._loading = false;
        this._loaded = true;
        this._render();
      });
    } else {
      // hass est pousse par HA a chaque changement d'etat DANS TOUTE LA
      // MAISON, pas seulement nos entites - ne redessiner que si une
      // valeur qui nous concerne a vraiment change, sinon un simple clic
      // (ex: allumer une lumiere ailleurs) reconstruit inutilement tout
      // le DOM ici (source du bug de clics perdus, 2026-09-25).
      if (this._updateValues()) this._render();
    }
  }

  async _load() {
    try {
      const [entities, devices] = await Promise.all([
        this._hass.callWS({ type: "config/entity_registry/list" }),
        this._hass.callWS({ type: "config/device_registry/list" }),
      ]);

      const myEntities = entities.filter((e) => e.platform === DOMAIN);
      const devicesById = Object.fromEntries(devices.map((d) => [d.id, d]));

      const byDevice = new Map();
      for (const ent of myEntities) {
        if (!byDevice.has(ent.device_id)) byDevice.set(ent.device_id, {});
        const metric = SORTS.find((s) => (ent.unique_id || "").endsWith(`_${s.key}`));
        if (metric) byDevice.get(ent.device_id)[metric.key] = ent.entity_id;
      }

      this._installations = [];
      for (const [deviceId, entityIds] of byDevice.entries()) {
        const device = devicesById[deviceId];
        if (!device) continue;
        this._installations.push({
          deviceId,
          name: device.name_by_user || device.name || "?",
          address: device.model || "",
          entityIds,
        });
      }
      this._error = null;
    } catch (err) {
      this._error = err && err.message ? err.message : String(err);
    }
    this._updateValues();
  }

  /** Retourne true si au moins une valeur pertinente a change. */
  _updateValues() {
    if (!this._hass) return false;
    let changed = false;
    for (const inst of this._installations) {
      const previous = inst.values;
      inst.values = {};
      let lastUpdated = null;
      for (const s of SORTS) {
        const entityId = inst.entityIds[s.key];
        const state = entityId ? this._hass.states[entityId] : null;
        const num = state && state.state !== "unknown" && state.state !== "unavailable"
          ? parseFloat(state.state)
          : null;
        inst.values[s.key] = Number.isNaN(num) ? null : num;
        if (!previous || previous[s.key] !== inst.values[s.key]) changed = true;
        if (state && state.last_updated) {
          const t = new Date(state.last_updated);
          if (!lastUpdated || t > lastUpdated) lastUpdated = t;
        }
      }
      inst.lastUpdated = lastUpdated;
    }
    return changed;
  }

  _setSort(key) {
    if (key === this._activeSort) {
      // Meme bouton reclique : inverse le sens (2026-09-25, demande utilisateur)
      this._sortAsc = !this._sortAsc;
    } else {
      // Nouvelle categorie : toujours repartir du defaut (croissant)
      this._activeSort = key;
      this._sortAsc = true;
    }
    this._render();
  }

  /**
   * Construit la coquille UNE SEULE FOIS (style + titre + boutons d'onglets
   * + conteneur de grille vide). Les boutons d'onglets restent les MEMES
   * noeuds DOM pour toute la vie du panneau - plus jamais recrees.
   *
   * Root cause du bug de clics perdus (2026-09-25, confirme en direct avec
   * les outils Chrome) : hass est pousse tres frequemment par HA (tout
   * changement d'etat systeme), et l'ancienne version remplacait TOUT le
   * innerHTML (y compris les boutons) a chaque rendu. Un clic .click()
   * programmatique fonctionnait toujours, mais un vrai clic souris pouvait
   * arriver pile pendant qu'un rendu remplaçait le bouton en dessous du
   * curseur - le navigateur perd alors l'evenement. Fix : ne plus jamais
   * toucher aux boutons apres leur creation initiale, seule la grille de
   * cartes est reconstruite.
   */
  _buildShell() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; height: 100%; font-family: var(--paper-font-body1_-_font-family, sans-serif); }
        .header {
          padding: 16px 24px 8px;
          background: var(--card-background-color, #fff);
          border-bottom: 1px solid var(--divider-color, #e0e0e0);
        }
        .title { font-size: 22px; font-weight: 500; margin: 0 0 12px; color: var(--primary-text-color, #212121); }
        .tabs { display: flex; gap: 8px; flex-wrap: wrap; }
        .tab {
          padding: 8px 16px;
          border-radius: 20px;
          border: none;
          background: var(--secondary-background-color, #f0f0f0);
          color: var(--primary-text-color, #212121);
          cursor: pointer;
          font-size: 14px;
        }
        .tab.active {
          background: var(--primary-color, #03a9f4);
          color: white;
        }
        .grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 12px;
          padding: 16px 24px;
        }
        .card {
          background: var(--card-background-color, #fff);
          border-left: 5px solid #9e9e9e;
          border-radius: 8px;
          padding: 12px 16px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.12);
        }
        .card-title { font-size: 15px; font-weight: 600; color: var(--primary-text-color, #212121); }
        .card-address { font-size: 12px; color: var(--secondary-text-color, #757575); margin-bottom: 8px; }
        .card-metrics { display: flex; flex-direction: column; gap: 4px; margin-top: 8px; }
        .metric { display: flex; justify-content: space-between; font-size: 13px; padding: 2px 0; }
        .metric.highlight { font-weight: 700; font-size: 14px; }
        .metric-label { color: var(--secondary-text-color, #757575); }
        .metric-value { font-weight: 600; }
        .placeholder { padding: 24px; }
      </style>
      <div class="header">
        <p class="title"></p>
        <div class="tabs">
          ${SORTS.map((s) => `<button class="tab" data-sort="${s.key}">${s.icon} ${s.label}<span class="dir"></span></button>`).join("")}
        </div>
      </div>
      <div class="grid"></div>
    `;
    this._titleEl = this.shadowRoot.querySelector(".title");
    this._gridEl = this.shadowRoot.querySelector(".grid");
    this._tabEls = [...this.shadowRoot.querySelectorAll(".tab")];
    this._shellBuilt = true;
  }

  _render() {
    if (!this.shadowRoot) return;
    if (!this._shellBuilt) this._buildShell();

    if (this._error) {
      this._titleEl.textContent = "🏥 Urgences Québec";
      this._gridEl.innerHTML = `<div class="placeholder" style="color:#d32f2f;">Erreur de chargement : ${this._error}</div>`;
      return;
    }

    if (!this._loaded) {
      this._titleEl.textContent = "🏥 Urgences Québec";
      this._gridEl.innerHTML = `<div class="placeholder">Chargement...</div>`;
      return;
    }

    if (this._installations.length === 0) {
      this._titleEl.textContent = "🏥 Urgences Québec";
      this._gridEl.innerHTML = `<div class="placeholder">
        Aucune installation sélectionnée. Configure l'intégration Urgences Québec
        (Paramètres → Appareils et services → Urgences Québec → Configurer) pour
        choisir les urgences à suivre.
      </div>`;
      return;
    }

    const sorted = [...this._installations].sort((a, b) => {
      const av = a.values[this._activeSort];
      const bv = b.values[this._activeSort];
      if (av === null) return 1;
      if (bv === null) return -1;
      // Defaut (this._sortAsc=true) : plus petit nombre en premier. Reclic
      // sur la meme categorie inverse (voir _setSort).
      return this._sortAsc ? av - bv : bv - av;
    });

    this._titleEl.textContent = `🏥 Urgences Québec — ${sorted.length} installation(s)`;

    for (const btn of this._tabEls) {
      const isActive = btn.dataset.sort === this._activeSort;
      btn.classList.toggle("active", isActive);
      btn.querySelector(".dir").textContent = isActive ? (this._sortAsc ? " ↑" : " ↓") : "";
    }

    this._gridEl.innerHTML = sorted
      .map((inst) => {
        const rows = SORTS.map((s) => {
          const v = inst.values[s.key];
          const display = v === null ? "—" : `${v}${s.unit}`;
          const highlight = s.key === this._activeSort;
          return `
            <div class="metric ${highlight ? "highlight" : ""}">
              <span class="metric-label">${s.icon} ${s.label}</span>
              <span class="metric-value" style="color:${colorFor(s.key, v)}">${display}</span>
            </div>`;
        }).join("");

        return `
          <div class="card" style="border-left-color:${colorFor(this._activeSort, inst.values[this._activeSort])}">
            <div class="card-title">${inst.name}</div>
            ${inst.address ? `<div class="card-address">${inst.address}</div>` : ""}
            <div class="card-metrics">${rows}</div>
          </div>`;
      })
      .join("");
  }
}

if (!customElements.get("urgences-quebec-panel")) {
  customElements.define("urgences-quebec-panel", UrgencesQuebecPanel);
}
