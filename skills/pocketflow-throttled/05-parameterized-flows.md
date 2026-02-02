---
name: "parameterized-flows"
description: "Pass different parameters to each flow instance. Use when each item needs different configuration or settings."
---

# Skill 05: Parameterized Flows

**Difficulty**: Intermediate
**Source**: `cookbook/rate_limited_llm_batch/parameterized_flow_example.py`, `docs/parameter_passing_mechanism.md`

## When to Use

- Each item in your batch needs **different configuration**
- Processing heterogeneous data (different user types, regions, models)
- Need to pass context through multi-node flows
- Want each flow instance to behave differently

## Key Concepts

In `ThrottledAsyncParallelBatchFlow`:

1. **`prep_async()`** returns a list of parameter dictionaries
2. Each dictionary becomes **`self.params`** for one flow instance
3. **All nodes** in that flow instance share the same `params`
4. Flow instances run **in parallel** with different params

**Critical Understanding**: Parameters flow from `prep_async()` → flow instance → all nodes in that instance.

## Core Pattern

```python
from pocketflow import AsyncNode
from pocketflow_throttled import ThrottledAsyncParallelBatchFlow

class StepA(AsyncNode):
    async def exec_async(self, _):
        # Access params passed from flow
        user_id = self.params["user_id"]
        user_type = self.params["user_type"]

        return await process(user_id, user_type)

class StepB(AsyncNode):
    async def exec_async(self, _):
        # Same params available here
        user_id = self.params["user_id"]
        return await more_processing(user_id)

class MyFlow(ThrottledAsyncParallelBatchFlow):
    max_concurrent_flows = 5

    async def prep_async(self, shared):
        """Return list of param dicts - one per flow instance."""
        return [
            {"user_id": 1, "user_type": "premium"},  # Flow instance 1
            {"user_id": 2, "user_type": "standard"}, # Flow instance 2
            {"user_id": 3, "user_type": "premium"},  # Flow instance 3
        ]

# Each flow instance gets different params
# Instance 1: params = {"user_id": 1, "user_type": "premium"}
# Instance 2: params = {"user_id": 2, "user_type": "standard"}
# Instance 3: params = {"user_id": 3, "user_type": "premium"}
```

## Complete Example: Multi-Region Document Processing

```python
from pocketflow import AsyncNode
from pocketflow_throttled import ThrottledAsyncParallelBatchFlow

# ═══════════════════════════════════════════════════
# Nodes that use params
# ═══════════════════════════════════════════════════

class FetchDocumentNode(AsyncNode):
    """Fetch document from region-specific storage."""

    async def exec_async(self, _):
        # Each flow instance has different params
        doc_id = self.params["doc_id"]
        region = self.params["region"]
        storage_type = self.params.get("storage_type", "s3")

        # Use params to customize behavior
        if storage_type == "s3":
            url = f"s3://{region}-bucket/{doc_id}"
        else:
            url = f"https://{region}.storage.com/{doc_id}"

        content = await fetch_from_storage(url)
        return content

    async def post_async(self, shared, prep_res, exec_res):
        # Store using unique key to avoid race conditions
        doc_id = self.params["doc_id"]
        shared.setdefault("documents", {})[doc_id] = exec_res
        return "analyze"

class AnalyzeDocumentNode(AsyncNode):
    """Analyze with region-specific model."""

    async def exec_async(self, _):
        doc_id = self.params["doc_id"]
        region = self.params["region"]
        model = self.params.get("model", "gpt-4")
        language = self.params.get("language", "english")

        # Different regions might use different models
        if region == "eu":
            # EU: Use GDPR-compliant model
            analysis = await call_eu_model(
                shared["documents"][doc_id],
                model=model
            )
        else:
            # Other regions: Standard model
            analysis = await call_standard_model(
                shared["documents"][doc_id],
                model=model
            )

        return analysis

    async def post_async(self, shared, prep_res, exec_res):
        doc_id = self.params["doc_id"]
        shared.setdefault("analyses", {})[doc_id] = exec_res
        return "default"

# ═══════════════════════════════════════════════════
# Flow with parameterized instances
# ═══════════════════════════════════════════════════

class DocumentProcessingFlow(ThrottledAsyncParallelBatchFlow):
    """Process documents with different configurations per document."""

    max_concurrent_flows = 5

    async def prep_async(self, shared):
        """
        Return list of param dicts.

        Each dict represents one document to process
        with its specific configuration.
        """
        documents = shared["documents"]

        return [
            {
                "doc_id": doc.id,
                "region": doc.region,
                "model": self._select_model(doc),
                "language": doc.language,
                "storage_type": doc.storage_type,
                "priority": doc.priority
            }
            for doc in documents
        ]

    def _select_model(self, doc):
        """Choose model based on document type."""
        if doc.is_technical:
            return "gpt-4"
        elif doc.is_creative:
            return "claude-3-opus"
        else:
            return "gpt-3.5-turbo"

# ═══════════════════════════════════════════════════
# Usage
# ═══════════════════════════════════════════════════

async def process_documents():
    # Build flow graph
    fetch = FetchDocumentNode()
    analyze = AnalyzeDocumentNode()
    fetch - "analyze" >> analyze

    flow = DocumentProcessingFlow(start=fetch)

    # Different documents with different configs
    shared = {
        "documents": [
            Document(id="doc1", region="us", language="english", is_technical=True),
            Document(id="doc2", region="eu", language="german", is_creative=True),
            Document(id="doc3", region="asia", language="japanese", is_technical=False),
        ]
    }

    await flow.run_async(shared)

    # Results keyed by doc_id
    for doc_id, analysis in shared["analyses"].items():
        print(f"{doc_id}: {analysis}")
```

