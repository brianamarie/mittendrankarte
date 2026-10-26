"""Build the public map site from article metadata. Full post text is not published."""
from __future__ import annotations

import html
import json
import re
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from articles_lib import description_from_text, extract_about_years  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ARTICLES = ROOT / "articles"
DOCS = ROOT / "docs"

# Stable palette for mittendran rubrics (readable on the map).
RUBRIK_COLORS = {
    "Aus dem Kiez": "#4a7c59",
    "Kunst und Kultur": "#8b4d9a",
    "Miteinander": "#c45c26",
    "Öffentlicher Raum und Verkehr": "#2f6f9f",
    "Bauen und Wohnen": "#8b6914",
    "Gewerbe und Gastronomie": "#b33b3b",
    "Kiez-Geschichte": "#5c4a3a",
    "kiek ma!": "#d4a017",
    "Kinder, Heranwachsende, Schule": "#3d8b8b",
    "Kiez mit Kind": "#5aa0a0",
    "In eigener Sache": "#6b6b6b",
    "Sport und Freizeit": "#3f7d4e",
    "Der andere Blick": "#7a4e8c",
}
RUBRIK_FALLBACK = "#7a6a58"

CSS = """
:root {
  color-scheme: light;
  --ink: #1a1a1a;
  --muted: #5c5c5c;
  --paper: #f7f4ef;
  --card: #fff;
  --line: #ddd6cb;
  --accent: #1a4f8b;
}
* { box-sizing: border-box; }
body { margin: 0; font: 1.05rem/1.55 "Segoe UI", system-ui, sans-serif; color: var(--ink); background: var(--paper); }
header, footer { padding: 0.7rem 1rem; background: #161616; color: #eee; }
header a, footer a { color: #b9d4ff; text-decoration: none; }
header a { display: inline-block; padding: 0.35rem 0; }
header a:hover, footer a:hover { text-decoration: underline; }
main { max-width: 46rem; margin: 0 auto; padding: 1.2rem 1.1rem 3rem; }
main.map-page { max-width: none; padding: 0; }
.map-intro { max-width: none; margin: 0; padding: 0; }
.map-bar {
  display: flex; flex-wrap: wrap; align-items: center; gap: 0.35rem 0.7rem;
  padding: 0.35rem 0.7rem; border-bottom: 1px solid var(--line); background: var(--paper);
}
.map-bar h1 { font-size: 1rem; margin: 0; }
.map-count { color: var(--muted); font-size: 0.82rem; }
.map-filters-toggle {
  margin-left: auto; font: inherit; font-size: 0.82rem; font-weight: 650;
  color: var(--ink); background: #fff; border: 1px solid var(--line);
  border-radius: 999px; padding: 0.2rem 0.7rem; cursor: pointer;
}
.map-filters-toggle:hover, .map-filters-toggle:focus-visible {
  border-color: var(--accent); color: var(--accent); outline: none;
}
.map-panel {
  max-height: 34vh; overflow: auto; padding: 0.4rem 0.75rem 0.55rem;
  border-bottom: 1px solid var(--line); background: #fff;
}
.map-panel[hidden] { display: none !important; }
.map-legend {
  display: flex; flex-wrap: wrap; gap: 0.28rem 0.45rem; align-items: center;
  font-size: 0.78rem; line-height: 1.25; color: var(--muted);
  margin-top: 0.35rem;
}
.map-legend .leg {
  display: inline-flex; align-items: center; gap: 0.3rem; white-space: nowrap; flex: none;
}
.map-legend button.leg {
  font: inherit; color: inherit; background: transparent;
  border: 1px solid transparent; border-radius: 999px;
  padding: 0.08rem 0.42rem; cursor: pointer;
}
.map-legend button.leg:hover,
.map-legend button.leg:focus-visible {
  background: #fff; border-color: var(--line); outline: none;
}
.map-legend button.leg[aria-pressed="false"] {
  opacity: 0.42; text-decoration: line-through;
}
.map-legend button.leg[aria-pressed="false"] .sw { filter: grayscale(1); }
.map-legend .leg-reset {
  font-weight: 600; color: var(--accent); text-decoration: none; opacity: 1;
}
.map-legend .sw {
  width: 0.7rem; height: 0.7rem; border-radius: 50%;
  border: 1px solid rgba(0,0,0,.25); flex: none;
}
.map-legend .sw.multi {
  border-radius: 2px;
  background: conic-gradient(#4a7c59 0 33%, #8b4d9a 33% 66%, #c45c26 66% 100%);
}
.map-filter-status { margin: 0.2rem 0 0; font-size: 0.78rem; }
.map-legend [hidden], .map-filter-status[hidden] { display: none !important; }
.map-years {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.25rem 0.65rem;
  align-items: baseline;
  margin: 0.4rem 0 0.15rem;
  font-size: 0.82rem;
  color: var(--muted);
  max-width: 32rem;
}
.map-years .year-heading { font-weight: 600; color: var(--ink); }
.map-years .year-label { font-variant-numeric: tabular-nums; color: var(--ink); font-weight: 600; }
.map-years .year-hint { grid-column: 1 / -1; font-size: 0.72rem; margin: 0; }
.map-years .year-modes {
  grid-column: 1 / -1;
  display: flex; flex-wrap: wrap; gap: 0.35rem 0.75rem;
  margin: 0.05rem 0 0.1rem;
}
.map-years .year-modes label {
  display: inline-flex; align-items: center; gap: 0.3rem;
  cursor: pointer; user-select: none; color: var(--ink);
}
.map-years .year-track {
  position: relative;
  height: 1.4rem;
  grid-column: 1 / -1;
}
.map-years input[type="range"] {
  position: absolute;
  left: 0; right: 0; top: 0;
  width: 100%;
  margin: 0;
  pointer-events: none;
  appearance: none;
  background: transparent;
  height: 1.4rem;
}
.map-years input[type="range"]::-webkit-slider-runnable-track {
  height: 4px; border-radius: 2px; background: #d0c8bc;
}
.map-years input[type="range"]::-moz-range-track {
  height: 4px; border-radius: 2px; background: #d0c8bc; border: none;
}
.map-years input[type="range"]::-webkit-slider-thumb {
  appearance: none; pointer-events: auto; width: 16px; height: 16px;
  border-radius: 50%; background: var(--accent); border: 2px solid #fff;
  box-shadow: 0 1px 3px rgba(0,0,0,.3); margin-top: -6px; cursor: pointer;
}
.map-years input[type="range"]::-moz-range-thumb {
  pointer-events: auto; width: 16px; height: 16px; border-radius: 50%;
  background: var(--accent); border: 2px solid #fff; box-shadow: 0 1px 3px rgba(0,0,0,.3); cursor: pointer;
}
@media (max-width: 700px) {
  .map-legend { flex-wrap: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .map-years { max-width: none; }
  .map-bar .map-areas { flex-basis: 100%; }
}
nav { display: flex; gap: 1.1rem; flex-wrap: wrap; align-items: baseline; }
h1 { font-size: 1.45rem; line-height: 1.25; margin: 0 0 0.35rem; }
html:has(.map-page) { height: 100%; overflow: hidden; }
body:has(.map-page) {
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
}
body:has(.map-page) header,
body:has(.map-page) footer,
body:has(.map-page) .map-intro { flex: none; }
body:has(.map-page) header { padding: 0.35rem 0.75rem; }
body:has(.map-page) footer { font-size: 0.78rem; line-height: 1.35; padding: 0.28rem 0.75rem; }
body:has(.map-page) .map-page {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.cards { display: grid; gap: 0.75rem; padding: 0; list-style: none; }
.cards a { display: block; background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 0.85rem 1rem; text-decoration: none; color: inherit; }
.cards a:hover { border-color: var(--accent); }
.meta { color: var(--muted); font-size: 0.92rem; }
.original { display: inline-block; margin: 0.4rem 0 1rem; }
.hero { max-width: 100%; height: auto; border-radius: 8px; }
#map { height: calc(100vh - 9.5rem); height: calc(100dvh - 9.5rem); min-height: 280px; width: 100%; background: #d8d4ce; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); touch-action: none; }
body:has(.map-page) #map { flex: 1; height: auto; min-height: 0; }
.lead { max-width: 40rem; }
.pin-multi {
  border: 1.5px solid #2a221c;
  box-shadow: 0 1px 3px rgba(0,0,0,.35);
  border-radius: 3px;
}
.leaflet-popup-content-wrapper { border-radius: 10px; box-shadow: 0 8px 28px rgba(0,0,0,.18); max-width: calc(100vw - 2.4rem); }
.leaflet-popup-content { margin: 0.75rem 0.85rem; }
.leaflet-popup-content .map-popup { margin: 0; min-width: min(240px, calc(100vw - 5rem)); max-width: calc(100vw - 4.2rem); padding-right: 1.6rem; }
.leaflet-popup-content .popup-place { font-size: 1.08rem; display: block; }
.leaflet-popup-content .popup-meta { color: var(--muted); font-size: 0.82rem; margin: 0.2rem 0 0.3rem; }
.leaflet-popup-content .rubrik-tag {
  display: inline;
  padding: 0.05em 0.38em;
  border-radius: 3px;
  color: #1a1a1a;
  font-weight: 600;
  -webkit-box-decoration-break: clone;
  box-decoration-break: clone;
}
.leaflet-popup-content a:hover .rubrik-tag { color: #1a1a1a; }
.leaflet-popup-content .popup-excerpt { margin: 0.2rem 0 0; font-size: 0.86rem; line-height: 1.35; color: #333;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.leaflet-popup-content .popup-articles { list-style: none; padding: 0; margin: 0.35rem 0 0; max-height: min(260px, 42dvh); overflow-y: auto; -webkit-overflow-scrolling: touch; }
.leaflet-popup-content .popup-articles li { border-top: 1px solid var(--line); padding: 0.5rem 0; }
.leaflet-popup-content .popup-articles a { display: grid; grid-template-columns: 0.55rem 1fr; gap: 0.55rem; text-decoration: none; color: inherit; border-radius: 4px; align-items: start; }
.leaflet-popup-content .popup-articles a:hover { color: var(--accent); }
.leaflet-popup-content .popup-articles .chip {
  width: 0.55rem; min-height: 1.1rem; border-radius: 2px; margin-top: 0.15rem;
  border: 1px solid rgba(0,0,0,.2);
}
.leaflet-popup-content .popup-articles .t { font-weight: 600; font-size: 0.95rem; }
.leaflet-popup-content .popup-more {
  display: block; margin-top: 0.55rem; padding-top: 0.45rem;
  border-top: 1px solid var(--line); font-weight: 600; font-size: 0.9rem;
  color: var(--accent); text-decoration: none;
}
.leaflet-popup-content .popup-more:hover { text-decoration: underline; }
.map-areas {
  display: flex; flex-wrap: wrap; gap: 0.3rem; margin: 0;
  font-size: 0.78rem;
}
.map-areas a {
  display: inline-block; padding: 0.2rem 0.55rem; border-radius: 999px;
  border: 1px solid var(--line); background: #fff; color: inherit; text-decoration: none;
}
.map-areas a:hover { border-color: var(--accent); color: var(--accent); }
.map-areas .lbl { color: var(--muted); align-self: center; margin-right: 0.15rem; }
.leaflet-container a.leaflet-popup-close-button {
  top: 2px; right: 2px; width: 44px; height: 44px;
  font: 28px/44px Arial, sans-serif; padding: 0; color: #3d342c;
}
main.place-page { max-width: 40rem; }
.place-back { margin: 0 0 1rem; font-size: 0.92rem; }
.place-back a { color: var(--accent); text-decoration: none; }
.place-back a:hover { text-decoration: underline; }
.place-kicker {
  margin: 0; font-size: 0.72rem; letter-spacing: 0.07em; text-transform: uppercase;
  color: var(--muted); font-weight: 650;
}
.place-page h1 { font-size: 1.9rem; line-height: 1.15; margin: 0.2rem 0 0.35rem; }
.place-stats { margin: 0 0 0.75rem; color: var(--muted); }
.place-page .lead { margin: 0 0 0.85rem; }
.place-search { display: block; margin: 0 0 0.7rem; }
.place-search input {
  width: 100%; font: inherit; font-size: 1rem;
  padding: 0.55rem 0.7rem; border: 1px solid var(--line); border-radius: 8px;
  background: #fff; color: inherit;
}
.place-search input:focus { outline: 2px solid color-mix(in srgb, var(--accent) 45%, white); border-color: var(--accent); }
.visually-hidden {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
}
.place-osm { font-size: 0.92rem; color: var(--accent); }
.place-related { margin: 0 0 1.15rem; }
.place-related h2, .place-year {
  font-size: 0.95rem; margin: 0 0 0.4rem; font-weight: 650;
}
.place-related p { margin: 0 0 0.45rem; }
.place-chips { display: flex; flex-wrap: wrap; gap: 0.35rem; padding: 0; list-style: none; }
.place-chips a {
  display: inline-block; padding: 0.18rem 0.55rem; border-radius: 999px;
  border: 1px solid var(--line); background: #fff; color: inherit;
  text-decoration: none; font-size: 0.84rem;
}
.place-chips a:hover { border-color: var(--accent); color: var(--accent); }
.place-chips .n { color: var(--muted); }
.place-rubriks {
  display: flex; flex-wrap: wrap; gap: 0.35rem; margin: 0 0 0.4rem; align-items: center;
}
.place-rubriks button, .place-rubriks .rubrik-static {
  font: inherit; font-size: 0.82rem; color: inherit;
  display: inline-flex; align-items: center; gap: 0.35rem;
  border: 1px solid var(--line); background: #fff; border-radius: 999px;
  padding: 0.18rem 0.55rem 0.18rem 0.4rem;
}
.place-rubriks button { cursor: pointer; }
.place-rubriks button:hover, .place-rubriks button:focus-visible {
  border-color: var(--accent); outline: none;
}
.place-rubriks button[aria-pressed="false"] { opacity: 0.42; text-decoration: line-through; }
.place-rubriks .n { color: var(--muted); }
.place-swatch, .place-bar {
  border: 1px solid rgba(0,0,0,.22); flex: none;
}
.place-swatch { width: 0.65rem; height: 0.65rem; border-radius: 50%; }
.place-year { margin: 1.35rem 0 0.45rem; }
.place-year .n { color: var(--muted); font-weight: 500; }
.place-page .cards { gap: 0.5rem; }
.place-page .cards a {
  display: grid; grid-template-columns: 0.4rem 1fr; gap: 0.7rem;
  padding: 0.7rem 0.8rem; align-items: stretch;
}
.place-bar { width: 0.4rem; border-radius: 3px; min-height: 100%; }
.place-card-body { min-width: 0; }
.place-tag {
  display: inline; padding: 0.04em 0.35em; border-radius: 3px;
  font-weight: 600; color: #1a1a1a;
}
.place-excerpt {
  margin: 0.28rem 0 0; color: #333; font-size: 0.9rem; line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.place-empty { color: var(--muted); margin-top: 1rem; }
.place-group[hidden], .place-page .cards li[hidden], .place-empty[hidden],
.place-rubriks [hidden] { display: none !important; }
"""

