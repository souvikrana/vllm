# Scheduler Performance Benchmark Guide

This guide will help you build vLLM with timing instrumentation and run benchmarks.

## Step 1: Build and Install vLLM

```bash
cd /home/souvik/repos/vllm

# Clean previous builds (optional)
rm -rf build dist *.egg-info

# Build and install in development mode
pip install -e . -v

# Or for faster build (skip some optimizations):
# MAX_JOBS=8 pip install -e . -v
```

**Expected time:** 10-20 minutes depending on your system.

## Step 2: Start vLLM Server

### Option A: Using a small model (faster, for testing)

```bash
# Using Qwen2.5-0.5B (small, fast to load)
vllm serve Qwen/Qwen2.5-0.5B-Instruct \
    --host 0.0.0.0 \
    --port 8000 \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.9
```

### Option B: Using a medium model (more realistic)

```bash
# Using Llama-3.2-3B
vllm serve meta-llama/Llama-3.2-3B-Instruct \
    --host 0.0.0.0 \
    --port 8000 \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.9
```

### Option C: Using your own model

```bash
vllm serve <your-model-name> \
    --host 0.0.0.0 \
    --port 8000 \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.9
```

**Important:** Keep the server running in one terminal!

## Step 3: Run the Benchmark (in a new terminal)

### Quick test (light load):
```bash
cd /home/souvik/repos/vllm
python benchmark_scheduler.py --scenario light
```

### Moderate load (recommended):
```bash
python benchmark_scheduler.py --scenario moderate
```

### Heavy load (scheduler stress test):
```bash
python benchmark_scheduler.py --scenario heavy
```

### Burst load (queue backlog test):
```bash
python benchmark_scheduler.py --scenario burst
```

### Run all scenarios:
```bash
python benchmark_scheduler.py --all-scenarios
```

## Step 4: Analyze Results

### In the benchmark terminal:
You'll see request-level metrics:
- Time to First Token (TTFT) - p50, p90, p99
- Total request time
- Throughput (tokens/sec, requests/sec)

### In the vLLM server terminal:
Every 100 schedule() calls, you'll see:
```
================================================================================
SCHEDULER TIMING ANALYSIS (averaged over 100 schedule() calls)
================================================================================
Total schedule() time:        2.500 ms/call
  - Running reqs processing:  0.800 ms  (32.0%)
  - Waiting reqs processing:  1.500 ms  (60.0%)

Waiting queue breakdown:
  - Status checks:            0.600 ms  (40.0% of waiting time)
    ∟ Remote KV checks:       0.200 ms  (10 reqs skipped)
    ∟ FSM checks:             0.150 ms  (5 reqs skipped)
    ∟ Streaming checks:       0.050 ms  (2 reqs skipped)
    ∟ LoRA checks:            0.200 ms  (3 reqs skipped)
  - Prefix cache lookups:     0.500 ms  (33.3%, 50 lookups)
  - KV cache allocations:     0.300 ms  (20.0%, 45 allocs)

Request processing:
  - Avg waiting reqs checked: 15.0 reqs/call
  - Avg waiting reqs scheduled: 10.0 reqs/call
  - Wasted checks (blocked):  5.0 reqs/call
================================================================================
```

### Key Metrics to Look For:

1. **Wasted checks (blocked)**: Higher = more optimization opportunity
2. **Status checks time**: If high % of waiting time, readiness cache will help
3. **Prefix cache lookups**: If high % and many lookups, caching will help
4. **Avg waiting reqs checked**: If >> scheduled, many blocked requests

## Step 5: Collect Baseline Results

Create a baseline report:

```bash
# In server terminal, redirect output
vllm serve <model> ... 2>&1 | tee baseline_scheduler_logs.txt

# In benchmark terminal
python benchmark_scheduler.py --all-scenarios 2>&1 | tee baseline_benchmark_results.txt
```

## Understanding the Results

### Scenario 1: Light Load
- **Purpose**: Baseline performance, minimal queueing
- **Expected**: Low TTFT, few blocked requests
- **Optimization potential**: Low

### Scenario 2: Moderate Load
- **Purpose**: Realistic production workload
- **Expected**: Moderate TTFT, some queueing
- **Optimization potential**: Medium

### Scenario 3: Heavy Load
- **Purpose**: Stress test scheduler
- **Expected**: High TTFT, significant queueing, many blocked checks
- **Optimization potential**: High (this is where optimizations shine!)

### Scenario 4: Burst Load
- **Purpose**: Test queue backlog handling
- **Expected**: Very high initial TTFT, gradual improvement
- **Optimization potential**: Very High (queue processing bottleneck)

## Next Steps

After collecting baseline:
1. Look at "Wasted checks (blocked)" - if > 20% of checked requests, readiness cache will help
2. Look at "Status checks time" - if > 30% of waiting time, optimization will help
3. Compare different scenarios to see where bottlenecks appear

## Troubleshooting

### Server won't start:
- Check CUDA is available: `nvidia-smi`
- Reduce `--max-model-len` if OOM
- Try smaller model

### Benchmark fails to connect:
- Check server is running: `curl http://localhost:8000/health`
- Check port is correct
- Check firewall settings

### No timing stats in server logs:
- Make sure you built the instrumented version
- Wait for at least 100 schedule() calls
- Check you're looking at the right terminal

## Cleanup

```bash
# Stop vLLM server: Ctrl+C in server terminal
# Remove build artifacts:
cd /home/souvik/repos/vllm
rm -rf build dist *.egg-info
```
