#!/usr/bin/env python3
"""
PacketAcceptanceTest Script
===========================

This script tests the inter-packet delay timing as described in NEM 671,
which specifies a minimum of 5ms between two data packets.

Test: Send motor start command, wait with configurable delay, then send
    emergency stop command while reading IO13/IO14 to verify response.

The inter_packet_delay_ms parameter can be adjusted for stress testing.
"""

import json
import serial
import time
import sys
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
        """
        Initialize RPC client.

        Args:
            port: Serial port (e.g., 'COM3' on Windows or '/dev/ttyACM0' on Linux)
            baudrate: Serial baud rate (default: 115200)
            timeout: Serial timeout in seconds (default: 2)
        """
        self.ser = serial.Serial(port, baudrate, timeout=timeout)
        time.sleep(0.5)  # Allow time for connection to establish

    def send_rpc(self, method, params):
        """
        Send an RPC request and return the response.

        Args:
            method: RPC method name
            params: Dictionary of parameters

        Returns:
            Response dictionary
        """
        request = {
            "method": method,
            "params": params
        }

        request_json = json.dumps(request) + '\r\n'
        log(2, f"→ {request_json.strip()}")

        self.ser.write(request_json.encode('utf-8'))

        # Read response
        response_line = self.ser.readline().decode('utf-8').strip()
        log(2, f"← {response_line}")

        if response_line:
            return json.loads(response_line)
        return None

    def close(self):
        """Close serial connection."""
        self.ser.close()


def calculate_dcc_checksum(bytes_list):
    """
    Calculate DCC packet checksum (XOR of all bytes).

    Args:
        bytes_list: List of packet bytes (address + instruction)

    Returns:
        Checksum byte
    """
    checksum = 0
    for byte in bytes_list:
        checksum ^= byte
    return checksum


def make_aux_io_packet(address, function_mask):
    """
    Create a DCC function group packet to control F0-F4.

    Args:
        address: Locomotive address (0-127 for short address)
        function_mask: Bitmask for F0-F4 (bit0=F0, bit1=F1, bit2=F2, bit3=F3, bit4=F4)

    Returns:
        List of packet bytes
    """
    function_state = int(function_mask) & 0x1F

    # Function group 1 encoding: 100 F4 F3 F2 F1 with F0 in bit 4
    instruction = 0x80 | ((function_state & 0x01) << 4) | ((function_state & 0x1E) >> 1)

    packet = [address, instruction]
    checksum = calculate_dcc_checksum(packet)
    packet.append(checksum)

    log(2, f"Aux IO packet for address {address}, mask=0x{function_state:02X}:")
    log(2, f"  Bytes: {' '.join(f'0x{b:02X}' for b in packet)}")
    log(2, "  Binary breakdown:")
    log(2, f"    Address:     0x{packet[0]:02X} ({packet[0]})")
    log(2, f"    Instruction: 0x{packet[1]:02X} (function group F0-F4)")
    log(2, f"    Checksum:    0x{packet[2]:02X}\n")

    return packet


def read_io1_io2_io3(rpc):
    """
    Read IO1, IO2, and IO3 via a single RPC call.

    Returns:
        Tuple (io1_high, io2_high, io3_high) or None on error
    """
    response = rpc.send_rpc("get_gpio_inputs", {})
    if response is None or response.get("status") != "ok":
        log(1, f"ERROR: Failed to read GPIO inputs: {response}")
        return None

    gpio_word = response.get("value")
    if gpio_word is None:
        log(1, f"ERROR: Missing GPIO value in response: {response}")
        return None

    io1_high = (gpio_word & (1 << 0)) != 0
    io2_high = (gpio_word & (1 << 1)) != 0
    io3_high = (gpio_word & (1 << 2)) != 0

    log(2, f"GPIO inputs: 0x{gpio_word:04X} (IO1={'HIGH' if io1_high else 'LOW'}, IO2={'HIGH' if io2_high else 'LOW'}, IO3={'HIGH' if io3_high else 'LOW'})")
    return io1_high, io2_high, io3_high