MAP_JS = """
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

function showingAllRubriks() {
  return activeRubriks.size === knownRubriks.size;
}

function syncRubrikButton(btn, on, all) {
  btn.setAttribute("aria-pressed", on ? "true" : "false");
  btn.title = all ? "Nur diese zeigen" : on ? "Abwählen" : "Hinzufügen";
}

function syncAllRubrikButtons() {
  const all = showingAllRubriks();
  document.querySelectorAll(".map-legend button[data-rubrik]").forEach((btn) => {
    const name = btn.getAttribute("data-rubrik") || "";
    syncRubrikButton(btn, all || activeRubriks.has(name), all);
  });
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
    btn.addEventListener("click", function () {
      if (showingAllRubriks()) {
        activeRubriks.clear();
        activeRubriks.add(name);
      } else if (activeRubriks.has(name)) {
        activeRubriks.delete(name);
        if (!activeRubriks.size) {
          knownRubriks.forEach((rubrik) => activeRubriks.add(rubrik));
        }
      } else {
        activeRubriks.add(name);
      }
      syncAllRubrikButtons();
      applyFilter();
    });
  });
  syncAllRubrikButtons();
  const reset = document.getElementById("map-filter-reset");
  if (reset) {
    reset.addEventListener("click", function () {
      activeRubriks.clear();
      knownRubriks.forEach((name) => activeRubriks.add(name));
      syncAllRubrikButtons();
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

(function () {
  const toggle = document.getElementById("map-filters-toggle");
  const panel = document.getElementById("map-panel");
  if (!toggle || !panel) return;
  toggle.addEventListener("click", function () {
    const open = panel.hasAttribute("hidden");
    if (open) panel.removeAttribute("hidden");
    else panel.setAttribute("hidden", "");
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.textContent = open ? "Filter schließen" : "Filter";
    map.invalidateSize();
  });
})();
"""


