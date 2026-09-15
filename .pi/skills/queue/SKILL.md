---
name: queue
description: Experiment task queue with priorities. Experimenter queue_put using a designer requirement_id. Reviewer queue_take and runs. Designer does not enqueue.
---

# Skill: queue

The queue is **durable memory** for *runnable* jobs (`<lab>/task_queue.json`). Ideas live in `reviews/requirements/`. It is not a Python runner.

Higher `priority` is taken first.

**Who writes jobs:** Experimenter (`proposed_by=experimenter` + `requirement_id` from `post_requirement`). The Designer must not `queue_put`. Divergence must not `queue_put`. The Reviewer `queue_take`s.

## Loop

```text
Designer post_requirement
Experimenter implements, queue_put
Reviewer queue_take → review → create → run → complete
empty → Divergence asks Designer (not a stop)
```

Do not ask the user to pick 1/2/3. Do not write a `while` in Python that pops the queue.

If `queue_take` returns `already_running`, finish or bounce that task first.

`blocked_on` = needs lab code. Experimenter unblocks after editing, then `status=queued`.
