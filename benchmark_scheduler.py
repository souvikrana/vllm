#!/usr/bin/env python3
"""
Scheduler Performance Benchmark Script

This script simulates realistic traffic patterns to measure scheduler overhead.
It sends requests with varying characteristics to stress-test the scheduler.
"""
import argparse
import asyncio
import json
import random
import time
from typing import List

import aiohttp


class BenchmarkConfig:
    """Configuration for benchmark scenarios."""

    def __init__(self, name: str, **kwargs):
        self.name = name
        self.num_requests = kwargs.get("num_requests", 100)
        self.arrival_rate = kwargs.get("arrival_rate", 10)  # requests/sec
        self.prompt_length_min = kwargs.get("prompt_length_min", 100)
        self.prompt_length_max = kwargs.get("prompt_length_max", 1000)
        self.max_tokens_min = kwargs.get("max_tokens_min", 50)
        self.max_tokens_max = kwargs.get("max_tokens_max", 200)
        self.concurrent_requests = kwargs.get("concurrent_requests", 50)


# Benchmark scenarios
SCENARIOS = {
    "light": BenchmarkConfig(
        "Light Load",
        num_requests=50,
        arrival_rate=5,
        prompt_length_min=100,
        prompt_length_max=500,
        max_tokens_min=50,
        max_tokens_max=100,
        concurrent_requests=10,
    ),
    "moderate": BenchmarkConfig(
        "Moderate Load",
        num_requests=100,
        arrival_rate=10,
        prompt_length_min=200,
        prompt_length_max=1000,
        max_tokens_min=100,
        max_tokens_max=200,
        concurrent_requests=25,
    ),
    "heavy": BenchmarkConfig(
        "Heavy Load - Scheduler Stress Test",
        num_requests=200,
        arrival_rate=20,
        prompt_length_min=500,
        prompt_length_max=2000,
        max_tokens_min=100,
        max_tokens_max=300,
        concurrent_requests=50,
    ),
    "burst": BenchmarkConfig(
        "Burst Load - Queue Backlog Test",
        num_requests=100,
        arrival_rate=50,  # High burst
        prompt_length_min=100,
        prompt_length_max=500,
        max_tokens_min=50,
        max_tokens_max=100,
        concurrent_requests=100,
    ),
}


class RequestStats:
    """Track statistics for a single request."""

    def __init__(self, request_id: int):
        self.request_id = request_id
        self.prompt_length = 0
        self.max_tokens = 0
        self.submit_time = 0.0
        self.first_token_time = 0.0
        self.complete_time = 0.0
        self.num_tokens = 0
        self.error = None

    @property
    def ttft(self) -> float:
        """Time to first token in seconds."""
        if self.first_token_time > 0:
            return self.first_token_time - self.submit_time
        return 0.0

    @property
    def total_time(self) -> float:
        """Total request time in seconds."""
        if self.complete_time > 0:
            return self.complete_time - self.submit_time
        return 0.0


async def send_request(
    session: aiohttp.ClientSession,
    url: str,
    request_id: int,
    prompt: str,
    max_tokens: int,
    stats: RequestStats,
):
    """Send a single completion request and track timing."""
    stats.submit_time = time.time()
    stats.prompt_length = len(prompt.split())
    stats.max_tokens = max_tokens

    payload = {
        "model": "model",
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "stream": True,
    }

    try:
        async with session.post(f"{url}/v1/completions", json=payload) as response:
            if response.status != 200:
                stats.error = f"HTTP {response.status}"
                return

            first_token = True
            async for line in response.content:
                if not line:
                    continue

                line = line.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue

                data = line[6:]  # Remove "data: " prefix
                if data == "[DONE]":
                    break

                try:
                    chunk = json.loads(data)
                    if first_token:
                        stats.first_token_time = time.time()
                        first_token = False

                    if "choices" in chunk and len(chunk["choices"]) > 0:
                        stats.num_tokens += 1

                except json.JSONDecodeError:
                    continue

            stats.complete_time = time.time()

    except Exception as e:
        stats.error = str(e)


def generate_prompt(length: int) -> str:
    """Generate a prompt with approximately 'length' tokens."""
    # Simple prompt generation - about 4 chars per token
    words = [
        "the",
        "quick",
        "brown",
        "fox",
        "jumps",
        "over",
        "lazy",
        "dog",
        "and",
        "then",
        "runs",
        "through",
        "forest",
    ]
    prompt_words = []
    while len(" ".join(prompt_words)) < length * 4:
        prompt_words.append(random.choice(words))
    return " ".join(prompt_words)


