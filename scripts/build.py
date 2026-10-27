"""Build the public map site from article metadata. Full post text is not published."""
from __future__ import annotations

import html
import json
import math
import re
import shutil
import sys
import urllib.parse
from pathlib import Path

import yaml
from PIL import Image, ImageOps

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
body:has(.map-page) header { position: relative; z-index: 1000; }
.nav-drop { position: relative; display: inline-flex; align-items: center; gap: 0.05rem; }
.nav-drop-btn {
  font: inherit; color: #b9d4ff; background: transparent; border: 0;
  padding: 0.35rem 0; cursor: pointer; line-height: 1;
}
.nav-drop-btn:hover, .nav-drop-btn:focus-visible { color: #fff; outline: none; }
.nav-menu {
  display: none; position: absolute; top: calc(100% - 0.15rem); left: 0; z-index: 2;
  min-width: 8.5rem; margin: 0; padding: 0.3rem 0;
  background: #1c1c1c; border: 1px solid #3a3a3a; border-radius: 8px;
  box-shadow: 0 10px 28px rgba(0,0,0,.35);
}
.nav-drop:hover .nav-menu,
.nav-drop:focus-within .nav-menu,
.nav-drop.is-open .nav-menu { display: block; }
.nav-menu a { display: block; padding: 0.32rem 0.85rem; white-space: nowrap; }
.nav-menu a:hover { background: #2a2a2a; text-decoration: none; color: #fff; }
.nav-n { color: #9aa; }
main { max-width: 46rem; margin: 0 auto; padding: 1.2rem 1.1rem 3rem; }
main.map-page { max-width: none; width: 100%; margin: 0; padding: 0; align-self: stretch; }
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
.outing-jump, .slot-filter { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.8rem 0 0.2rem; padding: 0; list-style: none; }
.outing-jump a, .slot-filter button {
  display: inline-block; padding: 0.25rem 0.6rem; border-radius: 999px;
  border: 1px solid var(--line); background: var(--card); text-decoration: none;
  color: inherit; font: inherit; font-size: 0.92rem; cursor: pointer;
}
.outing-jump a:hover, .slot-filter button:hover { border-color: var(--accent); color: var(--accent); }
.slot-filter button[aria-pressed="true"] { background: var(--accent); color: #fff; border-color: var(--accent); }
.date-card[hidden], .outing-section[hidden] { display: none !important; }
.outing-who { margin: 1.6rem 0 0.2rem; font-size: 1.2rem; }
.outing-note { margin: 0 0 0.65rem; }
.date-list { display: grid; gap: 0.75rem; padding: 0; list-style: none; }
.date-card { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 0.85rem 1rem; }
.date-card h3 { margin: 0 0 0.2rem; font-size: 1.05rem; }
.date-stops { display: flex; flex-wrap: wrap; gap: 0.35rem; margin: 0.5rem 0; padding: 0; list-style: none; }
.date-stops a, .date-stops span { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 999px; border: 1px solid var(--line); background: var(--paper); font-size: 0.88rem; }
.date-stops a { color: var(--accent); text-decoration: none; }
.date-stops a:hover { border-color: var(--accent); }
.date-food { margin: 0.85rem 0 0.2rem; padding: 0.45rem 0 0.45rem 0.7rem; border-left: 3px solid var(--accent); }
.date-card .date-food { margin: 0.45rem 0 0.15rem; }
.hours-link { margin-left: 0.35rem; white-space: nowrap; }
.date-card p { margin: 0.35rem 0 0; }
.date-card h3 a { color: inherit; text-decoration: none; }
.date-card h3 a:hover { color: var(--accent); }
.date-map { height: 28rem; min-height: 280px; width: 100%; background: #d8d4ce; border: 1px solid var(--line); border-radius: 8px; margin: 0.6rem 0 0.4rem; }
.date-pin { background: transparent; border: none; }
.date-pin span {
  display: flex; align-items: center; justify-content: center;
  width: 1.7rem; height: 1.7rem; border-radius: 50%;
  background: var(--accent); color: #fff; font-weight: 700; font-size: 0.85rem;
  border: 2px solid #fff; box-shadow: 0 1px 3px rgba(0,0,0,.35);
}
.date-order { margin: 0.2rem 0 1rem; padding-left: 1.2rem; }
.date-order li { margin: 0.85rem 0; }
.date-card { overflow: hidden; padding: 0; }
.date-card-body { padding: 0.85rem 1rem 0.95rem; }
.date-banner { display: block; line-height: 0; }
.date-banner img {
  width: 100%; height: 12.5rem; object-fit: cover; object-position: center; display: block;
}
.date-photo { margin: 0.45rem 0 0.15rem; }
.date-photo a { display: block; }
.date-photo img {
  width: 100%; height: auto; border-radius: 8px; display: block; background: #d8d4ce;
}
.date-photo figcaption { margin: 0.28rem 0 0; color: var(--muted); font-size: 0.88rem; }
.date-photo figcaption a { color: inherit; }
.date-narrative p { max-width: 42rem; margin: 0 0 0.95rem; }
.date-sources { padding-left: 1.1rem; margin: 0.3rem 0 0; }
.date-sources li { margin: 0.28rem 0; }
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
.place-page .map-years { margin: 0.2rem 0 0.8rem; max-width: none; }
.place-group { scroll-margin-top: 4.2rem; }
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


SITE_AREAS: list[dict] = []


def area_nav(root: str) -> str:
    """One Orte menu. The options are the Bereiche."""
    if not SITE_AREAS:
        return ""
    links = []
    for area in SITE_AREAS:
        slug = html.escape(str(area["slug"]))
        name = html.escape(str(area["name"]))
        links.append(f'<a href="{root}places/{slug}/">{name}</a>')
    return (
        '<div class="nav-drop">'
        '<button type="button" class="nav-drop-btn" aria-expanded="false" aria-haspopup="true">Orte ▾</button>'
        f'<div class="nav-menu" role="group">{"".join(links)}</div>'
        "</div>"
    )


NAV_JS = """
<script>
document.querySelectorAll(".nav-drop-btn").forEach(function (btn) {
  btn.addEventListener("click", function (ev) {
    ev.preventDefault();
    ev.stopPropagation();
    var drop = btn.closest(".nav-drop");
    var open = !drop.classList.contains("is-open");
    document.querySelectorAll(".nav-drop.is-open").forEach(function (other) {
      other.classList.remove("is-open");
      var b = other.querySelector(".nav-drop-btn");
      if (b) b.setAttribute("aria-expanded", "false");
    });
    if (open) {
      drop.classList.add("is-open");
      btn.setAttribute("aria-expanded", "true");
    }
  });
});
document.addEventListener("click", function () {
  document.querySelectorAll(".nav-drop.is-open").forEach(function (drop) {
    drop.classList.remove("is-open");
    var b = drop.querySelector(".nav-drop-btn");
    if (b) b.setAttribute("aria-expanded", "false");
  });
});
</script>
"""


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
      <a href="{root}ausgehen.html">Ausgehen</a>
      {area_nav(root)}
    </nav>
  </header>
  {body}
  <footer>
    Karte und Ortslisten zu Beiträgen auf
    <a href="https://www.mittendran.de/">mittendran.de</a>
    — nicht die offizielle mitteNdran-Seite.
  </footer>
  {NAV_JS}
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
  if (!buttons.length && !search && !document.getElementById("year-from")) return;
  var items = document.querySelectorAll(".place-page .cards li");
  var groups = document.querySelectorAll(".place-group");
  var empty = document.querySelector(".place-empty");
  var reset = document.getElementById("place-filter-reset");
  var fromEl = document.getElementById("year-from");
  var toEl = document.getElementById("year-to");
  var pubEl = document.getElementById("time-publish");
  var aboutEl = document.getElementById("time-about");
  var yearLabel = document.getElementById("year-label");
  var MONTHS = ["Jan","Feb","Mär","Apr","Mai","Jun","Jul","Aug","Sep","Okt","Nov","Dez"];
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
  function fmtMonth(idx) {
    var y = Math.floor(idx / 12);
    var m = ((idx % 12) + 12) % 12;
    return MONTHS[m] + " " + y;
  }
  function monthRange() {
    if (!fromEl || !toEl) return null;
    var a = parseInt(fromEl.value, 10);
    var b = parseInt(toEl.value, 10);
    if (a > b) {
      var swap = a;
      a = b;
      b = swap;
    }
    return { from: a, to: b, min: parseInt(fromEl.min, 10), max: parseInt(fromEl.max, 10) };
  }
  function timeActive() {
    var r = monthRange();
    if (!r) return false;
    var pub = !pubEl || pubEl.checked;
    var about = !aboutEl || aboutEl.checked;
    return r.from > r.min || r.to < r.max || !pub || !about;
  }
  function timeOn(li) {
    var r = monthRange();
    if (!r) return true;
    var pubOn = pubEl ? pubEl.checked : true;
    var aboutOn = aboutEl ? aboutEl.checked : false;
    if (!pubOn && !aboutOn) return true;
    var ok = false;
    if (pubOn) {
      var d = li.getAttribute("data-date") || "";
      var y = parseInt(d.slice(0, 4), 10);
      var m = parseInt(d.slice(5, 7), 10);
      if (y) {
        if (!m || m < 1 || m > 12) m = 1;
        var idx = y * 12 + (m - 1);
        if (idx >= r.from && idx <= r.to) ok = true;
      }
    }
    if (aboutOn) {
      var fromY = Math.floor(r.from / 12);
      var toY = Math.floor(r.to / 12);
      (li.getAttribute("data-about") || "").split(/\\s+/).forEach(function (raw) {
        var yy = parseInt(raw, 10);
        if (yy >= fromY && yy <= toY) ok = true;
      });
    }
    return ok;
  }
  function paintYears() {
    var r = monthRange();
    if (yearLabel && r) yearLabel.textContent = fmtMonth(r.from) + " – " + fmtMonth(r.to);
  }
  function apply() {
    var q = query();
    var shown = 0;
    items.forEach(function (li) {
      var name = li.getAttribute("data-rubrik") || "";
      var rubrikOn = !buttons.length || !name || !!active[name];
      var text = (li.textContent || "").toLocaleLowerCase("de");
      var on = rubrikOn && timeOn(li) && (!q || text.indexOf(q) !== -1);
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
        : timeActive() && hiddenCount() === 0
          ? "Keine Beiträge in diesem Zeitraum."
          : "Keine Beiträge für diese Auswahl.";
    }
    if (reset) reset.hidden = hiddenCount() === 0 && !timeActive() && !q;
    paint();
    paintYears();
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
      if (fromEl) fromEl.value = fromEl.min;
      if (toEl) toEl.value = toEl.max;
      if (pubEl) pubEl.checked = true;
      if (aboutEl) aboutEl.checked = true;
      apply();
    });
  }
  function syncSlider() {
    if (!fromEl || !toEl) return;
    var a = parseInt(fromEl.value, 10);
    var b = parseInt(toEl.value, 10);
    if (a > b) {
      if (document.activeElement === fromEl) b = a;
      else a = b;
      fromEl.value = String(a);
      toEl.value = String(b);
    }
    apply();
  }
  function syncModes() {
    var pub = !pubEl || pubEl.checked;
    var about = !aboutEl || aboutEl.checked;
    if (!pub && !about && pubEl) pubEl.checked = true;
    apply();
  }
  if (fromEl) fromEl.addEventListener("input", syncSlider);
  if (toEl) toEl.addEventListener("input", syncSlider);
  if (pubEl) pubEl.addEventListener("change", syncModes);
  if (aboutEl) aboutEl.addEventListener("change", syncModes);
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
            "Rubrik und Zeitraum grenzen die Liste ein. "
            "Straßen, Häuser und Plätze darin haben eigene Seiten."
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
        about = []
        for year_n in art.get("about_years") or []:
            try:
                yi = int(year_n)
            except (TypeError, ValueError):
                continue
            if 1700 <= yi <= 2100:
                about.append(str(yi))
        groups[year].append(
            f'<li data-rubrik="{html.escape(rubrik)}" '
            f'data-date="{html.escape(date)}" '
            f'data-about="{" ".join(about)}">'
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
            f'<section class="place-group" id="y{label}">'
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
    time_html = ""
    if kind == "bereich":
        month_indexes: list[int] = []
        for art in arts:
            mi = _month_index(str(art.get("date") or ""))
            if mi is not None:
                month_indexes.append(mi)
            for year_n in art.get("about_years") or []:
                try:
                    yi = int(year_n)
                except (TypeError, ValueError):
                    continue
                if 1700 <= yi <= 2100:
                    month_indexes.append(yi * 12)
        if month_indexes and min(month_indexes) < max(month_indexes):
            time_min = min(month_indexes)
            time_max = max(month_indexes)
            time_html = (
                '<div class="map-years" role="group" aria-label="Zeitraum filtern">'
                '<span class="year-heading">Zeitraum</span>'
                f'<span class="year-label" id="year-label">{html.escape(_fmt_month_de(time_min))} – '
                f"{html.escape(_fmt_month_de(time_max))}</span>"
                '<p class="year-hint">Monat genau · Beitrag zählt, wenn er im Fenster erschienen ist '
                "und/oder Jahre aus der Vergangenheit im Text liegen.</p>"
                '<div class="year-modes">'
                '<label><input type="checkbox" id="time-publish" checked /> Erschienen (Publikation)</label>'
                '<label><input type="checkbox" id="time-about" checked /> Historisches Thema (Jahre im Text)</label>'
                "</div>"
                '<div class="year-track">'
                f'<input type="range" id="year-from" min="{time_min}" max="{time_max}" '
                f'value="{time_min}" step="1" aria-label="Zeitraum von" />'
                f'<input type="range" id="year-to" min="{time_min}" max="{time_max}" '
                f'value="{time_max}" step="1" aria-label="Zeitraum bis" />'
                "</div></div>"
            )
    script = PLACE_FILTER_JS if (len(rubrik_order) > 1 or search_html or time_html) else ""
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
  {time_html}
  {rubrik_html}
  {''.join(sections)}
  <p class="place-empty" hidden>Keine Beiträge für diese Rubriken.</p>
  {script}
</main>
"""
    write(dest / "index.html", page_shell(place, body, root="../../"))


OUTINGS: list[dict] = [
    {
        "id": "essen-dann-kultur",
        "label": "Essen, dann Kultur",
        "note": "Abends, etwa 15 Minuten zu Fuß von der Pohlstraße. Erst essen, dann ein Haus.",
        "ideas": [
            {
                "title": "Von der Pohlstraße ins Varieté",
                "when": "Wochentag abends",
                "slot": "weekday-evening",
                "shape": "Essen, dann das Varieté",
                "stops": ["Les Climats", "Pohlstraße", "Wintergarten Varieté"],
                "food": {
                    "place": "Les Climats",
                    "where": "Pohlstraße 75",
                    "line": "Die Weinbar in der Pohlstraße 75. Der Beitrag vom Mai 2023 kündigt Jazz Manouche an und ein Pop-up von Chloé.",
                },
                "text": "In der Nähe essen, dann zum Wintergarten. Der Abend endet mit der Vorstellung.",
                "id": "pohlstrasse-variete",
                "narrative": [
                    "Die Serie „Kiez mit Kind“ kommt im August 2024 an der oberen Pohlstraße vorbei und merkt, dass sie den Spielplatz dort schon oft übersehen hat: nach dem Einkauf, nach dem Gleisdreieck, nach dem Eis. Der Beitrag zählt, was dort steht. Eine große Sandfläche, ein mittelgroßer Rutschturm, den man über die Treppe oder über ein Netz nimmt, zwei Schaukeln und keine Babyschaukel, dazu eine kleine Steile zur Seilbahn. Für die Kleinsten ein zusammenhängendes Element mit zwei Treppen, kleiner Rutsche und Tunnel, umgeben von einer Art Zaun, an dem man sich entlanghangeln kann, und einem kleinen Dach. Drei Tischtennisplatten und ein Käfig mit Basketballkörben, ausdrücklich als Ausweich, wenn im Gleisdreieck die Platten besetzt sind. Mauern, die Erhöhungen des Sandkastens und Bänke im Schatten zur Straße. Zu essen gibt es vor Ort nichts. Der Platz liegt zwischen Flottwellstraße und Potsdamer Straße, und der Text sagt, viele Lokale unterschiedlicher Vorlieben seien schnell zu erreichen. Für einen ganzen Tag, schreibt die Serie, taugt er weniger. Für einen längeren Abstecher, eine Pause, eine Gruppe mit verschiedenen Spielinteressen schon.",
                    "Essen ist in den Beiträgen an diesem Abend die Weinbar Les Climats. Der Text vom 16. Mai 2023 setzt sie in die Pohlstraße 75. Am Mittwoch darauf, dem 17. Mai, ist Jazz Manouche mit Jam-Session angekündigt, Beginn 19 Uhr, Eintritt frei: Thomas Dekas an der Gitarre, Matthieu Baud am Bass, Max Eisinger an der Violine. Daneben ein Pop-up. Chloé ist für einige Tage in Berlin und kocht, unter anderem Pâté en croute, die Coronation-Quiche, Spargel, Ceviche, Brandenburger Reh, Crème Caramel. Die Termine in dem Beitrag sind der 18., 19., 24., 25. und 27. Mai, jeweils ab 19 Uhr, Reservierung erbeten. Ob das Haus an einem anderen Abend so kocht, steht dort nicht.",
                    "Der Wintergarten, Potsdamer Straße 96, ist in den Stücken von 2022 das Haus, das dreißig Jahre alt wird. Der Beitrag vom 25. September beschreibt die Nacht zum Sonntag: volles Haus, ein zweistündiges Programm aus Höhepunkten der Shows. Direktor Georg Strecker zeigt Jonglage, Zauberei, Chanson und Berliner Klamauk, auch ernste Töne, und erkennt Artisten und Musiker ausdrücklich an. Bürgermeisterin Franziska Giffey begrüßt die Gäste. Peter Schwenkow, einer der Gründer, erzählt Anekdoten aus den Anfangszeiten. Aus dem Club „Quartier Latin“ sei ein Varieté mit Sternenhimmel geworden, Leitspruch „Dem Staunen gewidmet“. Neben dem rot-goldenen Saal gibt es einen Außenbereich, an dem Abend eine Gourmetmeile. Die von Fiona Bennett gestalteten Toiletten, die „Unterwelten“, nennt Giffey die schönsten Berlins.",
                    "Das Hoffest davor, geschildert am 18. Juni 2022, öffnet Küche, Restaurant, Café und Hof. Genannt werden Artisten, Zauberer, Flying Dreams, der ukrainische Artist Jeka und Gewebeakrobatik mit Dasha und Vadym aus der Ukraine. Am Sonntag, dem 19. Juni, von 11 bis 16 Uhr, kostet der Eintritt nichts. Live-Musik, Artistik, Comedy, Jonglage und Zauberei, Künstler der Shows Flying Dreams und Golden Years, Absolventen der Staatlichen Schule für Artistik und des Kindercircus Cabuwazi, dazu ein Brunch. Die Adresse im Text: Potsdamer Straße 96, 10785 Berlin-Tiergarten.",
                    "Lia Hiltz und Paul Enck setzen im November 2022 denselben Namen in eine andere Straße. Das Jubiläum sei gerade gefeiert worden. Die Namensgebung deute aber auf das Varieté Wintergarten an der nordwestlichen Ecke von Dorotheenstraße und Friedrichstraße, benannt nach dem Wintergarten des 1881 eröffneten Central-Hotels. Der Spaziergang erzählt die Dorotheenstadt von der Kurfürstin Dorothee (1636–1689) her: Sumpfland vor dem Spandauer Tor, zuerst Handwerker, dann Hugenotten, Beamte und Höflinge. In der Dorotheenstraße, die bis 1822 die „Letzte Straße“ hieß, steht seit 1705 das Maison d’Orange. Der Schmied Einicke hat ab 1818 Werkstatt und Wohnhaus, nachdem er aus der Armee ausgetreten ist. Im 19. Jahrhundert werden die zweistöckigen Häuser zu Mietshäusern, um die Reichsgründung herum zu Hotels und Behörden. Maison d’Orange und Einicke verkaufen und ziehen über den Landwehrkanal in die Friedrichsvorstadt, das spätere Lützow-Viertel.",
                    "Das Varieté selbst bleibt von 1887 bis zur Zerstörung 1944 am selben Ort, mehrfach um- und ausgebaut. Dort werden frühe Filmvorführungen gezeigt, Bioscop genannt. Genannt werden der Zauberkünstler Harry Houdini (1874–1926) und die Chansons von Claire Waldoff (1884–1957) und Otto Reutter (1870–1931). Nach dem Krieg, von 1946 bis 1955, gibt es ein Wintergarten-Kino-Varieté in der Hasenheide. 1992 nimmt das Haus in der Potsdamer Straße den Betrieb auf. Enck wünscht ihm mindestens die 57 Jahre des ersten. Dass es am Ende wieder in die Nähe von Maison d’Orange und der Einickeschen Schmiede zog, sei nicht abzusehen gewesen.",
                ],
                "sources": [
                    ("Kiez mit Kind: Der geheime Spielplatz in der Pohlstraße", "https://www.mittendran.de/kiez-mit-kind-der-geheime-spielplatz-der-pohlstrasse/"),
                    ("Der Wintergarten feiert seinen 30. Geburtstag", "https://www.mittendran.de/der-wintergarten-feiert-seinen-30-geburtstag/"),
                    ("Eindrücke vom Hoffest des Wintergarten Varieté", "https://www.mittendran.de/eindruecke-vom-hoffest-des-wintergarten-variet/"),
                    ("Spaziergang mit Lia Hiltz und Paul Enck (14): Der Wintergarten", "https://www.mittendran.de/spaziergang-mit-lia-hiltz-und-paul-enck-14-der-wintergarten/"),
                    ("Jazz live und Gute Küche im „Les Climats“", "https://www.mittendran.de/jazz-live-und-gute-kueche-im-les-climats/"),
                ],
            },
            {
                "title": "Diele und Kulturforum",
                "when": "Wochentag abends",
                "slot": "weekday-evening",
                "shape": "Zwei Stopps",
                "stops": ["Joseph-Roth-Diele", "Kulturforum"],
                "food": {
                    "place": "Joseph-Roth-Diele",
                    "where": "Potsdamer Straße",
                    "line": "Das Glas vor dem Kulturforum.",
                },
                "text": "Ein Glas in der Joseph-Roth-Diele, danach ein Haus im Kulturforum, wenn noch geöffnet ist. Sonst ist der Weg dorthin der zweite Teil.",
                "id": "diele-kulturforum",
                "narrative": [
                    "Zwei Beiträge halten die Joseph-Roth-Diele fest, und sie tun das sehr verschieden. Am 1. Mai 2024 steht die Diele in einem größeren Gedenken. Am Wochenende vor dem 79. Jahrestag der Befreiung, dem 8. Mai 1945, also am 4. und 5. Mai, erinnert „Denk Mal Am Ort“ mit 27 Veranstaltungen an Wohn- und Wirkungsstätten von Berlinerinnen und Berlinern, die in der NS-Zeit verfolgt wurden oder Widerstand leisteten. 14 Nachkommen reisen aus Amerika, Großbritannien, Argentinien, Spanien, den Niederlanden, Frankreich und Israel an. Ausstellungen, Erzählungen, Vorträge, Gedenkspaziergänge, Rundgänge, Lesungen, eine Performance, akustische Stolpersteine, zwei Zeitzeugengespräche. Der Eintritt ist überall frei. An der Potsdamer Straße erinnert am Samstag um 14 Uhr eine szenische Lesung an Joseph Roth und Friederike Roth-Reichler. Roth, geboren 1894 im damaligen Österreich-Ungarn, Journalist, Chronist, Romanautor, Gegner des Nationalsozialismus, lebte von 1920 bis 1933 in Berlin und verließ das Land am Tag der Ernennung Hitlers zum Reichskanzler. Andrea Schultz und Günter Schmidt lesen vor der Diele, Potsdamer Straße 75. Im Nebenhaus haben der Schriftsteller und seine Frau einige Jahre gelebt. Die Initiative geht auf OPEN JEWISH HOMES zurück. Marie Rolshoven hat das Projekt 2016 nach Deutschland geholt und das Gedenken auf alle NS-Verfolgten erweitert. Im Januar 2024 erhält sie den Obermayer Award.",
                    "Ende Dezember 2024 ist dieselbe Diele geschlossen, Weihnachten und Silvester. Für das Schaufenster zur Potsdamer Straße hat sie ein kleines Sichtfenster in die sonst nicht einsehbare Scheibe gesetzt. Dahinter steht ein leeres Restaurant im Puppenstubenformat, dem Original nachgebildet, und ein Wunsch für die Feiertage.",
                    "Danach, in den Beiträgen, liegt das Kulturforum, und die Stücke behandeln es als unfertige Stadtlandschaft, nicht als einen einzelnen Abend. „Jung, aber Denkmal“, angekündigt für den 4. November 2025 in der Urania, Kleist-Saal, An der Urania 17, formuliert die Nachkriegsvorstellung so: locker gruppierte Großbauten, weite Freiflächen, eine offene, fließende Stadtlandschaft. Hans Scharouns Philharmonie und Staatsbibliothek und Ludwig Mies van der Rohes Neue Nationalgalerie gelten dort als Ikonen der Nachkriegsmoderne. Das Forum blieb unvollendet. Ein Konsensplan Kulturforum werde als Leitbild erarbeitet. Mit der Generalinstandsetzung der Staatsbibliothek stehe die nächste Großbaustelle an. Einführung: Christoph Rauhut, Landeskonservator. Auf dem Podium Petra Kahlfeldt, Katja Erke, Achim Bonte, Stephan Schütz und Jürgen Tietz, Moderation Verena Pfeiffer-Kloss. Veranstalter sind das Landesdenkmalamt und die Architektenkammer, mit der Urania.",
                    "Ein Jahr später, am 13. September 2026, wird dasselbe Gelände zum fünften Mal ein „Tag im Grünen“, drinnen und draußen, am Tag des offenen Denkmals, mit der Architektur als Schwerpunkt. Die Häuser und die St. Matthäus-Kirche laden ein. Marion Ackermann, Präsidentin der Stiftung Preußischer Kulturbesitz, sagt, der Tag zeige die Vielfalt der Einrichtungen und die Zusammenarbeit über Institutionsgrenzen hinweg. Das Kulturforumsticket kostet an dem Tag 12 Euro, ermäßigt 6, statt 22 und 11. Wer eine Jahreskarte hat, kann eine Person mitbringen. Kinder und Jugendliche bis 18 Jahre haben wie sonst freien Eintritt. Draußen steht Berlins längste Tafel auf dem Scharounplatz. Wer kein Picknick mitbringt, findet Essen auf dem Gelände. Mitglieder der Karajan-Akademie spielen Kurzkonzerte auf der mobilen Bühne VeloStage. Das Künstlerkollektiv Bündnis Feuer & Flamme stellt eine offene Küche hin. Junge Berliner Bands spielen auf dem Scharounplatz. Führungen, Workshops und Ausstellungen in Gemäldegalerie, Kunstgewerbemuseum, Kupferstichkabinett, Kunstbibliothek und Neuer Nationalgalerie. Das Staatliche Institut für Musikforschung führt durch das Musikinstrumenten-Museum und das Institutsgebäude und jodelt danach auf der Dachterrasse. Im Ibero-Amerikanischen Institut läuft „Quadrinhos! – Brasilianische Comics in Berlin“, dazu ein Konzert. Die Staatsbibliothek führt durch ihr Haus Potsdamer Straße. St. Matthäus bietet Turmführungen, Vorträge, Workshops und einen Gottesdienst unter freiem Himmel. Die Baumschule Kulturforum gestaltet den Scharounplatz mit. Das Wissenschaftszentrum öffnet sein denkmalgeschütztes Gebäude. Dazu Rundgänge: architekturhistorisch, Urban Sketching, Photo-Walk.",
                    "In derselben Woche ist der Garten der Berlin Art Week am Kulturforum zu Gast, zwischen Neuer Nationalgalerie und Gemäldegalerie. Der Beitrag vom 1. September 2026 beschreibt das 15-jährige Jubiläum der Art Week: fünf Tage, vom 9. bis 13. September, wird das Areal zwischen Potsdamer Platz, Tiergarten und Landwehrkanal zum Treffpunkt. Workshops, Performances, DJ-Sets, Talks, Screenings, kostenlos und offen. Ein LeseGarten zum Ankommen. Der Garten bündelt das Festival: Routen durch die Stadt, mehr als 100 Partner, mehr als 300 Veranstaltungen, darunter über 100 Ausstellungseröffnungen. Am 10. September laden 54 Galerien des Gallery Weekend von 18 bis 22 Uhr zur Gallery Night. Die Ausstellungen sind von Freitag bis Sonntag jeweils von 12 bis 18 Uhr geöffnet. Mittwoch die Eröffnungen in Museen und Kunstvereinen, Donnerstag die Positions Berlin Art Fair und die Gallery Night, Freitag die Featured Night, am Wochenende Privatsammlungen.",
                ],
                "sources": [
                    ("Denk Mal Am Ort – Joseph-Roth-Diele", "https://www.mittendran.de/denk-mal-ort-joseph-roth-diele/"),
                    ("Weihnachten und Silvester geschlossen: Die Joseph Roth Diele macht Ferien", "https://www.mittendran.de/weihnachten-und-silvester-geschlossen-die-joseph-roth-diele-macht-ferien/"),
                    ("Jung, aber Denkmal: Kulturforum", "https://www.mittendran.de/jung-aber-denkmal-kulturforum/"),
                    ("Ein Tag im Grünen im Kulturforum", "https://www.mittendran.de/ein-tag-im-gruenen-im-kulturforum/"),
                    ("Berlin Art Week vom 9.–13. September", "https://www.mittendran.de/berlin-art-week-vom-9-13-september/"),
                ],
            },
        ],
    },
    {
        "id": "spielplatz",
        "label": "Spielplatz",
        "note": "Nachmittags. Ein Spielplatz und ein Platz zum Sitzen.",
        "ideas": [
            {
                "title": "Nachmittag auf der Luiseninsel",
                "when": "Wochenende nachmittags",
                "slot": "weekend-afternoon",
                "shape": "Spielplatz, dann eine Bank",
                "stops": ["Spielplatz Luiseninsel", "Café ODOR"],
                "food": {
                    "place": "Café ODOR",
                    "where": "Kurfürstenstraße 21–22",
                    "line": "Kleines Café im Souterrain, nach dem Sand. Der Beitrag von 2023 beschreibt Sauerteigbrot und Brunch.",
                },
                "text": "Der Sandspielplatz hinter der Philharmonie. Wasser mitnehmen. Danach das Café ODOR.",
                "id": "luiseninsel",
                "narrative": [
                    "Zu diesem Spielplatz gibt es einen Beitrag, vom 15. Juli 2024, und er ist genau. Der Kiez sei an Parks privilegiert: im Norden der Tiergarten, im Osten der Gleisdreieckpark, dazwischen grüne Inseln. Der Spielplatz an der Luiseninsel sei einer der Lieblinge. Rutschen für alle Alter, Schaukeln, Klettergerüste für jede Größe und jeden Mut, im Sommer eine Wasserpumpe mit eigenem Matsch-Sand-Bereich und Bagger, Platz für Ballspiele, viel Sand. Für die Kleinsten ein eigener Bereich, eine breite Rutsche, auf der zwei oder drei Kinder nebeneinander sitzen, selten mit Stau. Den überdachten Start erreicht man über eine Schräge, eine Leiter oder einen beidseitig gesicherten Steg, der manchmal das Highlight des Tages ist. Zwei bodennahe Hangelseile, ein beweglicher Sandeimer an der Kette. Zwei Bänke mit Blick auf die Rutsche, und die zwei kleinen Stufen zum Spielplatz hinunter, an der langen Seite zum Sitzen und Mitbacken.",
                    "Die mittleren Kinder nehmen die mittlere Rutsche über eine Leiter oder über einen Kletterparcours, den der Text mit Sendungen wie „American Gladiator“ vergleicht. Die große Rutsche nur über den Turm. Eine Nestschaukel, an der man sich zur Rushhour anstellt oder sie teilt, daneben zwei normale Schaukeln, und eine Kletterspinne, von der aus man den ganzen Platz übersieht. Bis auf zwei Eingänge ein hüfthoher Zaun. Mitten im Tiergarten geben die Bäume auch im heißesten Sommer Schatten. Im Frühling und Herbst hält das Laub einzelne Tropfen auf. Im Winter lassen immergrüne Pflanzen den Platz nicht trostlos aussehen. Ein Großteil der Geräte sei in den letzten zehn Jahren neu gebaut worden. Einzig die Kletterspinne stehe seit den neunziger Jahren, „Zeugin“ von jahrzehntelangem Spiel direkt hinter der Philharmonie.",
                    "Das einzige Manko, das der Beitrag nennt: es gibt quasi keine Verpflegung in der Nähe oder auf dem Weg. Im Sommer Wasser einpacken, für einen langen Tag. Einige Bänke taugen zum Picknick. Familien legen Kindergeburtstage und das Ende einer Schnitzeljagd hierher.",
                    "Gegessen wird deshalb erst danach, und das steht in einem anderen Stück. Am 23. Januar 2023 beschreibt mittendran das Café ODOR: drei Stufen hinunter ins Souterrain der Kurfürstenstraße 21/22, ein kleiner Raum, ein paar Tische, Stühle, zwei Sofas, der Tresen im Raum dahinter. Überwiegend internationale, junge Gäste, freundliches Personal. Auf der kleinen Karte hausgemachtes Gebäck, Bananenbrot zu 3,50 Euro, vegetarischer Brunch. Das Sauerteigbrot mit Avocado, Kresse, Rucola, Sonnenblumenkernen, Pesto und auf Wunsch Rührei zu 12,50 Euro. Espresso macchiato 2,80, Café Latte 3,40, Tees Yuzu/Pflaume 3,50, Earl Grey Milk Tea 4,00, heiße Schokolade mit Marshmallows 3,50. Das Mineralwasser kommt mit einem Minzezweig. Die beiden Betreiberinnen kommen aus Korea und führen das Café seit Mitte Juli 2022. Geöffnet, in diesem Beitrag, Dienstag bis Samstag 11 bis 18 Uhr, Montag und Sonntag geschlossen. Ob das noch gilt, steht hier nicht.",
                ],
                "sources": [
                    ("Kiez mit Kind: Der Spielplatz Tiergarten Luiseninsel", "https://www.mittendran.de/kiez-mit-kind-der-spielplatz-tiergarten-luiseninsel/"),
                    ("Café ODOR", "https://www.mittendran.de/caf%c3%a9-odor/"),
                ],
            },
            {
                "title": "Specht-Spielplatz und Gleisdreieck",
                "when": "Wochenende nachmittags",
                "slot": "weekend-afternoon",
                "shape": "Ein Park, zwei Ecken",
                "stops": ["Specht-Spielplatz", "Café Jules", "Gleisdreieck"],
                "food": {
                    "place": "Café Jules",
                    "where": "Luckenwalder Straße 6b",
                    "line": "Unter der U-Bahn, am B-Part. Freitags steht dort der Thaimarkt Thai-Bridge.",
                },
                "text": "Am Specht-Spielplatz anfangen und im Gleisdreieck bleiben. Aufhören, wenn jemand müde ist.",
                "id": "specht-gleisdreieck",
                "narrative": [
                    "Der Park am Karlsbad, schreibt die Serie im Juli 2025, wird zwischen dem nahen Tiergarten und dem Gleisdreieck nebenan schnell übersehen. Vom Vorbeifahren kennt man ihn, wenn man nicht direkt daneben wohnt. Der Spielplatz darin sei vor nicht allzu vielen Jahren erneuert worden. Was man von der Potsdamer Straße zuerst sieht, ist nicht der Specht: Sandkasten, kleines Karussell und Wackeltier, trist am Beginn des Parks, das soll man hinter sich lassen. Danach ein Fußballkäfig in einer Hecke und fünf Tischtennisplatten, von denen meist mindestens eine frei sei, ein Geheimtipp, wenn das Gleisdreieck voll ist. Erst dann der Spielplatz, dessen Name frei erfunden ist, nach dem Specht, der an einem Eingang untätig am Holzpfahl sitzt.",
                    "Grün, viele Bäume, ganz umzäunt oder von Hecke umgeben. An den drei Eingängen öffnen sich die Schwingtore von innen nur durch Ziehen, nicht durch Drücken, damit kleinere Kinder nicht ausbüxen. Eine mittelgroße Rutsche, ein Kletterelement mit Sitznetz, eine Kleinkindwippe in einer Größe, die die Serie sonst nirgends gesehen hat, eine Netzschaukel, zwei Schaukeln, keine Babyschaukeln, genug Sand. Ein fest installierter Spielkreisel, dessen metallener Kegel einen immer leicht herunterrutschen lässt. Und ein Element, das der Text nur als „Skateboard-Simulator“ bezeichnen kann: beidseitig ein Skateboard auf einer halbkreisförmigen Schiene, mit Haltegriff. Es gab das schon vor der Erneuerung und wurde behalten. Die Standbretter fehlen seit geraumer Zeit und sind nicht wieder angebracht. Wer das Gerät von früher nicht kennt, versteht nicht, wie man damit umgeht. Außerhalb, auf der Wiese, Picknick, Ball, Federball. Bänke im Sonnen- und im Schattenbereich. An Mülleimern mangelt es nicht, neben jeder Bank. Trotzdem ist der Eingangsbereich etwas vermüllt, und auf der Wiese liegen Taschentücher, Verpackungen und Tüten, nicht extrem viel, aber sichtbar. Zu trinken und zu essen einpacken. Die nächsten Läden an der Flottwellstraße, an der Potsdamer Straße oder gegenüber am Potsdamer Platz.",
                    "Im Oktober 2025 ein kurzes Update. Der kleine, trostlose Platz beim Specht werde offensichtlich umgebaut. Er habe ein Dreh-Element und ein Spielhaus für die Kleinen, mit Klettern aufs Dach. Die Serie wünscht sich noch eine Babyschaukel, bei den Schaukeln sei Platz, und eine andere Idee für den Skateboard-Simulator. Ob die Wünsche den Umbau beeinflusst haben oder alles Zufall ist, lässt der Text offen.",
                    "Bleibt man im Gleisdreieck, beschreibt dieselbe Serie zwei weitere Plätze, und sie sind nicht austauschbar. Der Stangenwald, Januar 2026, liegt an der Kreuzberger Wiese, an der Treppe zur Möckernstraße, und ist fürs Klettern gebaut: quadratisches Netz, Spinnennetz, Leiternetze, Mattennetze, dazwischen Stämme und Seile zum Balancieren, eine Slackline ohne Handlauf. Hängematten zum Ausruhen. Für alle anderen zwei Schaukeln auf dem Platz, zwei weitere der hoch gebauten Modelle, die mehrfach im Park stehen, eine Teller- oder Reifenschaukel, eine Rutsche. Kein Sand. Eine Mattenwippe für bis zu acht Kinder. Bänke, die große Wiese nebenan, ein Kiosk direkt daneben mit Kaltgetränken, kleineren Backwaren und Eis, und eine Toilette. Wenig Schatten auf den Geräten, Bäume drumherum, an den Kiosktischen im Sommer Sonnenschirme. Etwas abseits, streng genommen nicht mehr zum Platz gehörend, drei Tischtennisplatten im Schatten. Sandburgen, schreibt der Text, soll man woanders bauen.",
                    "Das Kinderzimmer, Juli 2026, ist kein Geheimtipp, aber auf der Schöneberger Seite vielen unbekannt und bei schönem Wetter oft nicht so voll, weil es nicht an einem Hauptweg liegt und etwas abgelegen hinter dem Spektrum. Eine Pumpe mit doppeltem Wasserlauf und mehreren Becken, Staudämme, Kanäle, Boote, auch für die Kleinsten erreichbar. Nachteil: die Pumpe sitzt so nah am Holzbrett, dass man dort kein frisches Wasser zum Händewaschen oder in einen Eimer zapfen kann. Zwei große Sandflächen, drei Rutschen, Wippplatten und Wippkisten, drei klassische Schaukeln, eine Netzschaukel, eine Babyschaukel, ein Schaukelseil, Wände, Stangen und Netze. Holzverschläge, hinter denen man sich versteckt. Hörröhren für Absprachen über Distanz. Ein Holzzaun. Mehr als die Hälfte im Schatten der Silberpappeln, Tische und Bänke mitten auf dem Platz, weitere Bänke am Weg. Kleinere Äste und Mulch, Barfußlaufen ist eingeschränkt. Einpacken, weil in der Nähe nichts zu kaufen ist. Die nächsten Läden diesseits der Großbeerenstraße: die Cafés Parkgenuss am Stangenwald und TorEins.",
                    "Essen, an einem Freitag, kann der Thaimarkt sein. Der Beitrag vom 17. Juni 2025 sagt, „Thai-Bridge“ stehe zum dritten Mal wieder im Gleisdreieckpark am Café Jules und am B-Part, Luckenwalder Straße, unter der U-Bahn. Jeden Freitag von 12 bis 22 Uhr, an kleinen Ständen gebrutzelt und gebacken, exotische Getränke, draußen kleine Tische an der „Thai-Bridge“.",
                ],
                "sources": [
                    ("Kiez mit Kind: Specht-Spielplatz am Karlsbad", "https://www.mittendran.de/kiez-mit-kind-specht-spielplatz-karlsbad/"),
                    ("Kiez mit Kind: Specht-Spielplatz II – ein Update", "https://www.mittendran.de/update-specht-spielplatz/"),
                    ("Kiez mit Kind: Spielplatz Stangenwald", "https://www.mittendran.de/kiez-mit-kind-spielplatz-stangenwald/"),
                    ("Kiez mit Kind: Spielplatz Kinderzimmer", "https://www.mittendran.de/kiez-mit-kind-spielplatz-kinderzimmer/"),
                    ("Thaimarkt „Thai-Bridge“ im Gleisdreieckpark", "https://www.mittendran.de/thaimarkt-thai-bridge-im-gleisdreieckpark/"),
                ],
            },
        ],
    },
    {
        "id": "spaziergang",
        "label": "Spaziergang",
        "note": "Vormittags, eine Stunde ohne Umweg. Park, dann die Straße, dann essen.",
        "ideas": [
            {
                "title": "Park, dann die Straße nach Süden",
                "when": "Wochenende vormittags",
                "slot": "weekend-morning",
                "shape": "Eine Stunde, kein Zurück",
                "stops": ["Gleisdreieck", "Potsdamer Straße", "Sofram"],
                "food": {
                    "place": "Sofram",
                    "where": "Potsdamer Straße 137",
                    "line": "Türkisches Familienrestaurant am Südende der Straße. Die Geschwister betreiben es, die Küche ist täglich frisch.",
                },
                "text": "Den Park von Osten queren, auf die Potsdamer Straße kommen und einmal essen. Was abseits der Linie liegt, wartet auf den nächsten Vormittag.",
                "id": "park-potsdamer",
                "narrative": [
                    "Der Vormittag, den diese Seite vorschlägt, quert den Park und kommt auf die Potsdamer Straße. Was die Beiträge dazu wirklich beschreiben, sind drei verschiedene Dinge, nicht eine durchgehende Wegbeschreibung.",
                    "Im Gleisdreieck ist es im Juli 2026 der Spielplatz Kinderzimmer. Kein Geheimtipp, schreibt die Serie, aber auf der Schöneberger Seite vielen unbekannt und bei schönem Wetter oft nicht so voll wie andere, weil er nicht an einem Hauptweg liegt und etwas abgelegen hinter dem Spektrum. Für den Sommer eine Pumpe mit doppeltem Wasserlauf und mehreren Zwischenbecken, Staudämme, Kanäle, Boote, auch für die Kleinsten erreichbar. Die Pumpe sitzt so nah am Holzbrett, dass man dort kein frisches Wasser zum Händewaschen zapfen kann. Zwei große Sandflächen, drei Rutschen, Wippplatten, drei klassische Schaukeln, eine Netzschaukel, eine Babyschaukel, ein Schaukelseil, Klettern und Balancieren. Holzverschläge, hinter denen der Platz nicht ganz einsehbar ist, Hörröhren für Absprachen, ein Holzzaun. Mehr als die Hälfte im Schatten der Silberpappeln. Tische mitten auf dem Platz. Kleinere Äste und Mulch. Einpacken: die nächsten Läden diesseits der Großbeerenstraße sind Parkgenuss am Stangenwald und TorEins.",
                    "Auf der Straße zählt Paul Enck am 13. September 2025, während der Art Week, neun Galerien allein in den Mercator-Höfen, drei davon in der Villa 81B. Im Erdgeschoss die Galerie Reiter: die dänische Künstlerin Mette Homar, Jahrgang 1974, Gemälde nach Landschaftsfotografien ihrer Heimat Ahl, oft dieselbe Landschaft zu verschiedenen Tages- und Jahreszeiten, von fern an japanische Gemälde erinnernd. In der ersten Etage Thomas Schulte: Julian Irlinger, Jahrgang 1986, aus Erlangen, die Installation Sleepwalkers, Papierlaternen in Form von Architekturmodellhäusern, Grafik, ein Videofilm. Das Thema, im Beitrag zitiert: Nachkriegsmoderne als eine Linse, durch die sichtbar wird, wie kulturelle Erzählungen konstruiert werden, zirkulieren und als Instrumente des Lernens oder Glaubens aufgenommen werden. Im Obergeschoss Hua International: der chinesische Künstler Tong Kunniao, Jahrgang 1990, „After the Waves and the Dusk“, Phantasien einer Welt im Jahr 3000, in und auf einem Meer von Watte. Seine Ästhetik, wieder zitiert, sei emotionale Szenografie, Ritual statt Monument.",
                    "Essen ist das Sofram, Potsdamer Straße 137, in einem Beitrag von Peter Fabian vom 17. April 2023. Muzaffer Yavuz kommt aus Ankara. Fabian erzählt die Stadt über den Anker des Königs Midas, Ankyra. Yavuz selbst findet 1989 in Charlottenburg seinen Anker und nennt das erste Restaurant „Angora“, wie Ankara zu Lebzeiten seiner Eltern noch hieß. Zum Abschluss einen türkischen Mokka, und aus dem Kaffeesatz gelesen, mit optimistischem Blick. Die Tester lobten die anatolische Küche. Die Berliner Zeitung nannte sie „die ultimative Antwort auf den Döner“. 2004 zieht er nach Schöneberg in die Potsdamer Straße und nennt das Lokal Sofram, nach „Açil Sofram, Açil!“, der türkischen Entsprechung von „Tischlein deck dich“. Betrieben von den vier Familien der Geschwister. Küchenchefin ist seine Frau Seher, der Vorname heißt „Morgenröte“. Die Hausgerichte täglich frisch. Der Holzkohlengrill ist Männersache und kam 2022 mit der technischen Modernisierung und den neu gestalteten Gästeräumen ins Haus. „Yavuz“, schreibt Fabian, steht im Türkischen für „schön“ und „großzügig“. Warme Küche in diesem Beitrag Montag bis Samstag 10 bis 23 Uhr. Fabian selbst hat seit zwanzig Jahren Kunstverlag und Redaktionsbüro in der Potsdamer Straße 73. Was abseits dieser drei Stücke liegt, wartet.",
                ],
                "sources": [
                    ("Kiez mit Kind: Spielplatz Kinderzimmer", "https://www.mittendran.de/kiez-mit-kind-spielplatz-kinderzimmer/"),
                    ("Art Week Impressionen", "https://www.mittendran.de/art-week-impressions-3/"),
                    ("Sofram, das türkische Tischlein deck dich", "https://www.mittendran.de/sofram-das-tuerkische-tischlein-deck-dich-in-der-potse/"),
                ],
            },
            {
                "title": "Kanal bis zum Varieté",
                "when": "Wochenende vormittags",
                "slot": "weekend-morning",
                "shape": "Eine Stunde am Wasser",
                "stops": ["Landwehrkanal", "Potsdamer Brücke", "Irma la Douce", "Wintergarten Varieté"],
                "food": {
                    "place": "Irma la Douce",
                    "where": "Potsdamer Straße 102",
                    "line": "Neben dem Varieté. Im Michelin-Beitrag von 2023 hat das Haus einen Stern.",
                },
                "text": "Am Kanal zur Brücke, ins Wintergarten nur wenn eine Matinee wirklich läuft. Gegessen wird bei Irma la Douce, Tür an Tür.",
                "id": "kanal-variete",
                "narrative": [
                    "2025 jährt sich die Eröffnung des Landwehrkanals zum 175. Mal. Der kurze Beitrag vom 17. März sucht Zeitzeugen. Dirk Zeiske plant eine Veröffentlichung und bittet um Anekdoten und persönliche Erlebnisse, außerdem um Menschen, die noch im „Studentenbad“ am Kanal gebadet haben. Das Alte Studentenbad lag in Kreuzberg, Ratiborstraße 14, am Kanalknie gegenüber der Einmündung des Neuköllner Kanals, und wurde 1954 geschlossen. Der Text nennt eine Adresse, an die man sich melden kann. Hier steht sie nicht noch einmal.",
                    "Am Ufer, in den längeren Stücken, liegt die Potsdamer Brücke, und Paul Enck schreibt am 3. September 2022 ihre Synagoge als die erste südlich des Landwehrkanals in der Schöneberger Vorstadt, die bei der Eröffnung schon mehr als zehn Jahre zu Berlin gehörte. 1840 ist das Areal noch unbebaut, einzelne Häuser an der Potsdamer Chaussee, die Maulbeerplantage des Seidenfabrikanten Pollack nicht mehr in Betrieb. Die Baugeschichte der Ecke Potsdamer Straße 24 / Schöneberger Ufer 26 beginnt 1863. Besitzer des Café Boulevard ist der Konditor J. A. Rosenthal. Ein Streit unmittelbar vor Weihnachten 1866, gemeldet in der Staatsbürger-Zeitung, beendet offenbar seine Karriere dort. Der Bankier L. W. Niedlich übernimmt das Haus und stellt der Königlichen Landwirtschaftlichen Hochschule Ausstellungsräume. Im April 1868 eröffnet ein provisorisches Museum, im Juni auch im zweiten Stock. Der König, der spätere Kaiser Wilhelm I., kommt zur Eröffnung. Niedlich stirbt 1872. Die Erben verkaufen an den Tiergarten-Synagogen-Verein. Auf der Fläche des Ausstellungsraums entsteht die Synagoge, das Wohnhaus links davon wird neu gebaut. Eröffnung 1875/76.",
                    "Um 1896 beschließt der Magistrat, die Brücke erneut auszubauen, nach 1848 und 1861, diesmal als Doppelbrücke. Viktoria-Luise-Straße und alte Potsdamer Straße treffen sich auf der Brücke. In der Mitte das Dreieck, das der Berliner Volksmund „Spucknapf“ nennt. Straße und Bürgersteige werden höher gelegt. Am Loeser-&-Wolff-Haus, das Enck am 28. Juli 2022 fotografiert, liegen die Eingänge noch heute fast einen Meter tiefer. 1897 waren es zwischen 22 und 85 Zentimetern. Die Baupolizei verlangt massive Treppen, eiserne Gitter, Entwässerung an die Kanalisation, auf Kosten der Eigentümer. Der Verein wehrt sich. Die Stadt hat ohne die Anlieger erhöht und einen Streifen Vorgarten eingezogen, bis zu vier Meter Breite auf etwa zwanzig Metern an der Potsdamer Straße und einen halben Meter auf vierzig Metern am Schöneberger Ufer, zusammen mehr als hundert Quadratmeter. Die Kanzlei Dr. Samter, Mohrenstraße 65, fordert 89.928,20 Reichsmark. Im Vergleich zahlt die Stadt 50.000 Reichsmark und übernimmt die Sicherungen, die zuvor auf etwa 10.000 geschätzt waren. Enck rechnet die 50.000 auf etwa 350.000 Euro Kaufkraft um.",
                    "Warum „Tempel der Millionäre“? Enck prüft die Akten und das, was vermutlich mit dem letzten Kassenwart nach Jerusalem ins Israelische Staatsarchiv gekommen ist: die Satzung von 1905, eine undatierte Mitgliederliste. Das Kassenbuch der Jahre 1926/27 stand ihm nicht zur Verfügung. Allein die Digitalisierung hätte 200 Euro gekostet. Die ersten Vorsitzenden, im Adressbuch, sind ein Rentier Oppenheim, ein Kommerzienrat Lachmann, ein Bankier Bamberger, ein Kaufmann Unger. Das klinge noch nicht nach Millionären. 1896 entsteht in der Lützowstraße 16 eine neue, große Synagoge der liberalen Gemeinde, bis zu 2000 Personen. Die an der Brücke bleibt, weil ihr Ritus ein anderer ist: konservativ, ohne Orgel, mit getrennten Sitzen, hebräisch statt deutsch. Die Liste, vermutlich um 1910, hat 135 Namen. Hinter jedem kann eine Familie stehen, Enck rechnet mit 400 bis 500 Personen. Weniger als die Hälfte wohnt im Lützow-Viertel. Das Einzugsgebiet reicht ins Scheunenviertel, in die Friedrichstadt, ins Hansaviertel, nach Schöneberg, Charlottenburg, Wilmersdorf, bis Dahlem. Von 104 Berufen, die er ermitteln kann: etwa gleich viele Bankiers und Kaufleute, dazu Rentiers, Fabrikanten, Juristen, Mediziner, Direktoren, Verleger, Akademiker, ein Ingenieur, ein Künstler, ein Juwelier. Der Beiname mag auf einige zugetroffen haben, schreibt er, sicher nicht auf alle. 1928 verkauft der Verein das Grundstück an Lucie Sommergut, geschiedene Regierungsrätin, geborene Loeser, für 1,2 Millionen Reichsmark. Dort entsteht die Zigarrenfabrik Loeser & Wolff. Das Haus steht noch und ist denkmalgeschützt. Aus dem Millionärstempel, schließt Enck, sei wenigstens ein Millionentempel geworden.",
                    "Ralf Hausding, Gastbeitrag vom 19. Juni 2026, erinnert sich an dieselbe Brücke aus der Nachkriegskindheit. Er ist in Tiergarten nah am Potsdamer Platz aufgewachsen. Nach dem Abriss seines Wohnhauses zieht es ihn nach Spandau. Heute bietet er Stadtrundgänge an. Auf dem Grundstück Potsdamer Straße 39, früher 123b, stand bis in die letzten Kriegsjahre ein Wohn- und Geschäftshaus zwischen Schöneberger Ufer und Am Karlsbad: das Weinrestaurant Lanzsch und Co., ein Zigarettengeschäft, die Kneipe „Zur Potsdamer Brücke“, die Schreibwarenhandlung Vincenz Sala. Sala hat den Laden mit dem charakteristischen Schriftzug nach dem Krieg in der Potsdamer Straße 97. Auf dem Dach Werbung für Suchard. In den zwanziger Jahren wird die Gründerzeitfassade abgeschlagen und glatt verputzt, Neue Sachlichkeit. Das Haus wird zerstört, das Grundstück vor 1950 abgeräumt. Die Firma G. & R. Weise, Autobedarf und vor allem Reifen, baut einen schmucklosen Flachbau. Ab etwa 1961 arbeitet Hausdings Mutter dort. Er ist ungefähr neun und schaut beim Räderwechsel zu, bei der Reparatur auch von LKW-Reifen, beim Auswuchten. Abends, hinter der Ladentür, der Verkehr auf der Brücke, noch ohne Ampel. Zwei Polizisten im Berufsverkehr, abends die Vorfahrtsregel. Er zerkratzt vor Aufregung den silbernen Alarmstreifen an der Scheibe. Im Februar 1962 drückt ein Sturm eine Scheibe zur Straße Am Karlsbad ein. Heute liegt dort der kleine Park zwischen Schöneberger Ufer und Am Karlsbad. Die Straße, schreibt er, ist nicht nach dem Kurort benannt, sondern nach einem Karl, der auf diesem Gelände sein Bad hatte.",
                    "Der Wintergarten am Ende der Stunde ist der Saal, den der Beitrag vom 25. September 2022 an der Potsdamer Straße seit dreißig Jahren als Varieté beschreibt, hervorgegangen aus dem Club „Quartier Latin“, mit Sternenhimmel und dem Satz „Dem Staunen gewidmet“. Hinein nur, wenn eine Matinee wirklich läuft. Das steht in keinem dieser Texte. Gegessen wird nebenan, und das steht im Michelin-Beitrag vom 15. April 2023: Irma la Douce, Potsdamer Straße 102, Küchenchef Michael Schulz, hat seinen Stern behalten. Ein Stern, zitiert der Text Wikipedia, heißt „eine Küche voller Finesse, einen Stopp wert“.",
                ],
                "sources": [
                    ("Zeitzeugen gesucht: Der Landwehrkanal wird 175 Jahre alt", "https://www.mittendran.de/zeitzeugen-gesucht-der-landwehrkanal-wird-175-jahre-alt/"),
                    ("Jüdische Geschichte in Tiergarten-Süd (3): Die Synagoge an der Potsdamer Brücke", "https://www.mittendran.de/juedische-geschichte-tiergarten-sued-3-die-synagoge-der-potsdamer-bruecke/"),
                    ("An der Potsdamer Brücke", "https://www.mittendran.de/der-potsdamer-bruecke/"),
                    ("Der Wintergarten feiert seinen 30. Geburtstag", "https://www.mittendran.de/der-wintergarten-feiert-seinen-30-geburtstag/"),
                    ("Der Guide Michelin 2023 hat gesprochen", "https://www.mittendran.de/der-guide-michelin-2023-hat-gesprochen/"),
                ],
            },
        ],
    },
    {
        "id": "ein-haus",
        "label": "Ein Haus, dann sitzen",
        "note": "Nachmittags, höchstens zehn Minuten zwischen den Türen. Kultur, dann Kaffee.",
        "ideas": [
            {
                "title": "Ein Museum, dann Kaffee",
                "when": "Wochentag nachmittags",
                "slot": "weekday-afternoon",
                "shape": "Zehn Minuten zwischen den Türen",
                "stops": ["Neue Nationalgalerie", "Matthäikirchplatz", "Facil"],
                "food": {
                    "place": "Facil",
                    "where": "Potsdamer Straße 3",
                    "line": "Zwei Sterne im Mandala-Hotel, der Beitrag vom April 2023. Ob der Tisch an dem Tag frei ist, steht auf der Seite des Hauses.",
                },
                "text": "Die Neue Nationalgalerie, danach auf dem Matthäikirchplatz sitzen. Kein zweites Museum.",
                "id": "museum-kaffee",
                "narrative": [
                    "Die Neue Nationalgalerie ist in den Beiträgen ein Haus mit einem Programm, und die Programme widersprechen sich nicht, sie liegen in verschiedenen Monaten.",
                    "Am 7. April 2023: „100 Werke für Berlin“, von Gerhard Richter ausgesucht, im Untergeschoss, auf unbestimmte Zeit, denn eines Tages sollen sie im neuen Museum der Moderne in der Nachbarschaft ihren Platz finden. Richter, geboren 1932, über sechs Jahrzehnte so vielfältig, dass man meinen könnte, fünf Künstler würden gezeigt. Hinter dem Bild „Tante Marianne“ verberge sich ein Familiendrama. Tickets online. Geöffnet Dienstag und Mittwoch 10 bis 18, Donnerstag 10 bis 20, Freitag bis Sonntag und feiertags 10 bis 18, montags zu. Jeden ersten Donnerstag im Monat von 16 bis 20 Uhr Eintritt frei. Sonst 14 Euro, ermäßigt 7.",
                    "Drei Monate früher, am 3. Januar 2023, eine andere Regelung, und sie ist als Erweiterung geschrieben. Ab Donnerstag, dem 5. Januar, ist der Eintritt im Rahmen von Volkswagen Art4All jeden Donnerstag von 16 bis 20 Uhr frei: Sonderausstellungen in der oberen Halle, Sammlung im Untergeschoss, Skulpturengarten, ohne Ticket. Anlass ist der Zuspruch für den monatlichen freien Eintritt seit dem 16. Dezember 2021. Live Speaker bieten Gespräche und Kurzführungen. Genannt werden Sonderausstellungen von Monica Bonvicini und, noch bis zum 8. Januar, Sascha Wiederhold. Klaus Biesenbach, Direktor, wird zitiert: Kunst sei ein essentielles Bedürfnis, der freie Eintritt stelle sicher, dass allen ein Weg offenstehe. Volkswagen Art4All seit 2018, mit der Nationalgalerie entwickelt, auch am Hamburger Bahnhof und im Kunstmuseum Wolfsburg. In dem Jahr erstmals Teil einer Ausstellungspartnerschaft: 14.000 Schülerinnen und Schüler besuchten mit solchen Tickets die documenta fifteen. Ob die Regel über diesen Winter hinaus gilt, sagt der Beitrag nicht.",
                    "Am 13. Juli 2023 steht vor dem Haus, schon im Titel des Stücks, eine Rose. Die Ausstellung heißt „Isa Genzken. 75/75“, zum 75. Geburtstag, 75 Skulpturen aus allen Phasen von den siebziger Jahren bis heute. Genannt werden das zehn Meter lange „Blau-grau-gelbes Hyperbolo ‚MBB‘“ (1981), „Atelier“ (1990), „Venedig“ (1993), „Nofretete – Das Original“ (2012), „Schauspieler“ (2013), und die Arbeit „Pink Rose 2016/2023“. Die Arbeiten sollen eher als bewegte Bilder fungieren als als Skulpturen: aus jedem Blickwinkel ein neues Bild, nichts starr, nichts zweidimensional, filmisch. Ort: Potsdamer Straße 50. Dauer: 13. Juli bis 27. November 2023. Dieselben Öffnungszeiten, Montag geschlossen. Quelle, schreibt der Beitrag, die Neue Nationalgalerie.",
                    "Der Matthäikirchplatz daneben ist der Ort, an dem St. Matthäus von Mai 2019 an den Künstlergarten „Das dritte Land“ hatte. Der Beitrag vom 5. Juli 2022 fragt, wo er geblieben ist. Seok Hyun Han und Seung Hwoe Kim, im Text auch Han Seok Hyun und Kim Seung Hwoe, hatten im 30. Jahr des Mauerfalls einen Grenzgarten gebaut, in dem Pflanzen aus Nord- und Südkorea gemeinsam wachsen. Das Baekdu-Daegan-Gebirge, das beide Koreas verbindet, stand Pate für die schwarzen Basaltformationen. 45 Arten weißblühender Wildblumen wurden nach Berlin gebracht. Bis November 2019 Performances, Konzerte, Diskussionen. Ein utopisches Biotop, das den Grenzkonflikt temporär künstlerisch überwindet, nicht weit vom ehemaligen Verlauf der Mauer, so wie der Grenzstreifen selbst ein Drittes zwischen Ost und West war. Über 160 Menschen aus der ganzen Welt unterstützten den Garten. Eröffnet am 23. Mai um 19 Uhr, auf 1.000 Quadratmetern, in Anwesenheit der Künstler. Geplant bis zum 15. November 2019, gestanden bis ins Frühjahr des Jahres, in dem der Beitrag erscheint. Dann ist er verschwunden. Auf dem alten Matthäikirchplatz steht noch die Edelstahlskulptur „Altar“ von Volkmar Haase. Die Tafel am Garten lud ein, über Grenzen und ihre Überwindung nachzudenken, und verwies für mehr in die Kirche. Am 24. September 2021, in der Langen Nacht der Museen, ein Vortrag in der Kunsthalle Erfurt. Anlass waren Planungen, den Garten zur Feier des Tags der Deutschen Einheit am 3. Oktober 2022 in Erfurt zu zeigen. Ob das geschehen ist, steht in dem Stück nicht.",
                    "Gegessen wird im Facil. Am 4. April 2023 werden in Karlsruhe die Michelin-Sterne bekanntgegeben. Für Tiergarten-Süd bestätigt „Facil“, Küchenchef Michael Kempf, Potsdamer Straße 3, seine zwei Sterne. Zwei Sterne, zitiert der Beitrag Wikipedia: „eine Spitzenküche, einen Umweg wert“. Ob an dem Nachmittag ein Tisch frei ist, steht auf der Seite des Hauses, nicht hier.",
                ],
                "sources": [
                    ("An Ostern ins Museum: Gerhard Richter in der Neuen Nationalgalerie", "https://www.mittendran.de/ostern-ins-museum-gerhard-richter-der-neuen-nationalgalerie/"),
                    ("Eine Rose vor der Neuen Nationalgalerie", "https://www.mittendran.de/eine-rose-vor-der-neuen-nationalgalerie/"),
                    ("Donnerstags freier Eintritt", "https://www.mittendran.de/donnerstags-freier-eintritt/"),
                    ("Wo ist „Das dritte Land“ geblieben?", "https://www.mittendran.de/wo-ist-das-dritte-land-geblieben/"),
                    ("Der Guide Michelin 2023 hat gesprochen", "https://www.mittendran.de/der-guide-michelin-2023-hat-gesprochen/"),
                ],
            },
            {
                "title": "Philharmonie und der Platz davor",
                "when": "Wochentag nachmittags",
                "slot": "weekday-afternoon",
                "shape": "Das Haus und der Platz",
                "stops": ["Philharmonie", "Kulturforum", "Golvet"],
                "food": {
                    "place": "Golvet",
                    "where": "Potsdamer Straße 58",
                    "line": "Im Michelin-Beitrag von 2023 hat Golvet einen Stern. Küche: Jonas Zörner.",
                },
                "text": "Den Saal von außen ansehen, oder hinein, wenn eine offene Probe ist. Danach Golvet.",
                "id": "philharmonie-platz",
                "narrative": [
                    "Der Saal von außen, oder hinein, wenn eine offene Probe ist. Das sagen die Beiträge nicht. Sie sagen, was mit dem Platz vor dem Haus geschieht, und was das Mahnmal nebenan zu erklären hat.",
                    "Am 17. November 2023: die vor ein paar Jahren verlegten Steine am Scharounplatz, auf dem Streifen entlang der Philharmonie, sind abgesackt. Der Untergrund wird erneuert, die Steine danach neu verlegt. Einige der Bäume in Kübeln aus der „Baumschule Kulturforum“ wurden auf das grüne Rondell der St. Matthäus-Kirche umgesetzt.",
                    "Wie die Bäume dort hingekommen sind, steht im Stück vom 28. August 2023. Junge Bäume in Pflanztöpfen besiedeln das Gelände, das oft als Steinwüste bezeichnet wird. Klaus Biesenbach, Direktor der Neuen Nationalgalerie und Initiator, hat die Rauminstallation mit dem atelier le balto erarbeitet und kuratiert. Projektträgerin ist die Stiftung St. Matthäus. Seit Ende Mai 2023 stehen heimische und nicht heimische Arten auf der Piazzetta vor dem Café Estrade, auf dem Scharounplatz, und demnächst auf dem Rondell. Auf der Piazzetta unter einer Pergola, an Gewächshäuser angelehnt, die im nächsten Jahr begrünt werden soll. Bambusstäbe gegen den Wind. Sitzgelegenheiten unter den Bäumen. Die Bäume kommen liegend auf dem Lkw, werden in Töpfe gehoben, die Töpfe mit Substrat gefüllt. Ein Topf wiegt bis zu einer halben Tonne. Jutesäcke halten das Substrat feucht. Ein Gartenbaubetrieb gießt. Der Scharounplatz bekommt ein Weiden-Carré aus 25 Bäumen in Pflanztrögen, dazu Bänke. Die Installation kann jederzeit kostenfrei besucht werden. Am Dienstag der Woche, in der der Beitrag erscheint, kommen noch 37 Bäume für den Scharounplatz, Ende der Woche 18 weitere für die Piazzetta. Schilder mit den Arten sind in Arbeit. Für die Art Week vom 13. bis 17. September 2023 soll vor der Neuen Nationalgalerie eine weitere, ebenfalls temporäre Baumschule entstehen. Am Sonntag, dem 3. September 2023, ab 11 Uhr, „Ein Tag im Grünen“, Eintritt frei, eine Tafel unter freiem Himmel. Der Text fragt, wie es wäre, wenn das Kulturforum immer grün wäre, und zählt auf, was Bäume tun: CO2 binden, Schadstoffe filtern, Sauerstoff, Kühle, Schatten, Raum und Nahrung für Tiere.",
                    "Neben der Philharmonie bleibt der Spaziergang von Lia Hiltz und Paul Enck am 3. Februar 2023 am Mahnmal für die Ermordeten der „Euthanasie“ stehen, und er besteht auf den Anführungszeichen. Euthanasie heiße schöner oder guter Tod. Was die Nationalsozialisten organisiert hatten, war die systematische Tötung von mehr als 300.000 vor allem geistig behinderten Menschen in Heimen und Kliniken in ganz Europa. Das Mahnmal heißt auch T4-Denkmal, nach der Adresse Tiergartenstraße 4, dem Haus, in dem dieser Mord geplant wurde. Das Programm begann 1933 in Brandenburg-Görden und dauerte bis zum Kriegsende. Die Tiergartenstraße war vom mittleren 18. Jahrhundert bis zum Krieg ein Wohnviertel der Reichen, vor allem Militärs und Unternehmer. An dieser Adresse ab 1750 ein Oberstleutnant von Kleist, dann der Bankdirektor Reichert, der Bankier Weißbach, zuletzt der Textilfabrikant Georg Liebermann (1844–1926). 1935 mietet die NSDAP die Villa von den Kindern des Fabrikanten, zusammen mit einem Nachbarhaus. 1940 wird sie „arisiert“: die jüdischen Besitzer enteignet, das Haus unter Marktwert an das Reichsfinanzministerium verkauft. Enck fragt, ob diese Morde mit den Judenmorden in den Lagern zu tun haben. Die Forschung, schreibt er, sagt ja: die Tötungen galten als Testfälle und wurden in die Lager exportiert, und sie wurden anhand der Erfahrung dort weiter rationalisiert. In den angeschlossenen Gebieten, Österreich, Elsass-Lothringen, Böhmen und Mähren, Warthegau, ist die „Euthanasie“ belegt, auch Erschießungen von Patienten in Polen und der Sowjetunion, nicht jedoch in Holland, Belgien und Frankreich. Für Italien und Spanien sagt die Forschung nein. Kirchliche Proteste in Deutschland um 1942 haben das Morden nicht verhindert, aber gebremst. Es ging in aller Stille weiter. Für die Menschen in den Heimen war die Bedrohung das Bild der grauen Busse der GEKRAT, der Gemeinnützigen Krankentransportgesellschaft, die in die Gaskammern von Grafeneck, Brandenburg, Heilbronn und anderen Orten fuhr. Das Denkmal der Grauen Busse stand von Januar 2008 bis Januar 2009 am früheren Ort der Villa und fuhr dann weiter nach Brandenburg.",
                    "Genannt wird das Café Estrade, vor dem die Piazzetta liegt. Gegessen wird auf dieser Seite im Golvet. Der Michelin-Beitrag vom 15. April 2023: Potsdamer Straße 58, Küchenchef Jonas Zörner, der Stern bleibt. Ein Stern heißt dort: eine Küche voller Finesse, einen Stopp wert.",
                ],
                "sources": [
                    ("Neues vom Scharounplatz", "https://www.mittendran.de/neues-vom-scharounplatz/"),
                    ("Jetzt sind die Bäume da", "https://www.mittendran.de/jetzt-sind-die-baeume-da/"),
                    ("Spaziergang mit Lia Hiltz und Paul Enck (17): Das Euthanasie-Mahnmal an der Philharmonie", "https://www.mittendran.de/spaziergang-mit-lia-hiltz-und-paul-enck-17-das-euthanasie-mahnmal-der-philharmonie/"),
                    ("Jung, aber Denkmal: Kulturforum", "https://www.mittendran.de/jung-aber-denkmal-kulturforum/"),
                    ("Der Guide Michelin 2023 hat gesprochen", "https://www.mittendran.de/der-guide-michelin-2023-hat-gesprochen/"),
                ],
            },
        ],
    },
    {
        "id": "den-kiez",
        "label": "Den Kiez kennenlernen",
        "note": "Abends, eine Stunde vom Magdeburger Platz.",
        "ideas": [
            {
                "title": "Drei Pins vom Magdeburger Platz",
                "when": "Wochentag abends",
                "slot": "weekday-evening",
                "shape": "Eine Stunde, drei Einführungen",
                "stops": ["Magdeburger Platz", "Schwules Museum", "FreiFläche", "Lützowplatz"],
                "food": {
                    "place": "FreiFläche",
                    "where": "Bülowstraße 90",
                    "line": "Bistro im Haus. Der Beitrag von 2023 meldet die Wiedereröffnung nach der Renovierung.",
                },
                "text": "Vom Platz los, am Schwulen Museum halten, auf dem Lützowplatz enden, solange es hell ist.",
                "id": "magdeburger-drei",
                "narrative": [
                    "Der Spielplatz auf dem Magdeburger Platz, Beitrag vom 14. März 2026, erwacht seit einigen Wochen aus dem Winterschlaf und wird umgegraben. Irgendetwas ist anders, und es sticht nicht sofort ins Auge: eine größere Freifläche, auf die noch ein Spielelement passen würde. Dann ist klar, das Holzplateau mit Seilzug und „Sandrutschen“ ist weg. War etwas kaputt, oder morsch? Kommt etwas Neues? An der kleinen Empore hatten viele Kinder und einige Generationen Spaß. Der Text lässt es offen und verspricht, auf dem Laufenden zu bleiben.",
                    "Essen, in einem anderen Stück, ist die FreiFläche in der Bülowstraße 90. Am 2. Oktober 2023 öffnet sie ab Mittwoch, dem 4. Oktober, nach längeren Renovierungsarbeiten wieder. Ein Ort für Konferenzen und Präsentationen. Das vegan-vegetarische Bistro bietet täglich hausgemachte Speisen und Getränke, für Veranstaltungen auch Catering. Geöffnet, in diesem Beitrag, Montag bis Freitag von 9 bis 15 Uhr. Die Studios: Konferenzaufbauten mit bis zu fünf Referenten und bis zu hundert Gästen vor Ort, und die Möglichkeit, an Tausende online zu streamen.",
                    "Das Schwule Museum, Lützowstraße 73, wird im Beitrag vom 4. Dezember 2025 vierzig. Gefeiert wird das Organisieren, Sammeln, Archivieren und Ausstellen. Am Sonntag, dem 7. Dezember, von 14 bis 18 Uhr, einen Tag nach dem Jahrestag am 6. Dezember, ist der Eintritt frei. Am Dienstag, dem 9. Dezember, 17 Uhr, ein Infotreffen fürs Ehrenamt im Museumscafé. Am Freitag, dem 12. Dezember, 13 bis 17 Uhr, Queer Writing: Lynn Breedlove, Musiker, Schriftsteller, Performer, Aktivist, trans Mann, bekannt durch die queeren Punkbands Tribe 8 und The Homobiles, leitet mit Panda Ortmann einen Workshop, in englischer Lautsprache, Eintritt 10 Euro oder 3, Anmeldung über die Museumsadresse. Laufende Ausstellungen in dem Text: „Feuer + Flamme dem Patriarchat. Petra Galls Fotos der Berliner FrauenLesben-Szene“, bis 23. Februar 2026. „A Heart that Beats – Focus on Queer Ukrainian Art“, bis 25. Januar 2026. „Love At First Fight – Queere Bewegungen in Deutschland seit Stonewall“, bis 29. Juni 2026. Dazu Online-Projekte, darunter „Wir waren schon immer überall“ in der Berlin History App, „Unknown Objects“, das Archivmagazin „Jahr der Frau_en“, „Queer as German Folk“, „Inter* Utopia“ und „Oral HIVstory“.",
                    "Der Lützowplatz am Ende ist in der Kinderserie vom 26. Juli 2024 der ehemalige Holzlagerplatz, und aus der Sicht eines Spielplatzkindes ein trauriger Ort. Die Serie fragt, ab wann ein Spielplatz ein Spielplatz ist. Machen ein Klettergerüst und eine Wippe in einem Sand-Rechteck ihn schon dazu? Kinder sieht man selten. Eher kommt man zufällig vorbei, mit Zeit bis zum Bus, oder die Familie isst in der gegenüberliegenden Pizzeria und das Kind will nicht sitzen bleiben. Viele Sitzplätze, im Sommer die Wiese als Liegefläche oder Ballplatz. Von allen Seiten laute und teilweise sehr schnelle Autos. Am Spielplatz direkt kein Schatten. Die Aufenthaltsqualität des Platzes selbst eher mäßig. Einigermaßen sauber, für eine Spielpause während des Pizzeriabesuchs noch geeignet. Die Brunnen und Wasserbecken, streng genommen nicht zum Spielplatz gehörend, sind kein Ersatz für den ehemals hier stehenden Herkulesbrunnen, bringen an heißen Tagen aber Frische. Das Fazit des Beitrags: auch der Spielplatz schafft es nicht, den Lützowplatz zu beleben. Drei Halt, solange es hell ist.",
                ],
                "sources": [
                    ("Leerfläche am Magdeburger Platz", "https://www.mittendran.de/leerflaeche-magdeburger-platz/"),
                    ("Glückwunsch! Das Schwule Museum wird 40 Jahre alt", "https://www.mittendran.de/dezember/"),
                    ("Kiez mit Kind: Der Spielplatz am Lützowplatz", "https://www.mittendran.de/kiez-mit-kind-der-spielplatz-luetzowplatz/"),
                    ("Wiedereröffnung FreiFläche", "https://www.mittendran.de/wiedereroeffnung-freiflaeche-eventspace-studio-bistro/"),
                ],
            },
            {
                "title": "Die Potsdamer Straße lernen",
                "when": "Wochentag abends",
                "slot": "weekday-evening",
                "shape": "Eine Stunde, eine Straße",
                "stops": ["Villa Lützow", "Nihon Mono", "Potsdamer Straße"],
                "food": {
                    "place": "Nihon Mono",
                    "where": "Potsdamer Straße 93",
                    "line": "Japanisches Geschäft mit Omakase: die Köchin oder der Koch entscheidet. Im Sommer hat die Villa zusätzlich ein Café auf dem Gelände.",
                },
                "text": "Die Villa für das Haus, Nihon Mono fürs Essen. Der Weg dazwischen ist der Punkt.",
                "id": "potsdamer-lernen",
                "narrative": [
                    "Der Spaziergang zur Villa Lützow fängt bei einem Bild von Lia Hiltz an, und Paul Enck liest am 6. Januar 2023 aus diesem Bild eine Geschichte, die er selbst als späte Rache, als ausgleichende Gerechtigkeit, als Sieg der Kunst über die Politik oder auch nur als schönen Zufall bezeichnet. Die heutige Villa steht an der Stelle, an der zwischen 1933 und 1945 die Reichskammer der bildenden Künste residierte, Blumeshof 5–6, die Behörde der Reichskulturkammer, die mit Zensur und dem Verdikt „entartete Kunst“ vielen Künstlerinnen und Künstlern das Leben schwer und vielen das Leben unmöglich machte. Dass viele von ihnen gleichzeitig Juden waren, machte die Lage im Blumeshof noch dramatischer. Lias Bild, schreibt er, hätte es dort schwer gehabt.",
                    "Der Blumeshof war eine Privatstraße, benannt nach dem Bankier Johann Carl Friedrich Blume (1819–1875), der das Stück Land zwischen der heutigen Kluckstraße und der Elisabethklinik, zwischen Schöneberger Ufer und Lützowstraße, 1862 vom Unternehmer Jungbluth kaufte. Jungbluth hatte dort eine Fabrik für Eisenbahnwaggons betrieben. Sechzehn Wohnhäuser. Um 1900 etwa 500 Eigentümer und Mietparteien, viele Rechtsanwälte, Ärzte, Wissenschaftler, darunter Hans Virchow (1852–1940), Anatomieprofessor an der Charité, Sohn von Rudolf Virchow, der hier ein Arbeitszimmer hatte. Wenige Gewerbe. Ein Theater, das Kleintheater von Paul von Schlippenbach, Blumeshof 12. Walter Benjamins beide Großmütter wohnten zeitweise im Blumeshof 8 und 12. Das Haus Nummer 15, ehemals Jungbluth, kauft 1917 die Jüdische Gemeinde, eher als Kapitalanlage. Ab 1933 werden die großen Wohnungen geteilt und immer dichter belegt, zuletzt ein „Judenhaus“, die letzte Zuflucht vor der Deportation ab 1942 nach Theresienstadt oder Auschwitz. Schräg gegenüber, wo heute die Villa steht, das Doppelhaus 5–6, seit 1920 der Ackerbaugesellschaft gehörend, bis 1935 mit vielen Mietern. Dann, laut Adressbuch, die Reichskammer, bald die einzige Mieterin, 1939 zeitweilig auch die Reichsmusikkammer. Enck zitiert eine Liste des Reichsministeriums für Volksaufklärung von 1937: bis dahin etwa 22.000 Kunstwerke in 100 deutschen Museen beschlagnahmt, etwa 5.000 verbrannt, andere im Ausland verkauft oder getauscht. Aus seiner Aufzählung, nur ein Teil: 1122 Bilder von Emil Nolde, 818 von Erich Heckel, 777 von Karl Schmidt-Rottluff, 750 von Ernst Ludwig Kirchner, 685 von Max Beckmann, 653 von Ernst Barlach, 605 von Oskar Kokoschka, 556 von Lyonel Feininger, 516 von Max Pechstein, 503 von Kurt Grosz, 408 von Otto Mueller, 373 von Otto Dix, 359 von Lovis Corinth, 262 von Wassily Kandinsky, 210 von Alexej von Jawlensky, 170 von Alfred Kubin, 150 von Franz Marc, 133 von Paul Klee, 112 von Willy Baumeister. Das farblose Jahrzehnt, schreibt er, nahm seinen Anfang.",
                    "Die späteren Beiträge kennen dasselbe Haus als Kiez-Zentrum. Am 17. September 2024 lädt das Team zum fünften Jahr ein: Angebote für Familien, queere Menschen, Gartenliebhaberinnen und Gartenliebhaber und alle anderen Nachbarinnen und Nachbarn rund um die Potsdamer Straße. Freitag, der 20. September, 15.30 bis 19 Uhr. Mosaik mit der KinderKUNSTMagistrale, Schnitzeljagd durch die versteckten Ecken, Kletterwand, Riesenseifenblasen, Bühne mit Tanz, Musik, Gesang und Theatershow, Grill und Buffet, und die Bitte um eine Kuchen- oder Essensspende für die nachbarschaftliche Tafel.",
                    "Im Sommer 2026, der Beitrag vom 30. Juli, gibt es alternativ das „Café in der Villa“ auf dem Gelände. Gabriele Hulitschke schreibt die Regeln, weil das Zentrum eine Einrichtung des Jugendamtes ist und der Kinder- und Jugendschutz für das ganze Gelände gilt. Rauchen vor dem Tor. Kein Alkohol, keine Drogen. Hunde nur nach Absprache, angeleint an der Kurzleine, und sie müssen gehen, wenn sich Kinder oder andere von ihnen bedroht fühlen. Das Gelände sei ein sicherer Ort, ein Safer Space: weder diskriminierendes noch rassistisches, gewalttätiges oder grenzüberschreitendes Verhalten in Wort und Tat. Am 28. April 2025 ein kurzes Stück über die Nacht: im üppigen Grün des Gemeinschaftsgartens singt eine Nachtigall, zahlreiche Melodien, am Zaun zu hören. Dem Beitrag liegt eine Tonaufnahme bei.",
                    "Essen, auf dem Weg, ist Nihon Mono in der Potsdamer Straße 93, Beitrag vom 19. Juni 2025. Eine japanische Boutique und Galerie, Kunst und Kunsthandwerk, Lebensmittelzutaten, und seit einiger Zeit Essen zum Mitnehmen. Mittwoch bis Freitag ab 11.30 Uhr je eine vegane und eine nicht vegane Bento-Box. Dagmar Maas, die Köchin, sammelt die Zutaten Montag und Dienstag auf lokalen Märkten. Keine feste Karte, sondern zwei Gerichte „omakase“: die Köchin entscheidet, am Anfang der Woche festgelegt. Sie hat Kochen in Japan gelernt und will eine Kochschule eröffnen. Jede Box, schreibt der Text, enthalte alle Geschmacksvarianten, süß, sauer, bitter, salzig, scharf, alle Farbvarianten, schwarz, weiß, rot, gelb, grün, und alle Kochvarianten, gebraten, gekocht, gedämpft, frittiert, roh. Der Weg dazwischen ist der Punkt.",
                ],
                "sources": [
                    ("Spaziergang mit Lia Hiltz und Paul Enck (16): Villa Lützow", "https://www.mittendran.de/spaziergang-mit-lia-hiltz-und-paul-enck-16-villa-luetzow/"),
                    ("5 Jahre Villa Lützow", "https://www.mittendran.de/5-jahre-villa-luetzow-freitag-20-september/"),
                    ("Café in der Villa Lützow", "https://www.mittendran.de/cafe-in-der-villa-luetzow/"),
                    ("Nachts vor der Villa Lützow", "https://www.mittendran.de/nachts-vor-der-villa-luetzow/"),
                    ("Omakase in der Potsdamer Straße 93", "https://www.mittendran.de/omakase-die-koechin-oder-der-koch-entscheidet-der-potsdamer-str-93/"),
                ],
            },
        ],
    },
    {
        "id": "queere-geschichte",
        "label": "Queere Geschichte",
        "note": "Ein längerer Nachmittag zwischen Lützowstraße und Nollendorfplatz. Essen in der Mitte.",
        "ideas": [
            {
                "title": "Vom Museum zum Nollendorfplatz",
                "when": "Wochenende nachmittags",
                "slot": "weekend-afternoon",
                "shape": "Ein längerer Spaziergang",
                "stops": [
                    "Schwules Museum",
                    "SOLE DELI",
                    "Kurfürstenstraße 130",
                    "Nollendorfplatz",
                    "Karl-Heinrich-Ulrichs-Straße",
                ],
                "food": {
                    "place": "SOLE DELI",
                    "where": "Zietenstraße 7",
                    "line": "Im Beitrag vom September 2025: mediterrane Küche in der Zietenstraße 1–9, auch glutenfrei, vegan und halal, mit Plätzen draußen.",
                },
                "text": "Museum, dann essen, dann die Aids-Hilfe und der Platz mit der umbenannten Straße.",
                "id": "queere-geschichte",
                "narrative": [
                    "Das Schwule Museum in der Lützowstraße 73 ist der Anfang, und die Beiträge behandeln es zugleich als Archiv und als angegriffenes Haus.",
                    "Am 4. Dezember 2025 wird es vierzig: Organisieren, Sammeln, Archivieren, Ausstellen. Am Sonntag, dem 7. Dezember, 14 bis 18 Uhr, einen Tag nach dem Jahrestag am 6. Dezember, kommen alle Besucherinnen und Besucher umsonst in die Ausstellungen. Am Dienstag darauf, 17 Uhr, ein Infotreffen fürs Ehrenamt im Museumscafé. Am Freitag, dem 12. Dezember, 13 bis 17 Uhr, ein Workshop zum queeren Schreiben mit Lynn Breedlove und Panda Ortmann, in englischer Lautsprache, 10 Euro oder 3. Laufend, in dem Text: Petra Galls Fotos der Berliner FrauenLesben-Szene, bis 23. Februar 2026. Queere ukrainische Kunst, bis 25. Januar 2026. „Love At First Fight“, queere Bewegungen in Deutschland seit Stonewall, bis 29. Juni 2026.",
                    "Zwei Jahre früher, am 13. August 2023, eine Pressemitteilung des Hauses, gezeichnet von Jan Künemund, mino Künze und Julia Heuser. Das Museum, eine weltweit einzigartige Institution für queere Geschichte und Kultur, sei seit Februar fünfmal von unbekannten Personen angegriffen worden. In der Nacht zum 24. Februar ein Luftgewehr auf die Frontscheiben, den Namensschriftzug und ein Kunstwerk vor der Tür. Anzeige gegen Unbekannt, breite Berichterstattung, Solidarität. Am 19. März, bei laufendem Betrieb, der Eingang mit Lebensmitteln beschmiert, Mitarbeiterinnen und Mitarbeiter beleidigt. Am 31. März die Front mit einem Feuerlöscher besprüht. Am 21. und am 28. Mai Wasserbomben ins Foyer. Wieder Anzeigen. Dazu das, was der Text ein Grundrauschen nennt: anti-queere Sticker vor dem Haus, rechtsradikale Aufkleber in den Toiletten, Schläge gegen die Scheibe, Beleidigungen am Telefon, in den sozialen Medien, im Gästebuch. Gruppenbezogene Gewalt, schreiben sie, treffe Menschen, Aktivistinnen und Institutionen, die sichtbar Stellung beziehen. Sie wissen von vernetzten Häusern, dass sie damit nicht allein sind. Die Absichtserklärungen von Senat und Bund, anti-queere Gewalt präziser zu erfassen, werden begrüßt. Gewünscht wird Hilfe, die über Polizei und Aufklärung hinausgeht: finanziell, personell, psychologisch. Die Versicherung stelle in Frage, ob eine Scheibe mit Einschusslöchern ausgetauscht werden müsse, solange sie intakt sei. Schriftzug, Kunstwerk und Reinigung trage das Haus selbst. Sicherheitskonzept, Training, Präventionsförderung neben dem Tagesgeschäft. Gegründet 1985, eines der größten LGBTIQ-Museen der Welt, Sammlung etwa 1,5 Millionen Archivalien, Ausstellungsfläche knapp 700 Quadratmeter, normalerweise bis zu drei Ausstellungen zugleich, gefördert vom Land Berlin. Der Ort bleibt der erste Halt.",
                    "Älter, und nicht auf diesem Nachmittag, liegt das Institut für Sexualwissenschaft. Der Beitrag vom 19. April 2023 erzählt es über Magnus Hirschfeld (14. Mai 1868 bis 14. Mai 1935) und das Leitmotiv „Durch Wissenschaft zur Gerechtigkeit“. Im Mai 1897 gründet er mit anderen das Wissenschaftlich-Humanitäre Komitee, um den Paragrafen 175 abzuschaffen. Er gilt als Begründer der Sexualwissenschaft, schreibt eine dreibändige Sexualpathologie und führt 1930 mit Ludwig Levy-Lenz die erste geschlechtsangleichende Operation durch. Nach 1918 kauft er die ehemalige Villa Joachim, In den Zelten 10, Ecke Beethovenstraße 3, zeitweiliges Palais des Fürsten von Hatzfeld, und gründet dort am 6. Juni 1919 das private Institut, das erste seiner Art. Archiv, Museum, Lehrstätte, Beratung, ein Zufluchtsort, solange Homosexualität illegal ist und trans Personen diskriminiert werden. Knapp vierzehn Jahre. Den Nationalsozialisten ist er verhasst als Jude, als Homosexueller, als Sozialist und als unabhängiger Forscher. Anfang Mai 1933 stürmen Sportstudenten des Nationalsozialistischen Deutschen Studentenbundes das Institut, stehlen 15 Zentner Literatur und bringen sie zum Studentenhaus in der Oranienburger Straße. Am 10. Mai werden die Bücher auf dem Opernplatz verbrannt. In den folgenden Jahren wird die homosexuelle Bürgerrechtsbewegung zerschlagen, Treffpunkte geschlossen, Zeitschriften verboten, Zehntausende homosexuelle Männer zu Gefängnis, Zuchthaus und Lager verurteilt. Heute, schreibt der Beitrag, eine eher bescheidene Gedenktafel, aufgestellt am 6. Juli 1994, 75 Jahre nach der Gründung, in der Nähe des ehemaligen Standorts. Eine Büste Hirschfelds steht im Schwulen Museum. Der Koalitionsvertrag einer damals möglichen CDU-SPD-Regierung von 2023 sieht vor, den 14. Mai als Magnus-Hirschfeld-Tag zu begehen. Dieser Nachmittag bleibt südlich der Lützowstraße.",
                    "Essen ist das SOLE DELI, Beitrag vom 16. September 2025: mediterrane Küche in der Zietenstraße 1–9, modern, familienfreundlich, glutenfrei, vegan und vegetarisch, auch halal, von der Vorspeise bis zum Dessert. Genannt werden hausgemachtes Bananenbrot zu 7,50 Euro, eine vegane Breakfast-Platte zu 13 Euro, Lachs Piccata zu 18 Euro. Plätze draußen. Geöffnet, in diesem Text, täglich von 9 bis 18 Uhr. Geeignet für Familienfeiern und größere Gruppen, auch Catering. Zwischen Museum und Platz.",
                    "In der Kurfürstenstraße 130, nahe am Nollendorfplatz, sitzt die Berliner Aids-Hilfe. Der Text zum 1. Dezember 2022 erinnert daran, dass Aids als „Schwulenseuche“ bezeichnet wurde, dass viele die Erkrankung anfangs verbargen, dass Unsinn verbreitet wurde, und dass seit Beginn der Pandemie weltweit über 40 Millionen Menschen gestorben sind. Der Verein kämpft seit 1985 als Menschenrechtsorganisation gegen die Stigmatisierung HIV-positiver Menschen. Gemeinnützig und mildtätig, heute auch im Auftrag des Landes Berlin für Versorgung und Prävention bei HIV, Aids, sexuell übertragbaren Infektionen und Hepatitiden. Im Haus ein Testzentrum und Beratung. Selbsthilfe, Gesprächsgruppen, Begegnung, individuelle Hilfe. Mit dem Land bei der Fast-Track-Cities-Initiative, Aids bis 2030 zu beenden, Null Diskriminierung im Vordergrund. Der Text sagt auch: heute leben rund 40 Millionen Menschen mit HIV, und heute müsse niemand mehr an HIV oder Aids sterben, schon gar nicht in Europa und Deutschland. Zugleich starben 2021 noch 650.000 HIV-Infizierte, vor allem in afrikanischen und asiatischen Ländern. In Deutschland seien 90 Prozent der Infektionen identifiziert, 97 Prozent der Diagnostizierten in Behandlung, bei 96 Prozent der so Behandelten keine Viren mehr nachweisbar, also nicht mehr ansteckend. Lea Susanna wird zitiert: sie lebe seit 19 Jahren mit HIV, mit effektiver Behandlung könne sie HIV nicht übertragen. Das Motto des Welt-Aids-Tags in dem Jahr: „Equalize“. Benannt werden, mit Winnie Byanyima von UNAIDS, schwule Männer, Menschen, die intravenös Drogen konsumieren, Sexarbeiterinnen und Sexarbeiter, Menschen in Haft, junge Frauen in Afrika, Transpersonen. Sie alle bräuchten Zugänge, die für sie passen.",
                    "Der Nollendorfplatz ist im Beitrag vom 10. Juli 2023 der Ort des Lesbisch-schwulen Stadtfests. Der Regenbogenfonds veranstaltet es zum 29. Mal, Motto „Gleiche Rechte für Ungleiche – weltweit!“, am 15. und 16. Juli 2023, täglich ab 11 Uhr, auf 20.000 Quadratmetern in der Motz-, Eisenacher-, Fugger- und Kalckreuthstraße. Fünf „Welten“: Film, Politik, Positive, Gesundheit und Wellness, Radio, Sport, dazu lesbische, schwule, bisexuelle und trans Projekte. Der Text spricht von weit über 350.000 Besucherinnen und Besuchern und von Europas größtem Fest dieser Art. Sechs Bühnen werden benannt, darunter 98.8 Kiss FM, Connection mit House und Techno, die FrauenLesbenTrans-Bühne, Queere Medien, Sunshine Live. Am Samstag von 15.30 bis 16.30 Uhr eine Politik-Talkshow mit Gerhard Hoffmann auf der Stadtfestbühne an der Ecke Eisenacher- und Fuggerstraße, danach Rock und Pop, samstags bis 23 Uhr, sonntags bis 21 Uhr. Das Foto im Stück zeigt das Fest von 2022.",
                    "Die Karl-Heinrich-Ulrichs-Straße daneben ist die umbenannte Einemstraße. Der Beitrag vom 30. November 2023 hängt die Umbenennung an einen neuen Layer zur queeren Geschichte in der berlinHistory-App, erarbeitet mit dem Schwulen Museum und dem Lesben- und Schwulenverband Berlin-Brandenburg, gefördert vom Berliner Beauftragten zur Aufarbeitung der SED-Diktatur und von zwei Senatsverwaltungen, zehn Autorinnen und Autoren. Rund 70 Orte, in Ost und West, vor der Teilung, Kultur, Treffpunkte, Vereine, Verlage, Ereignisse, Politik. Die Fragen, die der Text stellt, reichen über diesen Kiez hinaus: das Magnus-Hirschfeld-Ufer, eine Souterrain-Bar der fünfziger Jahre, Charlotte von Mahlsdorfs Gründerzeitmuseum, die Mulackritze, David Bowies Wohnung, das Grab von Johanna Elberskirchen. Integriert ist der Audiorundgang zur Sexarbeit am Bülowbogen, „Wir waren schon immer überall“, und eine Fahrrad-Audiotour zu Aids und HIV in Ostberlin, „AIDS: Nicht durch die Mauer zu stoppen“. Queere Geschichte, schließt der Beitrag, sei immer auch Demokratiegeschichte.",
                ],
                "sources": [
                    ("Glückwunsch! Das Schwule Museum wird 40 Jahre alt", "https://www.mittendran.de/dezember/"),
                    ("Das Schwule Museum als gefährdeter Ort", "https://www.mittendran.de/das-schwule-museum-als-gefaehrdeter-ort/"),
                    ("„Durch Wissenschaft zur Gerechtigkeit“", "https://www.mittendran.de/durch-wissenschaft-zur-gerechtigkeit/"),
                    ("Restaurant SOLE DELI", "https://www.mittendran.de/restaurant-sole-deli/"),
                    ("Die Diagnose kam einmal einem Todesurteil gleich", "https://www.mittendran.de/die-diagnose-kam-einmal-einem-todesurteil-gleich/"),
                    ("„Gleiche Rechte für Ungleiche – weltweit!“", "https://www.mittendran.de/gleiche-rechte-fuer-ungleiche-weltweit/"),
                    ("In der Berlin-Presse war es kurz erwähnt", "https://www.mittendran.de/der-berlin-presse-war-es-kurz-erwaehnt-hier-noch-einmal-ausfuehrlich/"),
                ],
            },
        ],
    },
]


def load_gazetteer_points() -> dict[str, tuple[float, float]]:
    path = ROOT / "gazetteer" / "streets.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    points: dict[str, tuple[float, float]] = {}
    for place in data.get("places") or []:
        name = str(place.get("name") or "").strip()
        if not name or place.get("lat") is None or place.get("lon") is None:
            continue
        points[name.casefold()] = (float(place["lat"]), float(place["lon"]))
    return points


def _feature_point(feat: dict) -> tuple[float, float, str]:
    lon, lat = feat["geometry"]["coordinates"]
    slug = str(feat["properties"].get("place_slug") or "")
    return float(lat), float(lon), slug


def _meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    mid = math.radians((lat1 + lat2) / 2)
    dy = (lat1 - lat2) * 111_320
    dx = (lon1 - lon2) * 111_320 * math.cos(mid)
    return math.hypot(dx, dy)


def _public_pin(feat: dict) -> dict:
    props = dict(feat.get("properties") or {})
    place = str(props.get("place") or "")
    slug = str(props.get("place_slug") or place_slug(place))
    props["place_url"] = f"../../places/{slug}/"
    return {
        "type": "Feature",
        "geometry": feat["geometry"],
        "properties": props,
    }


# Meal stops that are not places on the Karte. Coordinates and the hours
# link come from OpenStreetMap and the house's own site, not from a clock
# copied onto this page.
FOOD_STOPS: dict[str, dict] = {
    "Joseph-Roth-Diele": {
        "lat": 52.5026314,
        "lon": 13.3655794,
        "hours_url": "https://www.joseph-roth-diele.de/",
        "articles": [
            {
                "title": "Denk Mal Am Ort – Joseph-Roth-Diele",
                "url": "https://www.mittendran.de/denk-mal-ort-joseph-roth-diele/",
                "date": "2024-05-01",
                "rubrik": "Kunst und Kultur",
                "excerpt": "Am Wochenende vor dem 8. Mai 2024 hat „Denk Mal Am Ort“ in der Diele an der Potsdamer Straße 75 an die Befreiung erinnert.",
            }
        ],
    },
    "Les Climats": {
        "lat": 52.5010425,
        "lon": 13.3623405,
        "hours_url": "https://www.lesclimats.com/",
        "articles": [
            {
                "title": "Jazz live und Gute Küche im „Les Climats“",
                "url": "https://www.mittendran.de/jazz-live-und-gute-kueche-im-les-climats/",
                "date": "2023-05-16",
                "rubrik": "Gewerbe und Gastronomie",
                "excerpt": "Die Weinbar in der Pohlstraße, mit Küche und Jazz.",
            }
        ],
    },
    "Café Jules": {
        "lat": 52.4990847,
        "lon": 13.3733055,
        "hours_url": "https://www.jules-cafe.de/",
        "articles": [
            {
                "title": "Thaimarkt „Thai-Bridge“ im Gleisdreieckpark",
                "url": "https://www.mittendran.de/thaimarkt-thai-bridge-im-gleisdreieckpark/",
                "date": "2025-06-17",
                "rubrik": "Gewerbe und Gastronomie",
                "excerpt": "Der Markt steht freitags am Café Jules, Luckenwalder Straße 6b, unter der U-Bahn.",
            }
        ],
    },
    "SOLE DELI": {
        "lat": 52.4991877,
        "lon": 13.3575309,
        "hours_url": "https://brunchbysole.de/",
        "articles": [
            {
                "title": "Restaurant SOLE DELI",
                "url": "https://www.mittendran.de/restaurant-sole-deli/",
                "date": "2025-09-16",
                "rubrik": "Gewerbe und Gastronomie",
                "excerpt": "Mediterrane Küche in der Zietenstraße 1–9, glutenfrei, vegan und halal, mit Plätzen draußen.",
            }
        ],
    },
    "Café ODOR": {
        "lat": 52.4995699,
        "lon": 13.3651496,
        "hours_url": "https://www.google.com/maps/search/?api=1&query=Caf%C3%A9%20ODOR%20Kurf%C3%BCrstenstra%C3%9Fe%2021%20Berlin",
        "articles": [
            {
                "title": "Café ODOR",
                "url": "https://www.mittendran.de/caf%c3%a9-odor/",
                "date": "2023-01-23",
                "rubrik": "Gewerbe und Gastronomie",
                "excerpt": "Kleines Café im Souterrain der Kurfürstenstraße 21–22, mit Sauerteigbrot und Brunch.",
            }
        ],
    },
    "Sofram": {
        "lat": 52.4968724,
        "lon": 13.3619338,
        "hours_url": "https://www.google.com/maps/search/?api=1&query=Sofram%20Potsdamer%20Stra%C3%9Fe%20137%20Berlin",
        "articles": [
            {
                "title": "Sofram, das türkische Tischlein deck dich",
                "url": "https://www.mittendran.de/sofram-das-tuerkische-tischlein-deck-dich-in-der-potse/",
                "date": "2023-04-17",
                "rubrik": "Gewerbe und Gastronomie",
                "excerpt": "Familienrestaurant in der Potsdamer Straße 137, türkische Hausgerichte.",
            }
        ],
    },
    "Irma la Douce": {
        "lat": 52.5014844,
        "lon": 13.3639586,
        "hours_url": "https://www.irmaladouce.de/",
        "articles": [
            {
                "title": "Der Guide Michelin 2023 hat gesprochen",
                "url": "https://www.mittendran.de/der-guide-michelin-2023-hat-gesprochen/",
                "date": "2023-04-15",
                "rubrik": "Aus dem Kiez",
                "excerpt": "Irma la Douce in der Potsdamer Straße 102, neben dem Varieté. Im Beitrag von 2023 hat das Haus einen Stern.",
            }
        ],
    },
    "Facil": {
        "lat": 52.509059,
        "lon": 13.373848,
        "hours_url": "https://facil.berlin/",
        "articles": [
            {
                "title": "Der Guide Michelin 2023 hat gesprochen",
                "url": "https://www.mittendran.de/der-guide-michelin-2023-hat-gesprochen/",
                "date": "2023-04-15",
                "rubrik": "Aus dem Kiez",
                "excerpt": "Facil im Mandala-Hotel, Potsdamer Straße 3. Im Beitrag von 2023 zwei Sterne.",
            }
        ],
    },
    "Golvet": {
        "lat": 52.5055320,
        "lon": 13.3675963,
        "hours_url": "https://golvet.de",
        "articles": [
            {
                "title": "Der Guide Michelin 2023 hat gesprochen",
                "url": "https://www.mittendran.de/der-guide-michelin-2023-hat-gesprochen/",
                "date": "2023-04-15",
                "rubrik": "Aus dem Kiez",
                "excerpt": "Golvet in der Potsdamer Straße 58. Im Beitrag von 2023 ein Stern, Küche Jonas Zörner.",
            }
        ],
    },
    "FreiFläche": {
        "lat": 52.4984350,
        "lon": 13.3602987,
        "hours_url": "https://freiflaeche-berlin.com/bistro/",
        "articles": [
            {
                "title": "Wiedereröffnung FreiFläche",
                "url": "https://www.mittendran.de/wiedereroeffnung-freiflaeche-eventspace-studio-bistro/",
                "date": "2023-10-02",
                "rubrik": "Gewerbe und Gastronomie",
                "excerpt": "Bistro in der Bülowstraße 90, nach der Renovierung wieder offen.",
            }
        ],
    },
    "Nihon Mono": {
        "lat": 52.5013680,
        "lon": 13.3645232,
        "hours_url": "https://www.nihon-mono.com/ladengeschaeft",
        "articles": [
            {
                "title": "Omakase in der Potsdamer Straße 93",
                "url": "https://www.mittendran.de/omakase-die-koechin-oder-der-koch-entscheidet-der-potsdamer-str-93/",
                "date": "2025-06-19",
                "rubrik": "Gewerbe und Gastronomie",
                "excerpt": "Japanisches Geschäft in der Potsdamer Straße 93. Omakase: die Köchin oder der Koch entscheidet.",
            }
        ],
    },
}


def hours_link(place: str) -> str:
    spec = FOOD_STOPS.get(place)
    if not spec:
        return ""
    return (
        f'<a class="hours-link" href="{html.escape(spec["hours_url"])}" rel="noopener">'
        "Öffnungszeiten</a>"
    )


def food_pin(name: str) -> dict:
    spec = FOOD_STOPS[name]
    articles = spec["articles"]
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [spec["lon"], spec["lat"]]},
        "properties": {
            "place": name,
            "count": len(articles),
            "articles": articles,
            "hours_url": spec["hours_url"],
        },
    }


def pins_for_stops(
    stops: list[str],
    features: list[dict],
    points: dict[str, tuple[float, float, str]],
) -> list[dict]:
    """Karte pins for the named stops.

    A stop that is itself a pin is that pin. A street uses the address pins
    along it. A meal from FOOD_STOPS gets its own pin, drawn last so it sits
    above a house pin at the same door.
    """
    chosen: list[dict] = []
    seen: set[str] = set()

    def take(feat: dict) -> None:
        place = str((feat.get("properties") or {}).get("place") or "")
        key = place.casefold()
        if not key or key in seen:
            return
        seen.add(key)
        chosen.append(_public_pin(feat))

    by_name = {
        str((feat.get("properties") or {}).get("place") or "").casefold(): feat
        for feat in features
    }
    food_names = []
    for name in stops:
        if name in FOOD_STOPS:
            food_names.append(name)
            continue
        key = name.casefold()
        if key in by_name:
            take(by_name[key])
            continue
        prefix = key + " "
        along = [
            feat
            for feat in features
            if str((feat.get("properties") or {}).get("place") or "").casefold().startswith(prefix)
        ]
        if along:
            for feat in along:
                take(feat)
            continue
        if is_area_place(name):
            continue
        point = points.get(key)
        if not point:
            continue
        alat, alon = point[0], point[1]
        for feat in features:
            full = feat.get("_articles_full") or []
            named = any(
                key in {str(n).casefold() for n in (art.get("place_names") or [])}
                for art in full
            )
            if not named:
                continue
            lon, lat = feat["geometry"]["coordinates"]
            if _meters(lat, lon, alat, alon) <= 250:
                take(feat)
    for name in food_names:
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        chosen.append(food_pin(name))
    return chosen


DATE_MAP_JS = r"""
const RUBRIK_COLORS = window.RUBRIK_COLORS || {};
const RUBRIK_FALLBACK = "#7a6a58";

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
  return "hsl(" + (h % 360) + " 42% 42%)";
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
  const shown = articles.slice(0, 10);
  const items = shown.map(articleRow).join("");
  const moreHref = p.place_url || "";
  const more =
    n > 10 && moreHref
      ? "<a class='popup-more' href='" + esc(moreHref) + "'>Alle " + n + " Beiträge →</a>"
      : moreHref && n > 1
        ? "<a class='popup-more' href='" + esc(moreHref) + "'>Zur Ortsseite →</a>"
        : "";
  const hours = p.hours_url
    ? "<a class='popup-more' href='" + esc(p.hours_url) + "' rel='noopener'>Öffnungszeiten</a>"
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
    hours +
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
      conicFromArticles(arts) +
      "' title='" +
      esc(String(n) + " Beiträge") +
      "'></div>",
  });
}

const geo = window.DATE_PLACES || { type: "FeatureCollection", features: [] };
const map = L.map("date-map", { scrollWheelZoom: false });
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap",
}).addTo(map);
const layer = L.geoJSON(geo, {
  pointToLayer(feature, latlng) {
    const props = (feature && feature.properties) || {};
    const n = props.count || 1;
    if (props.hours_url) {
      return L.marker(latlng, { icon: multiIcon(feature), riseOnHover: true, zIndexOffset: 1000 });
    }
    if (n > 1) return L.marker(latlng, { icon: multiIcon(feature), riseOnHover: true });
    return L.circleMarker(latlng, singleStyle(feature));
  },
  onEachFeature(feature, lyr) {
    lyr.bindPopup(popupHtml(feature.properties || {}), {
      maxWidth: Math.min(320, Math.max(180, window.innerWidth - 56)),
      autoPan: true,
      autoPanPadding: [12, 12],
    });
  },
}).addTo(map);
if (layer.getBounds().isValid()) {
  map.fitBounds(layer.getBounds(), { padding: [28, 28], maxZoom: 16 });
}
map.invalidateSize();
"""


# One Beitragsbild per stop, the article that stop is written from.
# Stops whose only picture is a logo are left out.
DATE_PHOTOS: dict[str, dict[str, str]] = {
    "pohlstrasse-variete": {
        "Les Climats": "https://www.mittendran.de/jazz-live-und-gute-kueche-im-les-climats/",
        "Pohlstraße": "https://www.mittendran.de/kiez-mit-kind-der-geheime-spielplatz-der-pohlstrasse/",
        "Wintergarten Varieté": "https://www.mittendran.de/der-wintergarten-feiert-seinen-30-geburtstag/",
    },
    "diele-kulturforum": {
        "Joseph-Roth-Diele": "https://www.mittendran.de/weihnachten-und-silvester-geschlossen-die-joseph-roth-diele-macht-ferien/",
        "Kulturforum": "https://www.mittendran.de/jung-aber-denkmal-kulturforum/",
    },
    "luiseninsel": {
        "Spielplatz Luiseninsel": "https://www.mittendran.de/kiez-mit-kind-der-spielplatz-tiergarten-luiseninsel/",
        "Café ODOR": "https://www.mittendran.de/caf%c3%a9-odor/",
    },
    "specht-gleisdreieck": {
        "Specht-Spielplatz": "https://www.mittendran.de/kiez-mit-kind-specht-spielplatz-karlsbad/",
        "Café Jules": "https://www.mittendran.de/thaimarkt-thai-bridge-im-gleisdreieckpark/",
        "Gleisdreieck": "https://www.mittendran.de/kiez-mit-kind-spielplatz-stangenwald/",
    },
    "park-potsdamer": {
        "Gleisdreieck": "https://www.mittendran.de/kiez-mit-kind-spielplatz-kinderzimmer/",
        "Potsdamer Straße": "https://www.mittendran.de/art-week-impressions-3/",
        "Sofram": "https://www.mittendran.de/sofram-das-tuerkische-tischlein-deck-dich-in-der-potse/",
    },
    "kanal-variete": {
        "Landwehrkanal": "https://www.mittendran.de/zeitzeugen-gesucht-der-landwehrkanal-wird-175-jahre-alt/",
        "Potsdamer Brücke": "https://www.mittendran.de/der-potsdamer-bruecke/",
        "Irma la Douce": "https://www.mittendran.de/der-guide-michelin-2023-hat-gesprochen/",
        "Wintergarten Varieté": "https://www.mittendran.de/der-wintergarten-feiert-seinen-30-geburtstag/",
    },
    "museum-kaffee": {
        "Neue Nationalgalerie": "https://www.mittendran.de/eine-rose-vor-der-neuen-nationalgalerie/",
        "Matthäikirchplatz": "https://www.mittendran.de/wo-ist-das-dritte-land-geblieben/",
        "Facil": "https://www.mittendran.de/der-guide-michelin-2023-hat-gesprochen/",
    },
    "philharmonie-platz": {
        "Philharmonie": "https://www.mittendran.de/neues-vom-scharounplatz/",
        "Kulturforum": "https://www.mittendran.de/jetzt-sind-die-baeume-da/",
        "Golvet": "https://www.mittendran.de/der-guide-michelin-2023-hat-gesprochen/",
    },
    "magdeburger-drei": {
        "Magdeburger Platz": "https://www.mittendran.de/leerflaeche-magdeburger-platz/",
        "FreiFläche": "https://www.mittendran.de/wiedereroeffnung-freiflaeche-eventspace-studio-bistro/",
        "Lützowplatz": "https://www.mittendran.de/kiez-mit-kind-der-spielplatz-luetzowplatz/",
    },
    "potsdamer-lernen": {
        "Villa Lützow": "https://www.mittendran.de/spaziergang-mit-lia-hiltz-und-paul-enck-16-villa-luetzow/",
        "Nihon Mono": "https://www.mittendran.de/omakase-die-koechin-oder-der-koch-entscheidet-der-potsdamer-str-93/",
    },
    "queere-geschichte": {
        "SOLE DELI": "https://www.mittendran.de/restaurant-sole-deli/",
        "Karl-Heinrich-Ulrichs-Straße": "https://www.mittendran.de/der-berlin-presse-war-es-kurz-erwaehnt-hier-noch-einmal-ausfuehrlich/",
    },
}

_HERO_INDEX: dict[str, dict] | None = None


def _url_key(url: str) -> str:
    path = urllib.parse.unquote(urllib.parse.urlsplit(url.strip()).path)
    return path.rstrip("/").casefold()


def hero_index() -> dict[str, dict]:
    global _HERO_INDEX
    if _HERO_INDEX is not None:
        return _HERO_INDEX
    found: dict[str, dict] = {}
    for meta_path in ARTICLES.rglob("meta.yaml"):
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        url = str(meta.get("source_url") or "").strip()
        if not url:
            continue
        folder = meta_path.parent
        hero = next((p for p in folder.iterdir() if p.name.lower().startswith("hero.")), None)
        if hero is None:
            continue
        found[_url_key(url)] = {
            "path": hero,
            "title": str(meta.get("title") or "").strip(),
            "url": url,
        }
    _HERO_INDEX = found
    return found


def _publish_hero(src: Path, dest: Path) -> None:
    if dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    image = ImageOps.exif_transpose(Image.open(src))
    image = image.convert("RGB")
    width, height = image.size
    if width > 1400:
        image = image.resize((1400, round(height * 1400 / width)), Image.Resampling.LANCZOS)
    image.save(dest, "JPEG", quality=80, optimize=True)


def photos_for(idea: dict) -> list[dict]:
    """Published photos for this date, in stop order."""
    wanted = DATE_PHOTOS.get(str(idea["id"])) or {}
    if not wanted:
        return []
    heroes = hero_index()
    stops = list(idea["stops"])
    food = idea.get("food") or {}
    if food.get("place") and food["place"] not in stops:
        stops.append(food["place"])
    photos = []
    for name in stops:
        url = wanted.get(name)
        if not url:
            continue
        hero = heroes.get(_url_key(url))
        if not hero:
            print(f"  date photo missing: {idea['id']} / {name}")
            continue
        with Image.open(hero["path"]) as probe:
            if probe.size[0] < 600:
                continue
        rel = f"assets/dates/{idea['id']}/{len(photos)}.jpg"
        _publish_hero(hero["path"], DOCS / rel)
        photos.append(
            {
                "stop": name,
                "title": hero["title"],
                "url": hero["url"],
                "src": rel,
            }
        )
    return photos


def photo_figure(photo: dict, root: str) -> str:
    src = html.escape(f"{root}{photo['src']}")
    title = html.escape(photo["title"])
    href = html.escape(photo["url"])
    return (
        f'<figure class="date-photo">'
        f'<a href="{href}" rel="noopener"><img src="{src}" alt="{title}"></a>'
        f'<figcaption><a href="{href}" rel="noopener">{title}</a></figcaption>'
        f"</figure>"
    )


def write_date_page(
    group: dict,
    idea: dict,
    known_places: set[str],
    points: dict[str, tuple[float, float, str]],
    features: list[dict],
) -> None:
    """One evening: the Karte pins around its stops, and a text drawn from the articles."""
    date_id = str(idea["id"])
    root = "../../"

    def stop_html(name: str) -> str:
        label = html.escape(name)
        if name in known_places:
            inner = f'<a href="{root}places/{html.escape(place_slug(name))}/">{label}</a>'
        else:
            inner = label
        link = hours_link(name)
        return f"{inner} {link}".strip() if link else inner

    stops = list(idea["stops"])
    food = idea.get("food") or {}
    if food.get("place") and food["place"] not in stops:
        stops.append(food["place"])
    photos = {photo["stop"]: photo for photo in photos_for(idea)}
    order_bits = []
    for name in stops:
        figure = photo_figure(photos[name], root) if name in photos else ""
        order_bits.append(f"<li>{stop_html(name)}{figure}</li>")
    food_block = ""
    if food.get("place"):
        where = f", {html.escape(food['where'])}" if food.get("where") else ""
        extra = f" {html.escape(food['line'])}" if food.get("line") else ""
        food_block = (
            f"<p class='date-food'><strong>Essen.</strong> "
            f"{html.escape(food['place'])}{where}.{extra} {hours_link(food['place'])}</p>"
        )
    pins = pins_for_stops(stops, features, points)
    payload = json.dumps(
        {"type": "FeatureCollection", "features": pins},
        ensure_ascii=False,
    ).replace("<", "\\u003c")
    colors_js = json.dumps(RUBRIK_COLORS, ensure_ascii=False)
    map_block = ""
    if pins:
        map_block = f"""
  <div id="date-map" class="date-map" role="region" aria-label="Pins zu diesem Abend"></div>
  <p class="meta">{len(pins)} {"Pin" if len(pins) == 1 else "Pins"}. Ein Klick öffnet die Beiträge. Beim Essen liegt der Link zu den Öffnungszeiten im Pin.</p>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>window.RUBRIK_COLORS = {colors_js}; window.DATE_PLACES = {payload};</script>
  <script>{DATE_MAP_JS}</script>