def text_origin(meta: dict) -> str:
    if meta.get("text_origin"):
        return str(meta["text_origin"])
    if meta.get("wp_post_id"):
        return "wp"
    return "ocr"


def load_publishable() -> list[dict]:
    """WP-origin articles only; one folder per wp_post_id."""
    by_id: dict[int, dict] = {}
    orphans: list[dict] = []
    for meta_path in sorted(ARTICLES.rglob("meta.yaml")):
        folder = meta_path.parent
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        if meta.get("sample"):
            continue
        if text_origin(meta) != "wp":
            continue
        if not meta.get("source_url"):
            continue
        meta["_folder"] = folder
        meta["_slug"] = meta.get("slug") or folder.name
        description = str(meta.get("description") or "").strip()
        if not description:
            de_path = folder / "de.md"
            if de_path.exists():
                description = description_from_text(de_path.read_text(encoding="utf-8"))
        meta["_description"] = description
        wp_id = meta.get("wp_post_id")
        if wp_id is None:
            orphans.append(meta)
            continue
        wp_id = int(wp_id)
        prev = by_id.get(wp_id)
        # Prefer articles/web/ over Heft buckets when both exist.
        if prev is None:
            by_id[wp_id] = meta
        else:
            prev_web = "web" in prev["_folder"].parts
            cur_web = "web" in folder.parts
            if cur_web and not prev_web:
                by_id[wp_id] = meta
    items = list(by_id.values()) + orphans
    items.sort(key=lambda m: str(m.get("date") or ""), reverse=True)
    return items