def run_interpacket_acceptance_test(rpc, loco_address, inter_packet_delay_ms=1000, logging_level=1):
    """
    Run the packet acceptance test.

    Args:
        rpc: DCCTesterRPC client instance
        loco_address: Locomotive address
        inter_packet_delay_ms: Delay between packets in milliseconds (default: 1000ms)

    Returns:
        Dictionary with test results including pass/fail status
    """
    set_log_level(logging_level)

    log(2, "=" * 70)
    log(2, "DCC InterPacket Acceptance Test (NEM 671)")
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

        # Step 2: Create and load F1 on packet (reset queue)
        log(1, "Step 2: Loading F1 ON packet (reset queue)...")
        f1_packet = make_aux_io_packet(loco_address, 0b0010)
        response = rpc.send_rpc("command_station_load_packet", {"bytes": f1_packet, "replace": True})
        if response is None or response.get("status") != "ok":
            log(1, f"ERROR: Failed to load F1 packet: {response}")
            rpc.close()
            return {"status": "FAIL", "error": "Failed to load F1 packet"}

        # Step 3: Load F1+F2 on packet
        log(1, "Step 3: Loading F1+F2 ON packet...")
        f2_packet = make_aux_io_packet(loco_address, 0b0110)
        response = rpc.send_rpc("command_station_load_packet", {"bytes": f2_packet, "replace": False})
        if response is None or response.get("status") != "ok":
            log(1, f"ERROR: Failed to load F2 packet: {response}")
            rpc.close()
            return {"status": "FAIL", "error": "Failed to load F2 packet"}

        # Step 4: Load F1+F2+F3 on packet
        log(1, "Step 4: Loading F1+F2+F3 ON packet...")
        f3_packet = make_aux_io_packet(loco_address, 0b1110)
        response = rpc.send_rpc("command_station_load_packet", {"bytes": f3_packet, "replace": False})
        if response is None or response.get("status") != "ok":
            log(1, f"ERROR: Failed to load F3 packet: {response}")
            rpc.close()
            return {"status": "FAIL", "error": "Failed to load F3 packet"}

        # Step 5: Trigger queue dump with inter-packet delay
        log(1, f"Step 5: Triggering queue dump ({inter_packet_delay_ms} ms delay)...")
        response = rpc.send_rpc("command_station_transmit_packet", {"delay_ms": inter_packet_delay_ms})
        if response is None or response.get("status") != "ok":
            log(1, f"ERROR: Failed to transmit packet queue: {response}")
            rpc.close()
            return {"status": "FAIL", "error": "Failed to transmit packet queue"}

        # Step 6: Sleep 0.5 seconds
        log(1, "Step 6: Waiting 0.5 seconds...")
        time.sleep(0.5)

        # Step 7: Read IO1/IO2/IO3
        log(1, "Step 7: Reading IO1/IO2/IO3...")
        io_state = read_io1_io2_io3(rpc)
        if io_state is None:
            rpc.close()
            return {"status": "FAIL", "error": "Failed to read IO1/IO2/IO3"}
        io1_high, io2_high, io3_high = io_state
        log(1, f"✓ IO states: IO1={'HIGH' if io1_high else 'LOW'}, IO2={'HIGH' if io2_high else 'LOW'}, IO3={'HIGH' if io3_high else 'LOW'}")
        io_all_low = not (io1_high or io2_high or io3_high)

        # Step 8: Stop command station
        log(1, "Step 8: Stopping command station")
        response = rpc.send_rpc("command_station_stop", {})

        if response is None or response.get("status") != "ok":
            log(1, f"WARNING: Failed to stop command station: {response}")
        else:
            log(2, "✓ Command station stopped\n")

        # Evaluate pass/fail
        test_pass = io_all_low

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
        log(2, f"  Inter-packet delay:    {inter_packet_delay_ms} ms")
        log(2, "\nTest sequence completed:")
        log(2, "  1. Started command station in custom packet mode")
        log(2, "  2. Loaded F1 ON packet (reset queue)")
        log(2, "  3. Loaded F1+F2 ON packet")
        log(2, "  4. Loaded F1+F2+F3 ON packet")
        log(2, f"  5. Triggered queue dump with {inter_packet_delay_ms} ms delay")
        log(2, "  6. Waited 0.5 seconds")
        log(2, "  7. Read IO1/IO2/IO3")
        log(2, "  8. Stopped command station")
        log(2, "\nIO state measurements:")
        log(2, f"  IO1 LOW: {not io1_high}")
        log(2, f"  IO2 LOW: {not io2_high}")
        log(2, f"  IO3 LOW: {not io3_high}")
        log(2, "\nPass Criteria:")
        log(2, "  IO1, IO2, IO3 are all LOW")
        log(1, "")

        return {
            "status": "PASS" if test_pass else "FAIL",
            "inter_packet_delay_ms": inter_packet_delay_ms,
            "io1_low": not io1_high,
            "io2_low": not io2_high,
            "io3_low": not io3_high
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


