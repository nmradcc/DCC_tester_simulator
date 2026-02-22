#!/usr/bin/env python3
"""
RunBadBitTest Script
====================

This script runs multiple iterations of the BadBitTest.

The test is configured via:
    - SystemConfig.txt (global settings: serial port, in-circuit motor, logging level)
    - RunBadBitTestConfig.txt (test-specific settings: address, delays, flip mask, etc.)

If any iteration fails, the test aborts immediately.
"""

import sys
import os
import serial
import importlib.util
import msvcrt

script_dir = os.path.dirname(os.path.abspath(__file__))

# Import system configuration
sys.path.insert(0, script_dir)
import System


def load_bad_bit_module(file_path, module_name):
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
        return int(str(value).strip(), 0)
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
        "flip_mask",
        "test_stop_delay",
        "wait_key_press",
    }

    missing = sorted(required_keys - set(config.keys()))
    if missing:
        raise ValueError(f"Missing required config keys: {', '.join(missing)}")

    return {
        "address": _parse_int(config.get("address"), "address"),
        "inter_packet_delay_ms": _parse_int(config.get("inter_packet_delay_ms"), "inter_packet_delay_ms"),
        "pass_count": _parse_int(config.get("pass_count"), "pass_count"),
        "stop_on_failure": _parse_bool(config.get("stop_on_failure"), "stop_on_failure"),
        "flip_mask": _parse_int(config.get("flip_mask"), "flip_mask"),
        "test_stop_delay": _parse_int(config.get("test_stop_delay"), "test_stop_delay"),
        "wait_key_press": _parse_bool(config.get("wait_key_press"), "wait_key_press"),
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
        System.capture_screen(prefix="bad_bit_test", interactive=True)
    elif key_char == 'q':
        log(1, "✓ 'q' pressed - quitting test...")
        raise KeyboardInterrupt("User requested early exit")
    else:
        log(1, "✓ Key pressed, continuing...")


def main():
    """Main entry point."""

    print("=" * 70)
    print("DCC Bad Bit Test Runner")
    print("=" * 70)
    print()
    print("This script will run multiple iterations of the Bad Bit Test.")
    print()
    print("If any iteration fails, the test will continue unless stop on failure is enabled.")
    print()

    config_path = os.path.join(script_dir, "RunBadBitTestConfig.txt")
    try:
        config = load_test_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}")
        print("Please update RunBadBitTestConfig.txt with valid values.")
        return 1

    # Get system-level configuration
    sys_config = System.get_config()

    address = config["address"]
    delay_ms = config["inter_packet_delay_ms"]
    pass_count = config["pass_count"]
    stop_on_failure = config["stop_on_failure"]
    flip_mask = config["flip_mask"]
    test_stop_delay = config["test_stop_delay"]
    wait_key_press = config["wait_key_press"]
    
    # Get system-level settings
    logging_level = sys_config.logging_level
    port = sys_config.serial_port
    in_circuit_motor = sys_config.in_circuit_motor

    packet_module_path = os.path.join(script_dir, "PacketData", "BadBitTest.py")

    packet_module = load_bad_bit_module(
        packet_module_path,
        "bad_bit_test",
    )

    DCCTesterRPC = packet_module.DCCTesterRPC
    run_bad_bit_test = packet_module.run_bad_bit_test
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
    log(1, f"  Flip mask:          0x{flip_mask:08X}")
    log(1, f"  Stop on failure:    {stop_on_failure}")
    log(1, f"  Wait key press:     {wait_key_press}")
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

        passed_count = 0
        failed_count = 0

        for i in range(1, pass_count + 1):
            log(2, "")
            log(2, "=" * 70)
            log(2, f"Test Pass {i} of {pass_count}")
            log(2, "=" * 70)
            log(2, "")

            log(1, f"Step A: Running baseline test (flip_mask=0)")
            result_nominal = run_bad_bit_test(
                rpc,
                address,
                delay_ms,
                logging_level=logging_level,
                in_circuit_motor=in_circuit_motor,
                flip_mask=0,
                test_stop_delay_ms=test_stop_delay,
            )

            if result_nominal.get("status") != "PASS":
                failed_count += 1
                log(1, "")
                log(1, f"✗ Pass {i}/{pass_count} FAILED (baseline)")
                log(1, f"Error: {result_nominal.get('error', 'Unknown error')}")
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
                continue

            if flip_mask == 0:
                log(1, "Flip mask is 0; testing all 32 bits")
                all_bits_ok = True
                for bit_index in range(32):
                    bit_mask = 0x80000000 >> bit_index
                    log(1, f"Step A: Baseline test for mask 0x{bit_mask:08X}")
                    result_nominal = run_bad_bit_test(
                        rpc,
                        address,
                        delay_ms,
                        logging_level=logging_level,
                        in_circuit_motor=in_circuit_motor,
                        flip_mask=0,
                        test_stop_delay_ms=test_stop_delay,
                    )

                    if result_nominal.get("status") != "PASS":
                        failed_count += 1
                        all_bits_ok = False
                        log(1, "")
                        log(1, f"✗ Pass {i}/{pass_count} FAILED (baseline)")
                        log(1, f"Error: {result_nominal.get('error', 'Unknown error')}")
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
                        break

                    if wait_key_press:
                        log(1, "")
                        wait_for_key_press(rpc, log)

                    log(1, f"Step B: Running bad-bit test (flip_mask=0x{bit_mask:08X})")
                    result_bad = run_bad_bit_test(
                        rpc,
                        address,
                        delay_ms,
                        logging_level=logging_level,
                        in_circuit_motor=in_circuit_motor,
                        flip_mask=bit_mask,
                        test_stop_delay_ms=test_stop_delay,
                    )

                    if result_bad.get("status") == "PASS":
                        failed_count += 1
                        all_bits_ok = False
                        log(1, "")
                        log(1, f"✗ Pass {i}/{pass_count} FAILED (bad-bit accepted)")
                        log(1, f"Error: Bad-bit test unexpectedly passed for 0x{bit_mask:08X}")
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
                        break

                    # Wait for key press before next bit (after Step B completes)
                    if wait_key_press and bit_index < 31:
                        log(1, "")
                        wait_for_key_press(rpc, log)

                if all_bits_ok:
                    passed_count += 1
                    log(1, f"✓ Pass {i}/{pass_count} completed successfully (all 32 bits)")
                    if wait_key_press and i < pass_count:
                        log(1, "")
                        wait_for_key_press(rpc, log)
                continue

            if wait_key_press:
                log(1, "")
                wait_for_key_press(rpc, log)

            log(1, f"Step B: Running bad-bit test (flip_mask=0x{flip_mask:08X})")
            result_bad = run_bad_bit_test(
                rpc,
                address,
                delay_ms,
                logging_level=logging_level,
                in_circuit_motor=in_circuit_motor,
                flip_mask=flip_mask,
                test_stop_delay_ms=test_stop_delay,
            )

            if result_bad.get("status") != "PASS":
                passed_count += 1
                log(1, f"✓ Pass {i}/{pass_count} completed successfully")
            else:
                failed_count += 1
                log(1, "")
                log(1, f"✗ Pass {i}/{pass_count} FAILED (bad-bit accepted)")
                log(1, "Error: Bad-bit test unexpectedly passed")
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

            # Wait for key press after Step B
            if wait_key_press:
                log(1, "")
                wait_for_key_press(rpc, log)

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
