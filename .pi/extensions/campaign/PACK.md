# Pack: campaign

实验执行 loop。不发明下一刀。只做一件事：lab 已绑定且 `campaign_gate.may_yield=false` 时，**不要把话轮交给用户**，把 `must` 里的工具再调一次（含 `ask_user`）。

| 机制 | 作用 |
|------|------|
| `ask_user` | 开口闸。绑定 lab 后想问用户必须走这个 tool；`may_stop=false` 则失败；成功后写入 `asked_user.json`，`may_yield=true` |
| `agent_settled` | 模型想收工时，若 `may_yield=false`，自动注入 `[campaign-loop]` 再跑一回合（包括「该 ask_user」） |
| `message_end` | 无 tool call 的助手正文，在 `may_yield=false` 时一律改写成继续指令 |

用户说「停止 / 停下来 / stop」则 loop 让路。Python **禁止**自己选 kind/change。空队列先 `call_divergence`：拦截者独立提多样方案并反复质疑，满 3 轮后设计者仍要停，才 `record_exhausted` + `ask_user`。
