const $ = (selector) => document.querySelector(selector);
const localHost = ["localhost", "127.0.0.1", "::1"].includes(location.hostname);
const hosted = !localHost;
const state = { items: [], scanId: null, operationId: null, sample: false };
const sampleItems = [
  { id: "sample-1", original: "Q3 notes FINAL v2.xlsx", category: "Spreadsheets", new_name: "Q3-notes.xlsx", reason: "Removed obvious trailing version markers.", size: "184 KB" },
  { id: "sample-2", original: "IMG_0421 copy.jpg", category: "Images", new_name: "IMG-0421.jpg", reason: "Kept the camera number; removed the duplicate marker.", size: "3.4 MB" },
  { id: "sample-3", original: "voice memo 2.m4a", category: "Audio", new_name: "voice-memo.m4a", reason: "Shortened the filename without changing its format.", size: "8.1 MB" },
  { id: "sample-4", original: "tax_receipt_scan.pdf", category: "Documents", new_name: "tax-receipt-scan.pdf", reason: "Made the existing words easier to scan.", size: "620 KB" },
  { id: "sample-5", original: "website mockup NEW 4.png", category: "Design", new_name: "website-mockup.png", reason: "Removed the uncertain version suffix.", size: "2.2 MB" },
  { id: "sample-6", original: "source-files.zip", category: "Archives", new_name: "source-files.zip", reason: "No clear cleanup needed; the name stays as it is.", size: "18 MB" },
];

