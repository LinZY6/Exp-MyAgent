/**
 * spfit pack: sparse linear synthetic regression on a frozen CPU split.
 * Spawn only. Tool name is run_spfit (does not overwrite fnfit run_experiment).
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
	const runner = join(repoRoot(), "tools", "spfit", "run.py");
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

const runSpfit = defineTool({
	name: "run_spfit",
	label: "Run sp_fit experiment",
	description:
		"Fit one spec on the frozen sp_fit sparse linear split (CPU, milliseconds). " +
		"Does not write the ledger. Create the node first. Knobs: model=ols|ridge|lasso|oracle, " +
		"features=all|oracle, alpha (ridge/lasso). Primary metric test_mse, lower better.",
	parameters: Type.Object({
		experiment_id: Type.String({ description: "Id returned by create_experiment" }),
		model: Type.String({ description: "ols | ridge | lasso | oracle" }),
		collection: Type.Optional(Type.String({ description: "Must be sp_fit (default)" })),
		features: Type.Optional(Type.String({ description: "all | oracle (default all)" })),
		alpha: Type.Optional(Type.Number({ description: "ridge default 1; lasso default 0.08; ols/oracle omit" })),
	}),
	async execute(_id, input) {
		return asResult(invoke({ ...input }));
	},
});

export default function (pi: ExtensionAPI) {
	pi.registerTool(runSpfit);
}