"""

    paragraphs = "".join(f"<p>{html.escape(para)}</p>" for para in idea.get("narrative") or [])
    sources = []
    for title, url in idea.get("sources") or []:
        sources.append(
            f'<li><a href="{html.escape(url)}" rel="noopener">{html.escape(title)}</a></li>'
        )
    source_block = ""
    if sources:
        source_block = (
            "<h2>Aus den Beiträgen</h2>"
            f"<ul class='date-sources'>{''.join(sources)}</ul>"
        )
    body = f"""
<main class="date-page">
  <p class="place-back"><a href="{root}ausgehen.html">← Ausgehen</a></p>
  <p class="place-kicker">{html.escape(group["label"])}</p>
  <h1>{html.escape(idea["title"])}</h1>
  <p class="meta">{html.escape(idea["when"])} · {html.escape(idea["shape"])}</p>
  <p class="lead">{html.escape(group["note"])}</p>
  {food_block}
  {map_block}
  <h2>Stopps</h2>
  <ol class="date-order">{''.join(order_bits)}</ol>
  <h2>Gelesen</h2>
  <p class="meta">Zusammengelesen aus den genannten Beiträgen. Was dort nicht steht, steht hier nicht.</p>
  <div class="date-narrative">{paragraphs}</div>
  {source_block}
  <p class="meta">Öffnungszeiten stehen hier nicht. Der Link beim Essen führt auf die Seite des Hauses.</p>