## Parameter Flow Diagram

```
┌──────────────────────────────────────────────────────┐
│  prep_async() returns:                               │
│  [                                                   │
│    {"user_id": 1, "type": "premium", "region": "us"} │
│    {"user_id": 2, "type": "standard", "region": "eu"}│
│    {"user_id": 3, "type": "premium", "region": "asia"}│
│  ]                                                   │
└────────────────┬─────────────────────────────────────┘
                 │
    ┌────────────┴────────────┐
    │                         │
    ▼                         ▼
┌─────────────────┐    ┌─────────────────┐
│ Flow Instance 1 │    │ Flow Instance 2 │
│ params={        │    │ params={        │
│   user_id: 1,   │    │   user_id: 2,   │
│   type:premium, │    │   type:standard,│
│   region: us    │    │   region: eu    │
│ }               │    │ }               │
├─────────────────┤    ├─────────────────┤
│                 │    │                 │
│ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │ NodeA       │ │    │ │ NodeA       │ │
│ │ self.params │ │    │ │ self.params │ │
│ │ = {user_id:1│ │    │ │ = {user_id:2│ │
│ │    type:... }│ │    │ │    type:... }│ │
│ └──────┬──────┘ │    │ └──────┬──────┘ │
│        │        │    │        │        │
│        ▼        │    │        ▼        │
│ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │ NodeB       │ │    │ │ NodeB       │ │
│ │ self.params │ │    │ │ self.params │ │
│ │ = {user_id:1│ │    │ │ = {user_id:2│ │
│ │    type:... }│ │    │ │    type:... }│ │
│ └─────────────┘ │    │ └─────────────┘ │
└─────────────────┘    └─────────────────┘
```

## Common Patterns

### Pattern: Different LLM Models Per Item

```python
class ModelSelectionFlow(ThrottledAsyncParallelBatchFlow):
    async def prep_async(self, shared):
        return [
            {
                "task_id": 1,
                "model": "gpt-4",           # Expensive model for important task
                "temperature": 0.3,
                "max_tokens": 2000
            },
            {
                "task_id": 2,
                "model": "gpt-3.5-turbo",   # Cheap model for simple task
                "temperature": 0.7,
                "max_tokens": 500
            },
        ]

class LLMNode(AsyncNode):
    async def exec_async(self, _):
        # Use params to configure LLM call
        response = await call_llm(
            model=self.params["model"],
            temperature=self.params["temperature"],
            max_tokens=self.params["max_tokens"]
        )
        return response
```

### Pattern: User-Specific Configuration

```python
class UserFlow(ThrottledAsyncParallelBatchFlow):
    async def prep_async(self, shared):
        users = shared["users"]

        return [
            {
                "user_id": user.id,
                "tier": user.subscription_tier,  # "free", "pro", "enterprise"
                "rate_limit": self._get_user_rate_limit(user),
                "features": user.enabled_features,
                "locale": user.locale
            }
            for user in users
        ]

    def _get_user_rate_limit(self, user):
        if user.subscription_tier == "enterprise":
            return 100
        elif user.subscription_tier == "pro":
            return 50
        else:
            return 10

class ProcessUserNode(AsyncNode):
    async def exec_async(self, _):
        # Behavior varies by user tier
        tier = self.params["tier"]
        features = self.params["features"]

        if tier == "enterprise":
            # Use premium features
            result = await process_with_premium_features(features)
        else:
            result = await process_standard(features)

        return result
```

### Pattern: Dynamic Configuration from Database

