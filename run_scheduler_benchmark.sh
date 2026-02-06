#!/bin/bash
# Helper script to build and benchmark scheduler

set -e

echo "========================================="
echo "vLLM Scheduler Benchmark Helper"
echo "========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_step() {
    echo -e "${GREEN}[STEP]${NC} $1"
}

print_info() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ] || [ ! -d "vllm" ]; then
    print_error "This script must be run from the vLLM root directory"
    exit 1
fi

# Parse command line arguments
BUILD=false
SERVE=false
BENCHMARK=false
MODEL="Qwen/Qwen2.5-0.5B-Instruct"
SCENARIO="moderate"

while [[ $# -gt 0 ]]; do
    case $1 in
        --build)
            BUILD=true
            shift
            ;;
        --serve)
            SERVE=true
            shift
            ;;
        --benchmark)
            BENCHMARK=true
            shift
            ;;
        --model)
            MODEL="$2"
            shift 2
            ;;
        --scenario)
            SCENARIO="$2"
            shift 2
            ;;
        --all)
            BUILD=true
            print_info "Note: --serve and --benchmark must be run separately after build"
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --build              Build and install vLLM with instrumentation"
            echo "  --serve              Start vLLM server"
            echo "  --benchmark          Run benchmark (requires server to be running)"
            echo "  --model MODEL        Model to use (default: Qwen/Qwen2.5-0.5B-Instruct)"
            echo "  --scenario NAME      Benchmark scenario: light, moderate, heavy, burst"
            echo "  --all                Run all steps (interactive)"
            echo "  --help               Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --build"
            echo "  $0 --serve --model meta-llama/Llama-3.2-3B-Instruct"
            echo "  $0 --benchmark --scenario heavy"
            echo ""
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# If no options provided, show help
if [ "$BUILD" = false ] && [ "$SERVE" = false ] && [ "$BENCHMARK" = false ]; then
    echo "No action specified. Use --help for usage information."
    echo ""
    echo "Quick start:"
    echo "  1. $0 --build"
    echo "  2. $0 --serve       (in terminal 1, keep running)"
    echo "  3. $0 --benchmark   (in terminal 2)"
    exit 0
fi

# Step 1: Build
if [ "$BUILD" = true ]; then
    print_step "Building vLLM with scheduler instrumentation..."
    print_info "This may take 10-20 minutes..."

    # Clean previous builds
    rm -rf build dist *.egg-info 2>/dev/null || true

    # Build and install
    MAX_JOBS=8 pip install -e . -v

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Build complete!${NC}"
    else
        print_error "Build failed!"
        exit 1
    fi

    echo ""
    print_info "Next steps:"
    echo "  1. Start server:   $0 --serve"
    echo "  2. Run benchmark:  $0 --benchmark"
    exit 0
fi

# Step 2: Serve
if [ "$SERVE" = true ]; then
    print_step "Starting vLLM server..."
    print_info "Model: $MODEL"
    print_info "Port: 8000"
    echo ""
    print_info "Server logs will show timing stats every 100 schedule() calls"
    print_info "Press Ctrl+C to stop"
    echo ""

    # Check if port is already in use
    if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
        print_error "Port 8000 is already in use!"
        print_info "Stop the existing server or use a different port"
        exit 1
    fi

    # Start server
    vllm serve "$MODEL" \
        --host 0.0.0.0 \
        --port 8000 \
        --max-model-len 4096 \
        --gpu-memory-utilization 0.9

    exit 0
fi

# Step 3: Benchmark
if [ "$BENCHMARK" = true ]; then
    print_step "Running scheduler benchmark..."
    print_info "Scenario: $SCENARIO"
    echo ""

    # Check if server is running
    if ! curl -s http://localhost:8000/health >/dev/null 2>&1; then
        print_error "vLLM server is not running!"
        print_info "Start the server first: $0 --serve"
        exit 1
    fi

    echo -e "${GREEN}✓ Connected to vLLM server${NC}"
    echo ""

    # Run benchmark
    python benchmark_scheduler.py --scenario "$SCENARIO"

    echo ""
    print_info "Check the vLLM server terminal for detailed scheduler timing stats"
    exit 0
fi
