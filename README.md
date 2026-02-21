# DCC Command Station RPC Simulator

A virtual DCC command station that simulates RPC responses over a serial port, enabling testing of scripts and UI without physical hardware.

## Overview

The simulator provides:
- **Virtual Serial Port Communication** - Listens on a simulated COM port
- **Stateful Simulation** - Tracks command station state, parameters, decoder state
- **Smart Response Generation** - Default responses, learned from logs, or scenario-based
- **Realistic Timing** - Simulates hardware delays for authentic behavior
- **Full Logging** - Records all RPC traffic for debugging
- **Analog Feedback** - Simulates voltage and current readings with realistic noise

## Features

### Supported RPC Methods

The simulator fully implements all DCC_tester RPC methods:

**Command Station Control:**
- `echo` - Echo test
- `command_station_start` - Start command station (with loop modes)
- `command_station_stop` - Stop command station
- `decoder_start` / `decoder_stop` - Decoder control

**Parameter Management:**
- `command_station_params` - Set timing parameters
- `command_station_get_params` - Get all parameters
- `command_station_packet_override` - Set override parameters
- `command_station_packet_reset_override` - Reset overrides
- `command_station_packet_get_override` - Get override parameters
- `parameters_save` / `parameters_restore` - Flash operations
- `parameters_factory_reset` - Factory reset

**Analog Feedback:**
- `get_voltage_feedback_mv` - Read track voltage (with averaging support)
- `get_current_feedback_ma` - Read track current (with averaging support)

**Packet Control:**
- `command_station_load_packet` - Load custom packet queue

**System:**
- `system_reboot` - Reboot system (closes connection)

### Stateful Behavior

The simulator maintains state across RPC calls:
- Command station running/stopped status
- Loop mode (0-3)
- All timing parameters (preamble, bit durations, etc.)
- Override parameters (mask, deltaP, deltaN)
- Analog feedback values with realistic noise
- Packet queue

## Requirements

### Software Requirements
- Python 3.7 or higher
- `pyserial` library: `pip install pyserial`

### Virtual COM Port Setup (Windows)

The simulator requires a virtual COM port pair. Use **com0com** (free, open-source):

1. **Download com0com:**
   - Visit: https://sourceforge.net/projects/com0com/
   - Download and install the signed version

2. **Create Virtual Port Pair:**
   - Open "Setup Command Prompt" from com0com
   - Create a pair: `install PortName=COM9 PortName=COM10`
   - Verify: `list`

3. **Configure:**
   - Your test scripts connect to **COM9**
   - The simulator listens on **COM10**

**Alternative**: For Linux/Mac, use `socat` to create virtual serial ports.

## Quick Start

### 1. Basic Usage

```bash
# Start simulator with default configuration
python DCCSimulator.py

# Start with custom config file
python DCCSimulator.py my_config.txt
```

### 2. Configure Serial Port

Edit `SimulatorConfig.txt`:
```ini
serial_port=COM10  # Must match your virtual port setup
baudrate=115200
response_mode=default
simulate_timing=true
verbose=true
```

### 3. Run Your Scripts

```bash
# In another terminal, run your test scripts
# Make sure SystemConfig.txt has serial_port=COM9
cd Scripts
python System.py
```

The simulator will:
- Listen for RPC requests on COM10
- Log all traffic to console and file
- Respond with appropriate RPC responses
- Maintain state across requests

## Configuration

### SimulatorConfig.txt

```ini
# Serial port to listen on
serial_port=COM10

# Serial settings
baudrate=115200
timeout=2

# Response mode: "default", "replay", or "scenario"
response_mode=default

# Path to verbose log file (for replay mode)
log_file=None

# Path to scenario JSON (for scenario mode)
scenario_file=None

# Enable logging of RPC traffic
enable_logging=true
log_directory=simulator_logs

# Simulate realistic timing delays
simulate_timing=true

# Verbose console output
verbose=true
```

### Response Modes

#### Default Mode (Built-in)
Uses built-in response handlers with stateful behavior.

```ini
response_mode=default
```

Best for: General testing, script development, UI testing

#### Replay Mode (Learn from Logs)
Parses verbose log files to learn actual request/response patterns.

```ini
response_mode=replay
log_file=c:\tmp\logs\timing_test_20260220_143022.log
```

Best for: Reproducing specific test runs, debugging edge cases

#### Scenario Mode (Pre-defined Sequences)
Uses pre-defined test scenarios from JSON files.

```ini
response_mode=scenario
scenario_file=scenarios\timing_margin_pass.json
```

Best for: Repeatable test cases, regression testing

## Log Parser Utility

Extract RPC patterns from your verbose test logs:

```bash
# Parse a log file
python LogParser.py c:\tmp\logs\test_20260220.log

# Custom output prefix
python LogParser.py test.log my_output
```

**Output Files:**
- `<prefix>_pairs.json` - All request/response pairs
- `<prefix>_scenario.json` - Ready-to-use scenario file
- `<prefix>_summary.json` - Method usage summary

**Example Workflow:**
1. Run test with `logging_level=2` in SystemConfig.txt
2. Parse the log: `python LogParser.py c:\tmp\logs\test.log`
3. Use scenario: Edit `SimulatorConfig.txt`:
   ```ini
   response_mode=scenario
   scenario_file=test_scenario.json
   ```

## Advanced Features

### Analog Feedback Simulation

The simulator provides realistic analog readings:

**Voltage Feedback:**
- Base value: 15,000 mV (15V)
- Single-sample noise: ±200 mV
- Averaged noise: ±50 mV

**Current Feedback:**
- Running: 500 mA (base) ± noise
- Stopped: 0 mA
- Single-sample noise: ±50 mA
- Averaged noise: ±10 mA

