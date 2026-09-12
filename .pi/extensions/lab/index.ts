/**
 * Lab pack: bind a user folder after a safety check. Spawn only.
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

function invoke(params: Record<string, unknown>): string {
	const python = resolvePython();
	const runner = join(repoRoot(), "tools", "lab", "run.py");
	const proc = spawnSync(
		python,
		[runner, "--params", JSON.stringify({ ...params, repo: repoRoot() })],
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
	let parsed: { ok?: boolean; bound?: boolean; lab?: string } = {};
	try {
		parsed = JSON.parse(text) as { ok?: boolean; bound?: boolean; lab?: string };
	} catch {
		parsed = {};
	}
	if (parsed.ok && parsed.bound && parsed.lab) {
		process.env.EXPERIMENT_LAB = parsed.lab;
		process.env.EXPMEM_ROOT = parsed.lab;
	}
	return {
		content: [{ type: "text" as const, text }],
		details: parsed,
		isError: parsed.ok === false,
	};
}

const useLab = defineTool({
	name: "use_lab",
	label: "Use lab folder",
	description:
		"Inspect or bind a folder for this project (code + experiments.jsonl). " +
		"First call WITHOUT force: safety check only; show the resolved path and wait for the user to say yes. " +
		"Second call with force=true actually creates/binds. Never invent a path. " +
		"Relative names go under experiments/<name> in the repo.",
	parameters: Type.Object({
		path: Type.String({ description: "Folder the user named (absolute, or a short name)" }),
		force: Type.Optional(Type.Boolean({ description: "true only after the user explicitly confirms the resolved path" })),
		empty: Type.Optional(Type.Boolean({ description: "start with an empty ledger instead of the 7-node seed" })),
	}),
	async execute(_id, input) {
		return asResult(invoke({ action: "use_lab", ...input }));
	},
});

const labStatus = defineTool({
	name: "lab_status",
	label: "Lab status",
	description: "Show the currently bound lab folder, or that none is bound.",
	parameters: Type.Object({}),
	async execute() {
		return asResult(invoke({ action: "lab_status" }));
	},
});

const assertLabPath = defineTool({
	name: "assert_lab_path",
	label: "Check path in lab",
	description:
		"Before editing or writing a file, check that the path is inside the bound lab. " +
		"If in_lab is false, do not edit.",
	parameters: Type.Object({
		path: Type.String({ description: "File or directory to check" }),
	}),
	async execute(_id, input) {
		return asResult(invoke({ action: "assert_lab_path", ...input }));
	},
});

const labCodeHash = defineTool({
	name: "lab_code_hash",
	label: "Hash lab runner code",
	description:
		"SHA-256 of this lab's src/ plus protocol.json. Patch-reviewer must copy code_sha256 " +
		"into the approve verdict. After a later edit the hash changes; old approve files do not match.",
	parameters: Type.Object({}),
	async execute() {
		return asResult(invoke({ action: "lab_code_hash" }));
	},
});

const protocolCheck = defineTool({
	name: "protocol_check",
	label: "Protocol gate before run",
	description:
		"Hard check before any lab fit: if src/ or protocol.json drifted from the init baseline, " +
		"a patch-reviewer approve must carry the current lab_code_hash. Old approve files are not enough.",
	parameters: Type.Object({}),
	async execute() {
		return asResult(invoke({ action: "protocol_check" }));
	},
});

export function readLabSession(root = repoRoot()): { lab?: string; collection?: string } {
	const p = join(root, ".pi", "lab-session.json");
	if (!existsSync(p)) return {};
	try {
		return JSON.parse(readFileSync(p, "utf8")) as { lab?: string; collection?: string };
	} catch {
		return {};
	}
}

export default function (pi: ExtensionAPI) {
	pi.registerTool(useLab);
	pi.registerTool(labStatus);
	pi.registerTool(assertLabPath);
	pi.registerTool(labCodeHash);
	pi.registerTool(protocolCheck);
}