def md(text: str) -> str:
    """Minimal Markdown → HTML (no third-party markdown package required)."""
    if not (text or "").strip():
        return ""
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    para: list[str] = []
    in_code = False
    code: list[str] = []

    def flush_para() -> None:
        nonlocal para
        if not para:
            return
        chunk = " ".join(para).strip()
        para = []
        if not chunk:
            return
        out.append("<p>" + inline_md(chunk) + "</p>")

    def inline_md(s: str) -> str:
        s = html.escape(s)
        s = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r'<img src="\2" alt="\1">', s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
        s = s.replace("\n", "<br>\n")
        return s

    for line in lines:
        if line.strip().startswith("```"):
            if in_code:
                out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
                code = []
                in_code = False
            else:
                flush_para()
                in_code = True
            continue
        if in_code:
            code.append(line)
            continue
        if not line.strip():
            flush_para()
            continue
        heading = re.match(r"^(#{1,4})\s+(.*)$", line)
        if heading:
            flush_para()
            level = len(heading.group(1))
            out.append(f"<h{level}>" + inline_md(heading.group(2).strip()) + f"</h{level}>")
            continue
        if re.match(r"^[-*]\s+", line):
            flush_para()
            item = re.sub(r"^[-*]\s+", "", line)
            out.append(f"<li>{inline_md(item)}</li>")
            continue
        para.append(line.strip())
    flush_para()
    if in_code and code:
        out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
    # Wrap consecutive <li> into <ul>
    wrapped: list[str] = []
    buf: list[str] = []
    for part in out:
        if part.startswith("<li>"):
            buf.append(part)
            continue
        if buf:
            wrapped.append("<ul>" + "".join(buf) + "</ul>")
            buf = []
        wrapped.append(part)
    if buf:
        wrapped.append("<ul>" + "".join(buf) + "</ul>")
    return "\n".join(wrapped)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def page_shell(title: str, body: str, root: str = "../") -> str:
    t = html.escape(title)
    return f"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{t}</title>
  <link rel="stylesheet" href="{root}assets/style.css" />
</head>
<body>
  <header>
    <nav>
      <a href="{root}index.html">mittendran-archiv</a>
      <a href="{root}map.html">Karte</a>
    </nav>
  </header>
  {body}
  <footer>
    Karte und Ortslisten zu Beiträgen auf
    <a href="https://www.mittendran.de/">mittendran.de</a>
    — nicht die offizielle mitteNdran-Seite.
  </footer>
</body>
</html>
"""


_MONTHS_DE = (
    "Jan",
    "Feb",
    "Mär",
    "Apr",
    "Mai",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Okt",
    "Nov",
    "Dez",
)


def _month_index(date: str) -> int | None:
    d = (date or "").strip()
    if len(d) < 4 or not d[:4].isdigit():
        return None
    y = int(d[:4])
    m = 1
    if len(d) >= 7 and d[5:7].isdigit():
        m = max(1, min(12, int(d[5:7])))
    return y * 12 + (m - 1)


def _fmt_month_de(idx: int) -> str:
    y = idx // 12
    m = idx % 12
    return f"{_MONTHS_DE[m]} {y}"


def excerpt_from_md(text: str, limit: int = 220) -> str:
    lines = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("!["):
            continue
        s = re.sub(r"!\[([^\]]*)\]\([^)]+\)", "", s)
        s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
        lines.append(s)
    blob = " ".join(lines)
    blob = re.sub(r"\s+", " ", blob).strip()
    if len(blob) <= limit:
        return blob
    cut = blob[: limit - 1].rsplit(" ", 1)[0]
    return (cut or blob[: limit - 1]).rstrip(".,;:") + "…"


def _median(values: list[float]) -> float:
    vals = sorted(values)
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2


def place_slug(name: str) -> str:
    s = (name or "").lower().strip()
    for src, dst in (
        ("ä", "ae"),
        ("ö", "oe"),
        ("ü", "ue"),
        ("ß", "ss"),
    ):
        s = s.replace(src, dst)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:80] or "ort"


# Broad Kiez areas → list pages, not map pins.
AREA_CANONICAL: dict[str, str] = {
    "gleisdreieck": "Gleisdreieck",
    "gleisdreieckpark": "Gleisdreieck",
    "park am gleisdreieck": "Gleisdreieck",
    "potsdamer straße": "Potsdamer Straße",
    "potsdamer strasse": "Potsdamer Straße",
    "potsdamer platz": "Potsdamer Platz",
}


def is_area_place(name: str) -> bool:
    return name.casefold().strip() in AREA_CANONICAL


def area_canonical_name(name: str) -> str:
    return AREA_CANONICAL[name.casefold().strip()]


def place_specificity(name: str) -> int:
    """Higher = more specific. Used so vague streets don't stack with POIs/addresses."""
    n = (name or "").strip()
    if re.search(r"\d", n):
        return 3  # address / numbered
    if re.search(
        r"(museum|villa|haus|kirche|bibliothek|pumpe|galerie|stiftung|"
        r"nachbarschaft|schule|spielplatz|bunker|diele|café|cafe)",
        n,
        re.I,
    ):
        return 2
    return 1  # bare street / square / other


