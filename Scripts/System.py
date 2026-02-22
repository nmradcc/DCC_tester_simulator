#!/usr/bin/env python3
"""
DCC Tester System Menu
======================

Top-level menu system for running DCC tester scripts.
Provides centralized configuration management.
"""

import sys
import os
import subprocess
import threading
from pathlib import Path
from datetime import datetime

try:
    import mss
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

# Configure stdout/stderr for UTF-8 encoding on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Get the script directory
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "SystemConfig.txt"


class SystemConfig:
    """Manages system-level configuration."""
    
    def __init__(self):
        self.serial_port = "COM6"
        self.in_circuit_motor = False
        self.logging_level = 1
        self.monitor_index = 2
        self.screenshot_directory = "screenshots"
        self.save_logs = False
        self.log_directory = "logs"
        self._load_config()
    
    def _parse_bool(self, value):
        """Parse boolean value from config."""
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        normalized = str(value).strip().lower()
        return normalized in {"y", "yes", "true", "1"}
    
    def _parse_int(self, value, default=1):
        """Parse integer value from config."""
        if value is None or str(value).strip() == "":
            return default
        try:
            return int(str(value).strip(), 0)
        except ValueError:
            return default
    
    def _load_config(self):
        """Load configuration from SystemConfig.txt."""
        if not CONFIG_FILE.exists():
            print(f"Warning: {CONFIG_FILE} not found. Using defaults.")
            return
        
        try:
            config = {}
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip()
            
            # Parse configuration values
            self.serial_port = config.get("serial_port", "COM6")
            self.in_circuit_motor = self._parse_bool(config.get("in_circuit_motor", "false"))
            self.logging_level = self._parse_int(config.get("logging_level", "1"), default=1)
            self.monitor_index = self._parse_int(config.get("monitor_index", "2"), default=2)
            self.screenshot_directory = config.get("screenshot_directory", "screenshots")
            self.save_logs = self._parse_bool(config.get("save_logs", "false"))
            self.log_directory = config.get("log_directory", "logs")
            
        except Exception as e:
            print(f"Warning: Error loading config file: {e}")
            print("Using default values.")
    
    def display(self):
        """Display current configuration."""
        print("=" * 70)
        print("System Configuration:")
        print("=" * 70)
        print(f"  Serial port:         {self.serial_port}")
        print(f"  In-circuit motor:    {self.in_circuit_motor}")
        print(f"  Logging level:       {self.logging_level}")
        print(f"  Save logs:           {self.save_logs}")
        print(f"  Log directory:       {self.log_directory}")
        print(f"  Monitor index:       {self.monitor_index}")
        print(f"  Screenshot dir:      {self.screenshot_directory}")
        print("=" * 70)
    
    def toggle_logging(self):
        """Toggle save_logs setting (runtime only, does not update config)."""
        # Only allow toggle if save_logs is enabled in config
        if not self.save_logs:
            return None
        # Toggle is handled by caller through runtime flag
        return True


# Global config instance
_config = None
_log_file = None
_log_file_path = None  # Track log file path for appending
_logging_active = False  # Runtime logging state

class TeeOutput:
    """Write to both console and file."""
    def __init__(self, console, file_obj):
        self.console = console
        self.file = file_obj
    
    def write(self, message):
        self.console.write(message)
        if self.file:
            self.file.write(message)
            self.file.flush()
    
    def flush(self):
        self.console.flush()
        if self.file:
            self.file.flush()
    
    def isatty(self):
        return self.console.isatty()

def get_config():
    """Get the global system configuration."""
    global _config
    if _config is None:
        _config = SystemConfig()
    return _config


def start_logging():
    """Start logging to file if enabled. Console output is always displayed."""
    global _log_file, _log_file_path, _logging_active
    config = get_config()
    
    # Only start if runtime logging is active
    if not _logging_active:
        return
    
    try:
        # If we already have a log file path, reopen in append mode
        if _log_file_path:
            log_filename = _log_file_path
            _log_file = open(log_filename, "a", encoding="utf-8")
            print(f"Resuming logging to: {log_filename}")
        else:
            # Create log directory
            log_path = Path(config.log_directory)
            if not log_path.is_absolute():
                log_dir = SCRIPT_DIR / log_path
            else:
                log_dir = log_path
            log_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate log filename with timestamp (only once per session)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = log_dir / f"dcc_tester_{timestamp}.log"
            _log_file_path = log_filename
            
            # Open log file
            _log_file = open(log_filename, "w", encoding="utf-8")
            print(f"Logging to: {log_filename}")
        
        # Redirect stdout and stderr to both console and file
        sys.stdout = TeeOutput(sys.__stdout__, _log_file)
        sys.stderr = TeeOutput(sys.__stderr__, _log_file)
        
        print()
        
    except Exception as e:
        print(f"Warning: Could not start logging: {e}")