function notice(message, kind = "error") {
  const box = $("#feedback");
  box.textContent = message;
  box.classList.toggle("success", kind === "success");
  box.hidden = false;
}
function clearNotice() { $("#feedback").hidden = true; }
function setBusy(button, busy, label) {
  button.disabled = busy;
  if (busy) { button.dataset.previous = button.innerHTML; button.textContent = label; }
  else if (button.dataset.previous) { button.innerHTML = button.dataset.previous; delete button.dataset.previous; }
}
function bytesLabel(bytes) {
  if (typeof bytes === "string") return bytes;
  if (!Number.isFinite(bytes)) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024, unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit++; }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unit]}`;
}
function renderRows(items, { sample = false } = {}) {
  state.items = items.map((item) => ({ ...item, selected: true }));
  state.sample = sample;
  $("#empty-state").hidden = true;
  $("#results").hidden = false;
  $("#result-eyebrow").textContent = sample ? "A sample tidy-up plan" : "Your proposed plan";
  $("#results-title").textContent = sample ? "A little less pile." : "Here’s what the model suggests.";
  $("#result-count").textContent = `${items.length} ${items.length === 1 ? "file" : "files"} · review before moving`;
  $("#footnote").textContent = sample ? "Sample only. No files move in this hosted demo." : "Nothing moves until you say so. You can undo this pass.";
  $("#apply-button").hidden = sample;
  $("#undo-button").hidden = !state.operationId || sample;
  const body = $("#file-rows");
  body.replaceChildren();
  for (const item of state.items) {
    const row = document.createElement("tr");
    const checkCell = document.createElement("td"); checkCell.className = "check-col";
    const checkbox = document.createElement("input"); checkbox.className = "file-row-checkbox"; checkbox.type = "checkbox"; checkbox.checked = true; checkbox.setAttribute("aria-label", `Include ${item.original}`);
    checkbox.addEventListener("change", () => { item.selected = checkbox.checked; });
    checkCell.append(checkbox);
    const from = document.createElement("td");
    const oldName = document.createElement("span"); oldName.className = "file-name"; oldName.textContent = item.original;
    const sub = document.createElement("span"); sub.className = "file-sub"; sub.textContent = bytesLabel(item.bytes ?? item.size);
    from.append(oldName, sub);
    const to = document.createElement("td");
    const dest = document.createElement("div"); dest.className = "destination";
    const folder = document.createElement("span"); folder.className = "folder-badge"; folder.textContent = "↳";
    const destText = document.createElement("span"); destText.className = "destination-name"; destText.textContent = `${item.category}/${item.new_name}`;
    dest.append(folder, destText); to.append(dest);
    const why = document.createElement("td"); why.className = "reason";
    why.textContent = item.reason || "A tidy suggestion based on the filename and file type.";
    if (Number.isFinite(item.confidence)) { const confidence = document.createElement("div"); confidence.className = "confidence"; confidence.textContent = `${Math.round(item.confidence * 100)}% confidence`; why.append(confidence); }
    row.append(checkCell, from, to, why); body.append(row);
  }
}
async function api(path, payload) {
  const response = await fetch(path, { method: payload ? "POST" : "GET", headers: payload ? { "Content-Type": "application/json" } : {}, body: payload ? JSON.stringify(payload) : undefined });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status}).`);
  return result;
}
async function initialize() {
  if (hosted) {
    $("#local-controls").hidden = true;
    $("#hosted-note").hidden = false;
    $("#runtime-label").textContent = "Sample mode · local AI";
    return;
  }
  $("#hosted-note").hidden = true;
  try {
    const health = await api("/api/health");
    const select = $("#model-select"); select.replaceChildren();
    for (const model of health.models || []) {
      const option = document.createElement("option"); option.value = model; option.textContent = model; select.append(option);
    }
    if (health.models?.length) {
      select.value = health.models.includes(health.default_model) ? health.default_model : health.models[0];
      $("#runtime-label").textContent = "Local · Ollama connected";
    } else {
      const option = document.createElement("option"); option.value = ""; option.textContent = "Start Ollama to continue"; select.append(option);
      $("#runtime-label").textContent = "Start local Ollama";
    }
    if (health.suggested_folder) $("#folder-path").value = health.suggested_folder;
  } catch (_) {
    $("#runtime-label").textContent = "Local demo · start the server";
    const select = $("#model-select"); select.replaceChildren();
    const option = document.createElement("option"); option.value = ""; option.textContent = "Ollama connection unavailable"; select.append(option);
  }
}
async function scanAndPlan() {
  clearNotice();
  const path = $("#folder-path").value.trim();
  const model = $("#model-select").value;
  if (!path) return notice("Add the full path to a folder first. The Downloads folder is filled in as a starting point.");
  if (!model) return notice("SlothSort needs Ollama running with a local model installed. Try the sample pile while you set it up.");
  const button = $("#scan-button"); setBusy(button, true, "Taking a look…");
  try {
    const scanned = await api("/api/scan", { path });
    if (!scanned.items.length) { $("#results").hidden = true; $("#empty-state").hidden = false; return notice("This folder is already peaceful. I didn't find any loose files at the top level.", "success"); }
    const plan = await api("/api/plan", { scan_id: scanned.scan_id, model });
    state.scanId = scanned.scan_id; state.operationId = null;
    renderRows(plan.items);
    notice(`A plan for ${plan.items.length} files is ready. Check the names and destinations before tidying.`, "success");
  } catch (error) { notice(error.message); }
  finally { setBusy(button, false); }
}
async function applyPlan() {
  clearNotice();
  const selected = state.items.filter((item) => item.selected).map((item) => item.id);
  if (!selected.length) return notice("Select at least one file to tidy.");
  const button = $("#apply-button"); setBusy(button, true, "Tidying…");
  try {
    const result = await api("/api/apply", { scan_id: state.scanId, selected });
    state.operationId = result.operation_id || null;
    $("#undo-button").hidden = !state.operationId;
    notice(result.message, "success");
    $("#footnote").textContent = "This pass can be undone until you close the app.";
    $("#apply-button").hidden = true;
    $("#scan-button").textContent = "Scan another folder →";
  } catch (error) { notice(error.message); }
  finally { setBusy(button, false); }
}
async function undoPlan() {
  clearNotice();
  const button = $("#undo-button"); setBusy(button, true, "Undoing…");
  try {
    const result = await api("/api/undo", { operation_id: state.operationId });
    state.operationId = null; $("#undo-button").hidden = true; $("#apply-button").hidden = false;
    notice(result.message, "success");
  } catch (error) { notice(error.message); }
  finally { setBusy(button, false); }
}
$("#sample-button").addEventListener("click", () => { clearNotice(); state.scanId = null; state.operationId = null; renderRows(sampleItems, { sample: true }); $("#results").scrollIntoView({ behavior: "smooth", block: "nearest" }); });
$("#scan-button").addEventListener("click", scanAndPlan);
$("#apply-button").addEventListener("click", applyPlan);
$("#undo-button").addEventListener("click", undoPlan);
initialize();
