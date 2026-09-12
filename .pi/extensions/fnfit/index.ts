/**
 * fnfit pack: run one spec on the frozen Friedman #1 split.
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

function invoke(params: Record<string, unknown>): string {
	const python = resolvePython();
	const runner = join(repoRoot(), "tools", "fnfit", "run.py");
	const lab = (process.env.EXPERIMENT_LAB || readLabSession().lab || "").trim();
	const proc = spawnSync(python, [runner, "--params", JSON.stringify(params)], {
		encoding: "utf-8",
		env: {
			...process.env,
			...(lab ? { EXPERIMENT_LAB: lab, EXPMEM_ROOT: process.env.EXPMEM_ROOT || lab } : {}),
			PYTHONUTF8: "1",
			PYTHONIOENCODING: "utf-8",
		},
		maxBuffer: 8 * 1024 * 1024,
		timeout: 60_000,
		windowsHide: true,
	});
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

const runExperiment = defineTool({
	name: "run_experiment",
	label: "Run fn_fit experiment",
	description:
		"Fit one spec on the frozen fn_fit Friedman #1 split (CPU, milliseconds). " +
		"Does not write the experiment ledger. Create the node first, then pass experiment_id. " +
		"After metrics, call complete_experiment. Knobs: model=ols|ridge|poly, " +
		"features=all|signal|drop_x4, degree (poly only), alpha (ridge, or poly L2).",
	parameters: Type.Object({
		experiment_id: Type.String({ description: "Id returned by create_experiment" }),
		model: Type.String({ description: "ols | ridge | poly" }),
		collection: Type.Optional(Type.String({ description: "Must be fn_fit (default)" })),
		features: Type.Optional(Type.String({ description: "all | signal | drop_x4 (default all)" })),
		degree: Type.Optional(Type.Number({ description: "poly only: 1, 2, or 3 (3 needs features=signal)" })),
		alpha: Type.Optional(Type.Number({ description: "ridge default 1; ols must omit or 0" })),
	}),
	async execute(_id, input) {
		return asResult(invoke({ ...input }));
	},
});

export default function (pi: ExtensionAPI) {
	pi.registerTool(runExperiment);
}
