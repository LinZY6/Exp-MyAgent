# Pack: campaign

实验执行 loop。不发明下一刀。lab 已绑定且 `campaign_gate.may_yield=false` 时，不要把话轮交给用户。

| 机制 | 作用 |
|------|------|
| `ask_user` | 空队列：spawn 拦截者子 Agent；不停则充当用户打回主 loop |
| `tool_call` | 帽子不是实验者时拦截 `write` / `edit`；不是实验者/审查者时拦截 `powershell` |
| `message_end` | **只改写没有工具的空转收工**。有 `write` / `call_*` / `read` 的回合一律不改写 |
| `agent_settled` | 空转时催当前帽子做完，或催 `call_*`。回声 `[campaign-loop]` 后 2.5s 再踢，不要求用户打字 |

用户说「停止 / 停下来 / stop」则 loop 让路。Python **禁止**自己选 kind/change。不要用同一会话的 `call_divergence` 帽子代替拦截者子进程。
