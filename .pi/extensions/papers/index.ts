/**
 * Papers pack: download arXiv full text to disk; serve outline / grep / capped slices.
 * Spawn only. Does not write experiments.jsonl.
 */

import { existsSync, readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

function thisDir(): string {
	return dirname(fileURLToPath(import.meta.url));
}

function repoRoot(): string {
	return join(thisDir(), "..", "..", "..");
}

function resolvePython(): string {
	const envPy = process.env.EXPMEM_PYTHON || process.env.PYTHON || "";
	if (envPy && !envPy.includes("WindowsApps") && existsSync(envPy)) return envPy;
	const vendorWin = join(repoRoot(), ".vendor", "python", "python.exe");
	if (existsSync(vendorWin)) return vendorWin;
	const vendorUnix = join(repoRoot(), ".vendor", "python", "bin", "python3");
	if (existsSync(vendorUnix)) return vendorUnix;
	if (envPy && !envPy.includes("WindowsApps")) return envPy;
	return process.platform === "win32" ? "python" : "python3";
}

function readLabSession(): { lab?: string } {
	const p = join(repoRoot(), ".pi", "lab-session.json");
	if (!existsSync(p)) return {};
	try {
		return JSON.parse(readFileSync(p, "utf8")) as { lab?: string };
	} catch {
		return {};
	}
}

function invoke(params: Record<string, unknown>, timeoutMs: number): string {
	const python = resolvePython();
	const runner = join(repoRoot(), "tools", "papers", "run.py");
	const lab = (process.env.EXPERIMENT_LAB || readLabSession().lab || "").trim();
	const proc = spawnSync(
		python,
		[
			runner,
			"--params",
			JSON.stringify({ ...params, repo: repoRoot(), ...(lab ? { lab } : {}) }),
		],
		{
			encoding: "utf-8",
			env: {
				...process.env,
				PYTHONUTF8: "1",
				PYTHONIOENCODING: "utf-8",
			},
			maxBuffer: 2 * 1024 * 1024,
			timeout: timeoutMs,
			windowsHide: true,
		},
	);
	if (proc.error) return JSON.stringify({ ok: false, error: String(proc.error) });
	const stdout = (proc.stdout || "").trim();
	const stderr = (proc.stderr || "").trim();
	if (proc.status !== 0) {
		return JSON.stringify({ ok: false, error: stderr || stdout || `exit ${proc.status}` });
	}
	return stdout || "{}";
}

function asResult(text: string) {
	let parsed: { ok?: boolean } = {};
	try {
		parsed = JSON.parse(text) as { ok?: boolean };
	} catch {
		parsed = {};
	}
	return {
		content: [{ type: "text" as const, text }],
		details: parsed,
		isError: parsed.ok === false,
	};
}

const randomPaper = defineTool({
	name: "random_paper",
	label: "Random arXiv paper",
	description:
		"Pick a random arXiv paper, download it for you, and return title/outline — not the body. " +
		"You do not need a paper_id or a local PDF. Optional query or category (default cs.LG). " +
		"Then read_paper(section='Abstract').",
	parameters: Type.Object({
		query: Type.Optional(Type.String({ description: "Topic keywords, e.g. ridge regression" })),
		category: Type.Optional(Type.String({ description: "arXiv category, e.g. cs.LG or stat.ML" })),
	}),
	async execute(_id, input) {
		return asResult(invoke({ action: "random", ...input }, 180_000));
	},
});

const fetchPaper = defineTool({
	name: "fetch_paper",
	label: "Fetch paper full text",
	description:
		"Download one arXiv paper to the lab papers/ folder and extract text. " +
		"Returns title, abstract, outline, line count — NEVER the full body. " +
		"Then use paper_outline / search_paper / read_paper. Do not Pi-read paper.txt whole.",
	parameters: Type.Object({
		paper_id: Type.String({ description: "arXiv id, e.g. 1706.03762 or arxiv:1706.03762" }),
		force: Type.Optional(Type.Boolean({ description: "Re-download even if cached" })),
	}),
	async execute(_id, input) {
		return asResult(invoke({ action: "fetch", ...input }, 180_000));
	},
});

const paperOutline = defineTool({
	name: "paper_outline",
	label: "Paper outline",
	description:
		"List section headings with start line numbers for a fetched paper. " +
		"Does not return body text. Call fetch_paper or random_paper first.",
	parameters: Type.Object({
		paper_id: Type.String({ description: "arXiv id" }),
	}),
	async execute(_id, input) {
		return asResult(invoke({ action: "outline", ...input }, 30_000));
	},
});

const searchPaper = defineTool({
	name: "search_paper",
	label: "Search inside one paper",
	description:
		"Grep one fetched paper. Returns up to 8 short snippets with line numbers, not the whole paper. " +
		"Then open a hit with read_paper(start_line=...).",
	parameters: Type.Object({
		paper_id: Type.String({ description: "arXiv id" }),
		query: Type.String({ description: "Case-insensitive keywords" }),
		max_hits: Type.Optional(Type.Number({ description: "Max snippets, default 8, cap 8" })),
	}),
	async execute(_id, input) {
		return asResult(invoke({ action: "search", ...input }, 30_000));
	},
});

const readPaper = defineTool({
	name: "read_paper",
	label: "Read paper slice",
	description:
		"Read a capped slice of a fetched paper (default 50 lines, max 80 lines / 6000 chars). " +
		"Pass start_line or section (heading substring). If truncated, call again with start_line=next_line. " +
		"Never ask for the full paper.",
	parameters: Type.Object({
		paper_id: Type.String({ description: "arXiv id" }),
		start_line: Type.Optional(Type.Number({ description: "1-based line (ignored if section is set)" })),
		n_lines: Type.Optional(Type.Number({ description: "How many lines, default 50, max 80" })),
		section: Type.Optional(Type.String({ description: "Heading substring, e.g. Abstract or 3.1" })),
	}),
	async execute(_id, input) {
		return asResult(invoke({ action: "read", ...input }, 30_000));
	},
});

export default function (pi: ExtensionAPI) {
	pi.registerTool(randomPaper);
	pi.registerTool(fetchPaper);
	pi.registerTool(paperOutline);
	pi.registerTool(searchPaper);
	pi.registerTool(readPaper);
}