def select_map_places(places: list[dict]) -> list[dict]:
    """Drop area names from the map; if specifics exist, drop bare streets."""
    usable = []
    for place in places:
        name = str(place.get("name") or "").strip()
        if not name or is_area_place(name):
            continue
        usable.append(place)
    if not usable:
        return []
    best = max(place_specificity(str(p.get("name") or "")) for p in usable)
    return [p for p in usable if place_specificity(str(p.get("name") or "")) >= best]


def _empty_bucket(name: str) -> dict:
    return {"place": name, "lats": [], "lons": [], "articles": {}}


def load_map_and_areas() -> tuple[list[dict], dict[str, dict]]:
    """Map pins (specific places) + area buckets (list pages, no pins)."""
    buckets: dict[str, dict] = {}
    areas: dict[str, dict] = {
        canon: _empty_bucket(canon) for canon in sorted(set(AREA_CANONICAL.values()))
    }

    for meta_path in sorted(ARTICLES.rglob("meta.yaml")):
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        if meta.get("sample"):
            continue
        origin = meta.get("text_origin") or ("wp" if meta.get("wp_post_id") else "ocr")
        if origin != "wp":
            continue
        source_url = str(meta.get("source_url") or "")
        if not source_url:
            continue
        slug = str(meta.get("slug") or meta_path.parent.name)
        title = str(meta.get("title") or slug)
        url = source_url
        list_url = source_url
        de_path = meta_path.parent / "de.md"
        de_text = de_path.read_text(encoding="utf-8") if de_path.exists() else ""
        description = str(meta.get("description") or "").strip()
        if not description and de_text:
            description = description_from_text(de_text)
        excerpt = description
        date = str(meta.get("date") or "")
        rubrik = str(meta.get("rubrik") or "")
        author = meta.get("author")
        stored_years = meta.get("about_years")
        if de_text:
            about_years = extract_about_years(de_text + "\n" + title, date)
        elif isinstance(stored_years, list):
            about_years = []
            for year in stored_years:
                try:
                    about_years.append(int(year))
                except (TypeError, ValueError):
                    continue
        else:
            about_years = extract_about_years(title, date)
        article = {
            "title": title,
            "url": url,
            "list_url": list_url,
            "excerpt": excerpt,
            "date": date,
            "about_years": about_years,
            "rubrik": rubrik,
            "author": "" if author is None else str(author).strip(),
            "source_url": source_url,
            "place_names": [],
        }

        confirmed = [
            p
            for p in (meta.get("places") or [])
            if p.get("status") == "confirmed"
            and p.get("lat") is not None
            and p.get("lon") is not None
            and str(p.get("name") or "").strip()
        ]
        seen_names: set[str] = set()
        for place in confirmed:
            raw = str(place.get("name") or "").strip()
            name = area_canonical_name(raw) if is_area_place(raw) else raw
            if name in seen_names:
                continue
            seen_names.add(name)
            article["place_names"].append(name)

        # Areas always collect (even when also mapped elsewhere).
        for place in confirmed:
            name = str(place.get("name") or "").strip()
            if not is_area_place(name):
                continue
            canon = area_canonical_name(name)
            bucket = areas[canon]
            bucket["lats"].append(float(place["lat"]))
            bucket["lons"].append(float(place["lon"]))
            bucket["articles"][url] = article

        for place in select_map_places(confirmed):
            name = str(place.get("name") or "").strip()
            key = name.casefold()
            bucket = buckets.get(key)
            if not bucket:
                bucket = _empty_bucket(name)
                buckets[key] = bucket
            bucket["lats"].append(float(place["lat"]))
            bucket["lons"].append(float(place["lon"]))
            bucket["articles"][url] = article

    def to_feature(bucket: dict, *, for_map: bool) -> dict:
        arts = sorted(
            bucket["articles"].values(),
            key=lambda a: a.get("date") or "",
            reverse=True,
        )
        # Map popup links are from map.html (docs root).
        map_skip = {"list_url", "place_names", "author"}
        map_arts = [
            {
                **{k: v for k, v in a.items() if k not in map_skip},
                "url": a["url"],
            }
            for a in arts
        ]
        slug = place_slug(bucket["place"])
        props = {
            "place": bucket["place"],
            "count": len(arts),
            "articles": map_arts if for_map else arts,
            "place_url": f"places/{slug}/",
            "place_slug": slug,
            "title": arts[0]["title"] if arts else bucket["place"],
            "url": arts[0]["url"] if arts else "",
            "excerpt": arts[0].get("excerpt", "") if arts else "",
            "date": arts[0].get("date", "") if arts else "",
        }
        lon = _median(bucket["lons"]) if bucket["lons"] else 13.3615
        lat = _median(bucket["lats"]) if bucket["lats"] else 52.5038
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props,
            "_articles_full": arts,  # for place pages (with list_url)
        }

    features = []
    for bucket in buckets.values():
        if not bucket["articles"]:
            continue
        features.append(to_feature(bucket, for_map=True))
    features.sort(key=lambda f: (-f["properties"]["count"], f["properties"]["place"]))

    area_features = {}
    for name, bucket in areas.items():
        if not bucket["articles"]:
            continue
        area_features[name] = to_feature(bucket, for_map=False)
    return features, area_features


def _year_of(date: str) -> str:
    s = (date or "").strip()
    return s[:4] if len(s) >= 4 and s[:4].isdigit() else ""


def _tally_places(arts: list[dict], keep) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for art in arts:
        seen: set[str] = set()
        for name in art.get("place_names") or []:
            if name in seen or not keep(name):
                continue
            seen.add(name)
            counts[name] = counts.get(name, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].casefold()))


