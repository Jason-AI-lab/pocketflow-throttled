Here's a comprehensive comparison of all Flow classes:

## Flow Class Hierarchy

```
BaseNode
    │
    ├── Node (adds retry logic)
    │     ├── BatchNode
    │     └── AsyncNode
    │           ├── AsyncBatchNode
    │           └── AsyncParallelBatchNode
    │
    └── Flow (orchestrates nodes)
          │
          ├── BatchFlow (runs flow N times sequentially)
          │
          └── AsyncFlow (async orchestration)
                │
                ├── AsyncBatchFlow (runs flow N times sequentially, async)
                │
                └── AsyncParallelBatchFlow (runs flow N times in parallel)
```

## Summary Table

| Flow Type                  | Sync/Async | Batch? | Parallel? | Use Case                                 |
| -------------------------- | ---------- | ------ | --------- | ---------------------------------------- |
| `Flow`                   | Sync       | No     | No        | Simple linear workflows                  |
| `BatchFlow`              | Sync       | Yes    | No        | Process multiple param sets sequentially |
| `AsyncFlow`              | Async      | No     | No        | Workflows with I/O-bound nodes           |
| `AsyncBatchFlow`         | Async      | Yes    | No        | Multiple param sets, async, sequential   |
| `AsyncParallelBatchFlow` | Async      | Yes    | Yes       | Multiple param sets, all in parallel     |

---

## 1. Flow (Base Flow)

 **Purpose** : Orchestrate a graph of synchronous nodes.

```python
class Flow(BaseNode):
    def __init__(self, start=None):
        super().__init__()
        self.start_node = start
  
    def _orch(self, shared, params=None):
        curr, p, last_action = copy.copy(self.start_node), (params or {**self.params}), None
        while curr:
            curr.set_params(p)
            last_action = curr._run(shared)
            curr = copy.copy(self.get_next_node(curr, last_action))
        return last_action
  
    def _run(self, shared):
        p = self.prep(shared)
        o = self._orch(shared)
        return self.post(shared, p, o)
```

 **Execution Pattern** :

```
prep() → _orch() → post()
            │
            └── while curr: curr._run() → get_next_node()
```

 **Example** :

```python
from pocketflow import Flow, Node

class StepA(Node):
    def exec(self, _): 
        print("Step A")
        return "go_b"
    def post(self, shared, prep_res, exec_res): 
        return "go_b"

class StepB(Node):
    def exec(self, _): 
        print("Step B")

# Build flow
a, b = StepA(), StepB()
a - "go_b" >> b

flow = Flow(start=a)
flow.run({})  # Prints: Step A, Step B
```

---

## 2. BatchFlow

 **Purpose** : Run the entire flow multiple times with different parameter sets, sequentially.

```python
class BatchFlow(Flow):
    def _run(self, shared):
        pr = self.prep(shared) or []  # Returns list of param dicts
        for bp in pr:
            self._orch(shared, {**self.params, **bp})  # Run flow for each
        return self.post(shared, pr, None)
```

 **Execution Pattern** :

```
prep() → [params1, params2, params3, ...]
            │
            ├── _orch(params1) → Node A → Node B → ...
            ├── _orch(params2) → Node A → Node B → ...  (waits for previous)
            └── _orch(params3) → Node A → Node B → ...  (waits for previous)
            │
         post()
```

 **Example** :

```python
from pocketflow import BatchFlow, Node

class ProcessItem(Node):
    def exec(self, _):
        item_id = self.params.get("item_id")
        print(f"Processing item {item_id}")

class MyBatchFlow(BatchFlow):
    def prep(self, shared):
        # Return list of param dicts - one flow run per item
        return [{"item_id": 1}, {"item_id": 2}, {"item_id": 3}]

flow = MyBatchFlow(start=ProcessItem())
flow.run({})
# Output (sequential):
# Processing item 1
# Processing item 2
# Processing item 3
```

 **Key Insight** : Each `_orch()` call runs the **entire flow graph** with different params. The flow instances run one after another.

---

## 3. AsyncFlow

 **Purpose** : Orchestrate async nodes with non-blocking I/O.

