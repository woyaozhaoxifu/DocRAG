"use strict";

let api = null;
let lastQuery = "";
let lastResults = [];
let currentFilter = { exts: null, dir: null };

const $ = (id) => document.getElementById(id);

function fmtSize(n) {
  if (!n) return "";
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  return (n / 1024 / 1024).toFixed(1) + " MB";
}

function extClass(ext) {
  const e = (ext || "").replace(".", "").toLowerCase();
  const map = {
    pdf: "PDF", doc: "DOC", docx: "DOC", xls: "XLS", xlsx: "XLS",
    ppt: "PPT", pptx: "PPT", txt: "TXT", md: "MD", csv: "CSV",
    json: "JSON", html: "HTML", htm: "HTML", rtf: "RTF",
    png: "IMG", jpg: "IMG", jpeg: "IMG", bmp: "IMG", gif: "IMG",
  };
  return map[e] || (e ? e.slice(0, 4).toUpperCase() : "FILE");
}

function renderStats(s) {
  $("stat-total").textContent = s.total || 0;
  $("stat-archived").textContent = s.archived || 0;
  const sem = $("stat-sem");
  if (s.semantic) { sem.textContent = "开"; sem.style.color = "var(--green)"; }
  else { sem.textContent = "关"; sem.style.color = "var(--muted)"; }
}

function resultCard(item) {
  const card = document.createElement("div");
  card.className = "card" + (item.needs_download ? " placeholder" : "");

  const badge = document.createElement("div");
  badge.className = "badge";
  badge.textContent = extClass(item.ext);
  card.appendChild(badge);

  const body = document.createElement("div");
  body.className = "card-body";

  const titleRow = document.createElement("div");
  titleRow.className = "title-row";
  const title = document.createElement("span");
  title.className = "card-title";
  title.textContent = item.filename || item.path;
  title.onclick = () => showPreview(item.path);
  titleRow.appendChild(title);
  if (item.needs_download) {
    const tag = document.createElement("span");
    tag.className = "badge-ph";
    tag.textContent = "云盘占位符·需释放";
    titleRow.appendChild(tag);
  }
  if (item.archived) {
    const tag = document.createElement("span");
    tag.className = "card-archived";
    tag.textContent = "· 已归档";
    titleRow.appendChild(tag);
  }
  body.appendChild(titleRow);

  const path = document.createElement("div");
  path.className = "card-path";
  path.textContent = (item.dir_name ? "[" + item.dir_name + "] " : "") + item.path + (item.size ? "  ·  " + fmtSize(item.size) : "");
  body.appendChild(path);

  if (item.snippet) {
    const snip = document.createElement("div");
    snip.className = "snippet";
    snip.innerHTML = item.snippet; // 高亮命中词（<b>），来自后端，已转义
    body.appendChild(snip);
  }

  if (item.keywords && item.keywords.length) {
    const tags = document.createElement("div");
    tags.className = "tags";
    item.keywords.slice(0, 10).forEach((k) => {
      const t = document.createElement("span");
      t.className = "tag";
      t.textContent = k;
      tags.appendChild(t);
    });
    body.appendChild(tags);
  }

  const actions = document.createElement("div");
  actions.className = "actions";

  const openBtn = document.createElement("button");
  openBtn.className = "btn primary";
  openBtn.textContent = "打开";
  openBtn.onclick = () => openFile(item.path);
  actions.appendChild(openBtn);

  const prevBtn = document.createElement("button");
  prevBtn.className = "btn";
  prevBtn.textContent = "预览";
  prevBtn.onclick = () => showPreview(item.path);
  actions.appendChild(prevBtn);

  if (item.archived) {
    const restoreBtn = document.createElement("button");
    restoreBtn.className = "btn";
    restoreBtn.textContent = "还原";
    restoreBtn.onclick = () => restoreFile(item.path);
    actions.appendChild(restoreBtn);
  } else {
    const arcBtn = document.createElement("button");
    arcBtn.className = "btn danger";
    arcBtn.textContent = "归档";
    arcBtn.onclick = () => archiveFile(item.path);
    actions.appendChild(arcBtn);
  }
  body.appendChild(actions);
  card.appendChild(body);
  return card;
}

function renderResults(list) {
  const box = $("results");
  box.innerHTML = "";
  if (!list.length) {
    const e = document.createElement("div");
    e.className = "empty";
    e.textContent = lastQuery ? "没有匹配的文档" : "还没有索引到文档，或等待首次扫描完成…";
    box.appendChild(e);
    return;
  }
  list.forEach((it) => box.appendChild(resultCard(it)));
}