```python
from dataclasses import dataclass

@dataclass
class JobConfig:
    job_id: str
    input_file: str
    output_format: str
    quality: str
    notify_email: str

    def to_params(self):
        return {
            "job_id": self.job_id,
            "input_file": self.input_file,
            "output_format": self.output_format,
            "quality": self.quality,
            "notify_email": self.notify_email
        }

class JobProcessingFlow(ThrottledAsyncParallelBatchFlow):
    async def prep_async(self, shared):
        # Load job configs from database
        job_configs = await db.fetch_pending_jobs()

        # Convert to param dicts
        return [config.to_params() for config in job_configs]

class ProcessJobNode(AsyncNode):
    async def exec_async(self, _):
        # Use params from database
        job_id = self.params["job_id"]
        input_file = self.params["input_file"]
        output_format = self.params["output_format"]

        result = await process_file(input_file, output_format)
        return result

    async def post_async(self, shared, prep_res, exec_res):
        # Send notification using params
        notify_email = self.params["notify_email"]
        await send_email(notify_email, "Job complete", exec_res)
```

### Pattern: Multi-Region API Endpoints

```python
class RegionalAPIFlow(ThrottledAsyncParallelBatchFlow):
    ENDPOINTS = {
        "us": "https://api.us.example.com",
        "eu": "https://api.eu.example.com",
        "asia": "https://api.asia.example.com"
    }

    async def prep_async(self, shared):
        tasks = shared["tasks"]

        return [
            {
                "task_id": task.id,
                "region": task.region,
                "endpoint": self.ENDPOINTS[task.region],
                "api_key": self._get_regional_key(task.region),
                "timeout": self._get_regional_timeout(task.region)
            }
            for task in tasks
        ]

class APICallNode(AsyncNode):
    async def exec_async(self, _):
        endpoint = self.params["endpoint"]
        api_key = self.params["api_key"]
        timeout = self.params["timeout"]

        response = await call_api(
            url=f"{endpoint}/process",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout
        )
        return response
```

## Accessing Params in Nodes

### In `exec_async()`
```python
class MyNode(AsyncNode):
    async def exec_async(self, _):
        # Direct access
        user_id = self.params["user_id"]

        # With default
        priority = self.params.get("priority", 1)

        # Check existence
        if "optional_field" in self.params:
            value = self.params["optional_field"]
```

### In `prep_async()`
```python
class MyBatchNode(ThrottledParallelBatchNode):
    async def prep_async(self, shared):
        # Params from flow
        config = self.params["config"]

        # Use to prepare batch
        return shared[config["data_key"]]
```

### In `post_async()`
```python
class MyNode(AsyncNode):
    async def post_async(self, shared, prep_res, exec_res):
        # Store using params
        item_id = self.params["item_id"]
        shared.setdefault("results", {})[item_id] = exec_res
```

## Shared State Safety with Params

**❌ UNSAFE - Race Condition**
```python
async def post_async(self, shared, prep_res, exec_res):
    # Multiple flow instances writing to same key!
    shared["counter"] += 1  # RACE CONDITION!
```

**✅ SAFE - Use Params for Unique Keys**
```python
async def post_async(self, shared, prep_res, exec_res):
    # Each flow instance writes to different key
    item_id = self.params["item_id"]
    shared.setdefault("results", {})[item_id] = exec_res
```

## Merging Flow-Level and Batch-Level Params

```python
class MyFlow(ThrottledAsyncParallelBatchFlow):
    def __init__(self, global_config, **kwargs):
        super().__init__(**kwargs)
        # Set flow-level params
        self.params = {"global_config": global_config}

    async def prep_async(self, shared):
        # These get merged with flow-level params
        return [
            {"item_id": 1},  # Merged with self.params
            {"item_id": 2},
        ]

# Internally: {**self.params, **batch_params}
# Result: {"global_config": ..., "item_id": 1}
```

## Debugging Params

```python
class DebugNode(AsyncNode):
    async def exec_async(self, _):
        # Print params for debugging
        print(f"Node params: {self.params}")

        # Or use logging
        import logging
        logging.info(f"Processing with params: {self.params}")
```

## Common Mistakes

### ❌ Modifying Params
```python
async def exec_async(self, _):
    # Don't modify params - they're shared!
    self.params["new_field"] = "value"  # Bad!
```

### ❌ Assuming Params Exist
```python
async def exec_async(self, _):
    # This raises KeyError if "optional" not set
    value = self.params["optional"]

    # Better: Use get() with default
    value = self.params.get("optional", default_value)
```

### ❌ Forgetting to Return Params List
```python
async def prep_async(self, shared):
    items = shared["items"]
    # Wrong - returns items, not param dicts!
    return items

    # Correct - return list of dicts
    return [{"item_id": item.id} for item in items]
```

## Related Skills

- **Uses this**: [Skill 03: Flow-Level Throttling](03-flow-level-throttling.md) - All flow throttling uses params
- **Architecture**: [Skill 08: Architecture Patterns](08-architecture-patterns.md) - How params flow internally
- **Example**: [Skill 07: Nested Throttling](07-nested-throttling.md) - Complex param usage

## When NOT to Use

- **Same config for all items** → Just use `shared` dict
- **Single flow instance** → Use regular `AsyncFlow`
- **Params change during execution** → Use `shared` for dynamic state
