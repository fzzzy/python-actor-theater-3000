#!/usr/bin/env python3
"""Main Python script that runs on the main interpreter thread.
Handles signal processing while sub-interpreters run on other threads.
"""

import signal
import sys
import time


def signal_handler(signum, frame):
    print(f"\nReceived signal {signum}. Shutting down...")
    sys.exit(0)


def main():
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("Main interpreter running on main thread - handling signals...")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            time.sleep(0.1)  # Small sleep to prevent busy waiting
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received. Exiting...")


if __name__ == "__main__":
    main()
