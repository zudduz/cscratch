#!/bin/bash

URL="https://cscratch-dg-171510694317.us-central1.run.app/ping"

echo "🔌 Keep-alive active. Pinging $URL every 5 minutes..."
echo "❌ Press Ctrl+C to stop."

while true; do
    # Curl the URL, silence the output, and print a timestamp
    curl -s -o /dev/null -w "%{http_code}" "$URL"
    echo " - Pinged at $(date +%H:%M:%S)"
    
    # Wait 300 seconds (5 minutes)
    sleep 300
done