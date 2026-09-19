"use strict";

const form = document.querySelector("#evidence-form");
const tabs = document.querySelectorAll(".tab");
const pasteInput = document.querySelector("#paste-input");
const fileInput = document.querySelector("#file-input");
const message = document.querySelector("#evidence-message");
const list = document.querySelector("#evidence-list");
const count = document.querySelector("#evidence-count");
const preview = document.querySelector("#evidence-preview");
const settingsDialog = document.querySelector("#settings-dialog");
let mode = "text";
let evidence = [];
let extractedClaims = [];
let latestReport = null;
let recommendations = [];

document.querySelector("#generate-draft").addEventListener("click", async () => {
  const promptInput = document.querySelector("#prompt-input");
  const button = document.querySelector("#generate-draft");
  const generateMessage = document.querySelector("#generate-message");
  const draftInput = document.querySelector("#draft-answer");
  const prompt = promptInput.value.trim();
  if (!prompt) { generateMessage.textContent = "Enter a prompt before generating a draft."; return; }
  button.disabled = true; generateMessage.textContent = "Generating draft…";
  try {
    const response = await fetch("/api/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt }) });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "Draft generation failed.");
    draftInput.value = body.answer;
    generateMessage.textContent = "Draft generated. Finding relevant evidence sources…";
    await loadRecommendations(prompt);
    generateMessage.textContent = "Draft generated. Select sources or add your own evidence, then extract claims.";
  } catch (error) { generateMessage.textContent = error.message; }
  finally { button.disabled = false; }
});

async function loadRecommendations(prompt) {
  const listNode = document.querySelector("#recommendations-list");
  const copy = document.querySelector("#recommendations-copy");
  const messageNode = document.querySelector("#recommendations-message");
  const addButton = document.querySelector("#add-recommended-sources");
  copy.textContent = "Based on your prompt"; messageNode.textContent = "Searching for potential sources…";
  listNode.replaceChildren(); addButton.hidden = true;
  try {
    const response = await fetch("/api/sources/recommend", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt }) });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "Source recommendations could not be loaded.");
    recommendations = body.recommendations || [];
    if (!body.available) { messageNode.textContent = body.message || "Web source recommendations are unavailable. Add your own evidence below."; return; }
    if (!recommendations.length) { messageNode.textContent = "No web source recommendations were found. Add your own evidence below."; return; }
    messageNode.textContent = "Recommendations are not evidence and have not been retrieved.";
    addButton.hidden = false;
    recommendations.forEach((item) => {
      const row = document.createElement("div"); row.className = "recommendation";
      row.innerHTML = `<input type="checkbox" id="${escapeHtml(item.id)}" data-recommendation="${escapeHtml(item.id)}"><div><label for="${escapeHtml(item.id)}"><strong>${escapeHtml(item.title)}</strong>${item.is_official ? '<span class="official-badge">OFFICIAL DOMAIN</span>' : ''}</label><p>${escapeHtml(item.description || item.relevance_reason)}</p><small>${escapeHtml(item.domain)} · Selected sources are not yet retrieved</small></div><a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">Open</a>`;
      listNode.append(row);
    });
  } catch (error) { recommendations = []; messageNode.textContent = error.message; }
}

document.querySelector("#add-recommended-sources").addEventListener("click", async () => {
  const selected = [...document.querySelectorAll("[data-recommendation]:checked")].map((input) => input.dataset.recommendation);
  const messageNode = document.querySelector("#recommendations-message");
  if (!selected.length) { messageNode.textContent = "Select at least one recommended source first."; return; }
  const chosen = recommendations.filter((item) => selected.includes(item.id));
  const button = document.querySelector("#add-recommended-sources");
  button.disabled = true; messageNode.textContent = `Retrieving ${chosen.length} selected web source${chosen.length === 1 ? "" : "s"}…`;
  const outcomes = await Promise.all(chosen.map(async (item) => {
    try {
      const response = await fetch("/api/evidence/web", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: item.url, source_name: item.title }) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "RETRIEVAL FAILED");
      return { item: body };
    } catch (error) { return { error: error.message }; }
  }));
  const imported = outcomes.filter((outcome) => outcome.item).map((outcome) => outcome.item);
  const failed = outcomes.filter((outcome) => outcome.error);
  evidence.push(...imported); render();
  messageNode.textContent = `${imported.length} source${imported.length === 1 ? "" : "s"} imported as evidence${failed.length ? `; ${failed.length} source${failed.length === 1 ? "" : "s"} could not be retrieved.` : "."}`;
  button.disabled = false;
});

