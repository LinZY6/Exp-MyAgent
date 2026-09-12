---
name: queue
description: Experiment task queue with priorities. Load when planning several next trials, reprioritizing after metrics, or taking the next job from the lab queue.
---

# Skill: queue

The queue is **durable memory** for ideas (`<lab>/task_queue.json`). It is not a Python runner.

Higher `priority` is taken first. After metrics, **you** bump, insert, or skip — then `queue_take`.

## Loop

```text
queue_put ideas (A,B,C)
queue_take → create → run → complete
queue_set that id status=done (and experiment_id)
maybe queue_put D / queue_set C priority=200
queue_take → ...
```

Do not ask the user to pick 1/2/3. Do not write a `while` in Python that pops the queue.

If `queue_take` returns `already_running`, finish or `queue_set` skip/done that task first.

`blocked_on` = needs lab code (e.g. MARS). Unblock after you edit `fit.py`, then `status=queued`.

Divergence Reviewer (`.pi/skills/divergence-reviewer/SKILL.md`) may `queue_put` only. It must not `queue_take` and must not treat an empty queue as campaign stop.