</main>
"""
    write(DOCS / "dates" / date_id / "index.html", page_shell(idea["title"], body, root=root))


def write_outings(
    known_places: set[str],
    features: list[dict],
    area_features: dict[str, dict],
) -> None:
    """Routes for going out. Each evening has its own page, with a map of the stops."""
    points: dict[str, tuple[float, float, str]] = {}
    for name, latlon in load_gazetteer_points().items():
        points[name] = (latlon[0], latlon[1], "")
    for feat in list(area_features.values()) + list(features):
        place = str(feat["properties"].get("place") or "").strip()
        if not place:
            continue
        lat, lon, slug = _feature_point(feat)
        points[place.casefold()] = (lat, lon, slug)

    def stop_html(name: str) -> str:
        label = html.escape(name)
        if name in known_places:
            inner = f'<a href="places/{html.escape(place_slug(name))}/">{label}</a>'
        else:
            inner = f"<span>{label}</span>"
        link = hours_link(name)
        return f"{inner} {link}".strip() if link else inner

    slot_order = [
        ("weekday-evening", "Wochentag abends"),
        ("weekday-afternoon", "Wochentag nachmittags"),
        ("weekend-afternoon", "Wochenende nachmittags"),
        ("weekend-morning", "Wochenende vormittags"),
    ]
    slot_buttons = [
        '<button type="button" data-slot="" aria-pressed="true">Alle</button>'
    ]
    for slot_id, slot_label in slot_order:
        slot_buttons.append(
            f'<button type="button" data-slot="{html.escape(slot_id)}" aria-pressed="false">'
            f"{html.escape(slot_label)}</button>"
        )
    jumps = []
    sections = []
    for group in OUTINGS:
        jumps.append(
            f'<li><a href="#{html.escape(group["id"])}">{html.escape(group["label"])}</a></li>'
        )
        cards = []
        for idea in group["ideas"]:
            write_date_page(group, idea, known_places, points, features)
            href = f'dates/{html.escape(idea["id"])}/'
            food = idea.get("food") or {}
            card_stops = list(idea["stops"])
            if food.get("place") and food["place"] not in card_stops:
                card_stops.append(food["place"])
            stops = "".join(f"<li>{stop_html(name)}</li>" for name in card_stops)
            food_html = ""
            if food.get("place"):
                where = f", {html.escape(food['where'])}" if food.get("where") else ""
                food_html = (
                    f"<p class='date-food'><strong>Essen.</strong> "
                    f"{html.escape(food['place'])}{where} {hours_link(food['place'])}</p>"
                )
            banner = ""
            shot = next(iter(photos_for(idea)), None)
            if shot:
                banner = (
                    f'<a class="date-banner" href="{href}">'
                    f'<img src="{html.escape(shot["src"])}" alt="{html.escape(idea["title"])}">'
                    f"</a>"
                )
            cards.append(
                f'<li class="date-card" data-slot="{html.escape(idea["slot"])}">'
                f"{banner}"
                f'<div class="date-card-body">'
                f'<h3><a href="{href}">{html.escape(idea["title"])}</a></h3>'
                f"<p class='meta'>{html.escape(idea['when'])} · {html.escape(idea['shape'])}</p>"
                f"{food_html}"
                f"<ul class='date-stops'>{stops}</ul>"
                f"<p>{html.escape(idea['text'])}</p>"
                f"</div>"
                "</li>"
            )
        sections.append(
            f'<section class="outing-section" id="{html.escape(group["id"])}">'
            f"<h2 class='outing-who'>{html.escape(group['label'])}</h2>"
            f"<p class='meta outing-note'>{html.escape(group['note'])}</p>"
            f"<ul class='date-list'>{''.join(cards)}</ul>"
            "</section>"
        )
    body = f"""
