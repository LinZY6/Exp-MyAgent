/**
 * Campaign loop: do not yield to the user until campaign_gate allows a stop.
 * Does not pick the next scientific spec. Spawn only.
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

function parseGate(raw: string): {
	ok?: boolean;
	may_stop?: boolean;
	must?: string | null;
	next?: { id?: string; title?: string; status?: string } | null;
	error?: string;
	allowed?: boolean;
} {
	try {
		return JSON.parse(raw) as ReturnType<typeof parseGate>;
	} catch {
		return {};
	}
}

function asResult(text: string) {
	const parsed = parseGate(text);
	return {
		content: [{ type: "text" as const, text }],
		details: parsed,
		isError: parsed.ok === false,
	};
}

const ASK_MARKERS = [
	"要继续",
	"说一声",
	"要我接着",
	"哪一个",
	"选一个",
	"要不要",
	"继续吗",
	"should i continue",
	"which one",
];

const HALT = /停止这场|停止实验|别跑了|不要继续|stop campaign|\bhalt\b/i;

function looksLikeAsk(text: string): boolean {
	const t = text.trim().toLowerCase();
	if (!t) return false;
	return ASK_MARKERS.some((k) => t.includes(k.toLowerCase()));
}

function assistantText(message: unknown): string {
	const msg = message as { content?: unknown; role?: string };
	const c = msg?.content;
	if (typeof c === "string") return c;
	if (!Array.isArray(c)) return "";
	return c
		.filter((p) => p && typeof p === "object" && (p as { type?: string }).type === "text")
		.map((p) => String((p as { text?: string }).text || ""))
		.join("\n");
}

function hasToolCalls(message: unknown): boolean {
	const msg = message as { content?: unknown; toolCalls?: unknown[] };
	if (Array.isArray(msg?.toolCalls) && msg.toolCalls.length > 0) return true;
	const c = msg?.content;
	if (!Array.isArray(c)) return false;
	return c.some((p) => {
		const t = p && typeof p === "object" ? String((p as { type?: string }).type || "") : "";
		return t === "toolCall" || t === "tool_use" || t === "toolUse";
	});
}

function continuePrompt(gate: ReturnType<typeof parseGate>): string {
	const next = gate.next ? `${gate.next.id || ""} ${gate.next.title || ""}`.trim() : "";
	return (
		`[campaign-loop] 这场还没停。must=${gate.must || "queue_take"}` +
		(next ? ` next=${next}` : "") +
		"。现在就调用对应工具。禁止问用户。不要写收工报告。"
	);
}

const askUser = defineTool({
	name: "ask_user",
	label: "Ask the user (gated)",
	description:
		"The only way to ask the user a question once a lab is bound. " +
		"Calls the campaign intercept: if may_stop is false this tool fails and you must continue (queue_take / designer / unblock). " +
		"Do not write questions in assistant text.",
	parameters: Type.Object({
		text: Type.String({ description: "Draft question for the user" }),
	}),
	async execute(_id, input) {
		return asResult(invoke({ action: "ask_user", text: input.text }));
	},
});

export default function (pi: ExtensionAPI) {
	pi.registerTool(askUser);

	let userHalt = false;

	pi.on("input", async (event) => {
		if (event.source === "extension") return;
		const t = String(event.text || "").trim();
		if (HALT.test(t) || t === "停止" || t === "停下来" || t.toLowerCase() === "stop") {
			userHalt = true;
		}
	});

	pi.on("message_end", async (event) => {
		if (userHalt) return;
		const msg = event.message as { role?: string };
		if (msg?.role !== "assistant") return;
		if (hasToolCalls(event.message)) return;
		const text = assistantText(event.message);
		if (!looksLikeAsk(text)) return;
		const gate = parseGate(invoke({ action: "campaign_gate" }));
		if (gate.error && String(gate.error).includes("no lab bound")) return;
		if (gate.may_stop) return;
		const replacement = continuePrompt(gate);
		return {
			message: {
				...(event.message as object),
				content: [{ type: "text", text: replacement }],
			},
		};
	});

	pi.on("agent_settled", async () => {
		if (userHalt) return;
		const gate = parseGate(invoke({ action: "campaign_gate" }));
		if (gate.error && String(gate.error).includes("no lab bound")) return;
		if (gate.may_stop) return;
		await pi.sendMessage(
			{
				customType: "campaign-loop",
				content: continuePrompt(gate),
				display: false,
			},
			{ triggerTurn: true, deliverAs: "followUp" },
		);
	});
}
