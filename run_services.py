"""
Master Local Multi-Process Runner for Microservices Suite
==========================================================
Launches all 7 microservices concurrently with process management,
clean console status logs, and graceful shutdown on Ctrl+C.

Usage:
    python run_services.py                  # Launch all 7 microservices
    python run_services.py --only gateway   # Launch only API Gateway
    python run_services.py --only ocr dl    # Launch specific microservices
"""

import sys
import time
import signal
import argparse
import subprocess
from pathlib import Path
from typing import List, Dict

ROOT_DIR = Path(__file__).resolve().parent

SERVICES_CONFIG = [
    {
        "name": "OCR Service",
        "key": "ocr",
        "port": 8001,
        "app": "microservices.ocr_service.main:app",
        "desc": "PP-OCRv4 & OpenCV Preprocessor",
    },
    {
        "name": "Aadhaar Service",
        "key": "aadhaar",
        "port": 8002,
        "app": "microservices.aadhaar_service.main:app",
        "desc": "Aadhaar Card Extractor",
    },
    {
        "name": "DL Service",
        "key": "dl",
        "port": 8003,
        "app": "microservices.dl_service.main:app",
        "desc": "Driving Licence Extractor",
    },
    {
        "name": "PAN Service",
        "key": "pan",
        "port": 8004,
        "app": "microservices.pan_service.main:app",
        "desc": "PAN Card Extractor",
    },
    {
        "name": "RC Service",
        "key": "rc",
        "port": 8005,
        "app": "microservices.rc_service.main:app",
        "desc": "Vehicle RC Extractor",
    },
    {
        "name": "Validator Service",
        "key": "validator",
        "port": 8006,
        "app": "microservices.validator_service.main:app",
        "desc": "Identity Cross-Validator",
    },
    {
        "name": "API Gateway",
        "key": "gateway",
        "port": 8000,
        "app": "microservices.api_gateway.main:app",
        "desc": "Master Edge API Gateway & Orchestrator",
    },
]


def main():
    parser = argparse.ArgumentParser(description="Driver Verification Microservices Suite Runner")
    parser.add_argument(
        "--only",
        nargs="+",
        help="Run only specific services by key (e.g. --only gateway ocr dl)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind services to (default: 127.0.0.1)",
    )
    args = parser.parse_args()

    selected_keys = set(args.only) if args.only else None
    targets = [s for s in SERVICES_CONFIG if selected_keys is None or s["key"] in selected_keys]

    if not targets:
        print(f"[ERROR] No matching services found for filter: {args.only}")
        print(f"Available keys: {', '.join(s['key'] for s in SERVICES_CONFIG)}")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("  DRIVER DOCUMENT VERIFICATION — MICROSERVICES CLUSTER RUNNER")
    print("=" * 70)
    print(f"  Starting {len(targets)} microservice(s) on host: {args.host}...\n")

    processes: Dict[str, subprocess.Popen] = {}

    def shutdown(sig=None, frame=None):
        print("\n\n  [SHUTDOWN] Terminating all microservices...")
        for name, proc in processes.items():
            try:
                proc.terminate()
            except Exception:
                pass
        time.sleep(1.0)
        for name, proc in processes.items():
            try:
                proc.kill()
            except Exception:
                pass
        print("  [SHUTDOWN] All microservice processes stopped cleanly.\n")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Launch subprocesses
    for svc in targets:
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            svc["app"],
            "--host",
            args.host,
            "--port",
            str(svc["port"]),
            "--log-level",
            "warning",
        ]

        print(f"  -> Launching [{svc['name']:<18}] on http://{args.host}:{svc['port']} ({svc['desc']})")
        proc = subprocess.Popen(cmd, cwd=str(ROOT_DIR))
        processes[svc["name"]] = proc

    print("\n" + "-" * 70)
    print("  ALL MICROSERVICES INITIALIZED")
    print("-" * 70)
    print(f"  * Master Gateway Swagger Docs: http://{args.host}:8000/docs")
    print(f"  * Cluster Health Dashboard  : http://{args.host}:8000/health")
    print("  * Press Ctrl+C at any time to gracefully stop all services.")
    print("-" * 70 + "\n")

    try:
        # Keep main process alive and monitor child processes
        while True:
            time.sleep(2.0)
            for name, proc in list(processes.items()):
                poll_res = proc.poll()
                if poll_res is not None:
                    print(f"  [WARNING] Service '{name}' exited unexpectedly with code {poll_res}.")
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
