#!/usr/bin/env python3
"""
FunctionIOTest Script
=====================

This script tests inter-packet delay timing for locomotive function IO control.
Implements Function Group 1 (F1-F4) packets.
"""

import json
import serial
import time
from datetime import datetime


LOG_LEVEL = 1  # 0 = none, 1 = minimum, 2 = verbose


def set_log_level(level):
    """Set global logging level (0=none, 1=minimum, 2=verbose)."""
    global LOG_LEVEL
    try:
        level_int = int(level)
    except (TypeError, ValueError):
        level_int = 1
    LOG_LEVEL = max(0, min(2, level_int))


def log(level, message):
    if LOG_LEVEL >= level:
        if LOG_LEVEL == 2:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] {message}")
        else:
            print(message)


class DCCTesterRPC:
    """RPC client for DCC_tester command station."""

    def __init__(self, port, baudrate=115200, timeout=2):
        self.ser = serial.Serial(port, baudrate, timeout=timeout)
        time.sleep(0.5)

    def send_rpc(self, method, params):
        request = {
            "method": method,
            "params": params
        }

        request_json = json.dumps(request) + '\r\n'
        log(2, f"→ {request_json.strip()}")
        self.ser.write(request_json.encode('utf-8'))

        response_line = self.ser.readline().decode('utf-8').strip()
        log(2, f"← {response_line}")

        if response_line:
            return json.loads(response_line)
        return None

    def close(self):
        self.ser.close()


def calculate_dcc_checksum(bytes_list):
    """Calculate DCC packet checksum (XOR of all bytes)."""
    checksum = 0
    for byte in bytes_list:
        checksum ^= byte
    return checksum


def _validate_function_params(address, function_number):
    if not 1 <= function_number <= 4:
        raise ValueError("function_number must be between 1 and 4 (F1-F4)")
    if not 1 <= address <= 127:
        raise ValueError("address must be between 1 and 127 for short addresses")


def _function_group1_mask(function_number):
    # Function Group 1: 0x80 + F1..F4 bits
    return {
        1: 0x01,  # F1
        2: 0x02,  # F2
        3: 0x04,  # F3
        4: 0x08,  # F4
    }[function_number]


def make_function_on_packet(address, function_number):
    """Create a Function Group 1 packet turning a single function ON."""
    _validate_function_params(address, function_number)
    instruction = 0x80 | _function_group1_mask(function_number)
    packet = [address, instruction]
    checksum = calculate_dcc_checksum(packet)
    packet.append(checksum)

    log(2, f"Function ON packet for address {address}, F{function_number}:")
    log(2, f"  Bytes: {' '.join(f'0x{b:02X}' for b in packet)}")
    log(2, f"  Instruction: 0x{instruction:02X} (Group 1, F{function_number}=ON)")
    log(2, f"  Checksum:    0x{checksum:02X}\n")
    return packet


def make_function_off_packet(address, function_number):
    """Create a Function Group 1 packet turning a single function OFF."""
    _validate_function_params(address, function_number)
    instruction = 0x80  # Group 1 with all functions off
    packet = [address, instruction]
    checksum = calculate_dcc_checksum(packet)
    packet.append(checksum)

    log(2, f"Function OFF packet for address {address}, F{function_number}:")
    log(2, f"  Bytes: {' '.join(f'0x{b:02X}' for b in packet)}")
    log(2, f"  Instruction: 0x{instruction:02X} (Group 1, F{function_number}=OFF)")
    log(2, f"  Checksum:    0x{checksum:02X}\n")
    return packet


def read_function_io_state(rpc, function_number):
    """
    Read the IO state for a given function number.

    F1 reads IO1, F2 reads IO2, etc.
    Returns True if LOW, False if HIGH, or None on error.
    """
    response = rpc.send_rpc("get_gpio_inputs", {})
    if response is None or response.get("status") != "ok":
        log(1, f"ERROR: Failed to read GPIO inputs: {response}")
        return None

    gpio_word = response.get("value")
    if gpio_word is None:
        log(1, f"ERROR: Missing GPIO value in response: {response}")
        return None

    bit_index = function_number - 1
    io_high = (gpio_word & (1 << bit_index)) != 0
    log(2, f"GPIO inputs: 0x{gpio_word:04X} (IO{function_number}={'HIGH' if io_high else 'LOW'})")
    return not io_high