**Averaging Support:**
The simulator properly handles averaging parameters:
```json
{"method":"get_voltage_feedback_mv","params":{"num_samples":10,"sample_delay_ms":50}}
```
- Simulates actual sampling delay (10 × 50ms = 500ms)
- Returns reduced noise in averaged reading

### Timing Simulation

When `simulate_timing=true`:
- Echo: 1ms
- Start/Stop: 5ms
- Analog readings: 10ms
- Parameters: 2ms
- Flash save/restore: 50-100ms

Set to `false` for instant responses during debugging.

### State Tracking

The simulator maintains full state:
- Command station running/stopped
- All timing parameters
- Override parameters (RAM-only, cleared on stop)
- Decoder state
- Analog feedback values

Query state via `command_station_get_params`:
```bash
# Send via serial terminal or script
{"method":"command_station_get_params","params":{}}

# Response includes all parameters
{
  "status": "ok",
  "parameters": {
    "track_voltage": 15000,
    "preamble_bits": 17,
    "bit1_duration": 58,
    ...
  }
}
```

## Troubleshooting

### Simulator Won't Start

**Error:** `Failed to open serial port COM10`

**Solutions:**
1. Verify virtual port pair exists: `com0com list`
2. Check port number in `SimulatorConfig.txt`
3. Ensure no other program is using COM10
4. Try different port numbers

### Scripts Can't Connect

**Error:** `Serial port error: COM9`

**Solutions:**
1. Verify simulator is running on COM10
2. Check `SystemConfig.txt` has `serial_port=COM9`
3. Verify virtual port pair: COM9 ↔ COM10
4. Check for port conflicts

### Responses Seem Wrong

**Solutions:**
1. Check simulator logs in `simulator_logs/`
2. Enable verbose mode: `verbose=true`
3. Verify response_mode setting
4. Check for state issues (restart simulator)

### Timing Issues

If averaged readings don't take expected time:

**Solution:** Enable timing simulation:
```ini
simulate_timing=true
```

## Example Test Scenarios

### Run Packet Acceptance Test

```bash
# Terminal 1: Start simulator
python DCCSimulator.py

# Terminal 2: Run test
cd Scripts
python System.py
# Select: "1. Run Packet Acceptance Test"
```

The simulator will:
1. Respond to `command_station_start`
2. Provide voltage/current feedback
3. Track command station state
4. Respond to `command_station_stop`

### Test Timing Margin

```bash
# Terminal 1: Start simulator
python DCCSimulator.py

# Terminal 2: Run timing test
cd Scripts
python System.py
# Select: "2. Run Timing Margin Test"
```

The simulator will:
1. Accept parameter changes (`command_station_params`)
2. Track override parameters
3. Maintain state across multiple test iterations
4. Reset overrides when command station stops

### Create Scenario from Real Run

```bash
# 1. Run real test with hardware (logging_level=2)
cd Scripts
python RunPacketAcceptanceTest.py

# 2. Parse the log
cd ../Simulator
python LogParser.py c:\tmp\logs\test_20260220_143022.log packet_test

# 3. Configure simulator to use scenario
# Edit SimulatorConfig.txt:
#   response_mode=scenario
#   scenario_file=packet_test_scenario.json

# 4. Run simulator with learned scenario
python DCCSimulator.py

# 5. Run test again - simulator replays exact responses!
```

## Logging

### Simulator Logs

All RPC traffic is logged to `simulator_logs/simulator_YYYYMMDD_HHMMSS.log`:

```
[14:30:22.156] Opened serial port COM10
[14:30:22.157] Loaded response library from ResponseLibrary.json
[14:30:22.158] Logging to simulator_logs/simulator_20260220_143022.log
[14:30:22.159] Waiting for RPC requests...
[14:30:25.234] ← {"method":"command_station_start","params":{}}
[14:30:25.239] → {"status":"ok","message":"Command station started","loop":0}
[14:30:25.240] Command station started (loop=0)
```

### Control Logging

```ini
# Disable logging
enable_logging=false

# Change log directory
log_directory=c:\tmp\simulator_logs
```

## Architecture

```
┌─────────────────┐         ┌─────────────────┐
│  Test Scripts   │◄───────►│   Virtual Port  │
│   (COM9)        │  TCP/IP │   Pair Created  │
└─────────────────┘   or    │   by com0com    │
                    Serial  └─────────────────┘
                              ▲               ▼
                              │               │
                              │  ┌─────────────────────┐
                              └──│  DCC Simulator      │
                                 │  (COM10)            │
                                 │                     │
                                 │  • State Tracking  │
                                 │  • RPC Handlers    │
                                 │  • Response Gen    │
                                 │  • Logging         │
                                 └─────────────────────┘
```

## Files

- `DCCSimulator.py` - Main simulator program
- `SimulatorConfig.txt` - Configuration file
- `ResponseLibrary.json` - Default response templates
- `LogParser.py` - Log parsing utility
- `README.md` - This file

## Development

### Adding New RPC Methods

1. Add handler method to `DCCSimulator` class:
```python
def _handle_new_method(self, params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle new_method RPC."""
    # Process params
    # Update state
    return {"status": "ok", "result": "value"}
```

2. Register in `process_request()`:
```python
handlers = {
    "new_method": self._handle_new_method,
    ...
}
```

### Custom Response Logic

Override response generation by editing the handler methods. State is available via `self.state`.

## License

Part of DCC_tester project. See main repository for license details.

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review simulator logs in `simulator_logs/`
3. Test with verbose mode enabled
4. Verify virtual COM port setup

## Version History

- v1.0 (2026-02-20) - Initial release
  - Full RPC method support
  - Stateful simulation
  - Log parser utility
  - Realistic timing and analog feedback
