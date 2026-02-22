#!/usr/bin/env python3
"""
AcceptanceTestPacket Script
===========================

This script tests custom packet injection via RPC calls to send
DCC speed command packets using the DCC_tester command station.

Test: Send 3 half-speed reverse packets with 100ms delay between them
"""

import json
import serial
import time
import sys


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
        print(f"→ {request_json.strip()}")
        
        self.ser.write(request_json.encode('utf-8'))
        
        # Read response
        response_line = self.ser.readline().decode('utf-8').strip()
        print(f"← {response_line}")
        
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
    # Advanced operations speed instruction: 0b00111111 (0x3F)
    instruction = 0x3F
    
    # Speed byte: bit 7 = direction (1=forward, 0=reverse), bits 6-0 = speed
    if forward:
        speed_byte = (1 << 7) | (speed & 0x7F)
    else:
        speed_byte = speed & 0x7F
    
    packet = [address, instruction, speed_byte]
    checksum = calculate_dcc_checksum(packet)
    packet.append(checksum)
    
    return packet


def make_emergency_stop_packet(address):
    """
    Create a DCC emergency stop packet.
    
    Args:
        address: Locomotive address (0 for broadcast to all locomotives)
        
    Returns:
        List of packet bytes
    """
    # Advanced operations speed instruction: 0x3F
    # Emergency stop: speed = 1, direction = forward (bit 7 = 1)
    instruction = 0x3F
    speed_byte = (1 << 7) | 1  # 0x81
    
    packet = [address, instruction, speed_byte]
    checksum = calculate_dcc_checksum(packet)
    packet.append(checksum)
    
    return packet