PLACE_FILTER_JS = """
<script>
(function () {
  var buttons = Array.prototype.slice.call(
    document.querySelectorAll(".place-rubriks button[data-rubrik]")
  );
  var search = document.getElementById("place-search");
  if (!buttons.length && !search) return;
  var items = document.querySelectorAll(".place-page .cards li");
  var groups = document.querySelectorAll(".place-group");
  var empty = document.querySelector(".place-empty");
  var reset = document.getElementById("place-filter-reset");
  var active = {};
  buttons.forEach(function (btn) { active[btn.getAttribute("data-rubrik")] = true; });
  function hiddenCount() {
    return buttons.filter(function (btn) {
      return !active[btn.getAttribute("data-rubrik")];
    }).length;
  }
  function showingAll() {
    return !buttons.length || hiddenCount() === 0;
  }
  function paint() {
    var all = showingAll();
    buttons.forEach(function (btn) {
      var on = all || !!active[btn.getAttribute("data-rubrik")];
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      btn.title = all ? "Nur diese zeigen" : on ? "Abwählen" : "Hinzufügen";
    });
  }
  function query() {
    return search ? search.value.trim().toLocaleLowerCase("de") : "";
  }
  function apply() {
    var q = query();
    var shown = 0;
    items.forEach(function (li) {
      var name = li.getAttribute("data-rubrik") || "";
      var rubrikOn = !buttons.length || !name || !!active[name];
      var text = (li.textContent || "").toLocaleLowerCase("de");
      var on = rubrikOn && (!q || text.indexOf(q) !== -1);
      li.hidden = !on;
      if (on) shown += 1;
    });
    groups.forEach(function (group) {
      var visibleItems = group.querySelectorAll(".cards li:not([hidden])");
      group.hidden = visibleItems.length === 0;
      var count = group.querySelector(".place-year .n");
      if (count) count.textContent = String(visibleItems.length);
    });
    if (empty) {
      empty.hidden = shown !== 0;
      empty.textContent = q
        ? "Nichts in dieser Liste passt auf die Suche."
        : "Keine Beiträge für diese Rubriken.";
    }
    if (reset) reset.hidden = hiddenCount() === 0;
    paint();
  }
  buttons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var name = btn.getAttribute("data-rubrik");
      if (showingAll()) {
        buttons.forEach(function (other) {
          active[other.getAttribute("data-rubrik")] = false;
        });
        active[name] = true;
      } else if (active[name]) {
        active[name] = false;
        if (hiddenCount() === buttons.length) {
          buttons.forEach(function (other) {
            active[other.getAttribute("data-rubrik")] = true;
          });
        }
      } else {
        active[name] = true;
      }
      apply();
    });
  });
  if (reset) {
    reset.addEventListener("click", function () {
      buttons.forEach(function (btn) {
        active[btn.getAttribute("data-rubrik")] = true;
      });
      if (search) search.value = "";
      apply();
    });
  }
  if (search) search.addEventListener("input", apply);
  apply();
})();
</script>
"""


