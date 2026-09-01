/* Code Decode — 화면 로직
   서버가 흘려보내는 이벤트를 받아 주해를 쌓고, 원문의 해당 토큰에 밑줄을 긋는다.
   밑줄과 주해는 서로를 가리킨다: 토큰을 누르면 주해로, 주해를 누르면 토큰으로. */

const $ = (id) => document.getElementById(id);

const el = {
  code: $("code"),
  rendered: $("rendered"),
  entries: $("entries"),
  empty: $("empty"),
  legend: $("legend"),
  trace: $("trace"),
  traceSteps: $("trace-steps"),
  traceUsage: $("trace-usage"),
  hint: $("hint"),
  decode: $("btn-decode"),
  ast: $("btn-ast"),
  edit: $("btn-edit"),
  sample: $("btn-sample"),
  metaModel: $("meta-model"),
  metaScope: $("meta-scope"),
};

const SAMPLE = `from pathlib import Path
from PIL import Image

GEN_IMAGES_DIR = Path("./generated")

def make_thumbnails(size=(800, 800)):
    for src in sorted(GEN_IMAGES_DIR.glob("*.png")):
        img = Image.open(src)
        img.thumbnail(size)
        img.save(src.with_suffix(".thumb.png"))
`;

let entries = [];
let running = false;

/* ── 초기화 ─────────────────────────────────────────────────────────────── */

fetch("/api/config")
  .then((r) => r.json())
  .then((cfg) => {
    el.metaModel.textContent = cfg.model;
    el.metaScope.textContent = `표준 라이브러리 + ${cfg.third_party.join(", ")}`;
    if (!cfg.has_key) {
      setHint("ANTHROPIC_API_KEY 가 없습니다. .env 를 설정하면 해독이 됩니다.", true);
      el.decode.disabled = true;
    }
  })
  .catch(() => setHint("서버 설정을 읽지 못했습니다.", true));

el.sample.addEventListener("click", () => {
  showEditor();
  el.code.value = SAMPLE;
  el.code.focus();
});

el.edit.addEventListener("click", showEditor);
el.decode.addEventListener("click", runDecode);
el.ast.addEventListener("click", runAst);

el.code.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") runDecode();
});

/* ── 실행 ───────────────────────────────────────────────────────────────── */

