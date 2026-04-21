#!/usr/bin/env node
/**
 * Local bridge: receives Markdown over HTTP and triggers your existing Python
 * Gmail→Day One sender using a payload JSON under SEND_ROOT.
 *
 * Security: binds to 127.0.0.1 and requires a shared token header.
 */
const http = require("node:http");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const HOST = "127.0.0.1";
const PORT = Number.parseInt(process.env.PORT || "8765", 10);

// Path to Python sender: env override, or dayone_send.py next to this script.
const PY_SENDER = path.resolve(
  process.env.DAYONE_EMAIL_SENDER_PY || path.join(__dirname, "dayone_send.py")
);

// Payloads go under {SEND_ROOT}/outbox (same layout as skill README). Override with DAYONE_SEND_ROOT.
function getSendRoot() {
  if (process.env.DAYONE_SEND_ROOT) {
    return path.resolve(process.env.DAYONE_SEND_ROOT);
  }
  return path.dirname(PY_SENDER);
}

// Shared secret token; put the same value in the Tampermonkey script.
const TOKEN = process.env.DAYONE_BRIDGE_TOKEN;

function json(res, status, obj) {
  const body = JSON.stringify(obj, null, 2) + "\n";
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
  });
  res.end(body);
}

function safeSlug(s) {
  return String(s || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9._-]+/g, "")
    .replace(/^[-._]+|[-._]+$/g, "")
    .slice(0, 80) || "untitled";
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let total = 0;
    req.on("data", (c) => {
      total += c.length;
      if (total > 10 * 1024 * 1024) {
        reject(new Error("request too large"));
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}

function runPython(payloadPathAbs) {
  return new Promise((resolve) => {
    const child = spawn("python3", [PY_SENDER, "--payload", payloadPathAbs], {
      stdio: ["ignore", "pipe", "pipe"],
    });
    let out = "";
    let err = "";
    child.stdout.on("data", (d) => (out += d.toString("utf8")));
    child.stderr.on("data", (d) => (err += d.toString("utf8")));
    child.on("close", (code) => resolve({ code, out, err }));
  });
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.method === "GET" && req.url === "/health") {
      json(res, 200, { ok: true });
      return;
    }

    if (req.method !== "POST" || req.url !== "/dayone-email") {
      json(res, 404, { ok: false, error: "not found" });
      return;
    }

    if (!TOKEN) {
      json(res, 500, { ok: false, error: "DAYONE_BRIDGE_TOKEN not set" });
      return;
    }
    if (!fs.existsSync(PY_SENDER)) {
      json(res, 500, {
        ok: false,
        error: `Python sender not found: ${PY_SENDER}`,
      });
      return;
    }

    const auth = req.headers["x-bridge-token"];
    if (auth !== TOKEN) {
      json(res, 401, { ok: false, error: "unauthorized" });
      return;
    }

    const raw = await readBody(req);
    let payload;
    try {
      payload = JSON.parse(raw);
    } catch {
      json(res, 400, { ok: false, error: "invalid json" });
      return;
    }

    const subject = typeof payload.subject === "string" ? payload.subject.trim() : "";
    const body_markdown =
      typeof payload.body_markdown === "string" ? payload.body_markdown : "";

    if (!subject) {
      json(res, 400, { ok: false, error: "missing subject" });
      return;
    }
    if (!body_markdown.trim()) {
      json(res, 400, { ok: false, error: "missing body_markdown" });
      return;
    }

    const attachments = Array.isArray(payload.attachments) ? payload.attachments : [];

    const sendRoot = getSendRoot();
    const outbox = path.join(sendRoot, "outbox");
    ensureDir(outbox);
    const stamp = new Date().toISOString().replace(/[:.]/g, "").replace("Z", "Z");
    const base = `${stamp}-${safeSlug(subject)}`;
    const payloadPathAbs = path.join(outbox, `${base}.json`);

    fs.writeFileSync(
      payloadPathAbs,
      JSON.stringify({ subject, body_markdown, attachments }, null, 2) + "\n",
      "utf8"
    );

    const { code, out, err } = await runPython(payloadPathAbs);
    if (code !== 0) {
      json(res, 502, { ok: false, error: "python sender failed", code, out, err });
      return;
    }

    // Your python prints JSON; try to pass it through.
    let parsed = null;
    try {
      parsed = JSON.parse(out);
    } catch {
      parsed = { ok: true, raw_output: out };
    }

    json(res, 200, {
      ok: true,
      payload_path: payloadPathAbs,
      sender_result: parsed,
      stderr: err || undefined,
    });
  } catch (e) {
    json(res, 500, { ok: false, error: String(e?.message || e) });
  }
});

server.listen(PORT, HOST, () => {
  process.stdout.write(
    `dayone-email-bridge listening on http://${HOST}:${PORT}\n` +
      `POST /dayone-email (requires X-Bridge-Token)\n` +
      `Python sender: ${PY_SENDER}\n`
  );
});
