/**
 * Experiment task queue. Spawn only. Does not run fits or write experiments.jsonl.
 */

import { existsSync } from "node:fs";
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

function invoke(params: Record<string, unknown>): string {
	const python = resolvePython();
	const runner = join(repoRoot(), "tools", "queue", "run.py");
	const lab = (process.env.EXPERIMENT_LAB || "").trim();
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

const queueList = defineTool({
	name: "queue_list",
	label: "List experiment queue",
	description:
		"List the lab task queue, highest priority first. Does not run experiments. " +
		"Optional status filter: queued|running|done|skipped|blocked.",
	parameters: Type.Object({
		status: Type.Optional(Type.String({ description: "queued|running|done|skipped|blocked" })),
	}),
	async execute(_id, input) {
		return asResult(invoke({ action: "list", ...input }));
	},
});

const queuePut = defineTool({
	name: "queue_put",
	label: "Enqueue experiment",
	description:
		"Add or update an experiment idea on the lab queue. Higher priority is taken first. " +
		"Does not create a DAG node and does not fit. Persist ideas here instead of a chat menu.",
	parameters: Type.Object({
		title: Type.String({ description: "Short name, e.g. poly3 small ridge" }),
		priority: Type.Optional(Type.Number({ description: "Integer; higher = sooner (default 100)" })),
		reason: Type.Optional(Type.String()),
		kind: Type.Optional(Type.String()),
		upstream: Type.Optional(Type.String()),
		change: Type.Optional(Type.String()),
		rationale: Type.Optional(Type.String()),
		model: Type.Optional(Type.String()),
		features: Type.Optional(Type.String()),
		degree: Type.Optional(Type.Number()),
		alpha: Type.Optional(Type.Number()),
		blocked_on: Type.Optional(Type.String({ description: "If set, status becomes blocked (e.g. need model=mars)" })),
		id: Type.Optional(Type.String({ description: "Existing id to upsert" })),
	}),
	async execute(_id, input) {
		return asResult(invoke({ action: "put", ...input }));
	},
});

const queueSet = defineTool({
	name: "queue_set",
	label: "Update queue task",
	description:
		"Change priority or status of a queued idea after seeing new metrics. " +
		"Example: bump C after A looks overfit; mark a task done after complete_experiment.",
	parameters: Type.Object({
		id: Type.String(),
		priority: Type.Optional(Type.Number()),
		status: Type.Optional(Type.String({ description: "queued|running|done|skipped|blocked" })),
		note: Type.Optional(Type.String()),
		experiment_id: Type.Optional(Type.String({ description: "DAG id after create_experiment" })),
		blocked_on: Type.Optional(Type.String()),
		reason: Type.Optional(Type.String()),
	}),
	async execute(_id, input) {
		return asResult(invoke({ action: "set", ...input }));
	},
});

const queueTake = defineTool({
	name: "queue_take",
	label: "Take next queue task",
	description:
		"Return the highest-priority queued task and mark it running. Does not run the fit. " +
		"Then you search/create/run/complete. If something is already running, returns that instead. " +
		"peek=true lists the next task without claiming it.",
	parameters: Type.Object({
		peek: Type.Optional(Type.Boolean()),
	}),
	async execute(_id, input) {
		return asResult(invoke({ action: "take", ...input }));
	},
});

export default function (pi: ExtensionAPI) {
	pi.registerTool(queueList);
	pi.registerTool(queuePut);
	pi.registerTool(queueSet);
	pi.registerTool(queueTake);
}