def write_place_page(
    dest: Path,
    place: str,
    arts: list[dict],
    *,
    kind: str,
    lat: float | None = None,
    lon: float | None = None,
    related: list[tuple[str, int]] | None = None,
) -> None:
    """kind: 'ort' | 'bereich'. arts use list_url when present."""
    n = len(arts)
    years = [y for a in arts if (y := _year_of(str(a.get("date") or "")))]
    if not years:
        span = ""
    elif min(years) == max(years):
        span = min(years)
    else:
        span = f"{min(years)}–{max(years)}"
    count_label = "1 Beitrag" if n == 1 else f"{n} Beiträge"
    stats = count_label + (f" · {span}" if span else "")

    rubrik_counts: dict[str, int] = {}
    for art in arts:
        rubrik = str(art.get("rubrik") or "").strip()
        if rubrik:
            rubrik_counts[rubrik] = rubrik_counts.get(rubrik, 0) + 1
    top = sorted(rubrik_counts.items(), key=lambda kv: (-kv[1], kv[0].casefold()))[:2]
    when = ""
    if span and "–" in span:
        when = f" zwischen {span}"
    elif span:
        when = f" im Jahr {span}"
    focus = ""
    if top:
        focus = " Am häufigsten " + " und ".join(f"{name} ({count})" for name, count in top) + "."
    if kind == "bereich":
        kicker = "Bereich · ohne Pin"
        note = (
            f"{place} ist ein Gebiet, kein einzelner Punkt. "
            f"{count_label}{when} nennen diesen Bereich.{focus} "
            "Die Liste sammelt sie alle. Straßen, Häuser und Plätze darin haben eigene Seiten."
        )
    else:
        kicker = "Ort auf der Karte"
        note = (
            f"{count_label}{when} nennen {place}.{focus} "
            "Ein Titel öffnet den Beitrag auf mittendran.de. "
            "Suche und Rubriken grenzen die Liste ein; neueste stehen oben."
        )

    osm = ""
    if kind == "ort" and lat is not None and lon is not None:
        href = (
            f"https://www.openstreetmap.org/?mlat={lat:.5f}&mlon={lon:.5f}"
            f"#map=17/{lat:.5f}/{lon:.5f}"
        )
        osm = (
            f'<p class="place-osm"><a href="{html.escape(href)}" rel="noopener">'
            "Lage auf OpenStreetMap</a></p>"
        )

    related = related or []
    shown_related, extra_related = related[:20], max(0, len(related) - 20)
    related_html = ""
    if shown_related:
        chips = []
        for name, count in shown_related:
            chips.append(
                f'<li><a href="../{html.escape(place_slug(name))}/">{html.escape(name)}'
                f' <span class="n">{count}</span></a></li>'
            )
        if kind == "bereich":
            heading = "Orte auf der Karte"
            blurb = "Dieselben Beiträge nennen auch diese Orte. Jeder hat einen eigenen Pin."
        else:
            heading = "Bereiche"
            blurb = "Größere Bereiche ohne eigenen Pin, die in denselben Beiträgen vorkommen."
        extra = ""
        if extra_related:
            extra = (
                f'<p class="meta">Weitere {extra_related} '
                f'{"Ort hat" if extra_related == 1 else "Orte haben"} eine eigene Seite.</p>'
            )
        related_html = (
            '<section class="place-related">'
            f"<h2>{heading}</h2>"
            f'<p class="meta">{blurb}</p>'
            f'<ul class="place-chips">{"".join(chips)}</ul>'
            f"{extra}</section>"
        )

    rubrik_order = [r for r in RUBRIK_COLORS if r in rubrik_counts]
    rubrik_order += sorted(set(rubrik_counts) - set(rubrik_order))
    rubrik_html = ""
    if rubrik_order:
        bits = []
        interactive = len(rubrik_order) > 1
        for rubrik in rubrik_order:
            color = RUBRIK_COLORS.get(rubrik, RUBRIK_FALLBACK)
            swatch = (
                f'<span class="place-swatch" style="background:{html.escape(color)}"></span>'
            )
            label = f"{html.escape(rubrik)} <span class=\"n\">{rubrik_counts[rubrik]}</span>"
            if interactive:
                bits.append(
                    f'<button type="button" data-rubrik="{html.escape(rubrik)}" '
                    f'aria-pressed="true" title="Nur diese zeigen">{swatch}{label}</button>'
                )
            else:
                bits.append(f'<span class="rubrik-static">{swatch}{label}</span>')
        reset = ""
        if interactive:
            reset = (
                '<button type="button" id="place-filter-reset" hidden>alle einblenden</button>'
            )
        rubrik_html = (
            f'<div class="place-rubriks" role="group" aria-label="Nach Rubrik filtern">'
            f'{"".join(bits)}{reset}</div>'
        )

    groups: dict[str, list[str]] = {}
    group_order: list[str] = []
    for art in arts:
        year = _year_of(str(art.get("date") or "")) or "ohne Jahr"
        if year not in groups:
            groups[year] = []
            group_order.append(year)
        href = html.escape(str(art.get("list_url") or art.get("url") or "#"))
        title = html.escape(str(art.get("title") or ""))
        rubrik = str(art.get("rubrik") or "").strip()
        color = RUBRIK_COLORS.get(rubrik, RUBRIK_FALLBACK)
        date = str(art.get("date") or "")
        author = str(art.get("author") or "").strip()
        if author.lower() in {"none", "null"}:
            author = ""
        excerpt = str(art.get("excerpt") or "").strip()
        meta_bits = []
        if date:
            meta_bits.append(html.escape(date))
        if rubrik:
            mix = f"color-mix(in srgb, {color} 28%, white)"
            meta_bits.append(
                f'<span class="place-tag" style="background:{html.escape(mix)}">'
                f"{html.escape(rubrik)}</span>"
            )
        if author:
            meta_bits.append(html.escape(author))
        excerpt_html = (
            f'<p class="place-excerpt">{html.escape(excerpt)}</p>' if excerpt else ""
        )
        groups[year].append(
            f'<li data-rubrik="{html.escape(rubrik)}">'
            f'<a href="{href}" rel="noopener">'
            f'<span class="place-bar" style="background:{html.escape(color)}"></span>'
            f'<span class="place-card-body"><strong>{title}</strong>'
            f'<div class="meta">{" · ".join(meta_bits)}</div>{excerpt_html}'
            f"</span></a></li>"
        )

    sections = []
    for year in group_order:
        items = groups[year]
        label = html.escape(year)
        sections.append(
            f'<section class="place-group">'
            f'<h2 class="place-year">{label} · <span class="n">{len(items)}</span></h2>'
            f'<ul class="cards">{"".join(items)}</ul></section>'
        )

    search_html = ""
    if n > 6:
        search_html = (
            '<label class="place-search">'
            '<span class="visually-hidden">In der Liste suchen</span>'
            '<input type="search" id="place-search" placeholder="Titel oder Stichwort" />'
            "</label>"
        )
    script = PLACE_FILTER_JS if (len(rubrik_order) > 1 or search_html) else ""
    body = f"""
<main class="place-page">
  <p class="place-back"><a href="../../map.html">← Karte</a></p>
  <p class="place-kicker">{html.escape(kicker)}</p>
  <h1>{html.escape(place)}</h1>
  <p class="place-stats">{html.escape(stats)}</p>
  <p class="lead">{html.escape(note)}</p>
  {osm}
  {related_html}
  {search_html}
  {rubrik_html}
  {''.join(sections)}
  <p class="place-empty" hidden>Keine Beiträge für diese Rubriken.</p>
  {script}
</main>
"""
    write(dest / "index.html", page_shell(place, body, root="../../"))


