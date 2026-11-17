/* VEIN SEARCH frontend logic (vanilla JS, no build step) */
"use strict";

const $ = (sel) => document.querySelector(sel);

const state = {
  favourites: new Set(),
  compare: [],          // product ids chosen for comparison (max 3)
  lastResults: [],      // last search results (product objects with similarity)
  searching: false,
};

/* ---------------- helpers ---------------- */
async function api(path, opts) {
  const res = await fetch(path, opts);
  let body = null;
  try { body = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) {
    const msg = (body && (body.detail?.reason || body.detail)) || `Request failed (${res.status})`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return body;
}

function toast(msg, ms = 2600) {
  const el = $("#toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (el.hidden = true), ms);
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------------- favourites ---------------- */
async function loadFavourites() {
  try {
    const data = await api("/api/favourites");
    state.favourites = new Set(data.favourites.map((p) => p.id));
    updateFavCount();
  } catch (e) { console.warn("favourites load failed", e); }
}

function updateFavCount() {
  $("#favCount").textContent = state.favourites.size;
}

async function toggleFavourite(productId, btn) {
  try {
    if (state.favourites.has(productId)) {
      await api(`/api/favourites/${productId}`, { method: "DELETE" });
      state.favourites.delete(productId);
      toast("Removed from favourites");
    } else {
      await api(`/api/favourites/${productId}`, { method: "POST" });
      state.favourites.add(productId);
      toast("Saved to favourites ♥");
    }
    updateFavCount();
    document.querySelectorAll(`[data-fav="${productId}"]`).forEach((b) =>
      b.classList.toggle("is-fav", state.favourites.has(productId)));
  } catch (e) { toast(`Could not update favourite: ${e.message}`); }
}

/* ---------------- upload & search ---------------- */
function setPreviewImage(objectUrl, name, statusHtml) {
  $("#dzIdle").hidden = true;
  $("#dzPreview").hidden = false;
  $("#previewImg").src = objectUrl;
  $("#previewName").textContent = name;
  $("#previewStatus").innerHTML = statusHtml;
}

function resetDropzone() {
  $("#dzIdle").hidden = false;
  $("#dzPreview").hidden = true;
  $("#previewImg").src = "";
}

async function searchWithBytes(bytes, filename, displayName, mime = "image/jpeg") {
  if (state.searching) return;
  state.searching = true;
  const objectUrl = URL.createObjectURL(new Blob([bytes], { type: mime }));
  setPreviewImage(objectUrl, displayName, '<span class="spinner"></span>Analysing visual character…');
  $("#resultsTitle").textContent = "Reading the stone's character…";
  const grid = $("#resultsGrid");
  grid.innerHTML = '<div class="empty-state"><p>Comparing colour, veins, pattern and texture across the catalogue…</p></div>';

  const form = new FormData();
  form.append("file", new Blob([bytes], { type: mime }), filename);
  try {
    const data = await api("/api/search", { method: "POST", body: form });
    renderResults(data);
    $("#previewStatus").textContent = `Matched in ${data.meta.elapsed_ms} ms · ${data.meta.model}`;
    $("#resultsTitle").textContent = `Top ${data.results.length} matches for your reference`;
  } catch (e) {
    showErrorState(e.message);
    $("#previewStatus").textContent = "Search failed";
    $("#resultsTitle").textContent = "Something went wrong";
    toast(e.message);
  } finally {
    state.searching = false;
  }
}

async function handleFile(file) {
  if (!file) return;
  if (file.size > 10 * 1024 * 1024) {
    toast("File too large (max 10 MB).");
    return;
  }
  // Trust the file's magic bytes, not the browser-reported MIME type
  // (browsers report HEIC as image/heic, JPEG as image/jpg, or "" at times).
  const head = new Uint8Array(await file.slice(0, 16).arrayBuffer());
  const type = sniffImageType(head);
  if (!type) {
    toast("Unsupported file. Please use a photo (JPEG, PNG, WebP or HEIC).");
    return;
  }
  const buf = await file.arrayBuffer();
  const mime = { jpeg: "image/jpeg", png: "image/png", webp: "image/webp", heic: "image/heic" }[type];
  searchWithBytes(new Uint8Array(buf), file.name || `upload.${type}`, file.name || "Uploaded photo", mime);
}

function sniffImageType(head) {
  if (head.length >= 3 && head[0] === 0xff && head[1] === 0xd8 && head[2] === 0xff) return "jpeg";
  if (head.length >= 8 && head[0] === 0x89 && head[1] === 0x50 && head[2] === 0x4e && head[3] === 0x47) return "png";
  if (head.length >= 12 && head[0] === 0x52 && head[1] === 0x49 && head[2] === 0x46 && head[3] === 0x46
      && head[8] === 0x57 && head[9] === 0x45 && head[10] === 0x42 && head[11] === 0x50) return "webp";
  if (head.length >= 12 && head[4] === 0x66 && head[5] === 0x74 && head[6] === 0x79 && head[7] === 0x70) {
    const brand = String.fromCharCode(head[8], head[9], head[10], head[11]);
    if (/^(hei[cfmx]|hevc|hevx|mif1|msf1|heis)/.test(brand)) return "heic";
  }
  return null;
}

async function handleSample(p) {
  try {
    const res = await fetch(p.image_url);
    if (!res.ok) throw new Error("sample fetch failed");
    const buf = await res.arrayBuffer();
    searchWithBytes(new Uint8Array(buf), `${p.id}.jpg`, `Sample: ${p.name}`);
  } catch (e) {
    toast(`Could not load sample: ${e.message}`);
  }
}

function showErrorState(msg) {
  $("#resultsGrid").innerHTML =
    `<div class="error-state"><strong>Search failed.</strong> ${esc(msg)}</div>`;
}

/* ---------------- rendering ---------------- */
function simBadgeClass(p) {
  return p.is_synthetic ? "badge-synthetic" : "badge-source";
}
function simBadgeText(p) {
  return p.is_synthetic ? "Synthetic sample" : "Licensed photo";
}

function renderResults(data) {
  state.lastResults = data.results;
  $("#resultsMeta").hidden = false;
  $("#scoreNote").hidden = false;
  $("#metaText").textContent = `${data.meta.model} · ${data.meta.store} · ${data.meta.elapsed_ms} ms`;

  const grid = $("#resultsGrid");
  grid.innerHTML = data.results.map((p, i) => {
    const sim = p.similarity;
    const barWidth = Math.max(0, Math.min(1, (sim + 1) / 2)) * 100;
    const isFav = state.favourites.has(p.id);
    const inCompare = state.compare.includes(p.id);
    return `
    <article class="result-card" style="animation-delay:${i * 45}ms" data-id="${esc(p.id)}">
      <img class="rc-img" src="${esc(p.image_url)}" alt="${esc(p.name)}"
           loading="lazy" data-detail="${esc(p.id)}" title="View details" />
      <div class="rc-body">
        <div class="rc-title-row">
          <h3 class="rc-name">${esc(p.name)}</h3>
          <span class="rc-badge ${simBadgeClass(p)}">${simBadgeText(p)}</span>
        </div>
        <p class="rc-sub">${esc([p.category, p.colour_family].filter(Boolean).join(" · ")) || "—"}${p.is_synthetic ? "" : ""}</p>
        <div class="sim-row">
          <div class="sim-label"><span>Visual similarity</span><span class="sim-value">${sim.toFixed(3)}</span></div>
          <div class="sim-bar"><div class="sim-fill" style="width:${barWidth.toFixed(1)}%"></div></div>
        </div>
        <div class="rc-actions">
          <button class="ghost-btn" data-detail="${esc(p.id)}">Details</button>
          <button class="ghost-btn" data-compare="${esc(p.id)}">${inCompare ? "✓ Compare" : "Compare"}</button>
          <button class="ghost-btn fav-btn ${isFav ? "is-fav" : ""}" data-fav="${esc(p.id)}"
                  aria-label="Toggle favourite">
            <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true"><path fill="currentColor" d="M12 21s-7.5-4.7-9.7-9A5.6 5.6 0 0 1 12 6.6 5.6 5.6 0 0 1 21.7 12c-2.2 4.3-9.7 9-9.7 9z"/></svg>
          </button>
        </div>
      </div>
    </article>`;
  }).join("");

  // refresh compare buttons text
  updateCompareButtons();
}

function updateCompareButtons() {
  document.querySelectorAll("[data-compare]").forEach((btn) => {
    const on = state.compare.includes(btn.dataset.compare);
    btn.textContent = on ? "✓ In compare" : "Compare";
    btn.style.borderColor = on ? "var(--accent)" : "";
  });
}

/* ---------------- product details ---------------- */
function provenanceHtml(p) {
  if (p.is_synthetic) {
    return `<div class="prov-block">⚖️ <strong>Synthetic sample.</strong>
      ${esc(p.description || "")} This is <strong>not a real product</strong> — it was generated
      procedurally for this POC to demonstrate search behaviour. Origin/finish fields describe the
      rendered texture only.</div>`;
  }
  const prov = p.provenance || {};
  return `<div class="prov-block">⚖️ <strong>Image provenance:</strong>
    ${esc(prov.artist || "unknown author")} · License: ${esc(prov.license || "—")} ·
    Source: <a href="${esc(prov.source_page || "#")}" target="_blank" rel="noopener">Wikimedia Commons</a>
    (file: ${esc(prov.title || "")}). Description on record: ${esc(p.description || "none")}.
    Fetched ${esc(prov.fetched || "")}.</div>`;
}

function productDetailHtml(p, similarity) {
  const facts = [
    ["Category", p.category],
    ["Colour family", p.colour_family],
    ["Finish", p.finish],
    ["Origin", p.origin],
    ["Record ID", p.id],
    ...(similarity !== undefined ? [["Similarity", similarity.toFixed(4) + " (cosine, not a probability)"]] : []),
  ].map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v ?? "—")}</dd>`).join("");
  return `
    <h3 class="dlg-title">${esc(p.name)}</h3>
    <button class="close-btn" data-close>Close ✕</button>
    <div class="detail-grid">
      <img src="${esc(p.image_url)}" alt="${esc(p.name)}" />
      <div>
        <dl class="detail-facts">${facts}
          ${provenanceHtml(p)}
        </dl>
        <div class="rc-actions" style="margin-top:14px">
          <button class="ghost-btn fav-btn ${state.favourites.has(p.id) ? "is-fav" : ""}"
                  data-fav="${esc(p.id)}">
            <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true"><path fill="currentColor" d="M12 21s-7.5-4.7-9.7-9A5.6 5.6 0 0 1 12 6.6 5.6 5.6 0 0 1 21.7 12c-2.2 4.3-9.7 9-9.7 9z"/></svg>
            Favourite
          </button>

          <button class="ghost-btn" data-compare="${esc(p.id)}">Add to compare</button>
        </div>
      </div>
    </div>`;
}

function openDetail(productId) {
  const p = state.lastResults.find((r) => r.id === productId) ||
            catalogCache.find((r) => r.id === productId);
  if (!p) { toast("Product details unavailable"); return; }
  $("#detailBody").innerHTML = productDetailHtml(p, p.similarity);
  $("#detailDialog").showModal();
}

/* ---------------- compare ---------------- */
async function toggleCompare(productId) {
  const idx = state.compare.indexOf(productId);
  if (idx >= 0) state.compare.splice(idx, 1);
  else {
    if (state.compare.length >= 3) { toast("Compare holds up to 3 products"); return; }
    if (!state.compare.length) { /* first item */ }
    state.compare.push(productId);
    if (state.compare.length === 3) openCompare();
  }
  updateCompareButtons();
}

async function openCompare() {
  if (state.compare.length < 2) { toast("Select at least 2 products to compare"); return; }
  const ps = state.compare
    .map((id) => state.lastResults.find((r) => r.id === id) || catalogCache.find((r) => r.id === id))
    .filter(Boolean);
  if (ps.length < 2) { toast("Select at least 2 products to compare"); return; }

  const rows = [
    ["Image", (p) => `<img src="${esc(p.image_url)}" alt="${esc(p.name)}" />`],
    ["Name", (p) => `<span class="cmp-name">${esc(p.name)}</span>`],
    ["Similarity", (p) => p.similarity !== undefined ? p.similarity.toFixed(3) : "—"],
    ["Category", (p) => esc(p.category ?? "—")],
    ["Colour family", (p) => esc(p.colour_family ?? "—")],
    ["Finish", (p) => esc(p.finish ?? "—")],
    ["Origin", (p) => esc(p.origin ?? "—")],
    ["Type", (p) => p.is_synthetic ? "Synthetic sample" : "Licensed photo"],
  ];
  $("#compareBody").innerHTML = `
    <h3 class="dlg-title">Compare stones</h3>
    <button class="close-btn" data-close>Close ✕</button>
    <table><thead><tr><th></th>${ps.map((p) => `<th>${esc(p.name)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(([label, fn]) =>
      `<tr><th>${label}</th>${ps.map((p) => `<td>${fn(p)}</td>`).join("")}</tr>`).join("")}
    </tbody></table>
    <p class="rc-sub" style="margin-top:12px">Similarity shown relative to your last uploaded reference photo (— for items added later). Cosine similarity is a ranking, not a probability.</p>`;
  $("#compareDialog").showModal();
}

/* ---------------- favourites drawer ---------------- */
async function openFavourites() {
  let items = [];
  try {
    const data = await api("/api/favourites");
    items = data.favourites;
  } catch (e) { toast(e.message); return; }
  $("#favBody").innerHTML = `
    <h3 class="dlg-title">Your favourites</h3>
    <button class="close-btn" data-close>Close ✕</button>
    ${items.length ? items.map((p) => `
      <div class="fav-item">
        <img src="${esc(p.image_url)}" alt="${esc(p.name)}" data-detail="${esc(p.id)}" style="cursor:pointer" />
        <div class="grow">
          <strong>${esc(p.name)}</strong>
          <p class="rc-sub">${esc(p.category ?? "")} ${p.is_synthetic ? "· <span class='rc-badge badge-synthetic'>Synthetic</span>" : ""}</p>
        </div>
        <button class="ghost-btn small" data-fav="${esc(p.id)}">Remove</button>
      </div>`).join("")
    : '<p class="rc-sub">No favourites yet — tap ♥ on any result card.</p>'}`;
  $("#favDialog").showModal();
}

/* ---------------- samples & catalogue ---------------- */
let catalogCache = [];

async function loadSamples() {
  try {
    const data = await api("/api/samples");
    $("#sampleStrip").innerHTML = data.samples.map((p) => `
      <img class="sample-thumb" src="${esc(p.image_url)}" alt="Try ${esc(p.name)}"
           title="Try ${esc(p.name)}" data-sample="${esc(p.id)}" />`).join("");
    catalogCache = data.samples;
  } catch (e) { console.warn("samples failed", e); }
}

/* ---------------- dialog close wiring ---------------- */
document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-close]");
  if (btn) btn.closest("dialog").close();
});