function runDecode() {
  const code = el.code.value.trim();
  if (!code || running) return;

  running = true;
  entries = [];
  el.entries.innerHTML = "";
  el.empty.hidden = true;
  el.legend.hidden = false;
  el.traceSteps.innerHTML = "";
  el.traceUsage.textContent = "";
  el.trace.hidden = false;
  el.decode.disabled = true;
  el.ast.disabled = true;
  setHint("");
  renderSource(code, []);

  fetch("/api/decode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  })
    .then((res) => {
      if (!res.ok) throw new Error("서버가 요청을 거절했습니다.");
      return readStream(res.body.getReader(), code);
    })
    .catch((err) => {
      setHint(err.message, true);
      finish();
    });
}

function readStream(reader, code) {
  const decoder = new TextDecoder();
  let buffer = "";

  const pump = () =>
    reader.read().then(({ done, value }) => {
      if (done) return finish();
      buffer += decoder.decode(value, { stream: true });

      const chunks = buffer.split("\n\n");
      buffer = chunks.pop();

      for (const chunk of chunks) {
        const line = chunk.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        try {
          handleEvent(JSON.parse(line.slice(6)), code);
        } catch {
          /* 부분 프레임은 버린다 */
        }
      }
      return pump();
    });

  return pump();
}

function handleEvent(ev, code) {
  switch (ev.type) {
    case "tool_use":
      addTrace(`${ev.name}(${ev.input})`, true);
      break;
    case "tool_result":
      completeTrace(ev.summary);
      break;
    case "entry":
      entries.push(ev.entry);
      renderEntry(ev.entry, entries.length - 1);
      renderSource(code, entries);
      break;
    case "usage":
      el.traceUsage.textContent = formatUsage(ev);
      break;
    case "error":
      setHint(ev.message, true);
      break;
    case "done":
      el.traceUsage.textContent = `${formatUsage(ev)} · 항목 ${ev.entries}개`;
      if (!entries.length) setHint("항목을 만들지 못했습니다. 코드를 확인해 주세요.", true);
      break;
  }
}

function finish() {
  running = false;
  el.decode.disabled = false;
  el.ast.disabled = false;
  el.edit.hidden = false;
}

/* ── AST 전용 ───────────────────────────────────────────────────────────── */

function runAst() {
  const code = el.code.value.trim();
  if (!code) return;

  fetch("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  })
    .then((r) => r.json())
    .then((data) => {
      el.empty.hidden = true;
      el.legend.hidden = true;
      el.trace.hidden = true;
      el.edit.hidden = false;
      renderSource(code, []);
      renderAst(data);
    });
}

function renderAst(data) {
  if (data.error) {
    el.entries.innerHTML = `<p class="ast-note">파싱 실패 — ${escape(data.error)}</p>`;
    return;
  }

  const rows = data.symbols
    .map((s) => {
      const resolved = s.qualname
        ? `<td class="hit">${escape(s.qualname)}</td>`
        : `<td class="miss">해석 실패</td>`;
      const note = s.receiver_origin ? escape(s.receiver_origin) : "";
      return `<tr>
        <td>${s.line}</td>
        <td>${escape(s.source)}</td>
        ${resolved}
        <td>${escape(s.resolution)}</td>
        <td class="note">${note}</td>
      </tr>`;
    })
    .join("");

  const syntax = data.syntax
    .map((f) => `<tr><td>${f.line}</td><td colspan="4" class="note">${escape(f.label)}</td></tr>`)
    .join("");

  el.entries.innerHTML = `
    <p class="ast-note">LLM 없이 AST 분석만 돌린 결과입니다.
      심볼 ${data.symbols.length}개 중 ${data.unresolved_count}개는 정적 분석으로
      해석되지 않았습니다. 해석 실패가 이 도구의 결함이 아니라 정적 분석의
      경계라는 점이 중요합니다.</p>
    <table class="ast-table">
      <thead><tr><th>행</th><th>코드에 쓰인 이름</th><th>해석 결과</th><th>경로</th><th>단서</th></tr></thead>
      <tbody>${rows}${syntax}</tbody>
    </table>`;
}

/* ── 원문 렌더링 ────────────────────────────────────────────────────────── */

function renderSource(code, list) {
  el.code.hidden = true;
  el.rendered.hidden = false;

  const byLine = new Map();
  list.forEach((entry, i) => {
    if (!entry.line) return;
    if (!byLine.has(entry.line)) byLine.set(entry.line, []);
    byLine.get(entry.line).push({ entry, index: i });
  });

  el.rendered.innerHTML = code
    .split("\n")
    .map((text, i) => {
      const n = i + 1;
      const marks = byLine.get(n) || [];
      return `<span class="ln" data-line="${n}">${n}</span>` +
        `<span class="lt" data-line="${n}">${markup(text, marks)}</span>`;
    })
    .join("");

  el.rendered.querySelectorAll(".gloss").forEach((node) => {
    node.addEventListener("click", () => focusEntry(Number(node.dataset.index)));
  });
}

/* 해당 행에서 심볼 문자열을 찾아 밑줄을 긋는다.
   같은 행에 여러 항목이 있을 수 있으므로 긴 것부터 처리해 겹침을 피한다. */
function markup(text, marks) {
  if (!marks.length) return escape(text);

  const sorted = [...marks].sort(
    (a, b) => (b.entry.symbol || "").length - (a.entry.symbol || "").length
  );

  const slots = [];
  let masked = text;

  for (const { entry, index } of sorted) {
    const symbol = entry.symbol || "";
    if (!symbol) continue;
    const at = masked.indexOf(symbol);
    if (at === -1) continue;

    const token = `\u0000${slots.length}\u0000`;
    slots.push(
      `<span class="gloss gloss-${entry.status || "inferred"}" data-index="${index}" ` +
        `title="${escape(entry.qualname || symbol)}">${escape(symbol)}</span>`
    );
    masked = masked.slice(0, at) + token + masked.slice(at + symbol.length);
  }

  let out = escape(masked);
  slots.forEach((html, i) => {
    out = out.replace(`\u0000${i}\u0000`, html);
  });
  return out;
}

/* ── 주해 렌더링 ────────────────────────────────────────────────────────── */

function renderEntry(entry, index) {
  const node = document.createElement("article");
  node.className = "entry";
  node.dataset.index = index;
  node.dataset.status = entry.status || "inferred";

  const fields = [];
  if (entry.what) fields.push(["무엇", escape(entry.what), ""]);
  if (entry.why) fields.push(["왜", escape(entry.why), ""]);
  if (entry.gotcha) fields.push(["함정", escape(entry.gotcha), "gotcha"]);
  if (entry.example) fields.push(["예시", escape(entry.example), "mono"]);
  if (entry.check) fields.push(["확인", escape(entry.check), "check"]);
  if (entry.source && entry.source.url) {
    fields.push([
      "출처",
      `<a href="${escape(entry.source.url)}" target="_blank" rel="noopener">${escape(
        entry.source.label || entry.source.url
      )}</a>`,
      "",
    ]);
  }

  node.innerHTML = `
    <header class="entry-head">
      <span class="entry-line">${entry.line ? entry.line + "행" : "—"}</span>
      <span class="entry-symbol">${escape(entry.symbol || "")}</span>
      ${entry.qualname ? `<span class="entry-qual">${escape(entry.qualname)}</span>` : ""}
    </header>
    <dl class="fields">
      ${fields
        .map(([label, value, cls]) => `<dt>${label}</dt><dd class="${cls}">${value}</dd>`)
        .join("")}
    </dl>`;

  node.addEventListener("click", () => highlightLine(entry.line, index));
  el.entries.appendChild(node);
}

function focusEntry(index) {
  const node = el.entries.querySelector(`.entry[data-index="${index}"]`);
  if (!node) return;
  node.scrollIntoView({ behavior: "smooth", block: "center" });
  highlightLine(entries[index] && entries[index].line, index);
}

function highlightLine(line, index) {
  el.entries.querySelectorAll(".entry").forEach((n) => n.classList.remove("is-active"));
  el.rendered.querySelectorAll(".ln, .lt").forEach((n) => n.classList.remove("row-active"));

  const entry = el.entries.querySelector(`.entry[data-index="${index}"]`);
  if (entry) entry.classList.add("is-active");
  if (line) {
    el.rendered
      .querySelectorAll(`[data-line="${line}"]`)
      .forEach((n) => n.classList.add("row-active"));
  }
}

/* ── 진행 표시 ──────────────────────────────────────────────────────────── */

function addTrace(label, pending) {
  const li = document.createElement("li");
  if (pending) li.className = "pending";
  li.innerHTML = `<b>${escape(label)}</b>`;
  el.traceSteps.appendChild(li);
}

function completeTrace(summary) {
  const last = el.traceSteps.lastElementChild;
  if (!last) return;
  last.classList.remove("pending");
  last.innerHTML += ` ${escape(summary)}`;
}

function formatUsage(u) {
  const cached = u.cache_read ? ` · 캐시 ${u.cache_read.toLocaleString()}` : "";
  const cost = ((u.input * 2 + u.output * 10) / 1e6).toFixed(4);
  return `입력 ${u.input.toLocaleString()} · 출력 ${u.output.toLocaleString()}${cached} · 약 $${cost}`;
}

/* ── 유틸 ───────────────────────────────────────────────────────────────── */

function showEditor() {
  el.code.hidden = false;
  el.rendered.hidden = true;
  el.edit.hidden = true;
}

function setHint(text, isError) {
  el.hint.textContent = text;
  el.hint.classList.toggle("error", Boolean(isError));
}

function escape(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