async def run_benchmark(url: str, config: BenchmarkConfig) -> List[RequestStats]:
    """Run benchmark with given configuration."""
    print(f"\n{'=' * 80}")
    print(f"Running benchmark: {config.name}")
    print(f"  - Requests: {config.num_requests}")
    print(f"  - Arrival rate: {config.arrival_rate} req/s")
    print(f"  - Concurrent requests: {config.concurrent_requests}")
    print(f"  - Prompt length: {config.prompt_length_min}-{config.prompt_length_max}")
    print(f"{'=' * 80}\n")

    all_stats: List[RequestStats] = []
    semaphore = asyncio.Semaphore(config.concurrent_requests)

    async def send_with_semaphore(session, req_id):
        async with semaphore:
            stats = RequestStats(req_id)
            prompt_len = random.randint(config.prompt_length_min, config.prompt_length_max)
            max_tokens = random.randint(config.max_tokens_min, config.max_tokens_max)
            prompt = generate_prompt(prompt_len)

            await send_request(session, url, req_id, prompt, max_tokens, stats)
            all_stats.append(stats)

            # Print progress
            if len(all_stats) % 10 == 0:
                print(f"Completed {len(all_stats)}/{config.num_requests} requests...")

    async with aiohttp.ClientSession() as session:
        tasks = []
        inter_arrival_time = 1.0 / config.arrival_rate

        for i in range(config.num_requests):
            task = asyncio.create_task(send_with_semaphore(session, i))
            tasks.append(task)

            # Wait before sending next request (Poisson arrival process)
            await asyncio.sleep(inter_arrival_time * random.expovariate(1.0))

        # Wait for all requests to complete
        await asyncio.gather(*tasks)

    return all_stats


def analyze_results(stats: List[RequestStats]):
    """Analyze and print benchmark results."""
    successful = [s for s in stats if s.error is None and s.ttft > 0]
    failed = [s for s in stats if s.error is not None]

    if not successful:
        print("\n❌ No successful requests!")
        return

    ttfts = [s.ttft for s in successful]
    total_times = [s.total_time for s in successful]

    # Sort for percentile calculations
    ttfts.sorted = sorted(ttfts)
    total_times.sorted = sorted(total_times)

    print(f"\n{'=' * 80}")
    print("BENCHMARK RESULTS")
    print(f"{'=' * 80}")
    print(f"Total requests:     {len(stats)}")
    print(f"Successful:         {len(successful)}")
    print(f"Failed:             {len(failed)}")
    print()
    print("Time to First Token (TTFT):")
    print(f"  - Mean:           {sum(ttfts) / len(ttfts) * 1000:.2f} ms")
    print(f"  - Median (p50):   {ttfts.sorted[len(ttfts) // 2] * 1000:.2f} ms")
    print(f"  - p90:            {ttfts.sorted[int(len(ttfts) * 0.9)] * 1000:.2f} ms")
    print(f"  - p99:            {ttfts.sorted[int(len(ttfts) * 0.99)] * 1000:.2f} ms")
    print(f"  - Min:            {min(ttfts) * 1000:.2f} ms")
    print(f"  - Max:            {max(ttfts) * 1000:.2f} ms")
    print()
    print("Total Request Time:")
    print(f"  - Mean:           {sum(total_times) / len(total_times):.2f} s")
    print(f"  - Median (p50):   {total_times.sorted[len(total_times) // 2]:.2f} s")
    print(f"  - p90:            {total_times.sorted[int(len(total_times) * 0.9)]:.2f} s")
    print(f"  - p99:            {total_times.sorted[int(len(total_times) * 0.99)]:.2f} s")
    print()
    print("Throughput:")
    total_tokens = sum(s.num_tokens for s in successful)
    total_time = max(s.complete_time for s in successful) - min(
        s.submit_time for s in successful
    )
    print(f"  - Total tokens:   {total_tokens}")
    print(f"  - Tokens/sec:     {total_tokens / total_time:.2f}")
    print(f"  - Requests/sec:   {len(successful) / total_time:.2f}")
    print(f"{'=' * 80}\n")

    if failed:
        print("Failed requests:")
        for s in failed[:10]:  # Show first 10 errors
            print(f"  Request {s.request_id}: {s.error}")
        if len(failed) > 10:
            print(f"  ... and {len(failed) - 10} more")


async def main():
    parser = argparse.ArgumentParser(description="Benchmark vLLM scheduler performance")
    parser.add_argument(
        "--url",
        type=str,
        default="http://localhost:8000",
        help="vLLM server URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        choices=list(SCENARIOS.keys()),
        default="moderate",
        help="Benchmark scenario (default: moderate)",
    )
    parser.add_argument(
        "--all-scenarios",
        action="store_true",
        help="Run all benchmark scenarios",
    )

    args = parser.parse_args()

    # Check if server is available
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{args.url}/health") as response:
                if response.status != 200:
                    print(f"❌ Server not available at {args.url}")
                    return
    except Exception as e:
        print(f"❌ Cannot connect to server at {args.url}: {e}")
        return

    print(f"✓ Connected to vLLM server at {args.url}")

    # Run benchmark(s)
    if args.all_scenarios:
        for scenario_name, config in SCENARIOS.items():
            stats = await run_benchmark(args.url, config)
            analyze_results(stats)
            await asyncio.sleep(5)  # Cool down between scenarios
    else:
        config = SCENARIOS[args.scenario]
        stats = await run_benchmark(args.url, config)
        analyze_results(stats)

    print("\n✓ Benchmark complete!")
    print("\nTo see detailed scheduler timing stats, check the vLLM server logs.")
    print("Look for lines starting with 'SCHEDULER TIMING ANALYSIS'")


if __name__ == "__main__":
    asyncio.run(main())
