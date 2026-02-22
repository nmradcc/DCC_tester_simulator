#!/usr/bin/env python3
"""
PacketAcceptanceTest Script
===========================

Unified packet acceptance test for both motor current feedback and
voltage feedback (IO13/IO14). Uses the in_circuit_motor flag to select
measurement mode.
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

        request_json = json.dumps(request) + "\r\n"
        log(2, f"→ {request_json.strip()}")

        self.ser.write(request_json.encode("utf-8"))

        response_line = self.ser.readline().decode("utf-8").strip()
        log(2, f"← {response_line}")

        if response_line:
            return json.loads(response_line)
        return None

    def close(self):
        """Close serial connection."""
        self.ser.close()


def calculate_dcc_checksum(bytes_list):
    """Calculate DCC packet checksum (XOR of all bytes)."""
    checksum = 0
    for byte in bytes_list:
        checksum ^= byte
    return checksum


def make_speed_packet(address, speed, forward=True):
    """
    Create a DCC advanced operations speed packet (128-speed step mode).

    Args:
        address: Locomotive address (0-127 for short address)
        speed: Speed value (0-127, where 0=stop, 1=emergency stop, 2-127=speed steps)
        forward: True for forward, False for reverse

    Returns:
        List of packet bytes
    """
    instruction = 0x3F

    if forward:
        speed_byte = (1 << 7) | (speed & 0x7F)
    else:
        speed_byte = speed & 0x7F

    packet = [address, instruction, speed_byte]
    checksum = calculate_dcc_checksum(packet)
    packet.append(checksum)

    log(2, f"Packet for address {address}, speed {speed} {'forward' if forward else 'reverse'}:")
    log(2, f"  Bytes: {' '.join(f'0x{b:02X}' for b in packet)}")
    log(2, "  Binary breakdown:")
    log(2, f"    Address:     0x{packet[0]:02X} ({packet[0]})")
    log(2, f"    Instruction: 0x{packet[1]:02X} (advanced operations speed)")
    log(2, f"    Speed:       0x{packet[2]:02X} (dir={'forward' if forward else 'reverse'}, speed={speed})")
    log(2, f"    Checksum:    0x{packet[3]:02X}\n")

    return packet


def make_emergency_stop_packet(address):
    """
    Create a DCC emergency stop packet.

    Args:
        address: Locomotive address (0 for broadcast to all locomotives)

    Returns:
        List of packet bytes
    """
    instruction = 0x3F
    speed_byte = (1 << 7) | 1

    packet = [address, instruction, speed_byte]
    checksum = calculate_dcc_checksum(packet)
    packet.append(checksum)

    log(2, "Emergency stop packet:")
    log(2, f"  Bytes: {' '.join(f'0x{b:02X}' for b in packet)}")
    log(2, "  Binary breakdown:")
    log(2, f"    Address:     0x{packet[0]:02X} ({packet[0]})")
    log(2, f"    Instruction: 0x{packet[1]:02X} (advanced operations speed)")
    log(2, f"    Speed:       0x{packet[2]:02X} (emergency stop)")
    log(2, f"    Checksum:    0x{packet[3]:02X}\n")

    return packet


def read_io13_io14(rpc):
    """
    Read IO13 and IO14 via a single RPC call.

    Returns:
        Tuple (io13_high, io14_high) or None on error
    """
    response = rpc.send_rpc("get_gpio_inputs", {})
    if response is None or response.get("status") != "ok":
        log(1, f"ERROR: Failed to read GPIO inputs: {response}")
        return None

    gpio_word = response.get("value")
    if gpio_word is None:
        log(1, f"ERROR: Missing GPIO value in response: {response}")
        return None

    io13_high = (gpio_word & (1 << 12)) != 0
    io14_high = (gpio_word & (1 << 13)) != 0

    log(2, f"GPIO inputs: 0x{gpio_word:04X} (IO13={'HIGH' if io13_high else 'LOW'}, IO14={'HIGH' if io14_high else 'LOW'})")
    return io13_high, io14_high


def read_current_ma(rpc):
    response = rpc.send_rpc("get_current_feedback_ma", {"num_samples": 4, "sample_delay_ms": 25})
    if response is None or response.get("status") != "ok":
        log(1, f"ERROR: Failed to read current: {response}")
        return None
    return response.get("current_ma", 0)


def run_packet_acceptance_test(
    rpc,
    loco_address,
    inter_packet_delay_ms=1000,
    logging_level=1,
    in_circuit_motor=False,
    test_stop_delay_ms=1000,
):
    """
    Run the packet acceptance test.

    Args:
        rpc: DCCTesterRPC client instance
        loco_address: Locomotive address
        inter_packet_delay_ms: Delay between packets in milliseconds (default: 1000ms)
        in_circuit_motor: True to use current feedback, False for IO13/IO14

    Returns:
        Dictionary with test results including pass/fail status
    """
    HALF_SPEED = 64

    set_log_level(logging_level)

    log(2, "=" * 70)
    log(2, "DCC Packet Acceptance Test (NEM 671)")
    log(2, f"Inter-packet delay: {inter_packet_delay_ms} ms")
    log(2, f"Feedback mode: {'current' if in_circuit_motor else 'voltage'}")
    log(2, "=" * 70)
    log(2, "")

    try:
        log(1, "Step 1: Starting command station in custom packet mode")
        response = rpc.send_rpc("command_station_start", {"loop": 0})

        if response is None or response.get("status") != "ok":
            log(1, f"ERROR: Failed to start command station: {response}")
            return {"status": "FAIL", "error": "Failed to start command station"}
        log(2, f"✓ Command station started (loop={response.get('loop', 0)})\n")

        time.sleep(0.5)

        if in_circuit_motor:
            log(1, "Step 2: Reading motor off current as baseline...")
            motor_off_current_ma = read_current_ma(rpc)
            if motor_off_current_ma is None:
                rpc.close()
                return {"status": "FAIL", "error": "Failed to read motor off current"}
            log(1, f"✓ Motor off current: {motor_off_current_ma} mA (baseline)")
        else:
            log(1, "Step 2: Reading motor off IO status as baseline...")
            io_state = read_io13_io14(rpc)
            if io_state is None:
                rpc.close()
                return {"status": "FAIL", "error": "Failed to read IO13/IO14"}
            io13_high, io14_high = io_state
            motor_off_ok = io13_high and io14_high
            log(1, f"✓ Motor off IO state: {motor_off_ok} (IO13={'HIGH' if io13_high else 'LOW'}, IO14={'HIGH' if io14_high else 'LOW'})")

        log(1, f"Step 3: Creating motor start packet (speed {HALF_SPEED} reverse)...")
        start_packet = make_speed_packet(loco_address, HALF_SPEED, forward=False)

        log(1, "Step 4: Loading and transmitting motor start packet...")
        response = rpc.send_rpc("command_station_load_packet", {"bytes": start_packet, "replace": True})

        if response is None or response.get("status") != "ok":
            log(1, f"ERROR: Failed to load packet: {response}")
            rpc.close()
            return {"status": "FAIL", "error": "Failed to load packet"}

        response = rpc.send_rpc("command_station_transmit_packet", {"delay_ms": 0})

        if response is None or response.get("status") != "ok":
            log(1, f"ERROR: Failed to transmit packet: {response}")
            rpc.close()
            return {"status": "FAIL", "error": "Failed to transmit packet"}

        log(1, f"Step 5: Waiting {inter_packet_delay_ms} ms (inter-packet delay)...")
        time.sleep(inter_packet_delay_ms / 1000.0)
        log(2, "✓ Inter-packet delay complete\n")

        if in_circuit_motor:
            log(1, "Step 6: Reading motor run current...")
            motor_on_current_ma = read_current_ma(rpc)
            if motor_on_current_ma is None:
                rpc.close()
                return {"status": "FAIL", "error": "Failed to read motor current"}
            log(1, f"✓ Motor run current: {motor_on_current_ma} mA")
        else:
            log(1, "Step 6: Reading motor run IO status...")
            io_state = read_io13_io14(rpc)
            if io_state is None:
                rpc.close()
                return {"status": "FAIL", "error": "Failed to read IO13/IO14"}
            io13_high, io14_high = io_state
            motor_run_ok = (not io13_high) or (not io14_high)
            log(1, f"✓ Motor run IO state: {motor_run_ok} (IO13={'HIGH' if io13_high else 'LOW'}, IO14={'HIGH' if io14_high else 'LOW'})")

        log(1, f"Step 7: Sending emergency stop packet to address {loco_address}...")
        estop_packet = make_emergency_stop_packet(loco_address)

        response = rpc.send_rpc("command_station_load_packet", {"bytes": estop_packet, "replace": True})
        if response is None or response.get("status") != "ok":
            log(1, f"ERROR: Failed to load emergency stop packet: {response}")
            rpc.close()
            return {"status": "FAIL", "error": "Failed to load emergency stop packet"}
        log(2, "✓ Emergency stop packet loaded\n")
        response = rpc.send_rpc("command_station_transmit_packet", {"delay_ms": 0})
        if response is None or response.get("status") != "ok":
            log(1, f"ERROR: Failed to transmit emergency stop packet: {response}")
            rpc.close()
            return {"status": "FAIL", "error": "Failed to transmit emergency stop"}

        log(2, f"Step 8: Waiting {test_stop_delay_ms} ms for motor to stop...")
        time.sleep(test_stop_delay_ms / 1000.0)

        if in_circuit_motor:
            log(1, "Step 9: Reading motor stopped current...")
            motor_stopped_current_ma = read_current_ma(rpc)
            if motor_stopped_current_ma is None:
                rpc.close()
                return {"status": "FAIL", "error": "Failed to read stopped current"}
            log(1, f"✓ Motor stopped current: {motor_stopped_current_ma} mA")
        else:
            log(1, "Step 9: Reading motor stopped IO status...")
            io_state = read_io13_io14(rpc)
            if io_state is None:
                rpc.close()
                return {"status": "FAIL", "error": "Failed to read IO13/IO14"}
            io13_high, io14_high = io_state
            motor_stop_ok = io13_high and io14_high
            log(1, f"✓ Motor stopped IO state: {motor_stop_ok} (IO13={'HIGH' if io13_high else 'LOW'}, IO14={'HIGH' if io14_high else 'LOW'})")

        log(1, "Step 10: Stopping command station")
        response = rpc.send_rpc("command_station_stop", {})

        if response is None or response.get("status") != "ok":
            log(1, f"WARNING: Failed to stop command station: {response}")
        else:
            log(2, "✓ Command station stopped\n")

        if in_circuit_motor:
            current_increase = motor_on_current_ma - motor_off_current_ma
            current_decrease = motor_on_current_ma - motor_stopped_current_ma
            min_current_delta_ma = 1
            test_pass = (current_increase >= min_current_delta_ma and current_decrease >= min_current_delta_ma)

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
            log(2, f"  Motor speed:           {HALF_SPEED} (reverse)")
            log(2, f"  Inter-packet delay:    {inter_packet_delay_ms} ms")
            log(2, "\nTest sequence completed:")
            log(2, "  1. Started command station in custom packet mode")
            log(2, f"  2. Read motor off current: {motor_off_current_ma} mA (baseline)")
            log(2, f"  3. Created motor start packet (speed {HALF_SPEED} reverse)")
            log(2, f"  4. Transmitted motor start packet to address {loco_address}")
            log(2, f"  5. Waited {inter_packet_delay_ms} ms (inter-packet delay)")
            log(2, f"  6. Read motor run current: {motor_on_current_ma} mA")
            log(2, f"  7. Sent emergency stop packet to address {loco_address}")
            log(2, f"  8. Waited {test_stop_delay_ms} ms for motor to stop")
            log(2, f"  9. Read motor stopped current: {motor_stopped_current_ma} mA")
            log(2, "  10. Stopped command station")
            log(2, "\nCurrent measurements:")
            log(2, f"  Motor off:     {motor_off_current_ma} mA (baseline)")
            log(2, f"  Motor running: {motor_on_current_ma} mA (delta: {current_increase:+d} mA)")
            log(2, f"  Motor stopped: {motor_stopped_current_ma} mA (delta from baseline: {motor_stopped_current_ma - motor_off_current_ma:+d} mA)")
            log(2, f"\nPass Criteria (minimum delta: {min_current_delta_ma} mA):")
            log(2, f"  Current increased during run: {current_increase >= min_current_delta_ma} ({current_increase:+d} mA >= {min_current_delta_ma} mA)")
            log(2, f"  Current decreased after stop: {current_decrease >= min_current_delta_ma} ({current_decrease:+d} mA >= {min_current_delta_ma} mA)")
            log(1, "")

            return {
                "status": "PASS" if test_pass else "FAIL",
                "inter_packet_delay_ms": inter_packet_delay_ms,
                "motor_off_current_ma": motor_off_current_ma,
                "motor_on_current_ma": motor_on_current_ma,
                "motor_stopped_current_ma": motor_stopped_current_ma,
                "current_increase": current_increase,
                "current_decrease": current_decrease
            }

        test_pass = motor_off_ok and motor_run_ok and motor_stop_ok

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
        log(2, f"  Motor speed:           {HALF_SPEED} (reverse)")
        log(2, f"  Inter-packet delay:    {inter_packet_delay_ms} ms")
        log(2, "\nTest sequence completed:")
        log(2, "  1. Started command station in custom packet mode")
        log(2, f"  2. Read motor off IO state: {motor_off_ok}")
        log(2, f"  3. Created motor start packet (speed {HALF_SPEED} reverse)")
        log(2, f"  4. Transmitted motor start packet to address {loco_address}")
        log(2, f"  5. Waited {inter_packet_delay_ms} ms (inter-packet delay)")
        log(2, f"  6. Read motor run IO state: {motor_run_ok}")
        log(2, f"  7. Sent emergency stop packet to address {loco_address}")
        log(2, f"  8. Waited {test_stop_delay_ms} ms for motor to stop")
        log(2, f"  9. Read motor stopped IO state: {motor_stop_ok}")
        log(2, "  10. Stopped command station")
        log(2, "\nIO state measurements:")
        log(2, f"  Motor off OK:  {motor_off_ok}")
        log(2, f"  Motor run OK:  {motor_run_ok}")
        log(2, f"  Motor stop OK: {motor_stop_ok}")
        log(2, "\nPass Criteria:")
        log(2, "  Off, Run, Stop states are all True")
        log(1, "")

        return {
            "status": "PASS" if test_pass else "FAIL",
            "inter_packet_delay_ms": inter_packet_delay_ms,
            "motor_off_ok": motor_off_ok,
            "motor_run_ok": motor_run_ok,
            "motor_stop_ok": motor_stop_ok
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
