---
name: queue
description: Experiment task queue with priorities. Load when listing, taking, or updating jobs. New scientific ideas are queue_put by the Experiment Designer (or Divergence catching leftovers), not the Experimenter.
---

# Skill: queue

The queue is **durable memory** for ideas (`<lab>/task_queue.json`). It is not a Python runner.

Higher `priority` is taken first.

**Who writes ideas:** Experiment Designer (`proposed_by=experiment-designer`). Divergence Reviewer may `queue_put` leftovers (`proposed_by=divergence-reviewer`). The Experimenter must not `queue_put` a new 方案, and must not `queue_set` title / spec / priority.

## Loop

```text
Designer queue_put (A,B,C)     # only when nothing is queued
Experimenter queue_take → create → run → complete
queue_set that id status=done (and experiment_id)
still queued → Experimenter queue_take
empty again → Designer
about to stop → Divergence may queue_put leftovers
```

Do not ask the user to pick 1/2/3. Do not write a `while` in Python that pops the queue.

If `queue_take` returns `already_running`, finish or `queue_set` skip/done that task first.

`blocked_on` = needs lab code (e.g. MARS). Experimenter unblocks after editing `fit.py`, then `status=queued`. The idea itself stays the Designer’s.

Divergence Reviewer (`.pi/skills/divergence-reviewer/SKILL.md`) may `queue_put` leftovers only. It must not `queue_take` and must not treat an empty queue as campaign stop. After it writes `enqueue`, the Experimenter must `campaign_gate` then `queue_take` the same turn — leftover queue is remaining work, not a wait-for-user checkpoint.