def build() -> None:
    if DOCS.exists():
        shutil.rmtree(DOCS)
    articles = load_publishable()
    write(DOCS / "assets" / "style.css", CSS)
    write(DOCS / "assets" / "map.js", MAP_JS)
    write(DOCS / ".nojekyll", "")

    cards = []
    for a in articles:
        slug = a["_slug"]
        title = a.get("title") or slug
        date = html.escape(str(a.get("date") or ""))
        rubrik = html.escape(str(a.get("rubrik") or ""))
        author = html.escape(str(a.get("author") or ""))
        source = html.escape(str(a.get("source_url") or ""))
        desc = html.escape(str(a.get("_description") or ""))
        desc_html = f'<div class="meta">{desc}</div>' if desc else ""
        meta_line = ", ".join(x for x in (date, rubrik, author) if x)
        cards.append(
            f'<li><a href="{source}" rel="noopener"><strong>{html.escape(str(title))}</strong>'
            f'<div class="meta">{meta_line}</div>{desc_html}</a></li>'
        )

    features, area_features = load_map_and_areas()

    # Place list pages (map pins + broad areas).
    pinned_names = {feat["properties"]["place"] for feat in features}
    for feat in features:
        props = feat["properties"]
        slug = props["place_slug"]
        arts = feat.pop("_articles_full", props["articles"])
        lon, lat = feat["geometry"]["coordinates"]
        related = _tally_places(
            arts,
            lambda name, current=props["place"]: name != current and is_area_place(name),
        )
        write_place_page(
            DOCS / "places" / slug,
            props["place"],
            arts,
            kind="ort",
            lat=float(lat),
            lon=float(lon),
            related=related,
        )
    area_chips = []
    for name in ("Gleisdreieck", "Potsdamer Straße", "Potsdamer Platz"):
        feat = area_features.get(name)
        if not feat:
            continue
        props = feat["properties"]
        arts = feat.pop("_articles_full", props["articles"])
        slug = props["place_slug"]
        related = _tally_places(
            arts,
            lambda place_name, current=name: (
                place_name != current
                and not is_area_place(place_name)
                and place_name in pinned_names
            ),
        )
        write_place_page(
            DOCS / "places" / slug,
            name,
            arts,
            kind="bereich",
            related=related,
        )
        area_chips.append(
            f'<a href="places/{html.escape(slug)}/">{html.escape(name)}'
            f' ({props["count"]})</a>'
        )

    # Strip internal helpers before serializing geojson.
    clean_features = []
    for feat in features:
        feat.pop("_articles_full", None)
        clean_features.append(feat)
    features = clean_features
    geo = {"type": "FeatureCollection", "features": features}
    payload = json.dumps(geo, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")

    area_line = ""
    if area_chips:
        area_line = (
            '<div class="map-areas" aria-label="Bereiche ohne Pin">'
            '<span class="lbl">Bereiche (Liste, kein Pin):</span>'
            + "".join(area_chips)
            + "</div>"
        )

    index_body = f"""
<main>
  <h1>mittendran-archiv</h1>
  <p class="lead">
    Karte und Ortslisten für Beiträge aus
    <a href="https://www.mittendran.de/">mittendran.de</a>
    (Tiergarten Süd). Titel, Datum, Rubrik und ein kurzer Hinweis —
    der Beitrag selbst bleibt auf mittendran.de.
    Bestätigte Orte liegen auf der <a href="map.html">Karte</a>.
  </p>
  <p class="meta">{len(articles)} Beiträge</p>
  {area_line}
  <ul class="cards">
    {''.join(cards) if cards else '<li>Noch keine Beiträge.</li>'}
  </ul>
</main>
"""
    write(DOCS / "index.html", page_shell("mittendran-archiv", index_body, root=""))

    used_rubriks: set[str] = set()
    for feat in features:
        for art in feat["properties"].get("articles") or []:
            r = str(art.get("rubrik") or "").strip()
            if r:
                used_rubriks.add(r)
    legend_order = [r for r in RUBRIK_COLORS if r in used_rubriks]
    legend_order += sorted(used_rubriks - set(legend_order))
    legend_bits = [
        '<span class="leg"><span class="sw multi" aria-hidden="true"></span> mehrere Beiträge</span>'
    ]
    for r in legend_order:
        color = RUBRIK_COLORS.get(r, RUBRIK_FALLBACK)
        legend_bits.append(
            f'<button type="button" class="leg" data-rubrik="{html.escape(r)}" aria-pressed="true" title="Nur diese zeigen">'
            f'<span class="sw" style="background:{html.escape(color)}"></span>'
            f"{html.escape(r)}</button>"
        )
    legend_bits.append(
        '<button type="button" class="leg leg-reset" id="map-filter-reset" hidden>alle einblenden</button>'
    )
    colors_js = json.dumps(RUBRIK_COLORS, ensure_ascii=False)
    month_indexes: list[int] = []
    for feat in features:
        for art in feat["properties"].get("articles") or []:
            mi = _month_index(str(art.get("date") or ""))
            if mi is not None:
                month_indexes.append(mi)
            for y in art.get("about_years") or []:
                try:
                    yi = int(y)
                except (TypeError, ValueError):
                    continue
                if 1700 <= yi <= 2100:
                    # Theme years are year-granular; use January of that year.
                    month_indexes.append(yi * 12)
    time_min = min(month_indexes) if month_indexes else 2022 * 12
    time_max = max(month_indexes) if month_indexes else 2026 * 12 + 9
    if time_max < time_min:
        time_max = time_min
    time_range_js = json.dumps({"min": time_min, "max": time_max})
    label_from = _fmt_month_de(time_min)
    label_to = _fmt_month_de(time_max)

    map_body = f"""
<main class="map-page">
  <div class="map-intro">
    <div class="map-bar">
      <h1>Karte</h1>
      <span class="map-count">{len(features)} Orte</span>
      {area_line}
      <p class="map-filter-status meta" id="map-filter-status" hidden></p>
      <button type="button" class="map-filters-toggle" id="map-filters-toggle" aria-expanded="false" aria-controls="map-panel">Filter</button>
    </div>
    <div id="map-panel" class="map-panel" hidden>
    <div class="map-years" role="group" aria-label="Zeitraum filtern">
      <span class="year-heading">Zeitraum</span>
      <span class="year-label" id="year-label">{html.escape(label_from)} – {html.escape(label_to)}</span>
      <p class="year-hint">Monat genau · Beitrag zählt, wenn er im Fenster erschienen ist und/oder Jahre aus der Vergangenheit im Text liegen.</p>
      <div class="year-modes">
        <label><input type="checkbox" id="time-publish" checked /> Erschienen (Publikation)</label>
        <label><input type="checkbox" id="time-about" checked /> Historisches Thema (Jahre im Text)</label>
      </div>
      <div class="year-track">
        <input type="range" id="year-from" min="{time_min}" max="{time_max}" value="{time_min}" step="1" aria-label="Zeitraum von" />
        <input type="range" id="year-to" min="{time_min}" max="{time_max}" value="{time_max}" step="1" aria-label="Zeitraum bis" />
      </div>
    </div>
    <div class="map-legend" role="group" aria-label="Rubriken filtern">{''.join(legend_bits)}</div>
    </div>
  </div>
  <div id="map"></div>
</main>
<style>{CSS}</style>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>window.RUBRIK_COLORS = {colors_js}; window.TIME_RANGE = {time_range_js}; window.ARCHIVE_PLACES = {payload};</script>
<script>{MAP_JS}</script>
"""
    write(DOCS / "map.html", page_shell("Karte", map_body, root=""))
    write(DOCS / "data" / "articles.geojson", json.dumps(geo, ensure_ascii=False, indent=2))
    print(
        f"Built {len(articles)} German WP articles, {len(features)} map places, "
        f"{len(area_features)} areas -> {DOCS}"
    )


if __name__ == "__main__":
    build()