document.querySelector("#settings-button").addEventListener("click", () => settingsDialog.showModal());
document.querySelector("#close-settings").addEventListener("click", () => settingsDialog.close());
document.querySelector("#settings-model").value = localStorage.getItem("protocheck.preferredModel") || "";
document.querySelector("#settings-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const model = document.querySelector("#settings-model").value.trim();
  if (model) localStorage.setItem("protocheck.preferredModel", model);
  else localStorage.removeItem("protocheck.preferredModel");
  document.querySelector("#settings-api-key").value = "";
  document.querySelector("#settings-message").textContent = "Model preference saved locally. API keys are not stored.";
});

tabs.forEach((tab) => tab.addEventListener("click", () => {
  mode = tab.dataset.mode;
  tabs.forEach((item) => item.classList.toggle("active", item === tab));
  pasteInput.hidden = mode !== "text";
  fileInput.hidden = mode !== "file";
}));

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const sourceName = document.querySelector("#source-name").value;
  let response;
  try {
    if (mode === "text") {
      response = await fetch("/api/evidence/text", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content: document.querySelector("#evidence-content").value, source_name: sourceName || null }) });
    } else {
      const file = document.querySelector("#evidence-file").files[0];
      if (!file) throw new Error("Choose a TXT or PDF file first.");
      const payload = new FormData(); payload.append("file", file); payload.append("source_name", sourceName);
      response = await fetch("/api/evidence/upload", { method: "POST", body: payload });
    }
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "Evidence could not be added.");
    evidence.push(...body.items); form.reset(); message.textContent = `${body.items.length} evidence item${body.items.length === 1 ? "" : "s"} added.`; render();
  } catch (error) { message.textContent = error.message; }
});

async function removeEvidence(id) {
  const response = await fetch(`/api/evidence/${id}`, { method: "DELETE" });
  if (response.ok) { evidence = evidence.filter((item) => item.id !== id); render(); }
}
function render() {
  count.textContent = `${evidence.length} ITEM${evidence.length === 1 ? "" : "S"}`;
  list.replaceChildren();
  if (!evidence.length) { list.innerHTML = '<p class="empty-state">No evidence selected yet.</p>'; return; }
  evidence.forEach((item) => {
    const row = document.createElement("div"); row.className = "evidence-row";
    const provenance = item.url ? ` · ${escapeHtml(item.domain || item.url)}` : "";
    row.innerHTML = `<div><strong>${escapeHtml(item.source_name)}</strong><p>${item.source_type.replace("_", " ")} · ${item.character_count.toLocaleString()} characters${item.page_number ? ` · page ${item.page_number}` : ""}${provenance}</p></div><div><button class="link-button" data-view="${item.id}">View</button><button class="link-button danger" data-remove="${item.id}">Remove</button></div>`;
    list.append(row);
  });
}
list.addEventListener("click", (event) => {
  const id = event.target.dataset.view || event.target.dataset.remove; if (!id) return;
  const item = evidence.find((entry) => entry.id === id);
  if (event.target.dataset.remove) removeEvidence(id);
  if (event.target.dataset.view && item) { document.querySelector("#preview-title").textContent = item.title || item.source_name; document.querySelector("#preview-meta").textContent = `${item.source_type.replace("_", " ")}${item.url ? ` · ${item.url}` : ""}${item.file_name ? ` · ${item.file_name}` : ""}${item.page_number ? ` · page ${item.page_number}` : ""}`; document.querySelector("#preview-content").textContent = item.content; preview.showModal(); }
});
document.querySelector("#close-preview").addEventListener("click", () => preview.close());
function escapeHtml(value) { const node = document.createElement("span"); node.textContent = value; return node.innerHTML; }

