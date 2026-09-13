# Pack: campaign

实验执行 loop。不发明下一刀（那是实验设计者的 `queue_put`）。只做一件事：lab 已绑定且 `campaign_gate.may_stop=false` 时，**不要把话轮交给用户**。

| 机制 | 作用 |
|------|------|
| `ask_user` | 开口闸。绑定 lab 后想问用户必须走这个 tool；`may_stop=false` 则失败，返回 `must` |
| `agent_settled` | 模型想收工时，若还没场停，自动注入 `[campaign-loop]` 再跑一回合 |
| `message_end` | 助手文本里出现「要继续吗」之类，改写成继续指令 |

用户说「停止 / 停下来 / stop」则 loop 让路。Python **禁止**自己选 kind/change。
