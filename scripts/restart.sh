#!/bin/bash
# Safe Server Restart Script for SkywarnPlus-NG
# Ensures proper process termination and port availability

set -e

APP_DIR="/home/anarchy/skywarnplus-ng-3.0.0"
VENV_PYTHON="$APP_DIR/venv/bin/python3"
CONFIG_FILE="$APP_DIR/config/default.yaml"
LOG_FILE="$APP_DIR/server_safe_restart.log"
PID_FILE="$APP_DIR/server.pid"
WEB_PORT=8100
SERVER_HOST="10.0.0.41"
MAX_WAIT_TIME=30

echo "🔄 SkywarnPlus-NG Safe Server Restart"
echo "====================================="

# Function to check if port is in use
check_port() {
    local port=$1
    if netstat -tlnp 2>/dev/null | grep -q ":$port "; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

# Function to find processes using the port
find_port_processes() {
    local port=$1
    netstat -tlnp 2>/dev/null | grep ":$port " | awk '{print $7}' | cut -d'/' -f1 | grep -v '^-$' || true
}

# Function to find Python processes related to skywarnplus
find_skywarnplus_processes() {
    ps aux | grep -v grep | grep python | grep skywarnplus | awk '{print $2}' || true
}

# Step 1: Check current state
echo "📊 Checking current server state..."
if check_port $WEB_PORT; then
    echo "⚠️  Port $WEB_PORT is currently in use"
    PORT_PIDS=$(find_port_processes $WEB_PORT)
    if [ -n "$PORT_PIDS" ]; then
        echo "   Processes using port $WEB_PORT: $PORT_PIDS"
    fi
else
    echo "✅ Port $WEB_PORT is available"
fi

SKYWARN_PIDS=$(find_skywarnplus_processes)
if [ -n "$SKYWARN_PIDS" ]; then
    echo "⚠️  Found SkywarnPlus processes: $SKYWARN_PIDS"
else
    echo "✅ No SkywarnPlus processes found"
fi

# Step 2: Stop existing processes
echo ""
echo "🛑 Stopping existing processes..."

# Kill SkywarnPlus processes
if [ -n "$SKYWARN_PIDS" ]; then
    echo "   Terminating SkywarnPlus processes: $SKYWARN_PIDS"
    for pid in $SKYWARN_PIDS; do
        if kill -TERM "$pid" 2>/dev/null; then
            echo "   Sent SIGTERM to PID $pid"
        else
            echo "   Failed to send SIGTERM to PID $pid (may already be dead)"
        fi
    done
    
    # Wait for graceful shutdown
    echo "   Waiting for graceful shutdown..."
    for i in $(seq 1 10); do
        REMAINING_PIDS=$(find_skywarnplus_processes)
        if [ -z "$REMAINING_PIDS" ]; then
            echo "   ✅ All processes terminated gracefully"
            break
        fi
        echo "   Waiting... ($i/10) - Remaining PIDs: $REMAINING_PIDS"
        sleep 1
    done
    
    # Force kill if still running
    REMAINING_PIDS=$(find_skywarnplus_processes)
    if [ -n "$REMAINING_PIDS" ]; then
        echo "   ⚠️  Force killing remaining processes: $REMAINING_PIDS"
        for pid in $REMAINING_PIDS; do
            if kill -KILL "$pid" 2>/dev/null; then
                echo "   Force killed PID $pid"
            fi
        done
    fi
fi

# Kill any processes still using the port
if check_port $WEB_PORT; then
    PORT_PIDS=$(find_port_processes $WEB_PORT)
    if [ -n "$PORT_PIDS" ]; then
        echo "   ⚠️  Force killing processes using port $WEB_PORT: $PORT_PIDS"
        for pid in $PORT_PIDS; do
            if [ "$pid" != "-" ] && [ -n "$pid" ]; then
                if kill -KILL "$pid" 2>/dev/null; then
                    echo "   Force killed PID $pid"
                fi
            fi
        done
    fi
fi

# Step 3: Wait and verify port is free
echo ""
echo "⏳ Waiting for port to be released..."
for i in $(seq 1 10); do
    if ! check_port $WEB_PORT; then
        echo "✅ Port $WEB_PORT is now free"
        break
    fi
    echo "   Waiting for port release... ($i/10)"
    sleep 1
done

if check_port $WEB_PORT; then
    echo "❌ Port $WEB_PORT is still in use after cleanup!"
    echo "   Manual intervention may be required"
    exit 1
fi

# Clean up old PID file
if [ -f "$PID_FILE" ]; then
    rm -f "$PID_FILE"
    echo "🧹 Cleaned up old PID file"
fi

# Step 4: Start the server
echo ""
echo "🚀 Starting SkywarnPlus-NG server..."
cd "$APP_DIR"
source venv/bin/activate

# Start server in background
nohup "$VENV_PYTHON" -m skywarnplus_ng.cli run --config "$CONFIG_FILE" > "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"
echo "   Started with PID: $NEW_PID"

# Step 5: Verify startup
echo ""
echo "🔍 Verifying server startup..."
sleep 3

# Check if process is still running
if ! ps -p "$NEW_PID" > /dev/null 2>&1; then
    echo "❌ Server process died immediately!"
    echo "   Check logs: $LOG_FILE"
    tail -20 "$LOG_FILE" 2>/dev/null || echo "   No log file found"
    exit 1
fi

# Wait for port to be bound
echo "   Waiting for server to bind to port $WEB_PORT..."
for i in $(seq 1 $MAX_WAIT_TIME); do
    if check_port $WEB_PORT; then
        echo "✅ Server is listening on port $WEB_PORT"
        break
    fi
    if ! ps -p "$NEW_PID" > /dev/null 2>&1; then
        echo "❌ Server process died during startup!"
        echo "   Check logs: $LOG_FILE"
        tail -20 "$LOG_FILE" 2>/dev/null || echo "   No log file found"
        exit 1
    fi
    echo "   Waiting for port binding... ($i/$MAX_WAIT_TIME)"
    sleep 1
done

if ! check_port $WEB_PORT; then
    echo "❌ Server failed to bind to port $WEB_PORT within $MAX_WAIT_TIME seconds"
    echo "   Check logs: $LOG_FILE"
    tail -20 "$LOG_FILE" 2>/dev/null || echo "   No log file found"
    exit 1
fi

# Step 6: Test server response
echo ""
echo "🧪 Testing server response..."
sleep 2

# Test local connection first
if curl -s --connect-timeout 5 "http://localhost:$WEB_PORT/api/status" > /dev/null; then
    echo "✅ Server responding on localhost"
else
    echo "⚠️  Server not responding on localhost"
fi

# Test external connection
if curl -s --connect-timeout 5 "http://$SERVER_HOST:$WEB_PORT/api/status" > /dev/null; then
    echo "✅ Server responding on external IP"
else
    echo "⚠️  Server not responding on external IP (firewall?)"
fi

# Test the alerts history endpoint specifically
echo "   Testing alerts history endpoint..."
HISTORY_RESPONSE=$(curl -s --connect-timeout 5 -w "%{http_code}" "http://localhost:$WEB_PORT/api/alerts/history?hours=24" -o /dev/null)
if [ "$HISTORY_RESPONSE" = "200" ]; then
    echo "✅ Alerts history endpoint working (HTTP 200)"
elif [ "$HISTORY_RESPONSE" = "500" ]; then
    echo "⚠️  Alerts history endpoint returning HTTP 500 (check logs)"
else
    echo "⚠️  Alerts history endpoint returned HTTP $HISTORY_RESPONSE"
fi

echo ""
echo "🎉 Server restart completed!"
echo "   PID: $NEW_PID"
echo "   Log: $LOG_FILE"
echo "   URL: http://$SERVER_HOST:$WEB_PORT"
echo ""
echo "Recent log entries:"
tail -10 "$LOG_FILE" 2>/dev/null || echo "No log entries yet"
