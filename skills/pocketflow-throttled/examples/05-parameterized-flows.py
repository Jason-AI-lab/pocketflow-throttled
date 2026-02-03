"""
ThrottledAsyncParallelBatchFlow with Different Parameters Per Flow
==================================================================

This example demonstrates how each flow instance receives different parameters
from the prep_async method. This is the core use case for parallel batch flows.

Key Concepts:
    - prep_async returns a list of parameter dicts
    - Each dict becomes self.params for one flow instance
    - All nodes in that flow instance share the same params
    - Flow instances run in parallel (up to max_concurrent_flows)

Usage:
    python parameterized_flow_example.py
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Any, List

from pocketflow import AsyncNode

from pocketflow_throttled import ThrottledAsyncParallelBatchFlow


# =============================================================================
# Example 1: Simple User Processing with Different User Configs
# =============================================================================

class FetchUserNode(AsyncNode):
    """Fetch user data - uses self.params for user-specific config."""
    
    async def exec_async(self, _):
        # Each flow instance has different params
        user_id = self.params["user_id"]
        user_type = self.params.get("user_type", "standard")
        region = self.params.get("region", "us")
        
        print(f"  [Fetch] User {user_id} (type={user_type}, region={region})")
        await asyncio.sleep(0.1)  # Simulate API call
        
        return {
            "user_id": user_id,
            "user_type": user_type,
            "region": region,
            "data": f"profile_data_{user_id}"
        }
    
    async def post_async(self, shared, prep_res, exec_res):
        # Store result using user_id as key to avoid race conditions
        user_id = self.params["user_id"]
        shared.setdefault("user_data", {})[user_id] = exec_res
        return "process"


class ProcessUserNode(AsyncNode):
    """Process user - behavior varies based on params."""
    
    async def exec_async(self, _):
        user_id = self.params["user_id"]
        user_type = self.params.get("user_type", "standard")
        priority = self.params.get("priority", 1)
        
        # Different processing based on user_type
        if user_type == "premium":
            processing_time = 0.05  # Faster for premium
        else:
            processing_time = 0.1
        
        print(f"  [Process] User {user_id} (priority={priority}, time={processing_time}s)")
        await asyncio.sleep(processing_time)
        
        return {
            "user_id": user_id,
            "status": "processed",
            "priority": priority
        }
    
    async def post_async(self, shared, prep_res, exec_res):
        user_id = self.params["user_id"]
        shared.setdefault("results", {})[user_id] = exec_res
        return "default"


class UserProcessingFlow(ThrottledAsyncParallelBatchFlow):
    """
    Process users with different configurations per user.
    
    Each user can have:
    - Different user_type (standard, premium)
    - Different region (us, eu, asia)
    - Different priority level
    """
    max_concurrent_flows = 3  # Process 3 users at a time
    
    async def prep_async(self, shared) -> List[Dict[str, Any]]:
        """
        Return list of parameter dicts - one per flow instance.
        
        Each dict becomes self.params for all nodes in that flow.
        """
        # Different users with different configurations
        return [
            {"user_id": 1, "user_type": "premium", "region": "us", "priority": 3},
            {"user_id": 2, "user_type": "standard", "region": "eu", "priority": 1},
            {"user_id": 3, "user_type": "premium", "region": "asia", "priority": 2},
            {"user_id": 4, "user_type": "standard", "region": "us", "priority": 1},
            {"user_id": 5, "user_type": "premium", "region": "eu", "priority": 3},
            {"user_id": 6, "user_type": "standard", "region": "asia", "priority": 2},
        ]


async def example_1_user_processing():
    """Demonstrate different params per flow instance."""
    print("=" * 70)
    print("Example 1: User Processing with Different Configs")
    print("=" * 70)
    
    # Build flow: fetch -> process
    fetch_node = FetchUserNode()
    process_node = ProcessUserNode()
    fetch_node - "process" >> process_node
    
    flow = UserProcessingFlow(start=fetch_node)
    shared = {}
    
    print(f"\nProcessing 6 users with max_concurrent_flows={flow.max_concurrent_flows}")
    print("Each user has different: user_type, region, priority\n")
    
    start = time.time()
    await flow.run_async(shared)
    elapsed = time.time() - start
    
    print(f"\nResults ({elapsed:.2f}s):")
    for user_id, result in sorted(shared.get("results", {}).items()):
        print(f"  User {user_id}: {result}")
    
    print(f"\nFlow stats: {flow.stats}")


# =============================================================================
# Example 2: Document Processing with Different LLM Configs
# =============================================================================

class AnalyzeDocumentNode(AsyncNode):
    """Analyze document with configurable LLM settings."""
    
    async def exec_async(self, _):
        doc_id = self.params["doc_id"]
        model = self.params.get("model", "gpt-3.5-turbo")
        temperature = self.params.get("temperature", 0.7)
        max_tokens = self.params.get("max_tokens", 1000)
        
        print(f"  [Analyze] Doc {doc_id} with {model} (temp={temperature}, max_tokens={max_tokens})")
        await asyncio.sleep(0.15)  # Simulate LLM call
        
        return {
            "doc_id": doc_id,
            "model": model,
            "analysis": f"Analysis of doc {doc_id} using {model}"
        }
    
    async def post_async(self, shared, prep_res, exec_res):
        doc_id = self.params["doc_id"]
        shared.setdefault("analyses", {})[doc_id] = exec_res
        return "summarize"


class SummarizeDocumentNode(AsyncNode):
    """Summarize document - summary length varies by param."""
    
    async def exec_async(self, _):
        doc_id = self.params["doc_id"]
        summary_length = self.params.get("summary_length", "medium")
        language = self.params.get("output_language", "english")
        
        print(f"  [Summarize] Doc {doc_id} ({summary_length} summary in {language})")
        await asyncio.sleep(0.1)
        
        return {
            "doc_id": doc_id,
            "summary": f"{summary_length.upper()} summary of doc {doc_id} in {language}",
            "language": language
        }
    
    async def post_async(self, shared, prep_res, exec_res):
        doc_id = self.params["doc_id"]
        shared.setdefault("summaries", {})[doc_id] = exec_res
        return "default"


class DocumentProcessingFlow(ThrottledAsyncParallelBatchFlow):
    """Process documents with different LLM configurations per document."""
    
    max_concurrent_flows = 2  # 2 documents at a time
    
    async def prep_async(self, shared) -> List[Dict[str, Any]]:
        """Each document has its own processing configuration."""
        return [
            {
                "doc_id": "report_q1",
                "model": "gpt-4",
                "temperature": 0.3,
                "max_tokens": 2000,
                "summary_length": "detailed",
                "output_language": "english"
            },
            {
                "doc_id": "contract_v2",
                "model": "gpt-4",
                "temperature": 0.1,  # Low temp for legal docs
                "max_tokens": 3000,
                "summary_length": "detailed",
                "output_language": "english"
            },
            {
                "doc_id": "email_thread",
                "model": "gpt-3.5-turbo",  # Cheaper model for emails
                "temperature": 0.7,
                "max_tokens": 500,
                "summary_length": "brief",
                "output_language": "english"
            },
            {
                "doc_id": "meeting_notes",
                "model": "gpt-3.5-turbo",
                "temperature": 0.5,
                "max_tokens": 1000,
                "summary_length": "medium",
                "output_language": "spanish"  # Different output language
            },
        ]


async def example_2_document_processing():
    """Demonstrate different LLM configs per document."""
    print("\n" + "=" * 70)
    print("Example 2: Document Processing with Different LLM Configs")
    print("=" * 70)
    
    # Build flow: analyze -> summarize
    analyze_node = AnalyzeDocumentNode()
    summarize_node = SummarizeDocumentNode()
    analyze_node - "summarize" >> summarize_node
    
    flow = DocumentProcessingFlow(start=analyze_node)
    shared = {}
    
    print(f"\nProcessing 4 documents with max_concurrent_flows={flow.max_concurrent_flows}")
    print("Each document has different: model, temperature, summary_length, language\n")
    
    start = time.time()
    await flow.run_async(shared)
    elapsed = time.time() - start
    
    print(f"\nSummaries ({elapsed:.2f}s):")
    for doc_id, summary in shared.get("summaries", {}).items():
        print(f"  {doc_id}: {summary['summary']}")


# =============================================================================
# Example 3: Multi-Region API Calls with Region-Specific Endpoints
# =============================================================================

class RegionalAPINode(AsyncNode):
    """Call region-specific API endpoints."""
    
    # Simulated regional endpoints
    ENDPOINTS = {
        "us": "https://api.us.example.com",
        "eu": "https://api.eu.example.com",
        "asia": "https://api.asia.example.com",
    }
    
    async def exec_async(self, _):
        task_id = self.params["task_id"]
        region = self.params["region"]
        api_key = self.params.get("api_key", "default_key")
        timeout = self.params.get("timeout", 30)
        
        endpoint = self.ENDPOINTS.get(region, self.ENDPOINTS["us"])
        
        print(f"  [API] Task {task_id} -> {endpoint} (timeout={timeout}s)")
        await asyncio.sleep(0.1)
        
        return {
            "task_id": task_id,
            "region": region,
            "endpoint": endpoint,
            "response": f"Response from {region} for task {task_id}"
        }
    
    async def post_async(self, shared, prep_res, exec_res):
        task_id = self.params["task_id"]
        shared.setdefault("responses", {})[task_id] = exec_res
        return "default"


class MultiRegionFlow(ThrottledAsyncParallelBatchFlow):
    """Execute tasks across multiple regions with region-specific configs."""
    
    max_concurrent_flows = 4
    
    async def prep_async(self, shared) -> List[Dict[str, Any]]:
        """Tasks distributed across regions with different configs."""
        return [
            {"task_id": "task_1", "region": "us", "api_key": "us_key_123", "timeout": 30},
            {"task_id": "task_2", "region": "eu", "api_key": "eu_key_456", "timeout": 45},
            {"task_id": "task_3", "region": "asia", "api_key": "asia_key_789", "timeout": 60},
            {"task_id": "task_4", "region": "us", "api_key": "us_key_123", "timeout": 30},
            {"task_id": "task_5", "region": "eu", "api_key": "eu_key_456", "timeout": 45},
        ]


async def example_3_multi_region():
    """Demonstrate region-specific configurations."""
    print("\n" + "=" * 70)
    print("Example 3: Multi-Region API Calls")
    print("=" * 70)
    
    flow = MultiRegionFlow(start=RegionalAPINode())
    shared = {}
    
    print(f"\nExecuting 5 tasks across 3 regions with max_concurrent_flows={flow.max_concurrent_flows}")
    print("Each task has different: region, api_key, timeout\n")
    
    start = time.time()
    await flow.run_async(shared)
    elapsed = time.time() - start
    
    print(f"\nResponses ({elapsed:.2f}s):")
    for task_id, response in sorted(shared.get("responses", {}).items()):
        print(f"  {task_id}: {response['response']}")


# =============================================================================
# Example 4: Dynamic Parameters from External Source
# =============================================================================

@dataclass
class JobConfig:
    """Job configuration loaded from database/config file."""
    job_id: str
    input_file: str
    output_format: str
    quality: str
    notify_email: str
    
    def to_params(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "input_file": self.input_file,
            "output_format": self.output_format,
            "quality": self.quality,
            "notify_email": self.notify_email,
        }


class ProcessJobNode(AsyncNode):
    """Process a job with its specific configuration."""
    
    async def exec_async(self, _):
        job_id = self.params["job_id"]
        input_file = self.params["input_file"]
        output_format = self.params["output_format"]
        quality = self.params["quality"]
        
        print(f"  [Job] {job_id}: {input_file} -> {output_format} ({quality} quality)")
        await asyncio.sleep(0.2)
        
        return {
            "job_id": job_id,
            "status": "completed",
            "output": f"{input_file.replace('.', '_')}.{output_format}"
        }
    
    async def post_async(self, shared, prep_res, exec_res):
        job_id = self.params["job_id"]
        notify_email = self.params["notify_email"]
        
        shared.setdefault("completed_jobs", {})[job_id] = {
            **exec_res,
            "notified": notify_email
        }
        return "default"


class JobProcessingFlow(ThrottledAsyncParallelBatchFlow):
    """Process jobs with configs loaded from external source."""
    
    max_concurrent_flows = 2
    
    async def prep_async(self, shared) -> List[Dict[str, Any]]:
        """
        Load job configs from shared data (simulating database/API fetch).
        
        In real usage, this might:
        - Query a database for pending jobs
        - Read from a config file
        - Fetch from an API
        """
        job_configs: List[JobConfig] = shared.get("job_configs", [])
        
        # Convert dataclass objects to param dicts
        return [config.to_params() for config in job_configs]


async def example_4_dynamic_params():
    """Demonstrate loading parameters from external source."""
    print("\n" + "=" * 70)
    print("Example 4: Dynamic Parameters from External Source")
    print("=" * 70)
    
    # Simulate loading job configs from database
    job_configs = [
        JobConfig("job_001", "video1.mp4", "webm", "high", "user1@example.com"),
        JobConfig("job_002", "video2.mov", "mp4", "medium", "user2@example.com"),
        JobConfig("job_003", "audio1.wav", "mp3", "high", "user1@example.com"),
        JobConfig("job_004", "image1.png", "webp", "low", "user3@example.com"),
    ]
    
    flow = JobProcessingFlow(start=ProcessJobNode())
    shared = {"job_configs": job_configs}
    
    print(f"\nProcessing {len(job_configs)} jobs with max_concurrent_flows={flow.max_concurrent_flows}")
    print("Job configs loaded from external source (simulated database)\n")
    
    start = time.time()
    await flow.run_async(shared)
    elapsed = time.time() - start
    
    print(f"\nCompleted Jobs ({elapsed:.2f}s):")
    for job_id, result in shared.get("completed_jobs", {}).items():
        print(f"  {job_id}: {result['output']} (notify: {result['notified']})")


# =============================================================================
# Main
# =============================================================================

async def main():
    """Run all examples."""
    await example_1_user_processing()
    await example_2_document_processing()
    await example_3_multi_region()
    await example_4_dynamic_params()
    
    print("\n" + "=" * 70)
    print("Summary: How Parameters Flow")
    print("=" * 70)
    print("""
    ThrottledAsyncParallelBatchFlow Parameter Flow:
    
    1. prep_async(shared) returns: [
           {"user_id": 1, "type": "premium"},  # Flow instance 1
           {"user_id": 2, "type": "standard"}, # Flow instance 2
           {"user_id": 3, "type": "premium"},  # Flow instance 3
       ]
    
    2. Each dict becomes self.params for one flow instance:
       
       Flow Instance 1:              Flow Instance 2:
       ┌─────────────────┐          ┌─────────────────┐
       │ NodeA           │          │ NodeA           │
       │ self.params =   │          │ self.params =   │
       │ {user_id: 1,    │          │ {user_id: 2,    │
       │  type: premium} │          │  type: standard}│
       └────────┬────────┘          └────────┬────────┘
                │                            │
                ▼                            ▼
       ┌─────────────────┐          ┌─────────────────┐
       │ NodeB           │          │ NodeB           │
       │ self.params =   │          │ self.params =   │
       │ {user_id: 1,    │  ◄────►  │ {user_id: 2,    │
       │  type: premium} │ parallel │  type: standard}│
       └─────────────────┘          └─────────────────┘
    
    3. All nodes in the same flow instance share the same params
    
    4. Flow instances run in parallel (up to max_concurrent_flows)
    
    Key Points:
    - Use self.params in nodes to access flow-specific configuration
    - Store results in shared using unique keys (e.g., user_id) to avoid races
    - prep_async can load configs from any source (DB, API, file, etc.)
    """)


if __name__ == "__main__":
    asyncio.run(main())
