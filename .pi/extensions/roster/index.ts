/**
 * Agent roster: specialists as tools. Spawn only. Does not pick kind/change.
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

function invoke(params: Record<string, unknown>, timeoutMs = 60_000): string {
	const python = resolvePython();
	const runner = join(repoRoot(), "tools", "roster", "run.py");
	const lab = (process.env.EXPERIMENT_LAB || "").trim();
	const proc = spawnSync(
		python,
		[runner, "--params", JSON.stringify({ ...params, repo: repoRoot(), ...(lab ? { lab } : {}) })],
		{
			encoding: "utf-8",
			env: {
				...process.env,
				PYTHONUTF8: "1",
				PYTHONIOENCODING: "utf-8",
			},
			maxBuffer: 8 * 1024 * 1024,
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

function tool(
	name: string,
	label: string,
	description: string,
	parameters: ReturnType<typeof Type.Object>,
	action: string,
	timeoutMs?: number,
) {
	return defineTool({
		name,
		label,
		description,
		parameters,
		async execute(_id, input) {
			return asResult(invoke({ action, ...input }, timeoutMs));
		},
	});
}

export default function (pi: ExtensionAPI) {
	pi.registerTool(
		tool(
			"call_designer",
			"Call experiment designer",
			"Main loop: put on the Designer hat. Writes a whitelist packet (DIRECTIONS, DAG digest, papers, memory, unread questions). "
				+ "intent=propose|clarify|stop_check|discuss. Designer posts requirements; does not queue_put, take, run, or edit DAG.",
			Type.Object({
				intent: Type.Optional(Type.String({ description: "propose | clarify | stop_check | discuss" })),
				note: Type.Optional(Type.String()),
			}),
			"call_designer",
		),
	);
	pi.registerTool(
		tool(
			"call_experimenter",
			"Call experimenter",
			"Main loop: put on the Experimenter hat. Stateless: implements the current designer requirement or a reviewer bounce. "
				+ "May edit lab code, queue_put with requirement_id, or ask_designer. Must not run fits or write the DAG.",
			Type.Object({ note: Type.Optional(Type.String()) }),
			"call_experimenter",
		),
	);
	pi.registerTool(
		tool(
			"call_reviewer",
			"Call reviewer",
			"Main loop: put on the Reviewer hat. Takes the next queued job, checks leak + spec vs code, "
				+ "runs the fit, writes the DAG. Pass hard_checks into complete_experiment. "
				+ "On contrast_violation or fail, bounce_to_experimenter with the tool error verbatim. Must not edit lab src.",
			Type.Object({ note: Type.Optional(Type.String()) }),
			"call_reviewer",
		),
	);
	pi.registerTool(
		tool(
			"call_divergence",
			"Call divergence interceptor",
			"Main loop: intercept a would-be stop while the queue is empty. "
				+ "Pass summary= what you would tell the user (design/implement/review so far). "
				+ "Interceptor sees DIRECTIONS + that summary + DAG, not designer memory. "
				+ "It challenges missing properties, papers, stability, and remaining depth. "
				+ "Stop only after 2 challenge rounds. record_exhausted then ask_user. "
				+ "Do not write exhausted JSON with the editor.",
			Type.Object({
				summary: Type.String({
					description: "Main loop wrap-up of design/implement/review so far; what it would tell the user. Interceptor attacks this. Required.",
				}),
				note: Type.Optional(Type.String()),
			}),
			"call_divergence",
		),
	);
	pi.registerTool(
		tool(
			"ask_designer",
			"Ask the designer",
			"Experimenter: clarify a requirement. Divergence interceptor: independent challenge — "
				+ "at least two diverse proposals (different kind), ask WHY they were not tried, "
				+ "demand more papers and more schemes. Do not copy the Designer's prior plan. "
				+ "Main loop then call_designer.",
			Type.Object({
				from_role: Type.String({ description: "experimenter or divergence-interceptor" }),
				question: Type.String(),
				kind: Type.Optional(Type.String({ description: "clarify | low_value | stop_check" })),
				requirement_id: Type.Optional(Type.String()),
				task_id: Type.Optional(Type.String()),
				dag_summary: Type.Optional(Type.String()),
				proposals: Type.Optional(Type.String({
					description: "JSON list of {kind, change, reason}. Required when from_role=divergence-interceptor",
				})),
			}),
			"ask_designer",
		),
	);
	pi.registerTool(
		tool(
			"designer_reply",
			"Designer reply",
			"Designer: answer an experimenter question, or a stop_check challenge. "
				+ "challenge_round < 2: agree_stop is refused; deep_research a new query and post_requirement. "
				+ "After two challenges, cover interceptor proposals with DAG/DUPLICATE/DIRECTIONS/USER "
				+ "(CHARTER does not count) or unused papers still block stop. Pass mail_id from the packet.",
			Type.Object({
				mail_id: Type.Optional(Type.String()),
				kind: Type.Optional(Type.String({ description: "clarify | stop_check" })),
				meaning: Type.Optional(Type.String()),
				necessity: Type.Optional(Type.String()),
				reliability: Type.Optional(Type.String()),
				how_to_run: Type.Optional(Type.String()),
				papers: Type.Optional(Type.String({ description: "comma-separated paper ids" })),
				agree_stop: Type.Optional(Type.Boolean()),
				new_ideas: Type.Optional(Type.Boolean()),
				note: Type.Optional(Type.String()),
				off_charter_papers: Type.Optional(Type.String({
					description: "Paper ids DIRECTIONS/CHARTER exclude; unused papers otherwise block agree_stop",
				})),
				rejected_proposals: Type.Optional(Type.String({
					description: "JSON list of {change, why}. Required to agree_stop when the interceptor sent proposals. why starts with DAG|DUPLICATE|DIRECTIONS|USER (not CHARTER)",
				})),
			}),
			"designer_reply",
		),
	);
	pi.registerTool(
		tool(
			"post_requirement",
			"Post designer requirement",
			"Designer: give the Experimenter a brief (kind, change, knobs, papers, why). Not queue_put. "
				+ "Ablation must name upstream, held_fixed (same inputs as the parent), and expect_vs_parent "
				+ "(default not_worse). hard_checks freeze on this id. Check search_experiments first.",
			Type.Object({
				change: Type.String(),
				kind: Type.Optional(Type.String()),
				upstream: Type.Optional(Type.String()),
				held_fixed: Type.Optional(Type.String({ description: "comma-separated inputs that must match the parent" })),
				expect_vs_parent: Type.Optional(Type.String({ description: "improve | not_worse | worsen | any" })),
				hard_checks: Type.Optional(Type.String({ description: 'JSON object, e.g. {"emergency_zero":true}' })),
				reason: Type.Optional(Type.String()),
				meaning: Type.Optional(Type.String()),
				necessity: Type.Optional(Type.String()),
				reliability: Type.Optional(Type.String()),
				papers: Type.Optional(Type.String()),
				model: Type.Optional(Type.String()),
				features: Type.Optional(Type.String()),
				degree: Type.Optional(Type.Number()),
				alpha: Type.Optional(Type.Number()),
				blocked_on: Type.Optional(Type.String()),
				seat: Type.Optional(Type.String({ description: "A | B | merge" })),
				id: Type.Optional(Type.String()),
			}),
			"post_requirement",
		),
	);
	pi.registerTool(
		tool(
			"bounce_to_experimenter",
			"Bounce back to experimenter",
			"Reviewer: reject a cut or a crashed run. Include original requirement_id, task_id, reasons, "
				+ "optional run_error, and current code_sha256. Implementation defects only — do not authorize "
				+ "dropping hard_checks, and do not interpret metrics as science. Experimenter has no memory.",
			Type.Object({
				reasons: Type.String({ description: "Why it failed (semicolon-separated ok)" }),
				requirement_id: Type.Optional(Type.String()),
				task_id: Type.Optional(Type.String()),
				run_error: Type.Optional(Type.String()),
				code_sha256: Type.Optional(Type.String()),
				kind: Type.Optional(Type.String({ description: "review_reject | run_error" })),
			}),
			"bounce_to_experimenter",
		),
	);
	pi.registerTool(
		tool(
			"deep_research",
			"Designer DeepResearch",
			"Designer: OpenAlex (then Atom) search plus fetch_paper. Records hits in designer memory. "
				+ "Do not invent arXiv ids. Do not call search_papers again. Do not leave papers empty. "
				+ "Then paper_outline / search_paper / read_paper slices.",
			Type.Object({
				query: Type.String(),
				limit: Type.Optional(Type.Number({ description: "Max papers to fetch, default 3, cap 5" })),
			}),
			"deep_research",
			180_000,
		),
	);
	pi.registerTool(
		tool(
			"summarize_dag",
			"Summarize experiment DAG",
			"Read-only digest of lab experiments.jsonl: BEST, consecutive_non_improve, kinds, and last N lines. Designer and divergence may call this. Do not create/complete.",
			Type.Object({
				limit: Type.Optional(Type.Number()),
				primary: Type.Optional(Type.String({ description: "Preferred metric key" })),
			}),
			"summarize_dag",
		),
	);
	pi.registerTool(
		tool(
			"designer_memory_note",
			"Note in designer memory",
			"Designer: remember a paper id or a short note about a design. Persisted in lab/memory/designer.json.",
			Type.Object({
				note: Type.Optional(Type.String()),
				paper_id: Type.Optional(Type.String()),
				title: Type.Optional(Type.String()),
			}),
			"designer_memory_note",
		),
	);
	pi.registerTool(
		tool(
			"record_exhausted",
			"Record divergence exhausted",
			"Divergence interceptor only: write verdict=exhausted after designer agree_stop. "
				+ "skipped.why for leftover ideas may start with CHARTER|DIRECTIONS|DAG|USER|DUPLICATE; "
				+ "covering the interceptor's proposals requires DAG|DUPLICATE|DIRECTIONS|USER (not CHARTER). "
				+ "'already optimal' is not a reason to skip an untried direction. "
				+ "Unused downloaded papers block this. Do not hand-edit reviews/verdicts. Then campaign_gate and ask_user.",
			Type.Object({
				skipped: Type.Optional(Type.String({ description: "JSON list of {idea, why} leftovers that are repeats" })),
				note: Type.Optional(Type.String()),
			}),
			"record_exhausted",
		),
	);
	pi.registerTool(
		tool(
			"agent_done",
			"Finish this agent turn",
			"Drop the current hat and return to the main loop. Pass role=experiment-designer|experimenter|reviewer|divergence-interceptor.",
			Type.Object({
				role: Type.String(),
				result: Type.Optional(Type.String({ description: "posted | queued | bounced | ran | asked | exhausted" })),
				note: Type.Optional(Type.String()),
			}),
			"agent_done",
		),
	);
}
