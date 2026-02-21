#!/usr/bin/env python3
"""
Log Parser for DCC RPC Simulator
=================================

Parses verbose log files from test scripts to extract RPC request/response pairs.
These pairs can be used to create realistic simulator scenarios or replay modes.

Usage:
    python LogParser.py <log_file> [output_file]

The parser looks for patterns like:
    → {"method":"...","params":{...}}
    ← {"status":"...","...":...}

Output formats:
    - JSON: Structured request/response pairs
    - Scenario: Ready-to-use scenario file
    - Stats: Summary statistics
"""

import sys
import os
import json
import re
from typing import List, Dict, Any, Tuple
from collections import defaultdict


class LogParser:
    """Parse verbose log files to extract RPC traffic."""
    
    def __init__(self, log_file: str):
        self.log_file = log_file
        self.rpc_pairs = []
        self.stats = defaultdict(int)
        self.errors = []
    
    def parse(self):
        """Parse the log file and extract RPC request/response pairs."""
        print(f"Parsing log file: {self.log_file}")
        
        if not os.path.exists(self.log_file):
            print(f"ERROR: Log file not found: {self.log_file}")
            return False
        
        with open(self.log_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        
        print(f"Read {len(lines)} lines")
        
        # State machine for parsing
        pending_request = None
        line_num = 0
        
        for line in lines:
            line_num += 1
            line = line.strip()
            
            # Look for outgoing request (→)
            if "→ {" in line:
                json_start = line.find("→ {")
                json_str = line[json_start + 2:].strip()
                
                try:
                    request = json.loads(json_str)
                    pending_request = (request, line_num)
                    self.stats["requests"] += 1
                except json.JSONDecodeError as e:
                    self.errors.append(f"Line {line_num}: Invalid request JSON: {e}")
                    pending_request = None
            
            # Look for incoming response (←)
            elif "← {" in line:
                json_start = line.find("← {")
                json_str = line[json_start + 2:].strip()
                
                try:
                    response = json.loads(json_str)
                    self.stats["responses"] += 1
                    
                    # Match with pending request
                    if pending_request:
                        request, req_line = pending_request
                        self.rpc_pairs.append({
                            "request": request,
                            "response": response,
                            "line_num": req_line,
                            "method": request.get("method", "unknown")
                        })
                        
                        # Update method stats
                        method = request.get("method", "unknown")
                        self.stats[f"method_{method}"] += 1
                        
                        pending_request = None
                    else:
                        self.errors.append(f"Line {line_num}: Response without matching request")
                
                except json.JSONDecodeError as e:
                    self.errors.append(f"Line {line_num}: Invalid response JSON: {e}")
        
        # Check for unmatched requests
        if pending_request:
            self.errors.append(f"Line {pending_request[1]}: Request without matching response")
        
        print(f"Extracted {len(self.rpc_pairs)} RPC pairs")
        
        return True
    
    def print_stats(self):
        """Print parsing statistics."""
        print("\n" + "=" * 70)
        print("Parsing Statistics")
        print("=" * 70)
        print(f"Total requests found:  {self.stats['requests']}")
        print(f"Total responses found: {self.stats['responses']}")
        print(f"Matched RPC pairs:     {len(self.rpc_pairs)}")
        print(f"Errors:                {len(self.errors)}")
        print()
        
        # Method breakdown
        print("Methods used:")
        for key in sorted(self.stats.keys()):
            if key.startswith("method_"):
                method = key[7:]
                count = self.stats[key]
                print(f"  {method:40s} {count:5d}")
        
        if self.errors:
            print("\nErrors encountered:")
            for error in self.errors[:10]:  # Show first 10 errors
                print(f"  {error}")
            if len(self.errors) > 10:
                print(f"  ... and {len(self.errors) - 10} more")
    
    def save_json(self, output_file: str):
        """Save extracted RPC pairs as JSON."""
        print(f"\nSaving to JSON: {output_file}")
        
        output = {
            "source_file": self.log_file,
            "total_pairs": len(self.rpc_pairs),
            "stats": dict(self.stats),
            "rpc_pairs": self.rpc_pairs
        }
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        
        print(f"✓ Saved {len(self.rpc_pairs)} pairs to {output_file}")
    
    def save_scenario(self, output_file: str, scenario_name: str = "parsed_scenario"):
        """Save extracted RPC pairs as a simulator scenario."""
        print(f"\nSaving as scenario: {output_file}")
        
        scenario = {
            "name": scenario_name,
            "description": f"Auto-generated from {os.path.basename(self.log_file)}",
            "source_file": self.log_file,
            "sequence": []
        }
        
        for pair in self.rpc_pairs:
            scenario["sequence"].append({
                "request": pair["request"],
                "response": pair["response"]
            })
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(scenario, f, indent=2)
        
        print(f"✓ Saved scenario with {len(self.rpc_pairs)} steps to {output_file}")
    
    def analyze_methods(self) -> Dict[str, List[Dict[str, Any]]]:
        """Analyze and group RPC pairs by method."""
        methods = defaultdict(list)
        
        for pair in self.rpc_pairs:
            method = pair["method"]
            methods[method].append(pair)
        
        return methods
    
    def save_method_summary(self, output_file: str):
        """Save a summary of all methods and their typical responses."""
        print(f"\nSaving method summary: {output_file}")
        
        methods = self.analyze_methods()
        summary = {}
        
        for method, pairs in methods.items():
            # Get unique parameter combinations
            param_variations = []
            response_variations = []
            
            for pair in pairs:
                params = pair["request"].get("params", {})
                response = pair["response"]
                
                if params not in param_variations:
                    param_variations.append(params)
                if response not in response_variations:
                    response_variations.append(response)
            
            summary[method] = {
                "count": len(pairs),
                "unique_param_sets": len(param_variations),
                "unique_responses": len(response_variations),
                "example_params": param_variations[:3],  # First 3 examples
                "example_responses": response_variations[:3]
            }
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        
        print(f"✓ Saved method summary for {len(methods)} methods to {output_file}")
    
    def create_response_mapping(self) -> Dict[str, Any]:
        """Create a response mapping for each method based on most common responses."""
        methods = self.analyze_methods()
        mapping = {}
        
        for method, pairs in methods.items():
            # Find most common response for this method
            response_counts = defaultdict(int)
            
            for pair in pairs:
                response_json = json.dumps(pair["response"], sort_keys=True)
                response_counts[response_json] += 1
            
            # Get most common
            most_common = max(response_counts.items(), key=lambda x: x[1])
            mapping[method] = json.loads(most_common[0])
        
        return mapping


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python LogParser.py <log_file> [output_prefix]")
        print()
        print("Parses verbose log files to extract RPC request/response pairs.")
        print()
        print("Output files:")
        print("  <output_prefix>_pairs.json     - All RPC pairs")
        print("  <output_prefix>_scenario.json  - Simulator scenario format")
        print("  <output_prefix>_summary.json   - Method summary")
        print()
        sys.exit(1)
    
    log_file = sys.argv[1]
    
    # Generate output prefix from log filename if not provided
    if len(sys.argv) > 2:
        output_prefix = sys.argv[2]
    else:
        base_name = os.path.splitext(os.path.basename(log_file))[0]
        output_prefix = f"parsed_{base_name}"
    
    # Parse the log file
    parser = LogParser(log_file)
    
    if not parser.parse():
        sys.exit(1)
    
    # Print statistics
    parser.print_stats()
    
    # Save in multiple formats
    parser.save_json(f"{output_prefix}_pairs.json")
    parser.save_scenario(f"{output_prefix}_scenario.json")
    parser.save_method_summary(f"{output_prefix}_summary.json")
    
    print("\n" + "=" * 70)
    print("Parsing complete!")
    print("=" * 70)
    print("\nGenerated files:")
    print(f"  {output_prefix}_pairs.json     - All extracted RPC pairs")
    print(f"  {output_prefix}_scenario.json  - Simulator scenario")
    print(f"  {output_prefix}_summary.json   - Method summary")
    print()


if __name__ == "__main__":
    main()
