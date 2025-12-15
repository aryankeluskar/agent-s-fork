#!/bin/bash
# Build script for robotgo_executor

set -e

echo "Building robotgo_executor..."

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Initialize Go module if needed
if [ ! -f "go.mod" ]; then
    echo "Initializing Go module..."
    go mod init robotgo-executor
fi

# Download dependencies
echo "Downloading dependencies..."
go mod tidy

# Build the binary
echo "Building binary..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    go build -o robotgo_executor main.go
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    go build -o robotgo_executor main.go
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    # Windows
    go build -o robotgo_executor.exe main.go
else
    echo "Unknown OS: $OSTYPE"
    exit 1
fi

echo "✅ Build complete! Binary: ./robotgo_executor"

