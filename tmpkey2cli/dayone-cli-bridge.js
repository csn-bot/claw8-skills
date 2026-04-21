#!/usr/bin/env node
/**
 * Local bridge: receives Markdown over HTTP and creates a Day One entry via the
 * official `dayone` CLI (stdin), e.g. dayone -j Work -- new < body.md
 *
 * Security: binds to 127.0.0.1 and requires X-Bridge-Token (DAYONE_BRIDGE_TOKEN).
 */
const http = require("node:http");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const HOST = "127.0.0.1";
const PORT = Number.parseInt(process.env.PORT || "8765", 10);

const TOKEN = process.env.DAYONE_BRIDGE_TOKEN;
const DAYONE_BIN = process.env.DAYONE_BIN || "dayone";
const DAYONE_JOURNAL = process.env.DAYONE_JOURNAL || "Work";
/** Comma-separated entry tags, e.g. "ai-export,chat" */
const DAYONE_TAGS = process.env.DAYONE_TAGS || "";

function json(res, status, obj) {
  const body = JSON.stringify(obj, null, 2) + "\n";
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
  });
  res.end(body);
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

function tagsFromEnv() {
  return DAYONE_TAGS.split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function runDayoneNew(bodyMarkdown, attachmentPaths, extraTags) {
  const envTags = tagsFromEnv();
  const tagList = [...extraTags, ...envTags].filter(
    (t, i, a) => t && a.indexOf(t) === i
  );

  const att = (Array.isArray(attachmentPaths) ? attachmentPaths : [])
    .filter((p) => typeof p === "string" && p.trim())
    .map((p) => path.resolve(p.trim()))
    .filter((p) => fs.existsSync(p))
    .slice(0, 10);

  const args = ["-j", DAYONE_JOURNAL];
  for (const t of tagList) {
    args.push("-t", t);
  }
  if (att.length) {
    args.push("-a", ...att);
  }
  args.push("--", "new");

  return new Promise((resolve) => {
    const child = spawn(DAYONE_BIN, args, {
      stdio: ["pipe", "pipe", "pipe"],
    });
    let out = "";
    let err = "";
    child.stdout.on("data", (d) => (out += d.toString("utf8")));
    child.stderr.on("data", (d) => (err += d.toString("utf8")));
    child.stdin.write(bodyMarkdown, "utf8");
    child.stdin.end();
    child.on("error", (e) => {
      resolve({ code: 127, out, err: err + String(e.message || e) });
    });
    child.on("close", (code) => resolve({ code: code ?? 1, out, err }));
  });
}

const server = http.createServer(async (req, res) => {
  try {
    const urlPath = String(req.url || "").split("?")[0];

    if (req.method === "GET" && urlPath === "/health") {
      json(res, 200, { ok: true, bridge: "dayone-cli", journal: DAYONE_JOURNAL });
      return;
    }

    if (req.method !== "POST" || (urlPath !== "/dayone" && urlPath !== "/dayone/")) {
      json(res, 404, { ok: false, error: "not found" });
      return;
    }

    if (!TOKEN) {
      json(res, 500, { ok: false, error: "DAYONE_BRIDGE_TOKEN not set" });
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
    const bodyMarkdown =
      typeof payload.body_markdown === "string" ? payload.body_markdown : "";

    if (!subject) {
      json(res, 400, { ok: false, error: "missing subject" });
      return;
    }
    if (!bodyMarkdown.trim()) {
      json(res, 400, { ok: false, error: "missing body_markdown" });
      return;
    }

    const attachments = Array.isArray(payload.attachments) ? payload.attachments : [];
    const extraTags = Array.isArray(payload.tags)
      ? payload.tags.filter((x) => typeof x === "string" && x.trim()).map((x) => x.trim())
      : [];

    const { code, out, err } = await runDayoneNew(bodyMarkdown, attachments, extraTags);
    if (code !== 0) {
      json(res, 502, {
        ok: false,
        error: "dayone CLI failed",
        code,
        stdout: out,
        stderr: err,
      });
      return;
    }

    json(res, 200, {
      ok: true,
      journal: DAYONE_JOURNAL,
      stdout: out,
      stderr: err || undefined,
    });
  } catch (e) {
    json(res, 500, { ok: false, error: String(e?.message || e) });
  }
});

server.listen(PORT, HOST, () => {
  process.stdout.write(
    `dayone-cli-bridge listening on http://${HOST}:${PORT}\n` +
      `POST /dayone (header X-Bridge-Token; JSON: subject, body_markdown, attachments?, tags?)\n` +
      `dayone binary: ${DAYONE_BIN}  journal: ${DAYONE_JOURNAL}\n`
  );
});