document.querySelector("#extract-claims").addEventListener("click", async () => {
  const draft = document.querySelector("#draft-answer").value;
  const claimMessage = document.querySelector("#claim-message");
  const claimList = document.querySelector("#claims-list");
  const claimCount = document.querySelector("#claim-count");
  try {
    const response = await fetch("/api/claims/extract", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ draft_answer: draft }) });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "Claims could not be extracted.");
    extractedClaims = body.claims; latestReport = null; document.querySelector("#repair-button").hidden = true; claimList.replaceChildren(); claimCount.textContent = `${body.claims.length} CLAIM${body.claims.length === 1 ? "" : "S"} IDENTIFIED`;
    if (!body.claims.length) { claimList.innerHTML = '<div class="claim-icon">◇</div><div><strong>No factual claims identified.</strong><p>This draft contains no independently verifiable factual statements.</p></div>'; return; }
    body.claims.forEach((claim, index) => { const row = document.createElement("div"); row.className = "claim-row"; row.innerHTML = `<span>${String(index + 1).padStart(2, "0")}</span><div><strong>${escapeHtml(claim.text)}</strong><p>${escapeHtml(claim.claim_type)} · Extracted from draft sentence</p></div>`; claimList.append(row); });
    claimMessage.textContent = "Claims are ready for verification against selected evidence.";
  } catch (error) { claimMessage.textContent = error.message; claimCount.textContent = "NOT RUN"; }
});

document.querySelector("#run-verification").addEventListener("click", async () => {
  const messageNode = document.querySelector("#verification-message");
  const statusNode = document.querySelector("#verification-status");
  const reportStatus = document.querySelector("#report-status");
  const results = document.querySelector("#verification-results");
  if (!extractedClaims.length) { messageNode.textContent = "Extract at least one factual claim before verification."; return; }
  if (!evidence.length) { messageNode.textContent = "Add selected evidence before verification."; return; }
  statusNode.textContent = "ANALYZING"; messageNode.textContent = `Analyzing ${extractedClaims.length} claims against ${evidence.length} selected source${evidence.length === 1 ? "" : "s"}…`;
  try {
    const response = await fetch("/api/verify", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ claims: extractedClaims, selected_evidence: evidence }) });
    const report = await response.json(); if (!response.ok) throw new Error(report.detail || "Verification could not be completed.");
    renderVerification(report, results); statusNode.textContent = report.status; statusNode.className = `status ${report.status === "PASSED" ? "supported" : "warning"}`;
    const engineVerdict = document.querySelector("#engine-verdict");
    if (engineVerdict) engineVerdict.textContent = report.status === "PASSED" ? "SUPPORTED" : "ISSUES DETECTED";
    reportStatus.textContent = "VERIFIED AGAINST SELECTED EVIDENCE"; reportStatus.className = `status ${report.status === "PASSED" ? "supported" : "warning"}`;
    messageNode.textContent = report.summary;
    latestReport = report; document.querySelector("#repair-button").hidden = report.status === "PASSED";
  } catch (error) { statusNode.textContent = "NOT RUN"; statusNode.className = "status neutral"; messageNode.textContent = error.message; }
});

document.querySelector("#repair-button").addEventListener("click", async () => {
  const button = document.querySelector("#repair-button");
  const statusNode = document.querySelector("#repair-status");
  const output = document.querySelector("#repair-results");
  if (!latestReport) return;
  button.disabled = true; button.textContent = "Repairing & re-checking…"; statusNode.textContent = "RUNNING";
  try {
    const response = await fetch("/api/repair", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ original_prompt: document.querySelector("textarea[aria-label='Prompt']").value, original_draft: document.querySelector("#draft-answer").value, claims: extractedClaims, verification_report: latestReport, selected_evidence: evidence }) });
    const result = await response.json(); if (!response.ok) throw new Error(result.detail || "Repair could not be completed.");
    renderRepair(result, output); const verified = result.repaired_verification?.status === "PASSED"; statusNode.textContent = verified ? "VERIFIED FINAL ANSWER" : "REMAINING ISSUES"; statusNode.className = `status ${verified ? "supported" : "warning"}`;
  } catch (error) { output.innerHTML = `<div class="claim-icon">!</div><div><strong>Repair could not be completed.</strong><p>${escapeHtml(error.message)}</p></div>`; statusNode.textContent = "FAILED"; statusNode.className = "status warning"; }
  finally { button.disabled = false; button.textContent = "Fix & Regenerate"; }
});

