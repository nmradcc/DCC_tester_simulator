#!/usr/bin/env python3
"""
Quick Test for DCC Simulator
=============================

Sends a few RPC commands to verify the simulator is working correctly.

Usage:
    python TestSimulator.py [port]

Default port: COM9 (connects to simulator on COM10)
"""

import sys
import serial
import json
import time


def send_rpc(ser, method, params):
    """Send RPC request and get response."""
    request = {
        "method": method,
        "params": params
    }
    
    request_json = json.dumps(request) + "\r\n"
    print(f"→ {request_json.strip()}")
    
    ser.write(request_json.encode("utf-8"))
    
    response_line = ser.readline().decode("utf-8").strip()
    print(f"← {response_line}")
    
    if response_line:
        return json.loads(response_line)
    return None


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM9"
    
    print("=" * 70)
    print("DCC Simulator Test")
    print("=" * 70)
    print(f"Connecting to {port}...")
    print()
    
    try:
        ser = serial.Serial(port, 115200, timeout=2)
        time.sleep(0.5)
        print(f"✓ Connected to {port}")
        print()
        
        # Test 1: Echo
        print("Test 1: Echo")
        print("-" * 70)
        response = send_rpc(ser, "echo", {"test": "hello", "value": 123})
        assert response["status"] == "ok", "Echo failed"
        assert response["echo"]["test"] == "hello", "Echo mismatch"
        print("✓ Echo test passed")
        print()
        
        # Test 2: Get parameters
        print("Test 2: Get Parameters")
        print("-" * 70)
        response = send_rpc(ser, "command_station_get_params", {})
        assert response["status"] == "ok", "Get params failed"
        assert "parameters" in response, "No parameters returned"
        print(f"✓ Got parameters: {len(response['parameters'])} items")
        print()
        
        # Test 3: Start command station
        print("Test 3: Start Command Station")
        print("-" * 70)
        response = send_rpc(ser, "command_station_start", {})
        assert response["status"] == "ok", "Start failed"
        assert response["loop"] == 0, "Loop mode incorrect"
        print("✓ Command station started")
        print()
        
        # Test 4: Get voltage feedback
        print("Test 4: Voltage Feedback")
        print("-" * 70)
        response = send_rpc(ser, "get_voltage_feedback_mv", {})
        assert response["status"] == "ok", "Voltage reading failed"
        assert "voltage_mv" in response, "No voltage value"
        print(f"✓ Voltage: {response['voltage_mv']} mV")
        print()
        
        # Test 5: Get current feedback
        print("Test 5: Current Feedback")
        print("-" * 70)
        response = send_rpc(ser, "get_current_feedback_ma", {})
        assert response["status"] == "ok", "Current reading failed"
        assert "current_ma" in response, "No current value"
        print(f"✓ Current: {response['current_ma']} mA")
        print()
        
        # Test 6: Set parameters
        print("Test 6: Set Parameters")
        print("-" * 70)
        response = send_rpc(ser, "command_station_params", 
                           {"preamble_bits": 20, "bit1_duration": 60})
        assert response["status"] == "ok", "Set params failed"
        print("✓ Parameters updated")
        print()
        
        # Test 7: Verify parameters changed
        print("Test 7: Verify Parameter Change")
        print("-" * 70)
        response = send_rpc(ser, "command_station_get_params", {})
        assert response["parameters"]["preamble_bits"] == 20, "Preamble not updated"
        assert response["parameters"]["bit1_duration"] == 60, "Bit1 not updated"
        print("✓ Parameters verified")
        print()
        
        # Test 8: Stop command station
        print("Test 8: Stop Command Station")
        print("-" * 70)
        response = send_rpc(ser, "command_station_stop", {})
        assert response["status"] == "ok", "Stop failed"
        print("✓ Command station stopped")
        print()
        
        # Test 9: Averaged voltage reading with delay
        print("Test 9: Averaged Voltage (with delay)")
        print("-" * 70)
        print("(This should take ~500ms)")
        start_time = time.time()
        response = send_rpc(ser, "get_voltage_feedback_mv", 
                           {"num_samples": 10, "sample_delay_ms": 50})
        elapsed = time.time() - start_time
        assert response["status"] == "ok", "Averaged reading failed"
        assert response["averaged"] == True, "Not marked as averaged"
        print(f"✓ Averaged voltage: {response['voltage_mv']} mV (took {elapsed:.2f}s)")
        print()
        
        ser.close()
        
        print("=" * 70)
        print("All Tests Passed! ✓")
        print("=" * 70)
        print()
        print("The simulator is working correctly.")
        print()
        
    except serial.SerialException as e:
        print(f"\n✗ ERROR: Serial port error: {e}")
        print(f"\nMake sure:")
        print(f"  1. Virtual COM port pair is set up (e.g., COM9 ↔ COM10)")
        print(f"  2. Simulator is running on COM10")
        print(f"  3. No other program is using {port}")
        sys.exit(1)
    
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
