/**
 * microgrid pack: run one problem-1 dispatch variant in the bound lab.
 * Spawn only. Does not write experiments.jsonl, does not pick the variant.
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
	const lab = (process.env.EXPERIMENT_LAB || readLabSession().lab || "").trim();
	if (!lab) return JSON.stringify({ ok: false, error: "no lab bound" });
	const runner = join(lab, "src", "microgrid", "run.py");
	if (!existsSync(runner)) return JSON.stringify({ ok: false, error: `missing runner: ${runner}` });
	const args = [runner, "--variant", String(params.variant)];
	const proc = spawnSync(python, args, {
		encoding: "utf-8",
		cwd: lab,
		env: {
			...process.env,
			EXPERIMENT_LAB: lab,
			EXPMEM_ROOT: process.env.EXPMEM_ROOT || lab,
			PYTHONUTF8: "1",
			PYTHONIOENCODING: "utf-8",
		},
		maxBuffer: 8 * 1024 * 1024,
		timeout: 300_000,
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

const runMicrogrid = defineTool({
	name: "run_microgrid",
	label: "Run microgrid dispatch variant",
	description:
		"Run one problem-1 dispatch variant in the bound lab (src/microgrid/run.py). " +
		"Prints JSON metrics and writes result1.xlsx. Does not write the experiment ledger. " +
		"Create the DAG node first, then pass experiment_id. " +
		"variant: no_storage | greedy | lp | lp_no_curtail | lp_roundtrip_eta | milp_no_simultaneous.",
	parameters: Type.Object({
		experiment_id: Type.String({ description: "Id returned by create_experiment" }),
		variant: Type.String({ description: "no_storage|greedy|lp|lp_no_curtail|lp_roundtrip_eta|milp_no_simultaneous" }),
	}),
	async execute(_id, input) {
		return asResult(invoke({ ...input }));
	},
});

export default function (pi: ExtensionAPI) {
	pi.registerTool(runMicrogrid);
}