function renderVerification(report, results) {
  results.replaceChildren();
  report.claims.forEach((item) => {
    const card = document.createElement("article"); const verdict = item.verdict.toLowerCase(); card.className = `verification-result ${verdict}`;
    const references = item.evidence.map((reference) => { const source = evidence.find((entry) => entry.id === reference.evidence_id); return `<div class="evidence-reference"><strong>${escapeHtml(reference.source_name)}</strong>${source?.url ? ` · ${escapeHtml(source.url)}` : ""}${reference.page_number ? ` · page ${reference.page_number}` : ""}<blockquote>${escapeHtml(reference.relevant_excerpt)}</blockquote></div>`; }).join("");
    card.innerHTML = `<div class="result-verdict"><span>${item.verdict === "SUPPORTED" ? "✓" : item.verdict === "CONTRADICTED" ? "✕" : "⚠"}</span> ${escapeHtml(item.verdict)}</div><p class="result-claim">“${escapeHtml(item.claim.text)}”</p><p class="result-reason">${escapeHtml(item.reason)}</p>${references}`;
    results.append(card);
  });
}

function renderRepair(result, output) {
  output.replaceChildren();
  if (result.repair_error) { output.innerHTML = `<div class="claim-icon">!</div><div><strong>Original verification preserved.</strong><p>${escapeHtml(result.repair_error)}</p></div>`; return; }
  const before = document.createElement("div"); before.className = "repair-column"; before.innerHTML = `<p class="eyebrow">BEFORE</p><strong>Original answer</strong><p>${escapeHtml(result.original_draft)}</p><small>${escapeHtml(result.original_verification.summary)}</small>`;
  const after = document.createElement("div"); after.className = "repair-column"; after.innerHTML = `<p class="eyebrow">AFTER · RE-VERIFIED</p><strong>Repaired answer</strong><p>${escapeHtml(result.repaired_draft)}</p><small>${escapeHtml(result.repaired_verification.summary)}</small>`;
  const summary = document.createElement("div"); summary.className = "repair-summary"; summary.innerHTML = `<strong>${result.repaired_verification.status === "PASSED" ? "VERIFIED FINAL ANSWER" : "REMAINING ISSUES"}</strong><p>Repair iteration${result.repair_summary.iterations === 1 ? "" : "s"}: ${result.repair_summary.iterations} of ${result.repair_summary.max_attempts} · ${result.repair_summary.fixed_claims} fixed · ${result.repair_summary.removed_claims} removed · ${result.repair_summary.still_failed_claims} still failed · ${result.repair_summary.new_failed_claims} new failed</p>`;
  output.append(before, after, summary);
  result.repair_summary.outcomes.forEach((item) => { const row = document.createElement("p"); row.className = "repair-outcome"; row.textContent = `${item.original_claim_id}: ${item.outcome.replaceAll("_", " ")} — ${item.detail}`; output.append(row); });
}

// The progress rail reflects the section the user is actually viewing. It is
// presentation-only; all product state remains in the existing API workflow.
const journeyStages = document.querySelectorAll(".stage[data-stage]");
const stageIndicator = document.querySelector("#stage-indicator");
const stageLinks = document.querySelectorAll("[data-stage-link]");
if ("IntersectionObserver" in window) {
  const observer = new IntersectionObserver((entries) => {
    const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (!visible) return;
    const stage = visible.target.dataset.stage;
    stageIndicator.textContent = `${String(stage).padStart(2, "0")} / 07`;
    stageLinks.forEach((link) => link.classList.toggle("active", link.dataset.stageLink === stage));
  }, { threshold: 0.45 });
  journeyStages.forEach((stage) => observer.observe(stage));
}

