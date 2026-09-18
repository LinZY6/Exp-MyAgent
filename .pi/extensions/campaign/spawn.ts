/**
 * Spawn one official Pi subagent (fresh `pi --mode json -p --no-session`).
 * Same primitive as `.pi/extensions/subagent/index.ts`. Do not add a third spawn layer.
 */

import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { type AgentConfig, discoverAgents } from "../subagent/agents.ts";

function getPiInvocation(args: string[]): { command: string; args: string[] } {
	const currentScript = process.argv[1];
	const isBunVirtualScript = currentScript?.startsWith("/$bunfs/root/");
	if (currentScript && !isBunVirtualScript && fs.existsSync(currentScript)) {
		return { command: process.execPath, args: [currentScript, ...args] };
	}
	const execName = path.basename(process.execPath).toLowerCase();
	const isGenericRuntime = /^(node|bun)(\.exe)?$/.test(execName);
	if (!isGenericRuntime) {
		return { command: process.execPath, args };
	}
	return { command: "pi", args };
}

function getFinalOutput(messages: { role?: string; content?: Array<{ type?: string; text?: string }> }[]): string {
	for (let i = messages.length - 1; i >= 0; i--) {
		const msg = messages[i];
		if (msg.role === "assistant" && Array.isArray(msg.content)) {
			for (const part of msg.content) {
				if (part.type === "text" && part.text) return part.text;
			}
		}
	}
	return "";
}

export function parseInterceptVerdict(raw: string): {
	ok: boolean;
	stop: boolean;
	as_user: string;
	ask: string;
	error?: string;
} {
	const text = (raw || "").trim();
	if (!text) {
		return { ok: false, stop: false, as_user: "", ask: "", error: "interceptor returned empty output" };
	}
	if (/\[campaign-loop\]/i.test(text) || /\[interceptor-as-user\]/i.test(text)) {
		return {
			ok: false,
			stop: false,
			as_user: "",
			ask: "",
			error: "interceptor echoed a campaign injection; child must not run campaign hooks",
		};
	}
	const fence = text.match(/```json\s*([\s\S]*?)```/i);
	const blob = (fence ? fence[1] : text).trim();
	const start = blob.indexOf("{");
	const end = blob.lastIndexOf("}");
	if (start >= 0 && end > start) {
		try {
			const obj = JSON.parse(blob.slice(start, end + 1)) as {
				stop?: unknown;
				as_user?: unknown;
				ask?: unknown;
			};
			if (!("stop" in obj)) {
				return { ok: false, stop: false, as_user: "", ask: "", error: "interceptor JSON missing stop" };
			}
			const stop = obj.stop === true || obj.stop === "true";
			return {
				ok: true,
				stop,
				as_user: String(obj.as_user || "").trim(),
				ask: String(obj.ask || "").trim(),
			};
		} catch {
			/* fall through */
		}
	}
	return {
		ok: false,
		stop: false,
		as_user: "",
		ask: "",
		error: "interceptor did not return a JSON verdict {stop, as_user|ask}",
	};
}

export async function runProjectAgent(opts: {
	cwd: string;
	agent: string;
	task: string;
	signal?: AbortSignal;
}): Promise<{ ok: boolean; text: string; error?: string }> {
	const discovery = discoverAgents(opts.cwd, "project");
	const agent = discovery.agents.find((a: AgentConfig) => a.name === opts.agent);
	if (!agent) {
		const names = discovery.agents.map((a) => a.name).join(", ") || "none";
		return { ok: false, text: "", error: `unknown agent "${opts.agent}"; available: ${names}` };
	}
	const args: string[] = ["--mode", "json", "-p", "--no-session", "--approve", "--no-skills"];
	if (agent.model) args.push("--model", agent.model);
	if (agent.tools && agent.tools.length > 0) args.push("--tools", agent.tools.join(","));

	let tmpDir: string | null = null;
	try {
		if (agent.systemPrompt.trim()) {
			tmpDir = await fs.promises.mkdtemp(path.join(os.tmpdir(), "pi-subagent-"));
			const filePath = path.join(tmpDir, `prompt-${agent.name}.md`);
			await fs.promises.writeFile(filePath, agent.systemPrompt, { encoding: "utf-8", mode: 0o600 });
			args.push("--append-system-prompt", filePath);
		}
		args.push(`Task: ${opts.task}`);
		const messages: { role?: string; content?: Array<{ type?: string; text?: string }> }[] = [];
		let stderr = "";
		const exitCode = await new Promise<number>((resolve) => {
			const invocation = getPiInvocation(args);
			const proc = spawn(invocation.command, invocation.args, {
				cwd: opts.cwd,
				shell: false,
				stdio: ["ignore", "pipe", "pipe"],
				env: {
					...process.env,
					PI_CAMPAIGN_PASSIVE: "1",
				},
			});
			let buffer = "";
			const onLine = (line: string) => {
				if (!line.trim()) return;
				let event: { type?: string; message?: (typeof messages)[number] };
				try {
					event = JSON.parse(line) as typeof event;
				} catch {
					return;
				}
				if (event.type === "message_end" && event.message) messages.push(event.message);
			};
			proc.stdout.on("data", (data: Buffer) => {
				buffer += data.toString();
				const lines = buffer.split("\n");
				buffer = lines.pop() || "";
				for (const line of lines) onLine(line);
			});
			proc.stderr.on("data", (data: Buffer) => {
				stderr += data.toString();
			});
			proc.on("close", (code) => {
				if (buffer.trim()) onLine(buffer);
				resolve(code ?? 0);
			});
			proc.on("error", () => resolve(1));
			if (opts.signal) {
				const killProc = () => {
					proc.kill("SIGTERM");
					setTimeout(() => {
						if (!proc.killed) proc.kill("SIGKILL");
					}, 5000);
				};
				if (opts.signal.aborted) killProc();
				else opts.signal.addEventListener("abort", killProc, { once: true });
			}
		});
		const text = getFinalOutput(messages);
		if (exitCode !== 0 && !text) {
			return { ok: false, text: "", error: stderr.trim() || `pi exit ${exitCode}` };
		}
		return { ok: true, text: text || stderr.trim() };
	} finally {
		if (tmpDir) {
			try {
				fs.rmSync(tmpDir, { recursive: true, force: true });
			} catch {
				/* ignore */
			}
		}
	}
}