function openFile(path) {
  api.open_file(path).then((r) => {
    if (!r || !r.ok) alert("打开失败：" + ((r && r.error) || "未知错误"));
  });
}

function archiveFile(path) {
  api.archive_file(path).then((r) => {
    if (r && r.ok) refresh();
    else alert("归档失败：" + ((r && r.error) || "未知错误"));
  });
}

function restoreFile(archivePath) {
  api.restore(archivePath).then((r) => {
    if (r && r.ok) refresh();
    else alert("还原失败：" + ((r && r.error) || "未知错误"));
  });
}

function showPreview(path) {
  api.get_preview(path).then((r) => {
    if (!r || !r.ok) { alert("无法预览：" + ((r && r.error) || "")); return; }
    $("preview-title").textContent = r.path + (r.needs_download ? "（云盘占位符·需先释放才能打开）" : "");
    $("preview-body").textContent = r.text || "（无正文，可能为图片 / 扫描件，需开启 OCR）";
    $("preview").classList.remove("hidden");
  });
}
function closePreview() { $("preview").classList.add("hidden"); }

function refresh() {
  if (lastQuery.trim()) {
    doSearch(lastQuery);
  } else {
    // 未搜索（浏览）状态下也要应用"类型/目录"筛选
    const hasFilter = (!!currentFilter.exts && currentFilter.exts.length) || !!currentFilter.dir;
    const lim = hasFilter ? 500 : 20;
    api.list_recent(lim, currentFilter.exts, currentFilter.dir).then((list) => { lastResults = list; renderResults(list); });
  }
  api.get_stats().then(renderStats);
}

function doSearch(q) {
  lastQuery = q;
  if (!q.trim()) { refresh(); return; }
  $("status").textContent = "搜索中…";
  api.search(q, 30, currentFilter.exts, currentFilter.dir).then((list) => {
    lastResults = list;
    renderResults(list);
    $("status").textContent = `找到 ${list.length} 个结果`;
  });
}

// ---- 自动补全 ----
function handleSuggest(q) {
  const box = $("suggest");
  if (!q.trim()) { box.innerHTML = ""; box.classList.remove("open"); return; }
  api.suggest(q, 8).then((items) => {
    if (!items || !items.length) { box.innerHTML = ""; box.classList.remove("open"); return; }
    box.innerHTML = "";
    items.forEach((w) => {
      const d = document.createElement("div");
      d.className = "suggest-item";
      d.textContent = w;
      d.onmousedown = () => { $("search").value = w; box.innerHTML = ""; box.classList.remove("open"); doSearch(w); };
      box.appendChild(d);
    });
    box.classList.add("open");
  });
}

function init() {
  const input = $("search");
  let timer = null;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => { doSearch(input.value); handleSuggest(input.value); }, 250);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { $("suggest").classList.remove("open"); doSearch(input.value); }
    if (e.key === "Escape") { $("suggest").classList.remove("open"); }
  });
  input.addEventListener("blur", () => setTimeout(() => $("suggest").classList.remove("open"), 150));

  $("clear").onclick = () => {
    input.value = ""; lastQuery = ""; $("suggest").innerHTML = "";
    doSearch(""); input.focus();
  };
  $("reindex").onclick = () => {
    const btn = $("reindex");
    btn.disabled = true; btn.textContent = "扫描中…";
    api.reindex().then((s) => {
      btn.disabled = false; btn.textContent = "重新扫描";
      renderStats(s); refresh();
    });
  };
  $("smart").onclick = () => {
    api.smart_archive().then((r) => {
      alert((r.note ? r.note + "\n" : "") + "本次归档 " + (r.archived || 0) + " 个文件");
      refresh();
    });
  };
  $("preview-close").onclick = closePreview;
  $("preview").onclick = (e) => { if (e.target.id === "preview") closePreview(); };

  document.querySelectorAll("#filter-type .fchip").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll("#filter-type .fchip").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const e = btn.dataset.exts;
      currentFilter.exts = e ? e.split(",") : null;
      if (lastQuery.trim()) doSearch(lastQuery); else refresh();
    };
  });
  document.querySelectorAll("#filter-dir .fchip").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll("#filter-dir .fchip").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentFilter.dir = btn.dataset.dir || null;
      if (lastQuery.trim()) doSearch(lastQuery); else refresh();
    };
  });

  api.get_stats().then(renderStats);
  api.list_recent(20).then((list) => {
    lastResults = list;
    renderResults(list);
    $("status").textContent = list.length
      ? `已就绪，共 ${list.length} 个近期文档`
      : "首次扫描进行中，稍后将自动出现文档…";
  });
}

window.addEventListener("pywebviewready", () => {
  api = window.pywebview.api;
  init();
});