<main>
  <h1>Ausgehen</h1>
  <p class="lead">
    Wege durch den Kiez. Jeder hat eine eigene Seite: die Stopps auf einer Karte,
    und ein Text aus den Beiträgen auf mittendran.de.
    Öffnungszeiten stehen hier nicht. Der Link beim Essen führt auf die Seite des Hauses.
  </p>
  <div class="slot-filter" role="group" aria-label="Tageszeit">{''.join(slot_buttons)}</div>
  <ul class="outing-jump">{''.join(jumps)}</ul>
  {''.join(sections)}
</main>
<script>
document.querySelectorAll(".slot-filter button").forEach(function (btn) {{
  btn.addEventListener("click", function () {{
    var slot = btn.getAttribute("data-slot") || "";
    document.querySelectorAll(".slot-filter button").forEach(function (other) {{
      other.setAttribute("aria-pressed", other === btn ? "true" : "false");
    }});
    document.querySelectorAll(".date-card").forEach(function (card) {{
      card.hidden = slot !== "" && card.getAttribute("data-slot") !== slot;
    }});
    document.querySelectorAll(".outing-section").forEach(function (section) {{
      var any = false;
      section.querySelectorAll(".date-card").forEach(function (card) {{
        if (!card.hidden) any = true;
      }});
      section.hidden = !any;
    }});
  }});
}});
</script>
"""
    write(DOCS / "ausgehen.html", page_shell("Ausgehen", body, root=""))


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

    SITE_AREAS.clear()
    for name in ("Gleisdreieck", "Potsdamer Straße", "Potsdamer Platz"):
        feat = area_features.get(name)
        if not feat:
            continue
        counts: dict[str, int] = {}
        for art in feat.get("_articles_full") or feat["properties"].get("articles") or []:
            year = _year_of(str(art.get("date") or ""))
            if year:
                counts[year] = counts.get(year, 0) + 1
        SITE_AREAS.append(
            {
                "name": name,
                "slug": feat["properties"]["place_slug"],
                "years": sorted(counts.items(), reverse=True),
            }
        )

    # Place list pages (map pins + broad areas).
    pinned_names = {feat["properties"]["place"] for feat in features}
    for feat in features:
        props = feat["properties"]
        slug = props["place_slug"]
        arts = feat.get("_articles_full", props["articles"])
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
    for name in ("Gleisdreieck", "Potsdamer Straße", "Potsdamer Platz"):
        feat = area_features.get(name)
        if not feat:
            continue
        props = feat["properties"]
        arts = feat.get("_articles_full", props["articles"])
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

    write_outings(pinned_names | set(area_features), features, area_features)

    # Strip internal helpers before serializing geojson.
    clean_features = []
    for feat in features:
        feat.pop("_articles_full", None)
        clean_features.append(feat)
    features = clean_features
    geo = {"type": "FeatureCollection", "features": features}
    payload = json.dumps(geo, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")

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
