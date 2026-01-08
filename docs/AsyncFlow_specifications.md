# Flow vs AsyncFlow

### 1. **Orchestration Method**

```python
# Flow._orch (sync)
while curr:
    curr.set_params(p)
    last_action = curr._run(shared)  # Always sync
    curr = copy.copy(self.get_next_node(curr, last_action))

# AsyncFlow._orch_async
while curr:
    curr.set_params(p)
    # Checks node type and calls appropriate method
    last_action = await curr._run_async(shared) if isinstance(curr, AsyncNode) else curr._run(shared)
    curr = copy.copy(self.get_next_node(curr, last_action))
```

### 2. **Key Differences**

| Aspect                | Flow                    | AsyncFlow                                              |
| --------------------- | ----------------------- | ------------------------------------------------------ |
| Entry point           | `flow.run(shared)`    | `await flow.run_async(shared)`                       |
| Node execution        | Always `_run()`(sync) | `_run_async()`for AsyncNode,`_run()`for sync nodes |
| Can host sync nodes?  | ✅ Yes                  | ✅ Yes (calls `_run()`for them)                      |
| Can host async nodes? | ❌ No (would fail)      | ✅ Yes                                                 |
| I/O behavior          | Blocking                | Non-blocking (yields to event loop)                    |

### 3. **Node Execution Order: Still Sequential!**

**Yes, nodes still execute in strict order.** The `while curr` loop processes one node at a time:

```python
# Both Flow and AsyncFlow do this:
while curr:
    # Run current node (blocks until complete)
    last_action = ... curr runs here ...
    # Only then get next node
    curr = self.get_next_node(curr, last_action)
```

The `await` in AsyncFlow doesn't change the order - it just means "wait for this async operation to complete before continuing."

### 4. **Where Parallelism Actually Happens**

Parallelism is  **within a single node** , not between nodes:

```python
# AsyncBatchNode - Sequential within node
async def _exec(self, items):
    return [await super()._exec(i) for i in items]  # One at a time

# AsyncParallelBatchNode - Parallel within node
async def _exec(self, items):
    return await asyncio.gather(*(super()._exec(i) for i in items))  # All at once!
```

### 5. **Visual Comparison**

```
Flow with sync nodes:
┌────────┐    ┌────────┐    ┌────────┐
│ Node A │───▶│ Node B │───▶│ Node C │
└────────┘    └────────┘    └────────┘
   Run          Run          Run
  (block)      (block)      (block)

AsyncFlow with async nodes:
┌────────┐    ┌────────┐    ┌────────┐
│ Node A │───▶│ Node B │───▶│ Node C │
└────────┘    └────────┘    └────────┘
   await        await        await
 (yields)     (yields)     (yields)
                 │
                 ▼
         Still sequential!

AsyncParallelBatchNode (within one node):
┌─────────────────────────────────────┐
│  AsyncParallelBatchNode             │
│  ┌──────┐ ┌──────┐ ┌──────┐        │
│  │item1 │ │item2 │ │item3 │  ...   │  ← All run concurrently!
│  └──────┘ └──────┘ └──────┘        │
│         asyncio.gather()            │
└─────────────────────────────────────┘
```

### 6. **Why Use AsyncFlow?**

Even though nodes run sequentially, AsyncFlow is valuable because:

1. **Non-blocking I/O** : While Node A awaits an API response, the event loop can handle other tasks (e.g., other coroutines, timers)
2. **Enables parallel batch nodes** : `AsyncParallelBatchNode` needs an async context to use `asyncio.gather()`
3. **Mixed node support** : Can run both sync and async nodes in the same flow
4. **Composability** : An AsyncFlow can be a node in another AsyncFlow (nested flows)

### 7. **What If You Want Parallel Node Execution?**

PocketFlow doesn't support running Node A and Node B simultaneously. If you need that, you'd either:

1. **Combine them into one AsyncParallelBatchNode** that processes both tasks
2. **Use AsyncParallelBatchFlow** - runs multiple flow instances in parallel:

```python
class AsyncParallelBatchFlow(AsyncFlow, BatchFlow):
    async def _run_async(self, shared):
        pr = await self.prep_async(shared) or []
        # All batch params run their own flow instance in parallel!
        await asyncio.gather(*(self._orch_async(shared, {**self.params, **bp}) for bp in pr))
        return await self.post_async(shared, pr, None)
```

This runs **multiple copies of the entire flow** in parallel, each with different params.