// Screen-by-screen presentation navigation. This only changes which existing
// workspace is visible; it does not reset or alter the application workflow.
const screenStyle = document.createElement("style");
screenStyle.textContent = `
  .journey { padding-bottom: 0; }
  .stage { display: none; min-height: calc(100svh - 66px); border-bottom: 0; }
  .stage.active { display: block; }
  .completion { display: none; }
  .stage-navigation { display: flex; justify-content: space-between; align-items: center; margin-top: 28px; }
  .stage-navigation .secondary-action { visibility: hidden; }
  .stage-navigation .secondary-action.visible { visibility: visible; }
  #recommendations-list { max-height: 330px; overflow-y: auto; padding-right: 8px; }
  #recommendations-list .recommendation p { display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical; overflow: hidden; }
  #repair-button, .stage-navigation .secondary-action { color: #101522 !important; background: #fff !important; }
  .engine.humanized-engine { position: relative; overflow: hidden; align-items: flex-start; background: linear-gradient(145deg, #eeebff 0%, #fbfaff 58%, #f5f4f0 100%); }
  .engine.humanized-engine::before { content: "PROTOCHECK"; color: #6d5ce7; letter-spacing: .16em; font: 800 10px/1 Inter, ui-sans-serif, sans-serif; }
  .engine.humanized-engine .human-engine-copy { max-width: 13ch; margin: auto 0; color: #101522; font-family: "Canela Deck", Iowan Old Style, Palatino Linotype, Georgia, serif; font-size: clamp(30px, 3vw, 47px); font-weight: 700; line-height: .98; letter-spacing: -.045em; text-wrap: balance; }
  .engine.humanized-engine::after { content: ""; position: absolute; right: -45px; bottom: -45px; width: 170px; height: 170px; border: 1px solid #c8c0fa; border-radius: 50%; box-shadow: 0 0 0 25px #eeeaff80, 0 0 0 50px #eeeaff45; }
  .site-header .header-actions { margin-left: auto; }
  .site-header .brand { font-family: "Canela Deck", Iowan Old Style, Palatino Linotype, Georgia, serif; font-size: 22px; font-weight: 800; }
  .site-header .brand-mark, #stage-indicator, .stage-progress { display: none !important; }
  @media (max-width: 760px) { .stage { min-height: calc(100svh - 66px); } .stage-navigation { margin-top: 20px; } }
`;
document.head.append(screenStyle);

// Keep the Stage 2 source-import label legible against its white button.
document.querySelector("#add-recommended-sources").style.color = "#000";

