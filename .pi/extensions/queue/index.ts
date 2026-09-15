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
		"Add or update a runnable experiment after the Designer posted a requirement. " +
		"proposed_by must be experimenter and requirement_id is required. " +
		"Does not create a DAG node and does not fit.",
	parameters: Type.Object({
		title: Type.String({ description: "Short name, e.g. poly3 small ridge" }),
		proposed_by: Type.String({
			description: "Must be experimenter",
		}),
		requirement_id: Type.String({ description: "id from designer post_requirement" }),
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
		"Experimenter: status after a bounce fix; Reviewer: status, experiment_id, note after a run. " +
		"Changing title/spec/priority needs proposed_by=experimenter.",
	parameters: Type.Object({
		id: Type.String(),
		proposed_by: Type.Optional(
			Type.String({ description: "Required when changing title, spec, or priority" }),
		),
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
		"empty=true is not a campaign-stop: main loop call_divergence or call_designer. " +
		"The Reviewer is the one who takes. If something is already running, returns that instead. peek=true lists without claiming.",
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
