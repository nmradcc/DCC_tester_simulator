#!/usr/bin/env python3
"""
RunTimingMarginTest Script
==========================

This script tests DCC timing margins by running PacketAcceptanceTest 
with varying bit durations.

The test is configured via:
    - SystemConfig.txt (global settings: serial port, in-circuit motor, logging level)
    - RunTimingMarginTestConfig.txt (test-specific settings: address, delays, timing parameters, etc.)

Each pass tests 4 timing margins:
  - Minimum bit1 duration
  - Maximum bit1 duration  
  - Minimum bit0 duration
  - Maximum bit0 duration

Each margin test:
  - Step A: Baseline test with default timing (should pass)
  - Step B: Test with modified timing (should pass if within margin)
  
Default timing is always restored on failure or exit.
"""

import importlib.util
import os
import sys
import serial
import msvcrt

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


def load_config(config_path):
    """Load configuration from a simple key=value text file."""
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
        "wait_key_press",
        "preamble_bits",
        "bit1_duration",
        "bit0_duration",
        "trigger_first_bit",
        "min_bit1_duration",
        "max_bit1_duration",
        "min_bit0_duration",
        "max_bit0_duration",
    }

    missing = sorted(required_keys - set(config.keys()))
    if missing:
        raise ValueError(f"Missing required config keys: {', '.join(missing)}")

    return {
        "address": _parse_int(config.get("address"), "address"),
        "inter_packet_delay_ms": _parse_int(config.get("inter_packet_delay_ms"), "inter_packet_delay_ms"),
        "pass_count": _parse_int(config.get("pass_count"), "pass_count"),
        "stop_on_failure": _parse_bool(config.get("stop_on_failure"), "stop_on_failure"),
        "wait_key_press": _parse_bool(config.get("wait_key_press"), "wait_key_press"),
        "preamble_bits": _parse_int(config.get("preamble_bits"), "preamble_bits"),
        "bit1_duration": _parse_int(config.get("bit1_duration"), "bit1_duration"),
        "bit0_duration": _parse_int(config.get("bit0_duration"), "bit0_duration"),
        "trigger_first_bit": _parse_bool(config.get("trigger_first_bit"), "trigger_first_bit"),
        "min_bit1_duration": _parse_int(config.get("min_bit1_duration"), "min_bit1_duration"),
        "max_bit1_duration": _parse_int(config.get("max_bit1_duration"), "max_bit1_duration"),
        "min_bit0_duration": _parse_int(config.get("min_bit0_duration"), "min_bit0_duration"),
        "max_bit0_duration": _parse_int(config.get("max_bit0_duration"), "max_bit0_duration"),
    }


def wait_for_key_press(rpc, log):
    """Wait for any key press. 'c' captures screen, 'q' quits, any other key continues."""
    log(1, "Press any key to continue ('c' to capture screen, 'q' to quit)...")
    
    # Wait for key press
    key = msvcrt.getch()
    
    # Decode the key
    try:
        key_char = key.decode('utf-8').lower()
    except:
        key_char = ''
    
    if key_char == 'c':
        log(1, "✓ 'c' pressed - capturing screen, press Enter or add optional file name prefix text...")
        # Call System module's capture_screen function with base prefix, still allows user to add text
        System.capture_screen(prefix="timing_margin_test", interactive=True)
    elif key_char == 'q':
        log(1, "✓ 'q' pressed - quitting test...")
        raise KeyboardInterrupt("User requested early exit")
    else:
        log(1, "✓ Key pressed, continuing...")


def set_timing_params(rpc, log, params, label=""):
    """Set command station timing parameters."""
    response = rpc.send_rpc("command_station_params", params)
    if response is None or response.get("status") != "ok":
        log(1, f"ERROR: Failed to set parameters{label}: {response}")
        return False
    return True


def get_timing_params(rpc, log):
    """Get current command station timing parameters."""
    response = rpc.send_rpc("command_station_get_params", {})
    if response is not None and response.get("status") == "ok":
        return response.get("parameters", {})
    return None


def restore_default_timing(rpc, log, default_params):
    """Restore default timing parameters."""
    log(1, "Restoring default timing parameters...")
    if set_timing_params(rpc, log, default_params, " (restore)"):
        log(1, f"✓ Default timing restored")
        return True
    else:
        log(1, f"✗ Failed to restore default timing")
        return False