def run_function_io_test(rpc, loco_address, function_number, inter_packet_delay_ms=1000, logging_level=1):
    """Run the Function IO test for F1-F4."""
    set_log_level(logging_level)

    log(2, "=" * 70)
    log(2, "DCC Function IO Test (F1-F4)")
    log(2, f"Function number: F{function_number}")
    log(2, f"Inter-packet delay: {inter_packet_delay_ms} ms")
    log(2, "=" * 70)
    log(2, "")

    try:
        # Step 1: Start command station in custom packet mode (loop=0)
        log(1, "Step 1: Starting command station in custom packet mode")
        response = rpc.send_rpc("command_station_start", {"loop": 0})

        if response is None or response.get("status") != "ok":
            log(1, f"ERROR: Failed to start command station: {response}")
            return {"status": "FAIL", "error": "Failed to start command station"}
        log(2, f"✓ Command station started (loop={response.get('loop', 0)})\n")

        time.sleep(0.5)

        # Step 2: Create Function ON packet
        log(1, f"Step 2: Creating Function ON packet for F{function_number}...")
        func_on_packet = make_function_on_packet(loco_address, function_number)

        # Step 3: Load and transmit the Function ON packet
        log(1, "Step 3: Loading and transmitting Function ON packet...")
        response = rpc.send_rpc("command_station_load_packet", {"bytes": func_on_packet})

        if response is None or response.get("status") != "ok":
            log(1, f"ERROR: Failed to load Function ON packet: {response}")
            rpc.close()
            return {"status": "FAIL", "error": "Failed to load Function ON packet"}

        response = rpc.send_rpc("command_station_transmit_packet",
                               {"count": 1, "delay_ms": 0})

        if response is None or response.get("status") != "ok":
            log(1, f"ERROR: Failed to transmit Function ON packet: {response}")
            rpc.close()
            return {"status": "FAIL", "error": "Failed to transmit Function ON packet"}

        # Step 4: Read Function IO state after ON
        log(1, f"Step 4: Reading IO{function_number} after Function ON transmit...")
        func_on_state = read_function_io_state(rpc, function_number)
        if func_on_state is None:
            rpc.close()
            return {"status": "FAIL", "error": "Failed to read Function IO state (ON)"}
        func_on_ok = func_on_state is True
        log(1, f"✓ Function ON IO state: {func_on_ok} (IO{function_number}={'LOW' if func_on_state else 'HIGH'})")

        # Step 5: Wait for inter-packet delay
        log(1, f"Step 5: Waiting {inter_packet_delay_ms} ms (inter-packet delay)...")
        time.sleep(inter_packet_delay_ms / 1000.0)
        log(2, "✓ Inter-packet delay complete\n")

        # Step 6: Create Function OFF packet
        log(1, f"Step 6: Creating Function OFF packet for F{function_number}...")
        func_off_packet = make_function_off_packet(loco_address, function_number)

        # Step 7: Load and transmit the Function OFF packet
        log(1, "Step 7: Loading and transmitting Function OFF packet...")
        response = rpc.send_rpc("command_station_load_packet", {"bytes": func_off_packet})

        if response is None or response.get("status") != "ok":
            log(1, f"ERROR: Failed to load Function OFF packet: {response}")
            rpc.close()
            return {"status": "FAIL", "error": "Failed to load Function OFF packet"}

        response = rpc.send_rpc("command_station_transmit_packet",
                               {"count": 1, "delay_ms": 0})

        if response is None or response.get("status") != "ok":
            log(1, f"ERROR: Failed to transmit Function OFF packet: {response}")
            rpc.close()
            return {"status": "FAIL", "error": "Failed to transmit Function OFF packet"}

        # Step 8: Read Function IO state after OFF
        log(1, f"Step 8: Reading IO{function_number} after Function OFF transmit...")
        func_off_state = read_function_io_state(rpc, function_number)
        if func_off_state is None:
            rpc.close()
            return {"status": "FAIL", "error": "Failed to read Function IO state (OFF)"}
        func_off_ok = func_off_state is False
        log(1, f"✓ Function OFF IO state: {func_off_ok} (IO{function_number}={'LOW' if func_off_state else 'HIGH'})")

        # Step 9: Stop command station
        log(1, "Step 9: Stopping command station")
        response = rpc.send_rpc("command_station_stop", {})

        if response is None or response.get("status") != "ok":
            log(1, f"WARNING: Failed to stop command station: {response}")
        else:
            log(2, "✓ Command station stopped\n")

        test_pass = func_on_ok and func_off_ok

        log(2, "\n" + "=" * 70)
        log(2, "✓ TEST COMPLETE")
        log(2, "=" * 70)
        if test_pass:
            log(2, "✓ TEST PASS")
        else:
            log(2, "✗ TEST FAIL")
        log(2, "=" * 70)
        log(2, "\nTest Parameters:")
        log(2, f"  Locomotive address:    {loco_address}")
        log(2, f"  Function number:       F{function_number}")
        log(2, f"  Inter-packet delay:    {inter_packet_delay_ms} ms")
        log(2, "\nTest sequence completed:")
        log(2, "  1. Started command station in custom packet mode")
        log(2, f"  2. Created Function ON packet for F{function_number}")
        log(2, f"  3. Transmitted Function ON packet to address {loco_address}")
        log(2, f"  4. Read IO{function_number} after Function ON: {func_on_ok}")
        log(2, f"  5. Waited {inter_packet_delay_ms} ms (inter-packet delay)")
        log(2, f"  6. Created Function OFF packet for F{function_number}")
        log(2, f"  7. Transmitted Function OFF packet to address {loco_address}")
        log(2, f"  8. Read IO{function_number} after Function OFF: {func_off_ok}")
        log(2, "  9. Stopped command station")
        log(2, "\nIO state measurements:")
        log(2, f"  Function ON IO match:  {func_on_ok}")
        log(2, f"  Function OFF IO match: {func_off_ok}")
        log(2, "\nPass Criteria:")
        log(2, "  Function ON read is HIGH and Function OFF read is LOW")
        log(1, "")

        return {
            "status": "PASS" if test_pass else "FAIL",
            "inter_packet_delay_ms": inter_packet_delay_ms,
            "function_on_ok": func_on_ok,
            "function_off_ok": func_off_ok,
        }

    except serial.SerialException as e:
        log(1, f"\nERROR: Serial port error: {e}")
        return {"status": "FAIL", "error": f"Serial port error: {e}"}
    except KeyboardInterrupt:
        log(1, "\n\nTest interrupted by user.")
        return {"status": "FAIL", "error": "Test interrupted by user"}
    except Exception as e:
        log(1, f"\nERROR: Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "FAIL", "error": f"Unexpected error: {e}"}
