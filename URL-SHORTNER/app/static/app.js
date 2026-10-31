"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  offset: 0,
  limit: 10,
  query: "",
  loading: false,
  ready: false,
  creating: false,
  version: 0,
  pendingDelete: null,
};
const number = new Intl.NumberFormat();
const date = (value) => (value ? new Date(value).toLocaleString() : "Never");

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function toast(message, error = false) {
  const node = element("div", error ? "toast error" : "toast", message);
  $("toast-container").replaceChildren(node);
  setTimeout(() => node.remove(), 4500);
}

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(`/api/v1${path}`, {
      credentials: "same-origin",
      ...options,
    });
  } catch {
    throw new Error("Unable to connect. Check your connection and try again.");
  }
  const data =
    response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => `${item.loc.at(-1)}: ${item.msg}`).join(". ")
      : detail;
    throw new Error(
      message || "The service is unavailable. Please try again shortly.",
    );
  }
  return data;
}

async function copyLink(link) {
  try {
    await navigator.clipboard.writeText(link);
    toast("Link copied. Ready to share!");
  } catch {
    // Clipboard permission can be denied; let the user select the actual URL.
    $("result").hidden = false;
    $("result-link").href = link;
    $("result-link").textContent = link;
    const range = document.createRange();
    range.selectNodeContents($("result-link"));
    window.getSelection().removeAllRanges();
    window.getSelection().addRange(range);
    toast("Link selected. Press Ctrl+C or ⌘C to copy.");
  }
}

function updateSubmit() {
  $("shorten-button").disabled =
    !state.ready || state.creating || !$("url-input").value.trim();
}

