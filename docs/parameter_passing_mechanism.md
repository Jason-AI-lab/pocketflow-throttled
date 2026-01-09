## Parameter Passing Mechanism in ThrottledAsyncParallelBatchFlow

### Step-by-Step Trace

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PARAMETER FLOW DIAGRAM                               │
└─────────────────────────────────────────────────────────────────────────────┘

1. User calls: await flow.run_async(shared)
                    │
                    ▼
2. Flow._run_async() calls prep_async(shared)
                    │
                    ▼
3. prep_async() returns list of param dicts:
   ┌──────────────────────────────────────────────────────────┐
   │ [                                                        │
   │   {"user_id": 1, "type": "premium"},   # → Flow inst. 1  │
   │   {"user_id": 2, "type": "standard"},  # → Flow inst. 2  │
   │   {"user_id": 3, "type": "premium"},   # → Flow inst. 3  │
   │ ]                                                        │
   └──────────────────────────────────────────────────────────┘
                    │
                    ▼
4. For EACH dict (bp), call _orch_async(shared, {**self.params, **bp})
                    │
                    ▼
5. Inside _orch_async, for EACH node: curr.set_params(p)
                    │
                    ▼
6. Node accesses self.params in exec_async()
```

### The Key Code Paths

**Step 1: `_run_async` in ThrottledAsyncParallelBatchFlow**

```python
# In ThrottledAsyncParallelBatchFlow._run_async():
async def _run_async(self, shared: Dict[str, Any]) -> Any:
    # 1. Call prep_async to get list of param dicts
    pr = await self.prep_async(shared) or []
    # pr = [{"user_id": 1, ...}, {"user_id": 2, ...}, {"user_id": 3, ...}]
  
    async def run_throttled(bp: Dict[str, Any]) -> Any:
        async with self.flow_limiter:
            # 2. For each bp dict, call _orch_async with MERGED params
            #    {**self.params, **bp} merges flow's own params with batch params
            result = await self._orch_async(shared, {**self.params, **bp})
            return result
  
    # 3. Launch all flow instances in parallel (with throttling)
    results = await asyncio.gather(
        *(run_throttled(bp) for bp in pr),  # One task per param dict
        return_exceptions=True
    )
```

**Step 2: `_orch_async` in AsyncFlow (from PocketFlow)**

```python
# In AsyncFlow._orch_async() - the orchestrator:
async def _orch_async(self, shared, params=None):
    # 1. Copy the start node (to avoid shared state between flow instances)
    curr = copy.copy(self.start_node)
  
    # 2. params is the merged dict: {"user_id": 1, "type": "premium", ...}
    p = params or {**self.params}
  
    last_action = None
  
    # 3. Walk through the node graph
    while curr:
        # ★ KEY LINE: Set params on the current node ★
        curr.set_params(p)  # This makes params available as self.params
      
        # 4. Run the node (which can now access self.params)
        last_action = await curr._run_async(shared)
      
        # 5. Get next node based on return action
        curr = copy.copy(self.get_next_node(curr, last_action))
  
    return last_action
```

**Step 3: `set_params` in BaseNode (from PocketFlow)**

```python
# In BaseNode:
class BaseNode:
    def __init__(self):
        self.params = {}       # Initialize empty params dict
        self.successors = {}
  
    def set_params(self, params):
        self.params = params   # Simply assigns the dict to self.params
```

**Step 4: Node accesses `self.params`**

```python
class FetchUserNode(AsyncNode):
    async def exec_async(self, _):
        # self.params was set by _orch_async before this method was called
        user_id = self.params["user_id"]      # → 1, 2, or 3 depending on flow instance
        user_type = self.params["type"]       # → "premium" or "standard"
      
        return await fetch_user(user_id)
```

---

### Visual Execution Timeline

```
Time →
─────────────────────────────────────────────────────────────────────────────

prep_async() returns: [{"user_id":1}, {"user_id":2}, {"user_id":3}]

                     ┌─────────────────────────────────────────┐
asyncio.gather() →   │  Launch all 3 flow instances            │
                     │  (throttled to max_concurrent_flows)    │
                     └─────────────────────────────────────────┘
                                        │
         ┌──────────────────────────────┼──────────────────────────────┐
         ▼                              ▼                              ▼
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│ Flow Instance 1     │    │ Flow Instance 2     │    │ Flow Instance 3     │
│ params={user_id:1}  │    │ params={user_id:2}  │    │ params={user_id:3}  │
├─────────────────────┤    ├─────────────────────┤    ├─────────────────────┤
│                     │    │                     │    │                     │
│ _orch_async(        │    │ _orch_async(        │    │ _orch_async(        │
│   shared,           │    │   shared,           │    │   shared,           │
│   {user_id:1}       │    │   {user_id:2}       │    │   {user_id:3}       │
│ )                   │    │ )                   │    │ )                   │
│                     │    │                     │    │                     │
│ ┌─────────────────┐ │    │ ┌─────────────────┐ │    │ ┌─────────────────┐ │
│ │ NodeA           │ │    │ │ NodeA           │ │    │ │ NodeA           │ │
│ │ set_params({    │ │    │ │ set_params({    │ │    │ │ set_params({    │ │
│ │   user_id: 1    │ │    │ │   user_id: 2    │ │    │ │   user_id: 3    │ │
│ │ })              │ │    │ │ })              │ │    │ │ })              │ │
│ │ exec_async()    │ │    │ │ exec_async()    │ │    │ │ exec_async()    │ │
│ └────────┬────────┘ │    │ └────────┬────────┘ │    │ └────────┬────────┘ │
│          │          │    │          │          │    │          │          │
│          ▼          │    │          ▼          │    │          ▼          │
│ ┌─────────────────┐ │    │ ┌─────────────────┐ │    │ ┌─────────────────┐ │
│ │ NodeB           │ │    │ │ NodeB           │ │    │ │ NodeB           │ │
│ │ set_params({    │ │    │ │ set_params({    │ │    │ │ set_params({    │ │
│ │   user_id: 1    │ │    │ │   user_id: 2    │ │    │ │   user_id: 3    │ │
│ │ })              │ │    │ │ })              │ │    │ │ })              │ │
│ │ exec_async()    │ │    │ │ exec_async()    │ │    │ │ exec_async()    │ │
│ └─────────────────┘ │    │ └─────────────────┘ │    │ └─────────────────┘ │
│                     │    │                     │    │                     │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
         │                              │                              │
         └──────────────────────────────┼──────────────────────────────┘
                                        │
                                        ▼
                            asyncio.gather() collects results
```

---

### Key Insights

| Aspect                            | Mechanism                                                                           |
| --------------------------------- | ----------------------------------------------------------------------------------- |
| **How params are created**  | `prep_async()`returns `List[Dict]`                                              |
| **How params are merged**   | `{**self.params, **bp}`merges flow's params with batch params                     |
| **How params reach nodes**  | `_orch_async()`calls `curr.set_params(p)`before each node runs                  |
| **How nodes access params** | Via `self.params`attribute (set by `set_params()`)                              |
| **Why nodes are copied**    | `copy.copy(self.start_node)`ensures each flow instance has its own node instances |
| **How parallelism works**   | `asyncio.gather()`runs all `_orch_async()`calls concurrently                    |

### Why `copy.copy()` is Critical

```python
# Without copy: All flow instances would share the SAME node object
#               Setting params on one would overwrite another's params!

# With copy: Each flow instance gets its OWN node objects
curr = copy.copy(self.start_node)  # Creates a shallow copy
curr.set_params(p)                  # Safe - only affects this copy
```

This is why each flow instance can have different params even though they start from the same node definition.