```python
class AsyncFlow(Flow, AsyncNode):
    async def _orch_async(self, shared, params=None):
        curr, p, last_action = copy.copy(self.start_node), (params or {**self.params}), None
        while curr:
            curr.set_params(p)
            # Key difference: checks node type!
            last_action = await curr._run_async(shared) if isinstance(curr, AsyncNode) else curr._run(shared)
            curr = copy.copy(self.get_next_node(curr, last_action))
        return last_action
  
    async def _run_async(self, shared):
        p = await self.prep_async(shared)
        o = await self._orch_async(shared)
        return await self.post_async(shared, p, o)
```

 **Execution Pattern** :

```
await prep_async() → await _orch_async() → await post_async()
                          │
                          └── while curr:
                                  if AsyncNode: await curr._run_async()
                                  else: curr._run()  # sync fallback
                                  get_next_node()
```

 **Example** :

```python
import asyncio
from pocketflow import AsyncFlow, AsyncNode

class FetchData(AsyncNode):
    async def exec_async(self, _):
        await asyncio.sleep(1)  # Simulate API call
        return {"data": "fetched"}
  
    async def post_async(self, shared, prep_res, exec_res):
        shared["result"] = exec_res
        return "process"

class ProcessData(AsyncNode):
    async def exec_async(self, _):
        await asyncio.sleep(0.5)
        return "processed"

fetch, process = FetchData(), ProcessData()
fetch - "process" >> process

flow = AsyncFlow(start=fetch)
asyncio.run(flow.run_async({}))
```

 **Mixed Node Support** :

```python
# AsyncFlow can run both sync and async nodes
class SyncNode(Node):
    def exec(self, _): return "sync result"

class AsyncNode(AsyncNode):
    async def exec_async(self, _): return "async result"

sync_node >> async_node  # Works in AsyncFlow!
```

---

## 4. AsyncBatchFlow

 **Purpose** : Run multiple flow instances sequentially, with async support.

```python
class AsyncBatchFlow(AsyncFlow, BatchFlow):
    async def _run_async(self, shared):
        pr = await self.prep_async(shared) or []
        for bp in pr:
            await self._orch_async(shared, {**self.params, **bp})  # Sequential!
        return await self.post_async(shared, pr, None)
```

 **Execution Pattern** :

```
await prep_async() → [params1, params2, params3]
                          │
                          ├── await _orch_async(params1)  ─┐
                          ├── await _orch_async(params2)  ─┼── Sequential (one at a time)
                          └── await _orch_async(params3)  ─┘
                          │
                     await post_async()
```

 **Example** :

```python
import asyncio
from pocketflow import AsyncBatchFlow, AsyncNode

class ProcessUser(AsyncNode):
    async def exec_async(self, _):
        user_id = self.params.get("user_id")
        await asyncio.sleep(0.5)  # Simulate API call
        print(f"Processed user {user_id}")

class UserBatchFlow(AsyncBatchFlow):
    async def prep_async(self, shared):
        return [{"user_id": 1}, {"user_id": 2}, {"user_id": 3}]

flow = UserBatchFlow(start=ProcessUser())
asyncio.run(flow.run_async({}))
# Output (sequential, ~1.5s total):
# Processed user 1
# Processed user 2
# Processed user 3
```

 **When to Use** : When you need async I/O but must process batches in order (e.g., dependent operations, rate limiting at flow level).

---

## 5. AsyncParallelBatchFlow

 **Purpose** : Run multiple flow instances  **in parallel** .

```python
class AsyncParallelBatchFlow(AsyncFlow, BatchFlow):
    async def _run_async(self, shared):
        pr = await self.prep_async(shared) or []
        # Key difference: asyncio.gather for parallel execution!
        await asyncio.gather(*(self._orch_async(shared, {**self.params, **bp}) for bp in pr))
        return await self.post_async(shared, pr, None)
```

 **Execution Pattern** :

```
await prep_async() → [params1, params2, params3]
                          │
                          │   asyncio.gather()
                          ├── _orch_async(params1)  ─┐
                          ├── _orch_async(params2)  ─┼── All run concurrently!
                          └── _orch_async(params3)  ─┘
                          │
                     await post_async()
```

 **Example** :