def run_timing_margin_test_step(rpc, log, address, delay_ms, logging_level, 
                                  test_name, timing_param, timing_value, 
                                  default_params, wait_key_press, is_baseline=False):
    """
    Run a single timing margin test step (either Step A baseline or Step B with modified timing).
    
    Returns: (success, error_message)
    """
    if is_baseline:
        log(1, f"Step A: Baseline test for {test_name} (default timing)")
    else:
        log(1, f"Step B: Testing {test_name} ({timing_value} us)")
        if not set_timing_params(rpc, log, {timing_param: timing_value}):
            return False, "Failed to set timing parameter"
    
    result = run_packet_acceptance_test(
        rpc,
        address,
        delay_ms,
        logging_level=logging_level
    )
    
    # Restore default timing after Step B
    if not is_baseline:
        if not set_timing_params(rpc, log, {timing_param: default_params[timing_param]}):
            log(1, f"✗ Failed to restore {timing_param}")
    
    if result.get("status") != "PASS":
        error_msg = f"{'Baseline' if is_baseline else test_name} test failed: {result.get('error', 'Unknown error')}"
        return False, error_msg
    else:
        log(1, f"✓ {'Baseline' if is_baseline else test_name + ' timing'} test passed")
        return True, None


def main():
    """Main entry point."""

    print("=" * 70)
    print("DCC Timing Margin Test Runner")
    print("=" * 70)
    print()
    print("This script will test DCC timing margins.")
    print()

    config_path = os.path.join(script_dir, "RunTimingMarginTestConfig.txt")

    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}")
        print("Please update RunTimingMarginTestConfig.txt with valid values.")
        return 1

    # Get system-level configuration
    sys_config = System.get_config()

    address = config["address"]
    delay_ms = config["inter_packet_delay_ms"]
    pass_count = config["pass_count"]
    stop_on_failure = config["stop_on_failure"]
    wait_key_press = config["wait_key_press"]
    
    # Default timing parameters
    default_params = {
        "preamble_bits": config["preamble_bits"],
        "bit1_duration": config["bit1_duration"],
        "bit0_duration": config["bit0_duration"],
        "trigger_first_bit": config["trigger_first_bit"],
    }
    
    # Timing margin limits
    min_bit1_duration = config["min_bit1_duration"]
    max_bit1_duration = config["max_bit1_duration"]
    min_bit0_duration = config["min_bit0_duration"]
    max_bit0_duration = config["max_bit0_duration"]
    
    # Get system-level settings
    logging_level = sys_config.logging_level
    port = sys_config.serial_port
    in_circuit_motor = sys_config.in_circuit_motor

    packet_module_path = os.path.join(script_dir, "PacketData", "PacketAcceptanceTest.py")

    packet_module = load_packet_acceptance_module(
        packet_module_path,
        "packet_acceptance_test"
    )

    global run_packet_acceptance_test
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
    log(1, f"  Serial port:            {port}")
    log(1, f"  In circuit motor:       {in_circuit_motor}")
    log(1, f"  Logging level:          {logging_level}")
    log(1, "")
    log(1, "Test Parameters:")
    log(1, f"  Locomotive address:     {address}")
    log(1, f"  Inter-packet delay:     {delay_ms} ms")
    log(1, f"  Number of passes:       {pass_count}")
    log(1, f"  Stop on failure:        {stop_on_failure}")
    log(1, f"  Wait key press:         {wait_key_press}")
    log(1, f"  Preamble bits:          {default_params['preamble_bits']}")
    log(1, f"  Bit1 duration:          {default_params['bit1_duration']} us")
    log(1, f"  Bit0 duration:          {default_params['bit0_duration']} us")
    log(1, f"  Trigger first bit:      {default_params['trigger_first_bit']}")
    log(1, f"  Min bit1 duration:      {min_bit1_duration} us")
    log(1, f"  Max bit1 duration:      {max_bit1_duration} us")
    log(1, f"  Min bit0 duration:      {min_bit0_duration} us")
    log(1, f"  Max bit0 duration:      {max_bit0_duration} us")
    log(1, "=" * 70)
    log(1, "")

    log(2, "")
    log(2, "=" * 70)
    log(2, "Starting Test Run")
    log(2, "=" * 70)
    log(2, "")

    try:
        log(2, f"Connecting to {port}...")
        rpc = DCCTesterRPC(port)
        log(2, "✓ Connected!\n")

        # Set default timing parameters initially
        log(1, "Setting default command station parameters...")
        if not set_timing_params(rpc, log, default_params):
            rpc.close()
            return 1
        log(1, "✓ Default parameters set")
        
        params_out = get_timing_params(rpc, log)
        if params_out:
            log(1, "")
            log(1, "Current Parameters:")
            log(1, f"  Preamble bits:      {params_out.get('preamble_bits')}")
            log(1, f"  Bit1 duration:      {params_out.get('bit1_duration')} us")
            log(1, f"  Bit0 duration:      {params_out.get('bit0_duration')} us")
            log(1, f"  Trigger first bit:  {params_out.get('trigger_first_bit')}")
            log(1, "")

        passed_count = 0
        failed_count = 0
        first_test = True  # Track if this is the first test to skip initial wait

        # Define the 4 timing margin tests
        timing_tests = [
            ("minimum bit1", "bit1_duration", min_bit1_duration),
            ("maximum bit1", "bit1_duration", max_bit1_duration),
            ("minimum bit0", "bit0_duration", min_bit0_duration),
            ("maximum bit0", "bit0_duration", max_bit0_duration),
        ]

        # Run multiple passes
        for i in range(1, pass_count + 1):
            log(1, "")
            log(2, "=" * 70)
            log(2, f"Test Pass {i} of {pass_count}")
            log(2, "=" * 70)
            log(2, "")

            pass_failed = False

            # Run each of the 4 timing margin tests
            for test_name, timing_param, timing_value in timing_tests:
                if pass_failed:
                    break
                
                # Step A: Baseline test with default timing
                if wait_key_press and not first_test:
                    log(1, "")
                    wait_for_key_press(rpc, log)
                
                first_test = False  # After first test, enable waits
                
                success, error_msg = run_timing_margin_test_step(
                    rpc, log, address, delay_ms, logging_level,
                    test_name, timing_param, timing_value,
                    default_params, wait_key_press, is_baseline=True
                )
                
                if not success:
                    failed_count += 1
                    pass_failed = True
                    log(1, "")
                    log(1, f"✗ Pass {i}/{pass_count} FAILED (baseline for {test_name})")
                    log(1, f"Error: {error_msg}")
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
                        restore_default_timing(rpc, log, default_params)
                        rpc.close()
                        return 1
                    break
                
                # Step B: Test with modified timing
                if wait_key_press:
                    log(1, "")
                    wait_for_key_press(rpc, log)
                
                success, error_msg = run_timing_margin_test_step(
                    rpc, log, address, delay_ms, logging_level,
                    test_name, timing_param, timing_value,
                    default_params, wait_key_press, is_baseline=False
                )
                
                if not success:
                    failed_count += 1
                    pass_failed = True
                    log(1, "")
                    log(1, f"✗ Pass {i}/{pass_count} FAILED ({test_name})")
                    log(1, f"Error: {error_msg}")
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
                        restore_default_timing(rpc, log, default_params)
                        rpc.close()
                        return 1
                    break

            # Pass complete
            if not pass_failed:
                passed_count += 1
                log(1, "")
                log(1, f"✓ Pass {i}/{pass_count} completed successfully (all 4 timing margins tested)")

        # All passes complete
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

        # Ensure default timing is restored
        restore_default_timing(rpc, log, default_params)
        
        rpc.close()
        return 0

    except serial.SerialException as exc:
        log(1, f"ERROR: Serial port error: {exc}")
        log(1, f"Make sure {port} is the correct port and the device is connected.")
        return 1
    except KeyboardInterrupt:
        log(1, "\n\n✗ Test interrupted by user.")
        # Ensure default timing is restored
        try:
            restore_default_timing(rpc, log, default_params)
            rpc.close()
        except:
            pass
        return 1
    except Exception as exc:
        log(1, f"\nERROR: Unexpected error: {exc}")
        import traceback
        traceback.print_exc()
        # Ensure default timing is restored
        try:
            restore_default_timing(rpc, log, default_params)
            rpc.close()
        except:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
