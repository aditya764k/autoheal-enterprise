import time
import json
import os
import sys

# ANSI Color Codes
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
CYAN = '\033[96m'
MAGENTA = '\033[95m'
RESET = '\033[0m'
BOLD = '\033[1m'
DIM = '\033[2m'

def tail_file(filepath):
    """Generator that yields new lines appended to the file."""
    try:
        with open(filepath, 'r') as f:
            # Jump to the end of the file
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.2)
                    continue
                yield line
    except FileNotFoundError:
        print(f"{RED}Error: File {filepath} not found.{RESET}")
        print("Make sure the pipeline has started and logged at least one event.")
        sys.exit(1)

def format_log(line):
    """Parse JSON and print a human-readable, colorized output."""
    try:
        data = json.loads(line)
        
        ts = data.get("audit_timestamp", "").split(".")[0].replace("T", " ")
        zone = data.get("zone", "UNKNOWN")
        action = data.get("action", "unknown")
        target = data.get("target", "unknown")
        severity = data.get("severity", "UNKNOWN")
        confidence = data.get("confidence", 0.0)
        
        # Determine color for the zone
        if zone == "GREEN":
            c_zone = f"{GREEN}{BOLD}GREEN {RESET}"
        elif zone == "YELLOW":
            c_zone = f"{YELLOW}{BOLD}YELLOW{RESET}"
        elif zone == "RED":
            c_zone = f"{RED}{BOLD}RED   {RESET}"
        else:
            c_zone = f"{zone}"

        print(f"\n{DIM}[{ts}]{RESET} {c_zone} | {BOLD}{action}{RESET} on {CYAN}{target}{RESET} "
              f"{DIM}(Sev: {severity}, Conf: {confidence:.2f}){RESET}")
        print(f"  {MAGENTA}↳ Cause:{RESET} {data.get('root_cause', '')}")
        print(f"  {MAGENTA}↳ AI Reasoning:{RESET} {data.get('reasoning', '')}")
        
        # Display zone-specific details
        if zone == "GREEN":
            res = data.get("execution_result") or {}
            success = res.get("success", False)
            dur = res.get("duration_ms", 0)
            status = f"{GREEN}SUCCESS{RESET}" if success else f"{RED}FAILED{RESET}"
            detail = res.get("detail", "")
            print(f"  {GREEN}↳ Execution:{RESET} [{status}] in {dur}ms")
            print(f"      {detail}")
            
        elif zone == "YELLOW":
            print(f"  {YELLOW}↳ Action Paused:{RESET} {data.get('zone_reason', '')}")
            
        elif zone == "RED":
            print(f"  {RED}↳ Blocked by Safety Gate:{RESET} {data.get('zone_reason', '')}")
            
        print(f"{DIM}{'-'*80}{RESET}")
            
    except json.JSONDecodeError:
        pass # Ignore malformed lines

def main():
    log_path = "executor/audit_log.jsonl"
    print(f"{CYAN}{BOLD}🚀 AutoHeal Audit Log Viewer{RESET}")
    print(f"{DIM}Watching {log_path} for new events... (Press Ctrl+C to exit){RESET}")
    print(f"{DIM}{'-'*80}{RESET}")
    
    try:
        for line in tail_file(log_path):
            format_log(line)
    except KeyboardInterrupt:
        print(f"\n{DIM}Exiting viewer.{RESET}")

if __name__ == "__main__":
    main()