def main():
    """Main test function."""
    
    # Configuration
    COM_PORT = "COM6"  # Change this to match your USB CDC ACM port
    LOCO_ADDRESS = 3   # Locomotive address for speed test
    HALF_SPEED = 64    # Half of 127 (rounded up from 63.5)
    
    print("=" * 70)
    print("DCC_tester Acceptance Test")
    print("Half-Speed Reverse -> Emergency Stop")
    print("=" * 70)
    print()
    
    try:
        # Connect to DCC_tester
        print(f"Connecting to {COM_PORT}...")
        rpc = DCCTesterRPC(COM_PORT)
        print("Connected!\n")
        # Pre-step: Enable scope trigger on first bit
        print("Pre-step: Enabling scope trigger on first bit...")
        response = rpc.send_rpc("command_station_params", {"trigger_first_bit": True})
        if response is None or response.get("status") != "ok":
            print(f"WARNING: Failed to enable scope trigger: {response}")
        else:
            print("\u2713 Scope trigger enabled\n")
        
        # Step 1: Start command station in custom packet mode (loop=0)
        print("Step 1: Starting command station in custom packet mode...")
        response = rpc.send_rpc("command_station_start", {"loop": 0})
        
        if response is None or response.get("status") != "ok":
            print(f"ERROR: Failed to start command station: {response}")
            return 1
        print(f"✓ Command station started (loop={response.get('loop', 0)})\n")
        
        time.sleep(0.5)
        
        # Step 2: Read motor off current as baseline
        print("Step 2: Reading motor off current as baseline...")
        response = rpc.send_rpc("get_current_feedback_ma", {})
        
        if response is None or response.get("status") != "ok":
            print(f"ERROR: Failed to read current: {response}")
            return 1
        
        motor_off_current_ma = response.get("current_ma", 0)
        print(f"✓ Motor off current: {motor_off_current_ma} mA (baseline)\n")
        
        # Step 3: Create half-speed reverse packet
        print("Step 3: Creating half-speed reverse packet...")
        packet = make_speed_packet(LOCO_ADDRESS, HALF_SPEED, forward=False)
        print(f"Packet for address {LOCO_ADDRESS}, speed {HALF_SPEED} reverse:")
        print(f"  Bytes: {' '.join(f'0x{b:02X}' for b in packet)}")
        print(f"  Binary breakdown:")
        print(f"    Address:     0x{packet[0]:02X} ({packet[0]})")
        print(f"    Instruction: 0x{packet[1]:02X} (advanced operations speed)")
        print(f"    Speed:       0x{packet[2]:02X} (dir=reverse, speed={HALF_SPEED})")
        print(f"    Checksum:    0x{packet[3]:02X}\n")
        
        # Step 4: Load the packet
        print("Step 4: Loading packet into command station...")
        response = rpc.send_rpc("command_station_load_packet", {"bytes": packet})
        
        if response is None or response.get("status") != "ok":
            print(f"ERROR: Failed to load packet: {response}")
            return 1
        print(f"✓ Packet loaded (length={response.get('length')} bytes)\n")
        
        # Step 5: Transmit the packet 3 times with 100ms delay
        print("Step 5: Transmitting packet 3 times with 100ms delay...")
        response = rpc.send_rpc("command_station_transmit_packet", 
                               {"count": 3, "delay_ms": 100})
        
        if response is None or response.get("status") != "ok":
            print(f"ERROR: Failed to transmit packet: {response}")
            return 1
        
        # Step 6: motor run time
        time.sleep(0.5)        

        # Step 7: Read motor run current
        print("Step 7: Reading motor run current...")
        response = rpc.send_rpc("get_current_feedback_ma", {})
        
        if response is None or response.get("status") != "ok":
            print(f"ERROR: Failed to read current: {response}")
            return 1
        
        motor_on_current_ma = response.get("current_ma", 0)
        print(f"✓ Motor run current: {motor_on_current_ma} mA\n")

        # Step 8: Send emergency stop packet
        print(f"Step 8: Sending one emergency stop packet...")
        estop_packet = make_emergency_stop_packet(LOCO_ADDRESS)
        print(f"Emergency stop packet for address {LOCO_ADDRESS}:")
        print(f"  Bytes: {' '.join(f'0x{b:02X}' for b in estop_packet)}")
        print(f"  Binary breakdown:")
        print(f"    Address:     0x{estop_packet[0]:02X} ({estop_packet[0]})")
        print(f"    Instruction: 0x{estop_packet[1]:02X} (advanced operations speed)")
        print(f"    Speed:       0x{estop_packet[2]:02X} (emergency stop)")
        print(f"    Checksum:    0x{estop_packet[3]:02X}\n")
        
        response = rpc.send_rpc("command_station_load_packet", {"bytes": estop_packet})
        if response is None or response.get("status") != "ok":
            print(f"ERROR: Failed to load emergency stop packet: {response}")
            return 1
        print(f"✓ Emergency stop packet loaded (length={response.get('length')} bytes)\n")
        
        response = rpc.send_rpc("command_station_transmit_packet",
                               {"count": 1, "delay_ms": 100})
        if response is None or response.get("status") != "ok":
            print(f"ERROR: Failed to transmit emergency stop packet: {response}")
            return 1
        print(f"✓ Emergency stop packet transmission triggered")
        print(f"  Count: {response.get('count')}\n")
        
        print(f"Waiting 1 second for motor stop")
        time.sleep(1.0)
        
        # Step 9: Read motor stopped current
        print("\nStep 9: Reading motor stopped current...")
        response = rpc.send_rpc("get_current_feedback_ma", {})
        
        if response is None or response.get("status") != "ok":
            print(f"ERROR: Failed to read current: {response}")
            return 1
        
        motor_stopped_current_ma = response.get("current_ma", 0)
        print(f"✓ Motor stopped current: {motor_stopped_current_ma} mA\n")
        
        # Step 10: Stop command station
        print("Step 10: Stopping command station...")
        response = rpc.send_rpc("command_station_stop", {})
        
        if response is None or response.get("status") != "ok":
            print(f"WARNING: Failed to stop command station: {response}")
        else:
            print(f"✓ Command station stopped\n")
        
        print("\n" + "=" * 70)
        print("✓ TEST COMPLETE")
        print("=" * 70)
        if (motor_on_current_ma > motor_off_current_ma and
            motor_stopped_current_ma < motor_on_current_ma):
            print("✓ TEST PASS")
        else:
            print("✗ TEST FAIL")
        print("=" * 70)
        print(f"\nSent half-speed reverse packets to address {LOCO_ADDRESS}")
        print(f"Speed value: {HALF_SPEED} (approximately half of max speed 127)")
        print(f"\nTest sequence completed:")
        print(f"  1. Started command station in custom packet mode")
        print(f"  2. Read motor off current: {motor_off_current_ma} mA (baseline)")
        print(f"  3. Created half-speed reverse packet")
        print(f"  4. Loaded packet into command station")
        print(f"  5. Transmitted 3 half-speed reverse packets to address {LOCO_ADDRESS}")
        print(f"  6. Motor run time: 0.5 seconds")
        print(f"  7. Read motor run current: {motor_on_current_ma} mA")
        print(f"  8. Sent 1 emergency stop packet to address {LOCO_ADDRESS}")
        print(f"  9. Read motor stopped current: {motor_stopped_current_ma} mA")
        print(f" 10. Stopped command station")
        print(f"\nCurrent measurements:")
        print(f"  Motor off:     {motor_off_current_ma} mA (baseline)")
        print(f"  Motor running: {motor_on_current_ma} mA (delta: {motor_on_current_ma - motor_off_current_ma} mA)")
        print(f"  Motor stopped: {motor_stopped_current_ma} mA (delta: {motor_stopped_current_ma - motor_off_current_ma} mA)")
        print()
        
        # Close connection
        rpc.close()
        return 0
        
    except serial.SerialException as e:
        print(f"\nERROR: Serial port error: {e}")
        print(f"Make sure {COM_PORT} is the correct port and the device is connected.")
        return 1
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
        return 1
    except Exception as e:
        print(f"\nERROR: Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
