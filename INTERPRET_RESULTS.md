# Interpreting Scheduler Benchmark Results

This guide helps you understand what the timing data means and identify optimization opportunities.

## Quick Start

```bash
# Terminal 1: Build and start server
./run_scheduler_benchmark.sh --build
./run_scheduler_benchmark.sh --serve

# Terminal 2: Run benchmark
./run_scheduler_benchmark.sh --benchmark --scenario heavy
```

---

## Reading the Timing Stats

Every 100 schedule() calls, you'll see output like this:

```
================================================================================
SCHEDULER TIMING ANALYSIS (averaged over 100 schedule() calls)
================================================================================
Total schedule() time:        2.500 ms/call
  - Running reqs processing:  0.800 ms  (32.0%)
  - Waiting reqs processing:  1.500 ms  (60.0%)
```

### What to Look For:

1. **Total schedule() time**
   - **Good:** < 1ms
   - **Moderate:** 1-3ms
   - **Needs optimization:** > 3ms

   *Why it matters:* schedule() is called on every forward pass. High times directly impact TTFT and throughput.

2. **Waiting reqs processing %**
   - **Good:** < 40%
   - **Moderate:** 40-60%
   - **Hot spot:** > 60%

   *Why it matters:* This is where our optimization targets. High % means waiting queue processing is the bottleneck.

---

## Waiting Queue Breakdown

```
Waiting queue breakdown:
  - Status checks:            0.600 ms  (40.0% of waiting time)
    ∟ Remote KV checks:       0.200 ms  (10 reqs skipped)
    ∟ FSM checks:             0.150 ms  (5 reqs skipped)
    ∟ Streaming checks:       0.050 ms  (2 reqs skipped)
    ∟ LoRA checks:            0.200 ms  (3 reqs skipped)
  - Prefix cache lookups:     0.500 ms  (33.3%, 50 lookups)
  - KV cache allocations:     0.300 ms  (20.0%, 45 allocs)
```

### Status Checks

**Indicator:** `(40.0% of waiting time)`

| % of Waiting Time | Optimization Potential |
|-------------------|------------------------|
| < 20% | Low - not worth optimizing |
| 20-40% | Medium - readiness cache helps |
| > 40% | **High - readiness cache critical!** |

**Look at the breakdown:**
- **High "reqs skipped" counts** → Many blocked requests being checked repeatedly
- **Remote KV checks taking longest** → These involve I/O checks
- **FSM checks time** → Grammar compilation is blocking requests

### Prefix Cache Lookups

**Indicator:** `(33.3%, 50 lookups)`

| % of Waiting Time | What It Means |
|-------------------|---------------|
| < 20% | Prefix caching is efficient |
| 20-40% | **Optimization opportunity** |
| > 40% | Major bottleneck - cache the results! |

**Number of lookups:**
- If lookups >> scheduled requests → Many requests checking the same prefixes
- **Solution:** Cache prefix lookup results on Request object

### KV Cache Allocations

**Indicator:** `(20.0%, 45 allocs)`

| % of Waiting Time | Action Needed |
|-------------------|---------------|
| < 25% | No action needed |
| 25-40% | Consider batch allocation |
| > 40% | **Batch allocation critical!** |

**Number of allocations:**
- Should be ≈ number of requests scheduled
- If much higher → Requests being allocated and freed repeatedly

---

## Request Processing Metrics

```
Request processing:
  - Avg waiting reqs checked: 15.0 reqs/call
  - Avg waiting reqs scheduled: 10.0 reqs/call
  - Wasted checks (blocked):  5.0 reqs/call
```

### Wasted Checks Ratio

**Formula:** `Wasted checks / Waiting reqs checked`

| Ratio | Interpretation | Action |
|-------|----------------|--------|
| < 20% | Efficient - most checked requests are ready | No optimization needed |
| 20-40% | Moderate waste | Readiness cache provides modest gains |
| > 40% | **High waste - many blocked requests** | **Readiness cache critical!** |

**Example calculation:**
- Wasted: 5.0 reqs/call
- Checked: 15.0 reqs/call
- Ratio: 33.3% → Readiness cache will help!

### Efficiency Metrics

**Scheduling efficiency:** `Scheduled / Checked`
- **Good:** > 70% (most checked requests get scheduled)
- **Moderate:** 50-70%
- **Poor:** < 50% (checking many blocked requests)

---

## Benchmark Output Analysis

From `benchmark_scheduler.py`, you'll see:

```
Time to First Token (TTFT):
  - Mean:           250.50 ms
  - Median (p50):   200.00 ms
  - p90:            400.00 ms
  - p99:            800.00 ms
```

### TTFT Analysis

| Metric | What to Compare |
|--------|-----------------|
| **Mean vs Median** | Large gap → high variance, some requests very slow |
| **p90** | Should be < 2x median for consistent performance |
| **p99** | Outliers - check if > 3x median |

### Correlating with Scheduler Stats

**High p99 TTFT + High wasted checks:**
- Requests waiting in queue while blocked requests are checked
- **Solution:** Readiness cache will reduce p99

**High mean TTFT + High prefix cache time:**
- Prefix lookup overhead on every request
- **Solution:** Cache prefix lookups

**High p90/p99 + High KV allocation time:**
- Memory allocation contention
- **Solution:** Batch allocation

---

## Identifying Optimization Opportunities

### Scenario 1: Readiness Cache Will Help

**Symptoms:**
```
- Status checks:            0.800 ms  (50% of waiting time)  ← HIGH!
- Wasted checks (blocked):  8.0 reqs/call                   ← HIGH!
- Avg waiting reqs checked: 20.0 reqs/call
- Avg scheduled:            12.0 reqs/call
- Efficiency:              60%                               ← LOW!
```

**Expected improvement:** 30-50% reduction in waiting time

### Scenario 2: Prefix Cache Will Help

**Symptoms:**
```
- Prefix cache lookups:     0.900 ms  (45% of waiting time)  ← HIGH!
- Number of lookups:        80 lookups                       ← HIGH!
- Avg scheduled:            50 reqs/call
- Ratio lookups/scheduled:  1.6x                             ← WASTEFUL!
```

**Expected improvement:** 20-35% reduction in waiting time

### Scenario 3: Batch Allocation Will Help

**Symptoms:**
```
- KV cache allocations:     0.700 ms  (40% of waiting time)  ← HIGH!
- Number of allocations:    60 allocs
- Avg scheduled:            55 reqs/call
- Many allocations per request                                ← INEFFICIENT!
```

**Expected improvement:** 15-25% reduction in waiting time

### Scenario 4: Multiple Optimizations Needed

**Symptoms:**
```
- Status checks:            0.600 ms  (35%)  ← HIGH
- Prefix cache lookups:     0.500 ms  (30%)  ← HIGH
- KV cache allocations:     0.400 ms  (25%)  ← HIGH
Total waiting time:         1.700 ms
```

**Combined improvement:** 50-70% reduction in total waiting time!

---

## Running Comparisons

### Before Optimization:

```bash
./run_scheduler_benchmark.sh --benchmark --scenario heavy 2>&1 | tee baseline.txt
```

**Record these metrics:**
- Total schedule() time: ______ ms
- Waiting time: ______ ms (______%)
- Status checks: ______ ms (______%)
- Wasted checks: ______ reqs/call
- Mean TTFT: ______ ms
- p99 TTFT: ______ ms

### After Implementing Readiness Cache:

Run same benchmark, compare:

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Total schedule() time | | | |
| Waiting time | | | |
| Status checks time | | | |
| Wasted checks | | | |
| Mean TTFT | | | |
| p99 TTFT | | | |

---

## Red Flags

🚩 **Status checks > 40% of waiting time**
   → Implement readiness cache immediately

🚩 **Wasted checks > 50% of checked requests**
   → Queue has many blocked requests, readiness cache critical

🚩 **Prefix cache lookups > 35% of waiting time**
   → Cache lookup results on Request object

🚩 **Total schedule() time > 5ms**
   → Multiple bottlenecks, need comprehensive optimization

🚩 **p99 TTFT > 5x p50**
   → High variance, likely due to queue processing issues

---

## Success Criteria

After optimization, aim for:

✅ Total schedule() time: < 1ms
✅ Waiting time: < 40% of total
✅ Status checks: < 20% of waiting time
✅ Wasted checks: < 20% of checked requests
✅ Prefix cache lookups: < 25% of waiting time
✅ p99 TTFT: < 2x p50

---

## Next Steps

1. **Collect baseline:** Run all scenarios, save results
2. **Identify bottleneck:** Which metric is highest?
3. **Implement optimization:** Start with highest impact
4. **Re-benchmark:** Use same scenarios to compare
5. **Iterate:** Move to next bottleneck

**Priority order (by impact):**
1. Readiness cache (if wasted checks > 30%)
2. Cached prefix lookups (if prefix time > 30%)
3. Batch allocation (if allocation time > 30%)
4. Fast paths for common cases
5. Request queue indexing
