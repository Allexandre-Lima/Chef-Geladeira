"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const trunc = (text, max) => (text.length > max ? text.slice(0, max - 1) + "…" : text);

const ICONS = {
  hat: '<path d="M6 14.5V20h12v-5.5"/><path d="M6.5 14.5A4 4 0 0 1 8 6.7a4 4 0 0 1 8 0 4 4 0 0 1 1.5 7.8z"/>',
  chat: '<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8A8.5 8.5 0 0 1 8.7 3.9a8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z"/>',
  sliders: '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
  send: '<line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/>',
  up: '<path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.3a2 2 0 0 0 2-1.7l1.4-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/>',
  down: '<path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.7a2 2 0 0 0-2 1.7l-1.4 9a2 2 0 0 0 2 2.3zM17 2h2.7A2.3 2.3 0 0 1 22 4v7a2.3 2.3 0 0 1-2.3 2H17"/>',
  refresh: '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.5 9a9 9 0 0 1 14.9-3.4L23 10M1 14l4.6 4.4A9 9 0 0 0 20.5 15"/>',
  bolt: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
};
const icon = (name) =>
  `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;

const TOOL_LABELS = {
  search_recipes_by_ingredient: "Busca de receitas · TheMealDB",
  get_recipe_details: "Detalhes da receita · TheMealDB",
  get_food_nutrition: "Nutrição · USDA",
};
const TIPS = [
  "Esfrie o arroz cozido em até 2 horas antes de guardar na geladeira.",
  "Descongele alimentos na geladeira, não em temperatura ambiente.",
  "Talos e cascas limpas podem virar caldos, farofas e bolinhos.",
  "Reaqueça sobras até ficarem bem quentes e evite reaquecer mais de uma vez.",
  "Refogue o alho em fogo médio para ele não queimar.",
];
const RESULT_MESSAGES = {
  activated: ["ok", "Nova versão do prompt ativada. As próximas respostas já usam ela."],
  rejected_by_regression: ["warn", "A proposta não passou nos testes de regressão. A versão atual continua ativa."],
  rejected_by_guardrail: ["bad", "A proposta foi bloqueada pelos guardrails de segurança."],
  no_feedback: ["info", "Nenhum feedback novo para analisar."],
};

const state = { messages: [], answers: [], busy: false, status: null, poll: null, ratings: {} };

async function api(path, options = {}) {
  const res = await fetch("/api" + path, { headers: { "Content-Type": "application/json" }, ...options });
  let data = null;
  try {
    data = await res.json();
  } catch (e) {
    data = null;
  }
  if (!res.ok) {
    const detail = data && data.detail;
    throw new Error(typeof detail === "string" ? detail : `Erro ${res.status}. Verifique os dados enviados.`);
  }
  return data;
}

function toast(text) {
  const el = $("#toast");
  el.textContent = text;
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (el.hidden = true), 5000);
}

/* Markdown mínimo e seguro: escapa o HTML antes de formatar. */
function md(text) {
  const inline = (s) =>
    s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/(^|[^*])\*(?!\s)(.+?)\*(?!\*)/g, "$1<em>$2</em>");
  let html = "";
  let list = null;
  const close = () => {
    if (list) html += `</${list}>`;
    list = null;
  };
  for (const raw of esc(text).split("\n")) {
    const line = raw.trim();
    let m;
    if (!line) close();
    else if (/^-{3,}$/.test(line)) { close(); html += "<hr>"; }
    else if ((m = line.match(/^#{1,6}\s+(.*)/))) { close(); html += `<h4>${inline(m[1])}</h4>`; }
    else if ((m = line.match(/^[-*]\s+(.*)/))) {
      if (list !== "ul") { close(); html += "<ul>"; list = "ul"; }
      html += `<li>${inline(m[1])}</li>`;
    } else if ((m = line.match(/^\d+\.\s+(.*)/))) {
      if (list !== "ol") { close(); html += "<ol>"; list = "ol"; }
      html += `<li>${inline(m[1])}</li>`;
    } else { close(); html += `<p>${inline(line)}</p>`; }
  }
  close();
  return html;
}

/* ---------------------------------------------------------------- Chat */
function recipesHtml(recipes) {
  if (!recipes || !recipes.length) return "";
  const cards = recipes
    .map((r) => {
      const img = /^https:\/\//.test(r.thumbnail || "") ? `<img loading="lazy" src="${esc(r.thumbnail)}" alt="">` : "";
      return `<div class="recipe">${img}<div class="rb"><div class="rn">${esc(r.name)}</div><button class="pri" data-recipe="${esc(r.name)}" data-id="${esc(r.id)}">Ver receita</button></div></div>`;
    })
    .join("");
  return `<h3 style="margin-top:14px">Sugestões para você</h3><div class="recipes">${cards}</div>`;
}

function nutritionHtml(n) {
  if (!n || n.kcal == null) return "";
  const parts = [
    ["Proteínas", n.protein_g, (n.protein_g || 0) * 4, "#3DAA5C"],
    ["Carboidratos", n.carbs_g, (n.carbs_g || 0) * 4, "#F4A31E"],
    ["Gorduras", n.fat_g, (n.fat_g || 0) * 9, "#E5483E"],
  ];
  const total = parts.reduce((sum, p) => sum + p[2], 0) || 1;
  const circumference = 2 * Math.PI * 40;
  let offset = 0;
  const arcs = parts
    .map(([, , kcal, color]) => {
      const len = (circumference * kcal) / total;
      const arc = `<circle cx="55" cy="55" r="40" stroke="${color}" stroke-dasharray="${len.toFixed(1)} ${(circumference - len).toFixed(1)}" stroke-dashoffset="${(-offset).toFixed(1)}"/>`;
      offset += len;
      return arc;
    })
    .join("");
  const rows = parts
    .map(([label, grams, , color]) => `<tr><td><span class="dot" style="background:${color}"></span>${label}</td><td>${grams == null ? "—" : Math.round(grams * 10) / 10} g</td></tr>`)
    .join("");
  return `<h3 style="margin-top:14px">Informações nutricionais</h3><div class="card nutri">
    <svg width="120" height="120" viewBox="0 0 110 110" role="img"><title>Distribuição das calorias</title>
      <g transform="rotate(-90 55 55)" fill="none" stroke-width="14">${arcs}</g>
      <text x="55" y="56" text-anchor="middle" font-size="20" font-weight="600" fill="#2B2118">${Math.round(n.kcal)}</text>
      <text x="55" y="72" text-anchor="middle" font-size="11" fill="#6B5A4B">kcal</text></svg>
    <div><div class="muted" style="font-size:13px">${esc(n.name)} · por 100 g</div><table>${rows}</table></div></div>`;
}

function addUser(text) {
  const el = document.createElement("div");
  el.className = "msg user";
  el.innerHTML = `<span class="avatar" data-i>${icon("user")}</span><div class="body"><div class="bubble">${esc(text)}</div></div>`;
  $("#thread").appendChild(el);
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function addTyping() {
  const el = document.createElement("div");
  el.className = "msg chef";
  el.innerHTML = `<span class="avatar chef">${icon("hat")}</span><div class="body"><div class="bubble typing"><i></i><i></i><i></i> O chef está pensando...</div></div>`;
  $("#thread").appendChild(el);
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  return el;
}

function addChef(res, question) {
  const idx = state.answers.push({ question, answer: res.answer }) - 1;
  const badges = (res.tools_used || []).map((t) => `<span class="badge">${esc(TOOL_LABELS[t] || t)}</span>`).join("");
  const el = document.createElement("div");
  el.className = "msg chef";
  el.innerHTML = `<span class="avatar chef">${icon("hat")}</span><div class="body">
    <div class="bubble">${md(res.answer)}</div>${badges}${recipesHtml(res.recipes)}${nutritionHtml(res.nutrition)}
    <div class="rate" data-idx="${idx}"><span class="rate-t">Avaliar</span>
      <button data-rate="1">${icon("up")} Boa</button><button data-rate="-1">${icon("down")} Ruim</button>
      <input type="text" maxlength="500" placeholder="Sugestão de melhoria (opcional)" aria-label="Sugestão de melhoria">
      <button class="pri" data-send>Enviar</button><span class="msg-line" style="margin:0"></span></div></div>`;
  $("#thread").appendChild(el);
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function addError(message) {
  const el = document.createElement("div");
  el.className = "error-box";
  el.textContent = message;
  $("#thread").appendChild(el);
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function setBusy(busy) {
  state.busy = busy;
  $$("#chat-form input, #chat-form button, .chip").forEach((el) => (el.disabled = busy));
}

async function sendMessage(text) {
  text = text.trim();
  if (!text || state.busy) return;
  $("#thread-head").hidden = false;
  setBusy(true);
  addUser(text);
  const typing = addTyping();
  try {
    const res = await api("/chat", {
      method: "POST",
      body: JSON.stringify({ message: text, history: state.messages.slice(-12) }),
    });
    typing.remove();
    state.messages.push({ role: "user", content: text }, { role: "assistant", content: res.answer });
    addChef(res, text);
  } catch (err) {
    typing.remove();
    addError(err.message);
  } finally {
    setBusy(false);
    $("#chat-input").focus();
  }
}

async function submitFeedback(payload, onMessage) {
  try {
    const res = await api("/feedback", { method: "POST", body: JSON.stringify(payload) });
    onMessage("ok", "Feedback registrado! Obrigado.");
    if (res.auto_started) {
      toast("Análise automática iniciada. O prompt será atualizado se passar nos testes.");
      ensurePolling();
    }
    refreshAside();
    if ($("#view-feedback").classList.contains("active")) loadFeedback();
  } catch (err) {
    onMessage("bad", err.message);
  }
}

/* ------------------------------------------------------------ Feedback */
function diffHtml(current, other) {
  const a = current.split("\n");
  const b = other.split("\n");
  const out = [];
  a.forEach((l) => { if (!b.includes(l)) out.push(`<span class="del">- ${esc(l)}</span>`); });
  b.forEach((l) => { if (!a.includes(l)) out.push(`<span class="add">+ ${esc(l)}</span>`); });
  return `<pre class="code">${out.join("\n") || "(sem diferenças)"}</pre>`;
}

function renderVersions(versions) {
  const active = versions.find((v) => v.active);
  $("#versions").innerHTML = versions
    .map((v) => {
      const rejected = !v.active && (v.reason || "").startsWith("REJEITADA");
      const cls = v.active ? "ok" : rejected ? "bad" : "";
      const label = v.active ? "ativa" : rejected ? "rejeitada" : "anterior";
      const rate = v.pass_rate == null ? "—" : Math.round(v.pass_rate * 100) + "%";
      const body =
        active && v.version !== active.version
          ? `<p class="muted" style="font-size:13px">Comparação com a versão ativa: vermelho = só na ativa; verde = só nesta versão.</p>${diffHtml(active.content, v.content)}`
          : `<pre class="code">${esc(v.content)}</pre>`;
      const judge = (v.details || [])
        .map((d) => `<div class="judge">${icon(d.passed ? "check" : "x")} <b>${esc(d.question)}</b><span>${esc(d.reason)}</span></div>`)
        .join("");
      const button = v.active ? "" : `<button data-activate="${v.version}">Ativar v${v.version}</button>`;
      return `<details class="card version"><summary><span class="dot ${cls}"></span>v${v.version} · ${label} · aprovação ${rate}</summary>
        <p class="muted">${esc(v.reason || "")}</p>${body}${judge ? `<h3>Testes de regressão</h3>${judge}` : ""}${button}</details>`;
    })
    .join("");
}

function resultHtml(r) {
  const [kind, text] = r.status === "error" ? ["bad", r.message] : RESULT_MESSAGES[r.status] || ["info", r.status];
  let extra = "";
  if (r.pass_rate != null) {
    const judge = (r.details || [])
      .map((d) => `<div class="judge">${icon(d.passed ? "check" : "x")} <b>${esc(d.question)}</b><span>${esc(d.reason)}</span></div>`)
      .join("");
    extra = `<p style="margin:8px 0 0">Aprovação nos testes de regressão: <b>${Math.round(r.pass_rate * 100)}%</b>. ${esc(r.changes || "")}</p>${judge}`;
  } else if (r.message && r.status !== "error") {
    extra = `<p style="margin:6px 0 0">${esc(r.message)}</p>`;
  }
  return `<div class="result ${kind}">${esc(text)}${extra}</div>`;
}

function renderStatus(s) {
  state.status = s;
  $("#auto-banner").innerHTML = s.running
    ? `<span class="spinner"></span> Analisando feedbacks e rodando testes de regressão. Isso pode levar alguns minutos.`
    : s.auto
    ? `${icon("bolt")} Atualização automática ligada: a análise roda a cada ${s.threshold} feedbacks (aguardando ${s.pending} de ${s.threshold}).`
    : "Atualização automática desligada. Use o botão Analisar agora.";
  $("#btn-improve").disabled = s.running;
  $("#improve-result").innerHTML = s.last_result && !s.running ? resultHtml(s.last_result) : "";
  $("#nav-alert").hidden = !s.running;
  $("#aside-pending").textContent = s.running
    ? "Analisando feedbacks..."
    : `${s.pending} de ${s.threshold} feedbacks até a análise automática.`;
}

async function loadFeedback() {
  try {
    const [versions, feedbacks, status] = await Promise.all([api("/prompts"), api("/feedback"), api("/prompts/status")]);
    const active = versions.find((v) => v.active);
    $("#metrics").innerHTML = [
      ["Versão ativa", active ? `v${active.version}` : "—"],
      ["Versões", versions.length],
      ["Feedbacks", feedbacks.length],
      ["Até a análise", `${status.pending} de ${status.threshold}`],
    ].map(([l, v]) => `<div class="card metric"><span>${l}</span><strong>${esc(v)}</strong></div>`).join("");
    $("#active-prompt").textContent = active ? active.content : "";
    renderVersions(versions);
    renderStatus(status);
    if (status.running) ensurePolling();
    $("#fb-table").innerHTML =
      `<tr><th>Nota</th><th>Pergunta</th><th>Comentário</th><th>Categoria</th><th>Versão</th></tr>` +
      (feedbacks.length
        ? feedbacks
            .map((f) => {
              const v = f.processed_in_version;
              const ver = v === null ? "pendente" : v === 0 ? "descartado" : `v${v}`;
              return `<tr><td>${icon(f.rating > 0 ? "up" : "down")}</td><td>${esc(trunc(f.question, 60))}</td><td>${esc(f.comment || "—")}</td><td>${esc(f.category || "—")}</td><td>${ver}</td></tr>`;
            })
            .join("")
        : `<tr><td colspan="5" class="muted">Nenhum feedback ainda. Avalie uma resposta no chat.</td></tr>`);
    renderTargets();
  } catch (err) {
    toast(err.message);
  }
}

function renderTargets() {
  const select = $("#fb-target");
  const current = select.value;
  const options = [`<option value="">Sugestão geral (sem resposta específica)</option>`];
  state.answers.slice(-8).forEach((a, i, arr) => {
    const idx = state.answers.length - arr.length + i;
    options.push(`<option value="${idx}">Resposta sobre: ${esc(trunc(a.question, 50))}</option>`);
  });
  select.innerHTML = options.join("");
  if ([...select.options].some((o) => o.value === current)) select.value = current;
}

async function refreshAside() {
  try {
    const [versions, status] = await Promise.all([api("/prompts"), api("/prompts/status")]);
    const active = versions.find((v) => v.active);
    $("#aside-version").textContent = active ? `Versão ativa: v${active.version} (${versions.length} no histórico).` : "";
    renderStatus(status);
    if (status.running) ensurePolling();
  } catch (err) {
    console.warn(err);
  }
}

function ensurePolling() {
  if (state.poll) return;
  state.poll = setInterval(async () => {
    try {
      const s = await api("/prompts/status");
      renderStatus(s);
      if (!s.running) {
        clearInterval(state.poll);
        state.poll = null;
        refreshAside();
        if ($("#view-feedback").classList.contains("active")) loadFeedback();
        if (s.last_result) toast(s.last_result.status === "activated" ? "Prompt atualizado!" : "Análise concluída.");
      }
    } catch (err) {
      clearInterval(state.poll);
      state.poll = null;
    }
  }, 3000);
}

function showView(name) {
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  if (name === "feedback") loadFeedback();
  window.scrollTo({ top: 0 });
}

function setMsg(el, kind, text) {
  el.className = "msg-line " + kind;
  el.textContent = text;
}

/* ------------------------------------------------------------- Eventos */
document.addEventListener("click", async (event) => {
  const target = event.target.closest("button");
  if (!target) return;

  if (target.dataset.view) showView(target.dataset.view);
  else if (target.dataset.goto) showView(target.dataset.goto);
  else if (target.classList.contains("chip")) sendMessage(target.dataset.q);
  else if (target.dataset.recipe) sendMessage(`Explique passo a passo a receita "${target.dataset.recipe}" (id no TheMealDB: ${target.dataset.id}).`);
  else if (target.dataset.rate) {
    const box = target.closest(".rate");
    state.ratings[box.dataset.idx] = Number(target.dataset.rate);
    $$("[data-rate]", box).forEach((b) => b.classList.toggle("sel", b === target));
    setMsg($(".msg-line", box), "", "");
  } else if (target.hasAttribute("data-send")) {
    const box = target.closest(".rate");
    const msg = $(".msg-line", box);
    const rating = state.ratings[box.dataset.idx];
    if (!rating) return setMsg(msg, "bad", "Escolha uma nota primeiro.");
    const answer = state.answers[Number(box.dataset.idx)];
    submitFeedback(
      { question: answer.question, answer: answer.answer, rating, comment: $("input", box).value.trim() },
      (kind, text) => setMsg(msg, kind, text)
    );
  } else if (target.id === "new-chat") {
    state.messages = [];
    state.answers = [];
    state.ratings = {};
    $("#thread").innerHTML = "";
    $("#thread-head").hidden = true;
  } else if (target.dataset.activate) {
    try {
      await api(`/prompts/${target.dataset.activate}/activate`, { method: "POST" });
      toast(`Versão v${target.dataset.activate} ativada.`);
      loadFeedback();
      refreshAside();
    } catch (err) {
      toast(err.message);
    }
  } else if (target.id === "btn-improve") {
    try {
      const res = await api("/prompts/improve", { method: "POST" });
      toast(res.started ? "Análise iniciada." : "Já existe uma análise em andamento.");
      ensurePolling();
      loadFeedback();
    } catch (err) {
      toast(err.message);
    }
  } else if (target.id === "fb-up" || target.id === "fb-down") {
    state.formRating = target.id === "fb-up" ? 1 : -1;
    $("#fb-up").classList.toggle("sel", state.formRating === 1);
    $("#fb-down").classList.toggle("sel", state.formRating === -1);
    setMsg($("#fb-msg"), "", "");
  } else if (target.id === "fb-send") {
    const msg = $("#fb-msg");
    const comment = $("#fb-comment").value.trim();
    const pick = $("#fb-target").value;
    if (!state.formRating) return setMsg(msg, "bad", "Escolha uma nota primeiro.");
    if (pick === "" && !comment) return setMsg(msg, "bad", "Escreva a sugestão de melhoria.");
    const answer = pick === "" ? null : state.answers[Number(pick)];
    submitFeedback(
      { question: answer ? answer.question : "(sugestão geral)", answer: answer ? answer.answer : "", rating: state.formRating, comment },
      (kind, text) => {
        setMsg(msg, kind, text);
        if (kind === "ok") $("#fb-comment").value = "";
      }
    );
  }
});

$("#chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = $("#chat-input");
  const text = input.value;
  input.value = "";
  sendMessage(text);
});

$$("[data-icon]").forEach((el) => (el.innerHTML = icon(el.dataset.icon)));
$("#tip").textContent = TIPS[Math.floor(Math.random() * TIPS.length)];
renderTargets();
refreshAside();
