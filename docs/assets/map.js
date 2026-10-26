
const RUBRIK_COLORS = window.RUBRIK_COLORS || {};
const RUBRIK_FALLBACK = "#7a6a58";

const map = L.map("map", { scrollWheelZoom: true, closePopupOnClick: false }).setView([52.5038, 13.3615], 15);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap",
}).addTo(map);

function esc(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function rubrikColor(name) {
  const key = String(name || "").trim();
  if (!key) return RUBRIK_FALLBACK;
  if (RUBRIK_COLORS[key]) return RUBRIK_COLORS[key];
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  const hue = h % 360;
  return "hsl(" + hue + " 42% 42%)";
}

function conicFromArticles(articles) {
  if (!articles.length) return RUBRIK_FALLBACK;
  const counts = {};
  const order = [];
  articles.forEach((a) => {
    const r = String(a.rubrik || "").trim() || "Sonstiges";
    if (!counts[r]) {
      counts[r] = 0;
      order.push(r);
    }
    counts[r] += 1;
  });
  const total = articles.length;
  let start = 0;
  const parts = order.map((r) => {
    const share = (counts[r] / total) * 100;
    const end = start + share;
    const slice = rubrikColor(r) + " " + start.toFixed(2) + "% " + end.toFixed(2) + "%";
    start = end;
    return slice;
  });
  return "conic-gradient(" + parts.join(", ") + ")";
}

const POPUP_CAP = 10;
const MONTHS_DE = ["Jan","Feb","Mär","Apr","Mai","Jun","Jul","Aug","Sep","Okt","Nov","Dez"];
const TIME_BOUNDS = window.TIME_RANGE || { min: 2022 * 12, max: 2026 * 12 + 9 };
let monthFrom = TIME_BOUNDS.min;
let monthTo = TIME_BOUNDS.max;
let matchPublish = true;
let matchAbout = true;

function fmtMonth(idx) {
  const y = Math.floor(idx / 12);
  const m = ((idx % 12) + 12) % 12;
  return MONTHS_DE[m] + " " + y;
}

function publishMonthIndex(article) {
  const d = String((article && article.date) || "");
  const y = parseInt(d.slice(0, 4), 10);
  if (!Number.isFinite(y)) return null;
  let m = parseInt(d.slice(5, 7), 10);
  if (!Number.isFinite(m) || m < 1 || m > 12) m = 1;
  return y * 12 + (m - 1);
}

function timeOn(article) {
  const pub = publishMonthIndex(article);
  const about = Array.isArray(article.about_years) ? article.about_years : [];
  const fromY = Math.floor(monthFrom / 12);
  const toY = Math.floor(monthTo / 12);
  let ok = false;
  if (matchPublish && pub != null && pub >= monthFrom && pub <= monthTo) ok = true;
  if (matchAbout && about.some((y) => y >= fromY && y <= toY)) ok = true;
  // If user unchecked both, treat as "no time filter".
  if (!matchPublish && !matchAbout) return true;
  return ok;
}

function dateFilterActive() {
  return (
    monthFrom > TIME_BOUNDS.min ||
    monthTo < TIME_BOUNDS.max ||
    !matchPublish ||
    !matchAbout
  );
}

function articleRow(a) {
  const rubrik = String(a.rubrik || "").trim();
  const color = rubrikColor(rubrik);
  const tag = rubrik
    ? "<span class='rubrik-tag' style='background:color-mix(in srgb, " +
      color +
      " 28%, white)'>" +
      esc(rubrik) +
      "</span>"
    : "";
  const line = [a.date ? esc(a.date) : "", tag].filter(Boolean).join(" · ");
  const excerpt = a.excerpt
    ? "<p class='popup-excerpt'>" + esc(a.excerpt) + "</p>"
    : "";
  const inner =
    "<span class='chip' style='background:" +
    color +
    "' title='" +
    esc(rubrik || "ohne Rubrik") +
    "'></span><div><span class='t'>" +
    esc(a.title) +
    "</span>" +
    (line ? "<div class='popup-meta'>" + line + "</div>" : "") +
    excerpt +
    "</div>";
  return a.url
    ? "<li><a href='" + esc(a.url) + "'>" + inner + "</a></li>"
    : "<li style='display:grid;grid-template-columns:0.55rem 1fr;gap:0.55rem'>" +
        inner +
        "</li>";
}

function popupHtml(p) {
  const articles = Array.isArray(p.articles) ? p.articles : [];
  const place = p.place || (articles[0] && articles[0].title) || "Ort";
  const n = articles.length || p.count || 0;
  const meta = n > 1 ? n + " Beiträge" : n === 1 ? "1 Beitrag" : "";
  const shown = articles.slice(0, POPUP_CAP);
  const items = shown.map(articleRow).join("");
  const moreHref = p.place_url || "";
  const filtered =
    activeRubriks.size < knownRubriks.size || dateFilterActive();
  const moreLabel = filtered ? "Zur Ortsseite →" : "Alle " + n + " Beiträge →";
  const more =
    n > POPUP_CAP && moreHref
      ? "<a class='popup-more' href='" + esc(moreHref) + "'>" + moreLabel + "</a>"
      : moreHref && n > 1
        ? "<a class='popup-more' href='" + esc(moreHref) + "'>Zur Ortsseite →</a>"
        : "";
  return (
    "<div class='map-popup'>" +
    "<strong class='popup-place'>" +
    esc(place) +
    "</strong>" +
    (meta ? "<div class='popup-meta'>" + esc(meta) + "</div>" : "") +
    "<ul class='popup-articles'>" +
    items +
    "</ul>" +
    more +
    "</div>"
  );
}

function singleStyle(feature) {
  const arts = (feature.properties && feature.properties.articles) || [];
  const fill = rubrikColor(arts[0] && arts[0].rubrik);
  return {
    radius: 8,
    color: "#2a221c",
    weight: 1.4,
    fillColor: fill,
    fillOpacity: 0.92,
  };
}

function multiIcon(feature) {
  const arts = (feature.properties && feature.properties.articles) || [];
  const n = arts.length || 1;
  const size = Math.min(22, 12 + Math.sqrt(n) * 3.2);
  const bg = conicFromArticles(arts);
  return L.divIcon({
    className: "",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html:
      "<div class='pin-multi' style='width:" +
      size +
      "px;height:" +
      size +
      "px;background:" +
      bg +
      "' title='" +
      esc(String(n) + " Beiträge") +
      "'></div>",
  });
}

let placesLayer = null;
let sourceFeatures = [];
let fitted = false;
const knownRubriks = new Set();
const activeRubriks = new Set();

function rubrikOf(article) {
  return String((article && article.rubrik) || "").trim() || "Sonstiges";
}

function rubrikOn(name) {
  if (!knownRubriks.has(name)) return true;
  return activeRubriks.has(name);
}

function featureForFilter(feature) {
  const props = feature.properties || {};
  const articles = (Array.isArray(props.articles) ? props.articles : []).filter(
    (a) => rubrikOn(rubrikOf(a)) && timeOn(a)
  );
  if (!articles.length) return null;
  return {
    type: "Feature",
    geometry: feature.geometry,
    properties: Object.assign({}, props, { articles: articles, count: articles.length }),
  };
}

function drawPlaces(geo) {
  const layer = L.geoJSON(geo, {
    pointToLayer(feature, latlng) {
      const n = (feature.properties && feature.properties.count) || 1;
      if (n > 1) return L.marker(latlng, { icon: multiIcon(feature), riseOnHover: true });
      return L.circleMarker(latlng, singleStyle(feature));
    },
    onEachFeature(feature, lyr) {
      const p = feature.properties || {};
      lyr.bindPopup(popupHtml(p), {
        maxWidth: Math.min(320, Math.max(180, window.innerWidth - 56)),
        className: "article-popup",
        autoPan: true,
        autoPanPadding: [12, 12],
        closeButton: true,
        closeOnClick: false,
        autoClose: true,
      });
      lyr.on("click", function () {
        this.openPopup();
      });
    },
  }).addTo(map);
  if (!fitted && layer.getBounds().isValid()) {
    const kiez = L.latLngBounds([52.493, 13.345], [52.515, 13.385]);
    map.fitBounds(kiez.pad(0.08));
    const clipped = layer.getBounds().pad(0.12);
    if (kiez.intersects(clipped)) map.fitBounds(kiez.pad(0.05));
    fitted = true;
  }
  map.invalidateSize();
  return layer;
}

function updateYearLabel() {
  const el = document.getElementById("year-label");
  if (el) el.textContent = fmtMonth(monthFrom) + " – " + fmtMonth(monthTo);
}

function updateFilterStatus(visible, total) {
  const status = document.getElementById("map-filter-status");
  const reset = document.getElementById("map-filter-reset");
  const off = knownRubriks.size - activeRubriks.size;
  const dated = dateFilterActive();
  if (reset) reset.hidden = off === 0 && !dated;
  if (!status) return;
  if (!off && !dated) {
    status.hidden = true;
    status.textContent = "";
    return;
  }
  status.hidden = false;
  const bits = [
    visible + (visible === 1 ? " Ort" : " Orte") + " von " + total,
  ];
  if (monthFrom > TIME_BOUNDS.min || monthTo < TIME_BOUNDS.max) {
    bits.push(fmtMonth(monthFrom) + "–" + fmtMonth(monthTo));
  }
  if (!matchPublish || !matchAbout) {
    const modes = [];
    if (matchPublish) modes.push("Erschienen");
    if (matchAbout) modes.push("Thema");
    bits.push(modes.length ? modes.join("+") : "ohne Zeitfilter");
  }
  status.textContent = bits.join(" · ");
}

function applyFilter() {
  map.closePopup();
  const popupPane = map.getPane("popupPane");
  if (popupPane) popupPane.replaceChildren();
  if (placesLayer) {
    map.removeLayer(placesLayer);
    placesLayer = null;
  }
  const features = [];
  sourceFeatures.forEach((feature) => {
    const next = featureForFilter(feature);
    if (next) features.push(next);
  });
  placesLayer = drawPlaces({ type: "FeatureCollection", features: features });
  updateFilterStatus(features.length, sourceFeatures.length);
}

function syncRubrikButton(btn, on) {
  btn.setAttribute("aria-pressed", on ? "true" : "false");
  btn.title = on ? "Ausblenden" : "Einblenden";
}

function bindYearSliders() {
  const fromEl = document.getElementById("year-from");
  const toEl = document.getElementById("year-to");
  const pubEl = document.getElementById("time-publish");
  const aboutEl = document.getElementById("time-about");
  if (!fromEl || !toEl) return;
  fromEl.min = String(TIME_BOUNDS.min);
  fromEl.max = String(TIME_BOUNDS.max);
  toEl.min = String(TIME_BOUNDS.min);
  toEl.max = String(TIME_BOUNDS.max);
  fromEl.value = String(monthFrom);
  toEl.value = String(monthTo);
  if (pubEl) pubEl.checked = matchPublish;
  if (aboutEl) aboutEl.checked = matchAbout;
  updateYearLabel();

  function syncSlider() {
    let a = parseInt(fromEl.value, 10);
    let b = parseInt(toEl.value, 10);
    if (a > b) {
      if (document.activeElement === fromEl) b = a;
      else a = b;
      fromEl.value = String(a);
      toEl.value = String(b);
    }
    monthFrom = a;
    monthTo = b;
    updateYearLabel();
    applyFilter();
  }
  function syncModes() {
    matchPublish = !pubEl || pubEl.checked;
    matchAbout = !aboutEl || aboutEl.checked;
    if (!matchPublish && !matchAbout) {
      // Keep at least one criterion so the control stays meaningful.
      matchPublish = true;
      if (pubEl) pubEl.checked = true;
    }
    applyFilter();
  }
  fromEl.addEventListener("input", syncSlider);
  toEl.addEventListener("input", syncSlider);
  if (pubEl) pubEl.addEventListener("change", syncModes);
  if (aboutEl) aboutEl.addEventListener("change", syncModes);
}

function resetYears() {
  monthFrom = TIME_BOUNDS.min;
  monthTo = TIME_BOUNDS.max;
  matchPublish = true;
  matchAbout = true;
  const fromEl = document.getElementById("year-from");
  const toEl = document.getElementById("year-to");
  const pubEl = document.getElementById("time-publish");
  const aboutEl = document.getElementById("time-about");
  if (fromEl) fromEl.value = String(monthFrom);
  if (toEl) toEl.value = String(monthTo);
  if (pubEl) pubEl.checked = true;
  if (aboutEl) aboutEl.checked = true;
  updateYearLabel();
}

function bindLegend() {
  document.querySelectorAll(".map-legend button[data-rubrik]").forEach((btn) => {
    const name = btn.getAttribute("data-rubrik") || "";
    if (!name) return;
    knownRubriks.add(name);
    activeRubriks.add(name);
    syncRubrikButton(btn, true);
    btn.addEventListener("click", function () {
      if (activeRubriks.has(name)) activeRubriks.delete(name);
      else activeRubriks.add(name);
      syncRubrikButton(btn, activeRubriks.has(name));
      applyFilter();
    });
  });
  const reset = document.getElementById("map-filter-reset");
  if (reset) {
    reset.addEventListener("click", function () {
      activeRubriks.clear();
      knownRubriks.forEach((name) => activeRubriks.add(name));
      document.querySelectorAll(".map-legend button[data-rubrik]").forEach((btn) => {
        syncRubrikButton(btn, true);
      });
      resetYears();
      applyFilter();
    });
  }
}

function showPlaces(geo) {
  sourceFeatures = (geo && geo.features) || [];
  applyFilter();
}

bindYearSliders();
bindLegend();
const embedded = window.ARCHIVE_PLACES;
if (embedded && embedded.features) {
  showPlaces(embedded);
} else {
  fetch("data/articles.geojson").then((r) => r.json()).then(showPlaces);
}
window.addEventListener("resize", function () { map.invalidateSize(); });