```python
import asyncio
import time
from pocketflow import AsyncParallelBatchFlow, AsyncNode

class ProcessUser(AsyncNode):
    async def exec_async(self, _):
        user_id = self.params.get("user_id")
        await asyncio.sleep(0.5)  # Simulate API call
        print(f"Processed user {user_id}")

class ParallelUserFlow(AsyncParallelBatchFlow):
    async def prep_async(self, shared):
        return [{"user_id": i} for i in range(10)]

flow = ParallelUserFlow(start=ProcessUser())
start = time.time()
asyncio.run(flow.run_async({}))
print(f"Total time: {time.time() - start:.2f}s")
# Output (parallel, ~0.5s total instead of 5s):
# Processed user 0
# Processed user 3
# Processed user 1
# ...
# Total time: 0.52s
```

 **Warning - Shared State** : All parallel flows share the same `shared` dict. This can cause race conditions:

```python
# DANGER: Race condition!
class BadNode(AsyncNode):
    async def exec_async(self, _):
        shared["counter"] += 1  # Multiple flows writing simultaneously!

# SAFE: Use params for flow-specific data
class GoodNode(AsyncNode):
    async def exec_async(self, _):
        user_id = self.params["user_id"]  # Each flow has its own params
        # Write to shared using unique keys
        shared[f"result_{user_id}"] = "done"
```

---

## Comparison: Execution Timing

```python
# Assume each node takes 1 second

# Flow (3 nodes)
# Total: 3 seconds
Node A (1s) → Node B (1s) → Node C (1s)

# BatchFlow (3 iterations, 2 nodes each)
# Total: 6 seconds
[iter1] A (1s) → B (1s)
[iter2] A (1s) → B (1s)  # Waits for iter1
[iter3] A (1s) → B (1s)  # Waits for iter2

# AsyncFlow (3 async nodes)
# Total: 3 seconds (same as Flow, but non-blocking)
await A (1s) → await B (1s) → await C (1s)

# AsyncBatchFlow (3 iterations, 2 nodes each)
# Total: 6 seconds (same as BatchFlow, but non-blocking)
[iter1] await A → await B
[iter2] await A → await B  # Waits for iter1
[iter3] await A → await B  # Waits for iter2

# AsyncParallelBatchFlow (3 iterations, 2 nodes each)
# Total: 2 seconds! (parallel iterations)
[iter1] await A → await B  ─┐
[iter2] await A → await B  ─┼── All start together
[iter3] await A → await B  ─┘
```

---

## Decision Tree: Which Flow to Use?

```
Do you need async I/O (API calls, file I/O)?
│
├── NO → Do you need to run flow multiple times with different params?
│         │
│         ├── NO  → Flow
│         └── YES → BatchFlow
│
└── YES → Do you need to run flow multiple times with different params?
          │
          ├── NO  → AsyncFlow
          │
          └── YES → Can iterations run independently (no dependencies)?
                    │
                    ├── NO  → AsyncBatchFlow (sequential)
                    └── YES → Is shared state thread-safe / isolated?
                              │
                              ├── NO  → AsyncBatchFlow (sequential)
                              └── YES → AsyncParallelBatchFlow (parallel)
```

---

## Quick Reference

| Flow                       | Entry Method                | prep Returns   | Iterations     | Parallelism |
| -------------------------- | --------------------------- | -------------- | -------------- | ----------- |
| `Flow`                   | `run(shared)`             | Any            | 1              | None        |
| `BatchFlow`              | `run(shared)`             | `List[dict]` | N (sequential) | None        |
| `AsyncFlow`              | `await run_async(shared)` | Any            | 1              | None        |
| `AsyncBatchFlow`         | `await run_async(shared)` | `List[dict]` | N (sequential) | None        |
| `AsyncParallelBatchFlow` | `await run_async(shared)` | `List[dict]` | N (parallel)   | Flow-level  |

 **Note** : For **item-level parallelism** within a single node, use `AsyncParallelBatchNode` (not a flow). The parallel flows run entire graph copies in parallel, while parallel batch nodes process items within one node in parallel.