/* ---------------- events ---------------- */
function wire() {
  const dz = $("#dropZone");
  const fi = $("#fileInput");
  dz.addEventListener("click", () => fi.click());
  dz.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") fi.click(); });
  dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("dragover"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("dragover"));
  dz.addEventListener("drop", (e) => {
    e.preventDefault(); dz.classList.remove("dragover");
    handleFile(e.dataTransfer.files[0]);
  });
  fi.addEventListener("change", () => handleFile(fi.files[0]));
  $("#clearBtn").addEventListener("click", (e) => { e.stopPropagation(); resetDropzone(); });
  $("#scoreInfoBtn").addEventListener("click", () => { $("#scoreNote").hidden = false; });

  $("#favBtn").addEventListener("click", openFavourites);

  document.addEventListener("click", (e) => {
    const fav = e.target.closest("[data-fav]");
    if (fav) { toggleFavourite(fav.dataset.fav, fav); return; }
    const det = e.target.closest("[data-detail]");
    if (det) { openDetail(det.dataset.detail); return; }
    const cmp = e.target.closest("[data-compare]");
    if (cmp) { toggleCompare(cmp.dataset.compare); return; }
    const smp = e.target.closest("[data-sample]");
    if (smp) {
      const s = catalogCache.find((x) => x.id === smp.dataset.sample);
      if (s) handleSample(s);
    }
  });
}

wire();
loadFavourites();
loadSamples();
