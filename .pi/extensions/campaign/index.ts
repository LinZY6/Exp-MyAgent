/**
 * Campaign loop: do not yield to the user until the interceptor subprocess allows a stop.
 * Does not pick the next scientific spec. Spawn only (official `pi --mode json`).
 */

import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { Type } from "@earendil-works/pi-ai";
import { defineTool, type ExtensionAPI } from "@earendil-works/pi-coding-agent";

import { parseInterceptVerdict, runProjectAgent } from "./spawn.ts";

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
	may_yield?: boolean;
	must?: string | null;
	next?: { id?: string; title?: string; status?: string } | null;
	error?: string;
	allowed?: boolean;
	intercept?: boolean;
	interceptor_stop?: boolean;
	hat?: string;
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

function assistantText(message: unknown): string {
	const msg = message as { content?: unknown };
	const c = msg?.content;
	if (!Array.isArray(c)) return typeof c === "string" ? c : "";
	return c
		.map((p) => {
			if (p && typeof p === "object" && (p as { type?: string }).type === "text") {
				return String((p as { text?: string }).text || "");
			}
			return "";
		})
		.join("\n");
}

function isLoopInjection(message: unknown): boolean {
	const t = assistantText(message);
	return t.includes("[campaign-loop]") || t.includes("[interceptor-as-user]");
}

const HALT = /停止这场|停止实验|别跑了|不要继续|stop campaign|\bhalt\b/i;

function toolNames(message: unknown): string[] {
	const msg = message as { content?: unknown; toolCalls?: { name?: string }[] };
	const names: string[] = [];
	if (Array.isArray(msg?.toolCalls)) {
		for (const t of msg.toolCalls) {
			if (t?.name) names.push(String(t.name));
		}
	}
	const c = msg?.content;
	if (Array.isArray(c)) {
		for (const p of c) {
			if (p && typeof p === "object") {
				const t = p as { type?: string; name?: string };
				if (t.type === "toolCall" || t.type === "tool_use" || t.type === "toolUse") {
					if (t.name) names.push(String(t.name));
				}
			}
		}
	}
	return names;
}

const DISPATCH = new Set([
	"call_designer",
	"call_experimenter",
	"call_reviewer",
	"ask_user",
	"campaign_gate",
	"use_lab",
	"lab_status",
	"agent_done",
	"task",
]);

const IMPLEMENT = new Set(["write", "edit", "powershell", "bash", "shell"]);

function isDispatchTurn(message: unknown): boolean {
	return toolNames(message).some((n) => DISPATCH.has(n.toLowerCase()));
}

function continuePrompt(gate: ReturnType<typeof parseGate>): string {
	const hat = String(gate.hat || "main");
	if (hat === "experimenter") {
		return (
			"[campaign-loop] 实验者帽子还在。读 packet，assert_lab_path，write/edit 只改 lab src，然后 queue_put(requirement_id)。"
			+ "禁止再 call_experimenter。禁止问用户。不要写收工报告。"
		);
	}
	if (hat === "experiment-designer" || hat === "designer") {
		return (
			"[campaign-loop] 设计者帽子还在。post_requirement 或 designer_reply，然后 agent_done。"
			+ "禁止问用户。不要写收工报告。"
		);
	}
	if (hat === "reviewer") {
		return (
			"[campaign-loop] 审查者帽子还在。queue_take，审，run_* / complete，或 bounce_to_experimenter。"
			+ "禁止问用户。不要写收工报告。"
		);
	}
	const next = gate.next ? `${gate.next.id || ""} ${gate.next.title || ""}`.trim() : "";
	if (gate.must === "ask_user" && gate.interceptor_stop) {
		return (
			"[campaign-loop] 拦截者与设计者同意停场。现在再调一次 ask_user，把话轮交给真人。"
			+ "只问停止 / 导出 / 改 DIRECTIONS。禁止问要不要深化。禁止写收工报告。"
		);
	}
	if (gate.must === "ask_user" || (gate.may_stop && !gate.may_yield)) {
		return (
			"[campaign-loop] 这场还没停。must=ask_user。"
			+ "现在就调用 ask_user，把你本想告诉用户的汇总放进 text。"
			+ "这个工具会把草稿交给拦截者子 Agent（它再 task 设计者），不是交给用户。"
			+ "禁止在正文里问用户。"
		);
	}
	if (gate.must === "call_divergence") {
		return (
			"[campaign-loop] 这场还没停。空队列请 ask_user（拦截者子 Agent），不要再戴 call_divergence 帽子。"
		);
	}
	return (
		`[campaign-loop] 这场还没停。must=${gate.must || "call_designer"}` +
		(next ? ` next=${next}` : "") +
		"。现在就调用对应的 Agent 工具（call_designer / call_experimenter / call_reviewer / ask_user）。禁止问用户。不要写收工报告。"
	);
}