def stop_logging(close_file=False):
    """Stop logging and optionally close log file.
    
    Args:
        close_file: If True, close the log file completely. If False, just pause logging.
    """
    global _log_file, _log_file_path
    
    # Restore original stdout/stderr
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__
    
    # Close or flush log file
    if _log_file:
        try:
            if close_file:
                # Closing permanently, clear the path
                _log_file.close()
                _log_file = None
                _log_file_path = None
            else:
                # Just pausing, keep the path for later
                _log_file.flush()
                _log_file.close()
                _log_file = None
        except:
            pass


def capture_screen(prefix=None, interactive=True):
    """Capture screenshot from configured monitor and save with timestamp.
    
    Args:
        prefix: Optional base filename prefix. If provided and interactive=True, 
                user can add additional text that gets appended.
        interactive: If True, prompts for additional filename text. If False, uses default or provided prefix.
    """
    if not MSS_AVAILABLE:
        print("Error: mss not installed. Install with: pip install mss")
        return False
    
    config = get_config()
    monitor_index = config.monitor_index
    
    try:
        # Create screenshots folder from config
        screenshots_path = Path(config.screenshot_directory)
        if not screenshots_path.is_absolute():
            screenshots_dir = SCRIPT_DIR / screenshots_path
        else:
            screenshots_dir = screenshots_path
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        # Build the final prefix
        final_prefix = ""
        
        if prefix:
            # Sanitize the provided base prefix
            final_prefix = "".join(c for c in prefix if c.isalnum() or c in (' ', '_', '-')).strip()
            final_prefix = final_prefix.replace(' ', '_')
        
        if interactive:
            # Prompt for additional text
            if final_prefix:
                print(f"Enter additional text for filename (or press Enter for '{final_prefix}'): ", end='', flush=True)
            else:
                print("Enter text for filename (or press Enter for 'screen_capture'): ", end='', flush=True)
            
            user_input = input().strip()
            
            if user_input:
                # Sanitize the user input
                sanitized_input = "".join(c for c in user_input if c.isalnum() or c in (' ', '_', '-')).strip()
                sanitized_input = sanitized_input.replace(' ', '_')
                
                # Combine base prefix with additional text
                if final_prefix:
                    final_prefix = f"{final_prefix}_{sanitized_input}"
                else:
                    final_prefix = sanitized_input
        
        # Use default if no prefix was constructed
        if not final_prefix:
            final_prefix = "screen_capture"
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = screenshots_dir / f"{final_prefix}_{timestamp}.png"
        
        # Capture screenshot from configured monitor
        with mss.mss() as sct:
            # Monitor 0 is all monitors, Monitor 1 is primary, Monitor 2 is secondary
            monitors = sct.monitors
            
            if len(monitors) <= monitor_index:  # monitors[0] is all monitors
                print(f"Warning: Monitor {monitor_index} not available (only {len(monitors) - 1} monitor(s) detected)")
                print("Capturing from primary monitor instead")
                monitor_num = 1
            else:
                monitor_num = monitor_index
                print(f"Capturing from monitor {monitor_num}...")
            
            # Capture the screenshot
            screenshot = sct.grab(sct.monitors[monitor_num])
            
            # Save to PNG file
            mss.tools.to_png(screenshot.rgb, screenshot.size, output=str(filename))
        
        print(f"✓ Screenshot saved: {filename}")
        return True
        
    except Exception as e:
        print(f"Error capturing screen: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_script(script_name):
    """Run a test script."""
    global _log_file
    script_path = SCRIPT_DIR / script_name
    
    if not script_path.exists():
        print(f"\nError: Script not found: {script_path}")
        return 1
    
    print(f"\nLaunching {script_name}...")
    print()
    
    # Thread function to read and log output
    def read_output(pipe, output_file):
        """Read from pipe and write to both console and log file."""
        try:
            for line in pipe:
                # Write to console
                sys.__stdout__.write(line)
                sys.__stdout__.flush()
                
                # Write to log file if active
                if output_file:
                    output_file.write(line)
                    output_file.flush()
        except:
            pass
    
    try:
        # Run the script with Python in unbuffered mode
        # Redirect stdout/stderr but keep stdin for interactive input
        process = subprocess.Popen(
            [sys.executable, '-u', str(script_path)],
            cwd=str(SCRIPT_DIR),
            stdin=sys.stdin,  # Allow interactive input
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=0,  # Unbuffered
            encoding='utf-8',
            errors='replace'
        )
        
        # Start thread to read output
        output_thread = threading.Thread(
            target=read_output, 
            args=(process.stdout, _log_file),
            daemon=True
        )
        output_thread.start()
        
        # Wait for process to complete
        returncode = process.wait()
        
        # Wait for output thread to finish
        output_thread.join(timeout=1.0)
        
        return returncode
        
    except KeyboardInterrupt:
        print("\n\nScript interrupted by user.")
        if process:
            process.terminate()
        return 1
    except Exception as e:
        print(f"\nError running script: {e}")
        return 1


def display_menu():
    """Display the main menu and get user selection."""
    global _logging_active
    config = get_config()
    
    print()
    print("=" * 70)
    print("DCC TESTER - MAIN MENU")
    print("=" * 70)
    print()
    print("Available Tests:")
    print()
    print("  1. Packet Acceptance Test")
    print("  2. Timing Margin Test")
    print("  3. Inter-Packet Acceptance Test")
    print("  4. Bad Bit Test")
    print("  5. Function I/O Test")
    print("  6. Accessory I/O Test")
    print("  7. Acceptance Test with Override")
    print("  8. Set Command Station Parameters")
    print()
    print("  C. View/Edit System Configuration")
    
    # Only show logging toggle if save_logs is enabled in config
    if config.save_logs:
        log_status = "ON" if _logging_active else "OFF"
        print(f"  L. Toggle File Logging (currently {log_status}, screen always on)")
    
    print("  Q. Quit")
    print()
    print("=" * 70)
    print()
    
    choice = input("Select test to run (1-8, C, L, Q): ").strip().upper()
    return choice


def main():
    """Main entry point."""
    global _logging_active
    
    try:
        print()
        print("=" * 70)
        print("DCC TESTER SYSTEM")
        print("=" * 70)
        print()
        
        # Load and display configuration
        config = get_config()
        config.display()
        
        # Initialize runtime logging state from config
        _logging_active = config.save_logs
        
        # Start logging if enabled
        start_logging()
        
        while True:
            choice = display_menu()
            
            if choice == "Q":
                print("\nExiting DCC Tester System.")
                print()
                break
            
            elif choice == "C":
                config.display()
                print()
                print(f"To change settings, edit: {CONFIG_FILE}")
                print()
                input("Press Enter to continue...")
                continue
            
            elif choice == "L":
                # Only allow toggle if save_logs is enabled in config
                if not config.save_logs:
                    print()
                    print("Logging toggle is disabled (save_logs=false in config).")
                    print(f"To enable, set save_logs=true in {CONFIG_FILE}")
                    print()
                    input("Press Enter to continue...")
                    continue
                
                # Toggle runtime logging state
                _logging_active = not _logging_active
                status = "enabled" if _logging_active else "disabled"
                print()
                print(f"File logging {status} (runtime only, config unchanged).")
                print("Note: Console/screen output is always displayed.")
                
                if _logging_active:
                    # Stop current logging and restart with new state
                    stop_logging(close_file=False)  # Pause, don't close
                    start_logging()
                else:
                    stop_logging(close_file=False)  # Pause, don't close
                
                print()
                input("Press Enter to continue...")
                continue
            
            elif choice == "1":
                run_script("RunPacketAcceptanceTest.py")
            
            elif choice == "2":
                run_script("RunTimingMarginTest.py")
            
            elif choice == "3":
                run_script("RunInterPacketAcceptanceTest.py")
            
            elif choice == "4":
                run_script("RunBadBitTest.py")
            
            elif choice == "5":
                run_script("RunFunctionIOTest.py")
            
            elif choice == "6":
                run_script("RunAccessoryIOTest.py")
            
            elif choice == "7":
                run_script("RunAcceptanceTestWithOverride.py")
            
            elif choice == "8":
                run_script("RunSetCommandStationParameters.py")
            
            else:
                print("\nInvalid selection. Please choose 1-8, C, L, or Q.")
                continue
            
            print()
            input("Press Enter to return to menu...")
        
        return 0
    
    finally:
        # Always close log file on exit
        stop_logging(close_file=True)


if __name__ == "__main__":
    sys.exit(main())
