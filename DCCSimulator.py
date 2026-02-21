#!/usr/bin/env python3
"""
DCC Command Station RPC Simulator
==================================

A virtual DCC command station that simulates RPC responses over a serial port.
Allows testing scripts and UI without physical hardware.

Features:
- Virtual serial port communication (requires virtual COM port pair)
- Stateful simulation (tracks command station state, parameters, etc.)
- Smart response generation from default library or learned logs
- Realistic timing simulation
- Full logging of all RPC traffic

Usage:
    python DCCSimulator.py [config_file]

Requirements:
    - Virtual serial port pair (e.g., com0com on Windows)
    - pyserial library
"""

import sys
import os
import json
import serial
import time
import random
from datetime import datetime
from typing import Dict, Any, Optional

# Default configuration values
DEFAULT_CONFIG = {
    "serial_port": "COM10",
    "baudrate": 115200,
    "timeout": 2,
    "response_mode": "default",  # "default", "replay", "scenario"
    "log_file": None,  # Path to verbose log file for replay mode
    "scenario_file": None,  # Path to scenario JSON for scenario mode
    "enable_logging": True,
    "log_directory": "simulator_logs",
    "simulate_timing": True,  # Add realistic delays to responses
    "verbose": True
}


class CommandStationState:
    """Tracks the current state of the simulated command station."""
    
    def __init__(self):
        self.running = False
        self.loop_mode = 0
        self.decoder_running = False
        
        # Command station parameters (defaults from firmware)
        self.params = {
            "track_voltage": 15000,  # mV
            "preamble_bits": 17,
            "bit1_duration": 58,  # µs
            "bit0_duration": 100,  # µs
            "bidi_enable": False,
            "bidi_dac": 2048,
            "trigger_first_bit": False,
        }
        
        # Override parameters (RAM-only, not saved)
        self.override_params = {
            "zerobit_override_mask": 0,
            "zerobit_deltaP": 0,
            "zerobit_deltaN": 0,
        }
        
        # Analog feedback simulation
        self.voltage_mv = 15000  # Track voltage in mV
        self.current_ma = 0  # Track current in mA (0 when not running)
        
        # Custom packet queue
        self.packet_queue = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Return state as dictionary for logging."""
        return {
            "running": self.running,
            "loop_mode": self.loop_mode,
            "decoder_running": self.decoder_running,
            "params": self.params.copy(),
            "override_params": self.override_params.copy(),
            "voltage_mv": self.voltage_mv,
            "current_ma": self.current_ma,
        }


class DCCSimulator:
    """Main DCC RPC simulator class."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.state = CommandStationState()
        self.response_library = {}
        self.log_file = None
        
        # Load response library
        self._load_response_library()
        
        # Setup logging
        if config["enable_logging"]:
            self._setup_logging()
        
        # Open serial port
        try:
            self.ser = serial.Serial(
                config["serial_port"],
                config["baudrate"],
                timeout=config["timeout"]
            )
            self._log(f"Opened serial port {config['serial_port']}")
        except serial.SerialException as e:
            print(f"ERROR: Failed to open serial port {config['serial_port']}: {e}")
            print("Make sure you have a virtual COM port pair set up (e.g., using com0com)")
            sys.exit(1)
    
    def _load_response_library(self):
        """Load default response library from JSON file."""
        library_path = os.path.join(
            os.path.dirname(__file__),
            "ResponseLibrary.json"
        )
        if os.path.exists(library_path):
            with open(library_path, "r") as f:
                self.response_library = json.load(f)
            self._log(f"Loaded response library from {library_path}")
        else:
            self._log("WARNING: ResponseLibrary.json not found, using minimal defaults")
            self.response_library = {}
    
    def _setup_logging(self):
        """Setup log file for recording RPC traffic."""
        log_dir = self.config["log_directory"]
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(log_dir, f"simulator_{timestamp}.log")
        self.log_file = open(log_path, "w", encoding="utf-8")
        self._log(f"Logging to {log_path}")
    
    def _log(self, message: str):
        """Log a message to console and file."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_line = f"[{timestamp}] {message}"
        
        if self.config["verbose"]:
            print(log_line)
        
        if self.log_file:
            self.log_file.write(log_line + "\n")
            self.log_file.flush()
    
    def _simulate_delay(self, method: str):
        """Add realistic delay based on method type."""
        if not self.config["simulate_timing"]:
            return
        
        # Different methods take different times
        delays = {
            "echo": 0.001,
            "command_station_start": 0.005,
            "command_station_stop": 0.005,
            "get_voltage_feedback_mv": 0.010,
            "get_current_feedback_ma": 0.010,
            "command_station_params": 0.002,
            "parameters_save": 0.050,  # Flash write is slow
            "parameters_restore": 0.050,
            "parameters_factory_reset": 0.100,
        }
        
        delay = delays.get(method, 0.002)  # Default 2ms
        time.sleep(delay)
    
    def _handle_echo(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle echo RPC method."""
        return {
            "status": "ok",
            "echo": params
        }
    
    def _handle_command_station_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle command_station_start RPC method."""
        if self.state.running:
            return {
                "status": "error",
                "message": "Command station is already running"
            }
        
        # Parse loop parameter (can be int or bool for backward compatibility)
        loop = params.get("loop", 0)
        if isinstance(loop, bool):
            loop = 1 if loop else 0
        
        self.state.running = True
        self.state.loop_mode = loop
        self.state.current_ma = 500  # Simulate some current draw
        
        self._log(f"Command station started (loop={loop})")
        
        return {
            "status": "ok",
            "message": "Command station started",
            "loop": loop
        }
    
    def _handle_command_station_stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle command_station_stop RPC method."""
        if not self.state.running:
            return {
                "status": "error",
                "message": "Command station is not running"
            }
        
        self.state.running = False
        self.state.current_ma = 0
        # Reset override parameters on stop
        self.state.override_params = {
            "zerobit_override_mask": 0,
            "zerobit_deltaP": 0,
            "zerobit_deltaN": 0,
        }
        
        self._log("Command station stopped")
        
        return {
            "status": "ok",
            "message": "Command station stopped"
        }
    
    def _handle_decoder_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle decoder_start RPC method."""
        self.state.decoder_running = True
        self._log("Decoder started")
        return {
            "status": "ok",
            "message": "Decoder started"
        }
    
    def _handle_decoder_stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle decoder_stop RPC method."""
        self.state.decoder_running = False
        self._log("Decoder stopped")
        return {
            "status": "ok",
            "message": "Decoder stopped"
        }
    
    def _handle_command_station_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle command_station_params RPC method."""
        # Validate and update parameters
        valid_params = ["preamble_bits", "bit1_duration", "bit0_duration", 
                       "bidi_enable", "bidi_dac", "trigger_first_bit", "track_voltage"]
        
        for key, value in params.items():
            if key not in valid_params:
                continue
            
            # Type validation
            if key in ["bidi_enable", "trigger_first_bit"]:
                if not isinstance(value, bool):
                    return {
                        "status": "error",
                        "message": f"{key} must be a boolean"
                    }
            elif key in ["preamble_bits", "bit1_duration", "bit0_duration", "bidi_dac", "track_voltage"]:
                if not isinstance(value, int):
                    return {
                        "status": "error",
                        "message": f"{key} must be a positive integer"
                    }
            
            self.state.params[key] = value
        
        self._log(f"Parameters updated: {params}")
        
        return {
            "status": "ok",
            "message": "Command station parameters updated"
        }
    
    def _handle_command_station_get_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle command_station_get_params RPC method."""
        # Return all parameters including override params
        all_params = self.state.params.copy()
        all_params["zerobit_override_mask"] = f"0x{self.state.override_params['zerobit_override_mask']:016X}"
        all_params["zerobit_deltaP"] = self.state.override_params["zerobit_deltaP"]
        all_params["zerobit_deltaN"] = self.state.override_params["zerobit_deltaN"]
        
        return {
            "status": "ok",
            "parameters": all_params
        }
    
    def _handle_command_station_packet_override(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle command_station_packet_override RPC method."""
        for key in ["zerobit_override_mask", "zerobit_deltaP", "zerobit_deltaN"]:
            if key in params:
                value = params[key]
                # Handle hex string for mask
                if key == "zerobit_override_mask" and isinstance(value, str):
                    value = int(value, 16)
                self.state.override_params[key] = value
        
        self._log(f"Override parameters updated: {params}")
        
        return {
            "status": "ok",
            "message": "Packet override parameters updated"
        }
    
    def _handle_command_station_packet_reset_override(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle command_station_packet_reset_override RPC method."""
        self.state.override_params = {
            "zerobit_override_mask": 0,
            "zerobit_deltaP": 0,
            "zerobit_deltaN": 0,
        }
        self._log("Override parameters reset to 0")
        return {
            "status": "ok",
            "message": "Packet override parameters reset to 0"
        }
    
    def _handle_command_station_packet_get_override(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle command_station_packet_get_override RPC method."""
        mask = self.state.override_params["zerobit_override_mask"]
        return {
            "status": "ok",
            "zerobit_override_mask": f"0x{mask:016X}",
            "zerobit_override_mask_decimal": mask,
            "zerobit_deltaP": self.state.override_params["zerobit_deltaP"],
            "zerobit_deltaN": self.state.override_params["zerobit_deltaN"]
        }
    
    def _handle_parameters_save(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle parameters_save RPC method."""
        self._log("Parameters saved to flash (simulated)")
        return {
            "status": "ok",
            "message": "Parameters saved to flash"
        }
    
    def _handle_parameters_restore(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle parameters_restore RPC method."""
        self._log("Parameters restored from flash (simulated)")
        return {
            "status": "ok",
            "message": "Parameters restored from flash"
        }
    
    def _handle_parameters_factory_reset(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle parameters_factory_reset RPC method."""
        # Reset to defaults
        self.state.params = {
            "track_voltage": 15000,
            "preamble_bits": 17,
            "bit1_duration": 58,
            "bit0_duration": 100,
            "bidi_enable": False,
            "bidi_dac": 2048,
            "trigger_first_bit": False,
        }
        self._log("Factory reset completed (simulated)")
        return {
            "status": "ok",
            "message": "Factory reset completed - all parameters restored to defaults"
        }
    
    def _handle_get_voltage_feedback_mv(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get_voltage_feedback_mv RPC method."""
        # Check for averaging parameters
        num_samples = params.get("num_samples")
        sample_delay_ms = params.get("sample_delay_ms")
        
        if num_samples is not None and sample_delay_ms is not None:
            # Validate parameters
            if num_samples < 1 or num_samples > 16:
                return {
                    "status": "error",
                    "message": "num_samples must be between 1 and 16"
                }
            if sample_delay_ms < 0 or sample_delay_ms > 1000:
                return {
                    "status": "error",
                    "message": "sample_delay_ms must be between 0 and 1000"
                }
            
            # Simulate sampling delay
            if self.config["simulate_timing"]:
                total_delay = (num_samples * sample_delay_ms) / 1000.0
                time.sleep(total_delay)
            
            # Add slight variation to averaged reading (less noise)
            voltage = self.state.voltage_mv + random.randint(-50, 50)
            
            return {
                "status": "ok",
                "voltage_mv": voltage,
                "averaged": True,
                "num_samples": num_samples,
                "sample_delay_ms": sample_delay_ms
            }
        else:
            # Single sample with more noise
            voltage = self.state.voltage_mv + random.randint(-200, 200)
            return {
                "status": "ok",
                "voltage_mv": voltage
            }
    
    def _handle_get_current_feedback_ma(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get_current_feedback_ma RPC method."""
        # Check for averaging parameters
        num_samples = params.get("num_samples")
        sample_delay_ms = params.get("sample_delay_ms")
        
        if num_samples is not None and sample_delay_ms is not None:
            # Validate parameters
            if num_samples < 1 or num_samples > 16:
                return {
                    "status": "error",
                    "message": "num_samples must be between 1 and 16"
                }
            if sample_delay_ms < 0 or sample_delay_ms > 1000:
                return {
                    "status": "error",
                    "message": "sample_delay_ms must be between 0 and 1000"
                }
            
            # Simulate sampling delay
            if self.config["simulate_timing"]:
                total_delay = (num_samples * sample_delay_ms) / 1000.0
                time.sleep(total_delay)
            
            # Add slight variation to averaged reading (less noise)
            current = self.state.current_ma + random.randint(-10, 10)
            
            return {
                "status": "ok",
                "current_ma": current,
                "averaged": True,
                "num_samples": num_samples,
                "sample_delay_ms": sample_delay_ms
            }
        else:
            # Single sample with more noise
            current = self.state.current_ma + random.randint(-50, 50)
            return {
                "status": "ok",
                "current_ma": current
            }
    
    def _handle_system_reboot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle system_reboot RPC method."""
        self._log("System reboot requested (will close connection)")
        return {
            "status": "ok",
            "message": "System rebooting..."
        }
    
    def _handle_command_station_load_packet(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle command_station_load_packet RPC method."""
        bytes_list = params.get("bytes", [])
        replace = params.get("replace", False)
        
        # Validate bytes
        if not isinstance(bytes_list, list):
            return {
                "status": "error",
                "message": "bytes must be an array"
            }
        
        for b in bytes_list:
            if not isinstance(b, int) or b < 0 or b > 255:
                return {
                    "status": "error",
                    "message": "all bytes must be unsigned integers (0-255)"
                }
        
        if len(bytes_list) > 18:
            return {
                "status": "error",
                "message": "packet too long (max 18 bytes)"
            }
        
        if replace:
            self.state.packet_queue = [bytes_list]
        else:
            self.state.packet_queue.append(bytes_list)
        
        self._log(f"Packet loaded: {bytes_list} (replace={replace})")
        
        return {
            "status": "ok",
            "message": "Packet loaded successfully",
            "length": len(bytes_list),
            "replace": replace
        }
    
    def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process an RPC request and generate response."""
        method = request.get("method")
        params = request.get("params", {})
        
        # Validate request structure
        if not method:
            return {"status": "error", "message": "Malformed request"}
        
        if not isinstance(params, dict):
            return {"status": "error", "message": "Params must be an object"}
        
        # Add realistic delay
        self._simulate_delay(method)
        
        # Route to handler
        handlers = {
            "echo": self._handle_echo,
            "command_station_start": self._handle_command_station_start,
            "command_station_stop": self._handle_command_station_stop,
            "decoder_start": self._handle_decoder_start,
            "decoder_stop": self._handle_decoder_stop,
            "command_station_params": self._handle_command_station_params,
            "command_station_get_params": self._handle_command_station_get_params,
            "command_station_packet_override": self._handle_command_station_packet_override,
            "command_station_packet_reset_override": self._handle_command_station_packet_reset_override,
            "command_station_packet_get_override": self._handle_command_station_packet_get_override,
            "parameters_save": self._handle_parameters_save,
            "parameters_restore": self._handle_parameters_restore,
            "parameters_factory_reset": self._handle_parameters_factory_reset,
            "get_voltage_feedback_mv": self._handle_get_voltage_feedback_mv,
            "get_current_feedback_ma": self._handle_get_current_feedback_ma,
            "system_reboot": self._handle_system_reboot,
            "command_station_load_packet": self._handle_command_station_load_packet,
        }
        
        handler = handlers.get(method)
        if handler:
            return handler(params)
        else:
            return {"status": "error", "message": "Unknown method"}
    
    def run(self):
        """Main simulator loop."""
        self._log("=" * 70)
        self._log("DCC Command Station RPC Simulator Started")
        self._log("=" * 70)
        self._log(f"Serial port: {self.config['serial_port']}")
        self._log(f"Baudrate: {self.config['baudrate']}")
        self._log(f"Response mode: {self.config['response_mode']}")
        self._log("Waiting for RPC requests... (Press Ctrl+C to stop)")
        self._log("")
        
        try:
            while True:
                # Read line from serial port
                try:
                    line = self.ser.readline().decode("utf-8").strip()
                except UnicodeDecodeError:
                    self._log("ERROR: Received invalid UTF-8 data")
                    continue
                
                if not line:
                    continue
                
                self._log(f"← {line}")
                
                # Parse JSON request
                try:
                    request = json.loads(line)
                except json.JSONDecodeError:
                    response = {"status": "error", "message": "Invalid JSON"}
                    response_json = json.dumps(response)
                    self._log(f"→ {response_json}")
                    self.ser.write((response_json + "\r\n").encode("utf-8"))
                    continue
                
                # Process request
                response = self.process_request(request)
                
                # Send response
                response_json = json.dumps(response)
                self._log(f"→ {response_json}")
                self.ser.write((response_json + "\r\n").encode("utf-8"))
                
                # Special handling for reboot
                if request.get("method") == "system_reboot":
                    self._log("Simulating reboot... closing connection in 1 second")
                    time.sleep(1)
                    self.ser.close()
                    self._log("Connection closed. Exiting simulator.")
                    break
        
        except KeyboardInterrupt:
            self._log("")
            self._log("Simulator stopped by user")
        
        finally:
            if self.ser.is_open:
                self.ser.close()
            if self.log_file:
                self.log_file.close()
            self._log("Shutdown complete")


def load_config(config_file: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from file or use defaults."""
    config = DEFAULT_CONFIG.copy()
    
    if config_file and os.path.exists(config_file):
        with open(config_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Parse value type
                    if value.lower() in ["true", "false"]:
                        value = value.lower() == "true"
                    elif value.isdigit():
                        value = int(value)
                    elif value == "None":
                        value = None
                    
                    config[key] = value
    else:
        # Look for SimulatorConfig.txt in same directory
        default_config = os.path.join(
            os.path.dirname(__file__),
            "SimulatorConfig.txt"
        )
        if os.path.exists(default_config):
            return load_config(default_config)
    
    return config


def main():
    """Main entry point."""
    print("=" * 70)
    print("DCC Command Station RPC Simulator")
    print("=" * 70)
    print()
    
    # Load configuration
    config_file = sys.argv[1] if len(sys.argv) > 1 else None
    config = load_config(config_file)
    
    # Create and run simulator
    simulator = DCCSimulator(config)
    simulator.run()


if __name__ == "__main__":
    main()