function makeRow(item) {
  const row = element("article", "link-row");
  row.dataset.shortCode = item.short_code;
  const info = element("div", "link-info");
  const link = element(
    "a",
    "short-link",
    item.short_url.replace(/^https?:\/\//, ""),
  );
  link.href = item.short_url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  const destination = element("p", "original-url", item.original_url);
  destination.title = item.original_url;
  info.append(
    link,
    destination,
    element(
      "div",
      "link-time",
      `Created ${new Date(item.created_at).toLocaleDateString()}`,
    ),
  );
  const clicks = element("div", "click-count", number.format(item.clicks));
  clicks.append(element("span", "", item.clicks === 1 ? "click" : "clicks"));
  const expired = item.expires_at && new Date(item.expires_at) <= new Date();
  const status = element(
    "span",
    expired ? "link-status expired" : "link-status",
    expired ? "Expired" : "Active",
  );
  status.title = item.expires_at
    ? `Expires ${date(item.expires_at)}`
    : "No expiry";
  const actions = element("div", "row-actions");
  for (const [label, className, callback] of [
    ["Copy", "copy-link", () => copyLink(item.short_url)],
    ["Insights", "stats-link", () => showStats(item.short_code)],
    [
      "×",
      "delete-link",
      () => {
        state.pendingDelete = item;
        $("delete-modal").showModal();
      },
    ],
  ]) {
    const button = element("button", className, label);
    button.type = "button";
    button.setAttribute(
      "aria-label",
      `${className === "delete-link" ? "Delete" : label} ${item.short_code}`,
    );
    button.addEventListener("click", callback);
    actions.append(button);
  }
  row.append(info, clicks, status, actions);
  return row;
}

async function showStats(code) {
  $("stats-body").replaceChildren(element("p", "subtle", "Loading insights…"));
  $("stats-modal").showModal();
  try {
    const stats = await api(`/stats/${encodeURIComponent(code)}`);
    const count = element("div", "big-clicks", number.format(stats.clicks));
    count.append(element("span", "", "total destination visits"));
    const grid = element("div", "stat-grid");
    for (const [label, value, wide] of [
      ["Destination", stats.original_url, true],
      ["Short code", stats.short_code, false],
      [
        "Status",
        stats.expires_at && new Date(stats.expires_at) <= new Date()
          ? "Expired"
          : "Active",
        false,
      ],
      ["Created", date(stats.created_at), false],
      ["Expires", date(stats.expires_at), false],
      [
        "Last visit",
        stats.last_accessed ? date(stats.last_accessed) : "No visits yet",
        true,
      ],
    ]) {
      const field = element("div", `stat-field${wide ? " wide" : ""}`);
      field.append(element("span", "", label), element("strong", "", value));
      grid.append(field);
    }
    $("stats-body").replaceChildren(count, grid);
  } catch (error) {
    $("stats-body").replaceChildren(element("p", "form-error", error.message));
  }
}

async function loadCollection() {
  const version = ++state.version;
  state.loading = true;
  $("refresh").disabled = true;
  $("next").disabled = true;
  $("previous").disabled = true;
  try {
    const [page, summary] = await Promise.all([
      api(
        `/urls?limit=${state.limit}&offset=${state.offset}&q=${encodeURIComponent(state.query)}`,
      ),
      api("/summary"),
    ]);
    if (version !== state.version) return;
    if (!page.items.length && page.total && state.offset >= page.total) {
      state.offset = Math.floor((page.total - 1) / state.limit) * state.limit;
      return loadCollection();
    }
    $("recent-urls").replaceChildren(...page.items.map(makeRow));
    $("list-message").hidden = page.items.length > 0;
    $("list-message").textContent = state.query
      ? "No links match your search."
      : "Your collection starts here. Shorten your first link above.";
    $("link-count").textContent = number.format(page.total);
    $("page-info").textContent = page.total
      ? `${state.offset + 1}–${state.offset + page.items.length} of ${page.total} links`
      : "No links yet";
    $("previous").disabled = state.offset === 0;
    $("next").disabled = state.offset + state.limit >= page.total;
    for (const key of [
      "total_links",
      "total_clicks",
      "active_links",
      "expired_links",
    ]) {
      $(key.replaceAll("_", "-")).textContent = number.format(summary[key]);
    }
  } catch (error) {
    if (version !== state.version) return;
    $("list-message").hidden = false;
    $("list-message").textContent = `${error.message} Use Refresh to retry.`;
  } finally {
    if (version === state.version) {
      state.loading = false;
      $("refresh").disabled = false;
    }
  }
}

async function initialize() {
  try {
    await api("/session");
    state.ready = true;
    updateSubmit();
    await loadCollection();
  } catch (error) {
    $("list-message").hidden = false;
    $("list-message").textContent = `${error.message} Use Refresh to retry.`;
  }
}

$("url-input").addEventListener("input", updateSubmit);
$("ttl-unit").addEventListener("change", () => {
  $("ttl-input").max = String(
    Math.floor(31536000 / Number($("ttl-unit").value)),
  );
});
$("shorten-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.creating || !state.ready) return;
  $("form-error").hidden = true;
  const payload = { url: $("url-input").value.trim() };
  if ($("ttl-input").value)
    payload.ttl_seconds =
      Number($("ttl-input").value) * Number($("ttl-unit").value);
  state.creating = true;
  updateSubmit();
  $("shorten-button").textContent = "Shortening…";
  try {
    const item = await api("/shorten", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    $("result-link").href = item.short_url;
    $("result-link").textContent = item.short_url;
    $("result").hidden = false;
    $("shorten-form").reset();
    $("ttl-input").max = "365";
    state.offset = 0;
    state.query = "";
    $("search").value = "";
    toast("Your new link is ready.");
    await loadCollection();
  } catch (error) {
    $("form-error").textContent = error.message;
    $("form-error").hidden = false;
  } finally {
    state.creating = false;
    $("shorten-button").textContent = "Shorten link ↗";
    updateSubmit();
  }
});
$("copy-result").addEventListener("click", () =>
  copyLink($("result-link").href),
);
$("refresh").addEventListener("click", () =>
  state.ready ? loadCollection() : initialize(),
);
$("previous").addEventListener("click", () => {
  state.offset = Math.max(0, state.offset - state.limit);
  loadCollection();
});
$("next").addEventListener("click", () => {
  state.offset += state.limit;
  loadCollection();
});
let searchTimer;
$("search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.query = $("search").value;
    state.offset = 0;
    if (state.ready) loadCollection();
  }, 250);
});
$("modal-close").addEventListener("click", () => $("stats-modal").close());
$("cancel-delete").addEventListener("click", () => $("delete-modal").close());
$("confirm-delete").addEventListener("click", async () => {
  if (!state.pendingDelete) return;
  $("confirm-delete").disabled = true;
  try {
    const code = state.pendingDelete.short_code;
    await api(`/urls/${encodeURIComponent(code)}`, { method: "DELETE" });
    $("delete-modal").close();
    if ($("result-link").href.endsWith(`/${code}`)) $("result").hidden = true;
    state.pendingDelete = null;
    toast("Link deleted.");
    await loadCollection();
  } catch (error) {
    $("delete-modal").close();
    toast(error.message, true);
  } finally {
    $("confirm-delete").disabled = false;
  }
});
window.addEventListener("focus", () => {
  if (state.ready && !state.loading) loadCollection();
});
initialize();