function showStage(stageNumber, updateHash = true) {
  const number = Math.max(1, Math.min(7, Number(stageNumber) || 1));
  journeyStages.forEach((stage) => stage.classList.toggle("active", Number(stage.dataset.stage) === number));
  stageIndicator.textContent = `${String(number).padStart(2, "0")} / 07`;
  stageLinks.forEach((link) => link.classList.toggle("active", Number(link.dataset.stageLink) === number));
  if (updateHash) history.replaceState(null, "", `#${journeyStages[number - 1].id}`);
  typeStageHeading(journeyStages[number - 1]);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

const typingHeadings = new WeakMap();
document.querySelector(".product-label")?.remove();
document.querySelector(".brand-mark")?.remove();
document.querySelector("#stage-indicator")?.remove();
document.querySelector(".stage-progress")?.remove();
document.querySelectorAll(".stage-copy .eyebrow").forEach((label) => {
  label.textContent = label.textContent.replace(/^\s*\d{2}\s*\/\s*07\s*/, "");
});
const understandEngine = document.querySelector("#understand .engine");
if (understandEngine) {
  understandEngine.classList.add("humanized-engine");
  understandEngine.innerHTML = '<p class="human-engine-copy">give your own prompt to chat interface</p>';
}
const gatherEngine = document.querySelector("#gather .engine");
if (gatherEngine) {
  gatherEngine.classList.add("humanized-engine");
  gatherEngine.innerHTML = '<p class="human-engine-copy">Protofine ai system recommend related sources according to your prompt</p>';
}
const generateEngine = document.querySelector("#generate .engine");
if (generateEngine) {
  generateEngine.classList.add("humanized-engine");
  generateEngine.innerHTML = '<p class="human-engine-copy">unverified response from llm</p>';
}
const groundEngine = document.querySelector("#ground .engine");
if (groundEngine) {
  groundEngine.classList.add("humanized-engine");
  groundEngine.innerHTML = '<p class="human-engine-copy">only selected sources enter the trusted evidence boundary</p>';
}
const decomposeEngine = document.querySelector("#decompose .engine");
if (decomposeEngine) {
  decomposeEngine.classList.add("humanized-engine");
  decomposeEngine.innerHTML = '<p class="human-engine-copy">claims are extracted from the output, one fact at a time</p>';
}
const verifyEngine = document.querySelector("#verify .engine");
if (verifyEngine) {
  verifyEngine.classList.add("humanized-engine");
  verifyEngine.innerHTML = '<p class="human-engine-copy">selected evidence checks every claim before a verdict</p>';
}
const repairEngine = document.querySelector("#repair .engine");
if (repairEngine) {
  repairEngine.classList.add("humanized-engine");
  repairEngine.innerHTML = '<p class="human-engine-copy">repair, re-verify, and return an evidence-grounded answer</p>';
}
const understandLede = document.querySelector("#understand .lede");
if (understandLede) understandLede.textContent = "Start with a question worth checking.";
document.querySelectorAll("#understand .stage-copy h1, #gather .stage-copy h2, #ground .stage-copy h2, #generate .stage-copy h2, #decompose .stage-copy h2, #verify .stage-copy h2").forEach((heading) => {
  if (heading.closest("#understand")) heading.textContent = "Loop Engineering System for Hallucination Safe";
  typingHeadings.set(heading, heading.textContent.trim());
});

function typeStageHeading(stage) {
  const heading = stage.querySelector(".stage-copy h1, .stage-copy h2");
  const text = heading && typingHeadings.get(heading);
  if (!heading || !text || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (heading._typingTimer) window.clearTimeout(heading._typingTimer);
  heading.textContent = "";
  let index = 0;
  const typeNext = () => {
    heading.textContent = text.slice(0, ++index);
    if (index < text.length) heading._typingTimer = window.setTimeout(typeNext, 24);
  };
  typeNext();
}

journeyStages.forEach((stage, index) => {
  const navigation = document.createElement("nav");
  navigation.className = "stage-navigation";
  navigation.setAttribute("aria-label", "Stage navigation");
  navigation.innerHTML = `<button class="secondary-action${index ? " visible" : ""}" type="button" data-stage-back="${index + 1}">← Back</button><button class="primary-action" type="button" data-stage-next="${index + 1}">${index === 6 ? "Start again" : "Next"} <span>→</span></button>`;
  stage.append(navigation);
});

document.addEventListener("click", (event) => {
  const next = event.target.closest("[data-stage-next]");
  const back = event.target.closest("[data-stage-back]");
  const link = event.target.closest("[data-stage-link]");
  if (next) { showStage(Number(next.dataset.stageNext) === 7 ? 1 : Number(next.dataset.stageNext) + 1); }
  if (back) { showStage(Number(back.dataset.stageBack) - 1); }
  if (link) { event.preventDefault(); showStage(link.dataset.stageLink); }
});

document.querySelector(".brand").addEventListener("click", (event) => { event.preventDefault(); showStage(1); });
document.querySelector(".header-actions a").addEventListener("click", (event) => { event.preventDefault(); showStage(7); });

const initialStage = Number((window.location.hash.match(/(?:understand|gather|ground|generate|decompose|verify|repair)/) || [])[0] && ({ understand: 1, gather: 2, ground: 3, generate: 4, decompose: 5, verify: 6, repair: 7 })[window.location.hash.slice(1)]);
showStage(initialStage || 1, false);
