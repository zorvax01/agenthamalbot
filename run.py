#!/usr/bin/env python3
"""Run agenthamalbot (bot.py) and the proxy stats bot (stats_bot.py)
side by side in this one container. If either exits, restart it.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROCS = [
    ("agenthamalbot", [sys.executable, os.path.join(HERE, "bot.py")]),
    ("stats_bot", [sys.executable, os.path.join(HERE, "stats_bot.py")]),
]


def main():
    procs = {}
    for name, cmd in PROCS:
        print(f"starting {name}: {' '.join(cmd)}", flush=True)
        procs[name] = subprocess.Popen(cmd)
    while True:
        for name, cmd in PROCS:
            p = procs[name]
            if p.poll() is not None:
                print(
                    f"{name} exited with code {p.returncode}, "
                    "restarting in 5s",
                    flush=True,
                )
                time.sleep(5)
                procs[name] = subprocess.Popen(cmd)
        time.sleep(5)


if __name__ == "__main__":
    main()
