// Loaded as an external file because the CSP header is "default-src 'self'"
// (no inline scripts). URLs come from data- attributes rendered by url_for().
const API = document.body.dataset.api;
const STREAM = document.body.dataset.stream;
const NEXT = { todo: "doing", doing: "done", done: "todo" };

const list = document.getElementById("tasks");
const form = document.getElementById("add-form");
const titleInput = document.getElementById("title");
const errorBox = document.getElementById("error");
const conn = document.getElementById("conn");

function showError(msg) {
  errorBox.textContent = msg || "";
  errorBox.hidden = !msg;
}

async function call(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed (${res.status})`);
  }
  return res.status === 204 ? null : res.json();
}

function render(tasks) {
  list.replaceChildren(...tasks.map(renderTask));
}

function renderTask(t) {
  const li = document.createElement("li");
  li.className = t.status;

  const badge = document.createElement("button");
  badge.className = "badge";
  badge.textContent = t.status;
  badge.title = "Click to advance status";
  badge.onclick = () =>
    call(t.url, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: NEXT[t.status] }),
    }).catch((e) => showError(e.message));

  const title = document.createElement("span");
  title.textContent = t.title; // textContent, never innerHTML: avoids XSS

  const del = document.createElement("button");
  del.className = "del";
  del.textContent = "×";
  del.onclick = () => call(t.url, { method: "DELETE" }).catch((e) => showError(e.message));

  li.append(badge, title, del);
  return li;
}

async function refresh() {
  try {
    render(await call(API));
    showError("");
  } catch (e) {
    showError(e.message);
  }
}

form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  try {
    await call(API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: titleInput.value }),
    });
    titleInput.value = "";
    showError("");
  } catch (e) {
    showError(e.message);
  }
});

// Live updates: any event means "something changed", so reload the list.
const source = new EventSource(STREAM);
source.onopen = () => { conn.textContent = "live"; conn.className = "pill on"; refresh(); };
source.onerror = () => { conn.textContent = "reconnecting…"; conn.className = "pill off"; };
["task_created", "task_updated", "task_deleted"].forEach((name) =>
  source.addEventListener(name, refresh)
);

refresh();
