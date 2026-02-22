#!/usr/bin/env python3
"""
RunPacketAcceptanceTest Script
===============================

This script runs multiple iterations of the PacketAcceptanceTest
to verify NEM 671 inter-packet delay requirements.

The test is configured via:
    - SystemConfig.txt (global settings: serial port, in-circuit motor, logging level)
    - RunPacketAcceptanceTestConfig.txt (test-specific settings: address, delays, etc.)

If any iteration fails, the test aborts immediately.
"""

import sys
import os
import serial
import importlib.util

script_dir = os.path.dirname(os.path.abspath(__file__))

# Import system configuration
sys.path.insert(0, script_dir)
import System

def load_packet_acceptance_module(file_path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module from {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parse_bool(value, key):
    if isinstance(value, bool):
        return value
    if value is None:
        raise ValueError(f"Missing boolean value for '{key}'")
    normalized = str(value).strip().lower()
    if normalized in {"y", "yes", "true", "1"}:
        return True
    if normalized in {"n", "no", "false", "0"}:
        return False
    raise ValueError(f"Invalid boolean value for '{key}': {value}")


def _parse_int(value, key):
    if value is None or str(value).strip() == "":
        raise ValueError(f"Missing integer value for '{key}'")
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"Invalid integer value for '{key}': {value}") from exc


def load_test_config(config_path):
    """Load test configuration from a simple key=value text file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    config = {}
    with open(config_path, "r", encoding="utf-8") as config_file:
        for raw_line in config_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            if "=" not in line:
                raise ValueError(f"Invalid config line (expected key=value): {raw_line.strip()}")
            key, value = line.split("=", 1)
            config[key.strip()] = value.strip()

    required_keys = {
        "address",
        "inter_packet_delay_ms",
        "pass_count",
        "stop_on_failure",
        "test_stop_delay",
    }

    missing = sorted(required_keys - set(config.keys()))
    if missing:
        raise ValueError(f"Missing required config keys: {', '.join(missing)}")

    return {
        "address": _parse_int(config.get("address"), "address"),
        "inter_packet_delay_ms": _parse_int(config.get("inter_packet_delay_ms"), "inter_packet_delay_ms"),
        "pass_count": _parse_int(config.get("pass_count"), "pass_count"),
        "stop_on_failure": _parse_bool(config.get("stop_on_failure"), "stop_on_failure"),
        "test_stop_delay": _parse_int(config.get("test_stop_delay"), "test_stop_delay"),
    }


def main():
    """Main entry point."""
    
    print("=" * 70)
    print("DCC Packet Acceptance Test Runner")
    print("NEM 671 Compliance Testing")
    print("=" * 70)
    print()
    print("This script will run multiple iterations of the Packet Acceptance")
    print("test to verify NEM 671 compliance.")
    print()
    print("If any iteration fails, the test will continue unless stop on failure is enabled.")
    print()
    
    config_path = os.path.join(script_dir, "RunPacketAcceptanceTestConfig.txt")
    try:
        config = load_test_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}")
        print("Please update RunPacketAcceptanceTestConfig.txt with valid values.")
        return 1

    address = config["address"]
    delay_ms = config["inter_packet_delay_ms"]
    pass_count = config["pass_count"]
    stop_on_failure = config["stop_on_failure"]
    test_stop_delay = config["test_stop_delay"]
    
    # Get system-level configuration
    sys_config = System.get_config()
    logging_level = sys_config.logging_level
    port = sys_config.serial_port
    in_circuit_motor = sys_config.in_circuit_motor
    
    packet_module_path = os.path.join(script_dir, "PacketData", "PacketAcceptanceTest.py")

    packet_module = load_packet_acceptance_module(
        packet_module_path,
        "packet_acceptance"
    )

    DCCTesterRPC = packet_module.DCCTesterRPC
    run_packet_acceptance_test = packet_module.run_packet_acceptance_test
    log = packet_module.log
    set_log_level = packet_module.set_log_level

    set_log_level(logging_level)

    log(1, "")
    log(1, "=" * 70)
    log(1, "Configuration Summary:")
    log(1, "=" * 70)
    log(1, "System Parameters:")
    log(1, f"  Serial port:        {port}")
    log(1, f"  In circuit motor:   {in_circuit_motor}")
    log(1, f"  Logging level:      {logging_level}")
    log(1, "")
    log(1, "Test Parameters:")
    log(1, f"  Locomotive address: {address}")
    log(1, f"  Inter-packet delay: {delay_ms} ms")
    log(1, f"  Test stop delay:    {test_stop_delay} ms")
    log(1, f"  Number of passes:   {pass_count}")
    log(1, f"  Stop on failure:    {stop_on_failure}")
    log(1, "=" * 70)
    log(1, "")
    
    log(2, "")
    log(2, "=" * 70)
    log(2, "Starting Test Run")
    log(2, "=" * 70)
    log(2, "")
    
    try:
        # Connect to DCC_tester
        log(2, f"Connecting to {port}...")
        rpc = DCCTesterRPC(port)
        log(2, "✓ Connected!\n")
        
        # Run test iterations
        passed_count = 0
        failed_count = 0
        
        for i in range(1, pass_count + 1):
            log(2, "")
            log(2, "=" * 70)
            log(2, f"Test Pass {i} of {pass_count}")
            log(2, "=" * 70)
            log(2, "")
            
            # Run the test
            result = run_packet_acceptance_test(
                rpc,
                address,
                delay_ms,
                logging_level=logging_level,
                in_circuit_motor=in_circuit_motor,
                test_stop_delay_ms=test_stop_delay,
            )
            
            if result.get("status") == "PASS":
                passed_count += 1
                log(1, f"✓ Pass {i}/{pass_count} completed successfully")
            else:
                failed_count += 1
                log(1, "")
                log(1, f"✗ Pass {i}/{pass_count} FAILED")
                log(1, f"Error: {result.get('error', 'Unknown error')}")
                if stop_on_failure:
                    log(1, "")
                    log(1, "=" * 70)
                    log(1, "TEST ABORTED DUE TO FAILURE")
                    log(1, "=" * 70)
                    log(1, "\nResults Summary:")
                    log(1, f"  Total passes run: {i}")
                    log(1, f"  Passed: {passed_count}")
                    log(1, f"  Failed: {failed_count}")
                    log(1, "")
                    rpc.close()
                    return 1
        
        # All tests passed
        log(1, "")
        log(1, "=" * 70)
        log(1, "ALL TESTS COMPLETED SUCCESSFULLY")
        log(1, "=" * 70)
        log(1, "\nResults Summary:")
        log(1, f"  Total passes: {pass_count}")
        log(1, f"  Passed: {passed_count}")
        log(1, f"  Failed: {failed_count}")
        log(1, "  Success rate: 100%")
        log(1, "")
        log(1, f"✓ All {pass_count} test passes completed with {delay_ms}ms inter-packet delay")
        log(1, "")
        
        # Close connection
        rpc.close()
        return 0
        
    except serial.SerialException as e:
        log(1, f"\nERROR: Serial port error: {e}")
        log(1, f"Make sure {port} is the correct port and the device is connected.")
        return 1
    except KeyboardInterrupt:
        log(1, "\n\nTest interrupted by user.")
        log(1, "")
        log(1, "=" * 70)
        log(1, "Results Summary (Partial):")
        log(1, "=" * 70)
        log(1, f"  Completed passes: {passed_count + failed_count}")
        log(1, f"  Passed: {passed_count}")
        log(1, f"  Failed: {failed_count}")
        log(1, "")
        return 1
    except Exception as e:
        log(1, f"\nERROR: Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