export default function (pi: ExtensionAPI) {
	if (process.env.PI_CAMPAIGN_PASSIVE === "1") {
		return;
	}

	pi.registerTool(
		defineTool({
			name: "ask_user",
			label: "Ask the user (gated)",
			description:
				"Once a lab is bound, this is the only user-facing channel. " +
				"Empty queue: the tool spawns the interceptor subagent (isolated pi process) with your text. " +
				"The interceptor must task(agent=designer). If they continue, that reply is injected as the user to the main loop. " +
				"If they stop, this tool then yields halt/export/DIRECTIONS to the human. " +
				"Queue still busy: the tool fails; call the agent in must.",
			parameters: Type.Object({
				text: Type.String({
					description: "Wrap-up you would tell the user, or (after interceptor stop) halt/export/DIRECTIONS only",
				}),
			}),
			async execute(_id, input, signal) {
				const first = parseGate(invoke({ action: "ask_user", text: input.text }));
				if (first.ok === false || first.allowed) {
					return asResult(JSON.stringify(first));
				}
				if (!first.intercept) {
					return asResult(JSON.stringify(first));
				}
				const spawned = await runProjectAgent({
					cwd: repoRoot(),
					agent: "interceptor",
					task: [
						"The main loop called ask_user. That is not a human yet.",
						"Consult designer via task { agent: \"designer\", agentScope: \"both\" }.",
						"Then return the JSON verdict (stop true/false).",
						"",
						"Main-loop draft:",
						input.text,
					].join("\n"),
					signal,
				});
				if (!spawned.ok) {
					return {
						content: [{ type: "text" as const, text: JSON.stringify({ ok: false, error: spawned.error }) }],
						details: { ok: false, error: spawned.error },
						isError: true,
					};
				}
				const verdict = parseInterceptVerdict(spawned.text);
				if (!verdict.ok) {
					return {
						content: [
							{
								type: "text" as const,
								text: JSON.stringify({
									ok: false,
									error: verdict.error,
									raw: (spawned.text || "").slice(0, 800),
								}),
							},
						],
						details: { ok: false, error: verdict.error },
						isError: true,
					};
				}
				const asUser = verdict.as_user;
				invoke({
					action: "record_intercept",
					stop: verdict.stop,
					as_user: asUser,
					ask: verdict.ask,
					raw: spawned.text,
					summary: input.text,
				});
				if (!verdict.stop) {
					if (!asUser) {
						return {
							content: [
								{
									type: "text" as const,
									text: JSON.stringify({
										ok: false,
										error: "interceptor continue requires as_user text",
									}),
								},
							],
							details: { ok: false, error: "interceptor continue requires as_user text" },
							isError: true,
						};
					}
					const payload = asUser;
					await pi.sendMessage(
						{
							customType: "interceptor-as-user",
							content: `[interceptor-as-user]\n${payload}`,
							display: true,
						},
						{ triggerTurn: true, deliverAs: "followUp" },
					);
					return {
						content: [
							{
								type: "text" as const,
								text: JSON.stringify({
									ok: true,
									allowed: false,
									may_yield: false,
									intercept: true,
									interceptor_stop: false,
									acted_as_user: true,
									as_user: payload,
									must: "call_designer",
									hint: "Interceptor acted as the user. Follow that steer; do not ask the human.",
								}),
							},
						],
						details: {
							ok: true,
							allowed: false,
							may_yield: false,
							acted_as_user: true,
						},
						isError: false,
					};
				}
				const yieldText = verdict.ask || "题内工作拦截者与设计者认为可以停。导出、停止，或改 DIRECTIONS。不要问要不要深化。";
				return asResult(invoke({ action: "ask_user", text: yieldText }));
			},
		}),
	);

	let userHalt = false;
	let awaitingModel = false;
	let lastKickAt = 0;
	let kickTimer: ReturnType<typeof setTimeout> | null = null;
	const KICK_GAP_MS = 2500;

	async function kick(gate: ReturnType<typeof parseGate>) {
		if (userHalt || awaitingModel) return;
		if (gate.error && String(gate.error).includes("no lab bound")) return;
		if (gate.may_yield) return;
		awaitingModel = true;
		lastKickAt = Date.now();
		await pi.sendMessage(
			{
				customType: "campaign-loop",
				content: continuePrompt(gate),
				display: false,
			},
			{ triggerTurn: true, deliverAs: "followUp" },
		);
	}

	function armKick(gate: ReturnType<typeof parseGate>, wait: number) {
		if (kickTimer || userHalt) return;
		kickTimer = setTimeout(() => {
			kickTimer = null;
			void kick(gate);
		}, Math.max(wait, 0));
	}

	pi.on("tool_call", async (event: { toolName?: string; name?: string }) => {
		const name = String(event.toolName || event.name || "").toLowerCase();
		if (!IMPLEMENT.has(name)) return;
		const gate = parseGate(invoke({ action: "campaign_gate" }));
		if (gate.error && String(gate.error).includes("no lab bound")) return;
		if (gate.may_yield) return;
		const hat = String(gate.hat || "main");
		const canWrite = hat === "experimenter";
		const canShell = hat === "experimenter" || hat === "reviewer";
		if ((name === "write" || name === "edit") && !canWrite) {
			return {
				block: true,
				reason:
					`[campaign-loop] 主 loop 不能自己改代码或写结果。当前 hat=${hat} must=${gate.must || "call_designer"}。`
					+ "先 call_designer / call_experimenter / call_reviewer。实验者帽子才能 write/edit。",
			};
		}
		if ((name === "powershell" || name === "bash" || name === "shell") && !canShell) {
			return {
				block: true,
				reason:
					`[campaign-loop] 主 loop 不能自己跑实验。当前 hat=${hat} must=${gate.must || "call_designer"}。`
					+ "先 call_designer；跑实验是审查者的 run_*，不是 powershell。",
			};
		}
	});

	pi.on("input", async (event) => {
		if (event.source === "extension") return;
		const t = String(event.text || "").trim();
		if (HALT.test(t) || t === "停止" || t === "停下来" || t.toLowerCase() === "stop") {
			userHalt = true;
		}
		awaitingModel = false;
	});

	pi.on("message_end", async (event) => {
		if (userHalt) return;
		const msg = event.message as { role?: string };
		if (msg?.role !== "assistant") return;
		if (isDispatchTurn(event.message) || toolNames(event.message).length > 0) {
			awaitingModel = false;
			return;
		}
		if (isLoopInjection(event.message)) {
			awaitingModel = false;
			return;
		}
		const gate = parseGate(invoke({ action: "campaign_gate" }));
		if (gate.error && String(gate.error).includes("no lab bound")) return;
		if (gate.may_yield) return;
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
		if (gate.may_yield) return;
		if (awaitingModel) return;
		const wait = KICK_GAP_MS - (Date.now() - lastKickAt);
		if (wait > 0) {
			armKick(gate, wait);
			return;
		}
		await kick(gate);
	});
}
