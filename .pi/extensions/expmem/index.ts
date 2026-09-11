/**
 * expmem pack: one Pi tool per Python action.
 * Spawn only. Business logic stays in tools/expmem.
 */

import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, delimiter, join } from "node:path";
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

function pythonPath(): string {
	const src = join(repoRoot(), "tools", "expmem", "src");
	const prev = process.env.PYTHONPATH || "";
	return prev ? `${src}${delimiter}${prev}` : src;
}

function invoke(action: string, params: Record<string, unknown>, project: string): string {
	const python = resolvePython();
	const root = process.env.EXPMEM_ROOT || join(repoRoot(), "expmem_data");
	const runner = join(repoRoot(), "tools", "expmem", "run.py");
	const proc = spawnSync(
		python,
		[
			runner,
			"--root",
			root,
			"--project",
			project,
			"invoke",
			"--action",
			action,
			"--params",
			JSON.stringify(params),
		],
		{
			encoding: "utf-8",
			env: {
				...process.env,
				PYTHONPATH: pythonPath(),
				PYTHONUTF8: "1",
				PYTHONIOENCODING: "utf-8",
			},
			maxBuffer: 8 * 1024 * 1024,
			timeout: 60_000,
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

const searchPapers = defineTool({
	name: "search_papers",
	label: "Search papers",
	description:
		"Search arXiv for external literature (not the experiment DB). " +
		"After a hit, still call search_experiments before creating a node.",
	parameters: Type.Object({
		query: Type.String({ description: "arXiv search query" }),
		limit: Type.Optional(Type.Number({ description: "Max hits, default 5" })),
	}),
	async execute(_id, input) {
		const text = invoke("search_papers", { ...input }, process.env.EXPMEM_PROJECT || "default");
		return asResult(text);
	},
});

const searchExperiments = defineTool({
	name: "search_experiments",
	label: "Search experiments",
	description:
		"BM25 search over one experiment collection. Required: collection + keywords. " +
		"Always call before create_experiment. Hits are past trials, not papers.",
	parameters: Type.Object({
		collection: Type.String({
			description: "Experiment DB name under EXPMEM_ROOT (e.g. rec_ctr), or path to experiments.jsonl",
		}),
		keywords: Type.String({
			description: "BM25 keywords: paper id, module name, rationale, intended change",
		}),
		kind: Type.Optional(Type.String({ description: "baseline|ablation|add_module|change_module|other" })),
		paper: Type.Optional(Type.String({ description: "Filter by arxiv id or title substring" })),
		upstream: Type.Optional(Type.String({ description: "Filter by parent experiment id" })),
		status: Type.Optional(Type.String({ description: "planned|running|done|failed" })),
		fields: Type.Optional(
			Type.String({ description: "BM25 fields: papers,rationale,change,expected (default all)" }),
		),
		top_k: Type.Optional(Type.Number()),
	}),
	async execute(_id, input) {
		const project = input.collection || process.env.EXPMEM_PROJECT || "default";
		const text = invoke("search_experiments", { ...input }, project);
		return asResult(text);
	},
});

const createExperiment = defineTool({
	name: "create_experiment",
	label: "Create experiment",
	description:
		"Record a planned experiment node. Call search_experiments first; duplicates are rejected. " +
		"Non-baseline kinds require upstream parent id(s).",
	parameters: Type.Object({
		collection: Type.String({ description: "Which experiment DB under EXPMEM_ROOT" }),
		kind: Type.String({ description: "baseline|ablation|add_module|change_module|other" }),
		rationale: Type.String({ description: "Why this change" }),
		change: Type.String({ description: "What will be changed" }),
		expected: Type.Optional(Type.String({ description: "Expected outcome, e.g. auc +0.002" })),
		upstream: Type.Optional(
			Type.String({ description: "Comma-separated parent experiment ids (required unless baseline)" }),
		),
		papers: Type.Optional(Type.String({ description: "Comma-separated arxiv ids or titles" })),
		force: Type.Optional(Type.Boolean({ description: "Skip duplicate gate" })),
	}),
	async execute(_id, input) {
		const project = input.collection || process.env.EXPMEM_PROJECT || "default";
		const payload: Record<string, unknown> = { ...input };
		if (typeof payload.upstream === "string") {
			payload.upstream = payload.upstream
				.split(",")
				.map((s) => s.trim())
				.filter(Boolean);
		}
		const text = invoke("create_experiment", payload, project);
		return asResult(text);
	},
});

const completeExperiment = defineTool({
	name: "complete_experiment",
	label: "Complete experiment",
	description: "Write actual metrics after training. Does not create a node; experiment_id must already exist.",
	parameters: Type.Object({
		collection: Type.String({ description: "Which experiment DB under EXPMEM_ROOT" }),
		experiment_id: Type.String({ description: "Id returned by create_experiment" }),
		metrics: Type.Optional(Type.String({ description: 'JSON object string, e.g. {"auc":0.73}' })),
		verdict: Type.Optional(Type.String({ description: "improved|flat|regressed|failed" })),
		delta: Type.Optional(Type.Number()),
		error: Type.Optional(Type.String()),
		note: Type.Optional(Type.String()),
		failed: Type.Optional(Type.Boolean()),
	}),
	async execute(_id, input) {
		const project = input.collection || process.env.EXPMEM_PROJECT || "default";
		const text = invoke("complete_experiment", { ...input }, project);
		return asResult(text);
	},
});

export default function (pi: ExtensionAPI) {
	pi.registerTool(searchPapers);
	pi.registerTool(searchExperiments);
	pi.registerTool(createExperiment);
	pi.registerTool(completeExperiment);
}
