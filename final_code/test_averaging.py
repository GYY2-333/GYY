#!/usr/bin/env python3
"""
Test script to demonstrate the DDC112U averaging functionality.
This simulates the averaging algorithm used in the final code.
"""

import random
import statistics

# Averaging parameters (same as in main.cpp)
AVERAGING_SAMPLES = 16
MIN_SAMPLES_FOR_OUTPUT = 8

# Calibration factors (same as in main.cpp)
CALIBRATION_FACTOR = [1.024, 1.018, 1.021, 1.019, 1.022, 1.020, 1.023, 1.025]

# Full scale values for each range (same as in main.cpp)
IFS_A = [2.0e-6, 1.0e-7, 2.0e-7, 3.0e-7, 4.0e-7, 5.0e-7, 6.0e-7, 7.0e-7]

# Current display scale factors
current_scale = [1e6, 1e9, 1e9, 1e9, 1e9, 1e9, 1e9, 1e9]
current_units = ["μA", "nA", "nA", "nA", "nA", "nA", "nA", "nA"]

class DDC112Averaging:
    def __init__(self):
        self.sample_buffer = [0] * AVERAGING_SAMPLES
        self.buffer_index = 0
        self.sample_count = 0
        self.buffer_full = False
        self.current_range = 0
    
    def add_sample(self, sample):
        """Add a sample to the averaging buffer"""
        self.sample_buffer[self.buffer_index] = sample
        self.buffer_index = (self.buffer_index + 1) % AVERAGING_SAMPLES
        
        if self.sample_count < AVERAGING_SAMPLES:
            self.sample_count += 1
        else:
            self.buffer_full = True
    
    def calculate_average(self):
        """Calculate the average of current samples"""
        if self.sample_count < MIN_SAMPLES_FOR_OUTPUT:
            return 0.0  # Not enough samples
        
        count = AVERAGING_SAMPLES if self.buffer_full else self.sample_count
        samples = self.sample_buffer[:count]
        return sum(samples) / count
    
    def get_stable_current(self):
        """Get the averaged and calibrated current reading"""
        avg_raw = self.calculate_average()
        if avg_raw == 0.0:
            return 0.0
        
        # Same calculation as in main.cpp
        ifs = IFS_A[self.current_range]
        calibration = CALIBRATION_FACTOR[self.current_range]
        full_scale = float((1 << 19) - 1)  # 20-bit signed full scale
        
        current_amp = (avg_raw / full_scale) * ifs * calibration
        return current_amp
    
    def get_display_current(self):
        """Get current in display units"""
        current_amp = self.get_stable_current()
        if current_amp == 0.0:
            return 0.0, "N/A"
        
        display_current = current_amp * current_scale[self.current_range]
        unit = current_units[self.current_range]
        return display_current, unit
    
    def set_range(self, range_val):
        """Set measurement range and reset buffer"""
        if 0 <= range_val <= 7:
            self.current_range = range_val
            # Reset buffer when changing ranges
            self.buffer_index = 0
            self.sample_count = 0
            self.buffer_full = False
            return True
        return False

def simulate_noisy_signal(base_value, noise_level=0.1):
    """Simulate a noisy ADC reading"""
    noise = random.uniform(-noise_level, noise_level) * base_value
    return int(base_value + noise)

def test_averaging():
    """Test the averaging functionality"""
    print("DDC112U Software Averaging Test")
    print("=" * 40)
    
    avg_system = DDC112Averaging()
    
    # Test with range 1 (100 nA scale)
    avg_system.set_range(1)
    print(f"Testing with Range 1 (100 nA scale, Cal={CALIBRATION_FACTOR[1]})")
    print()
    
    # Simulate a stable 50 nA signal with noise
    base_signal = 250000  # Raw ADC value for ~50 nA
    
    print("Sample | Raw Value | Avg Value | Current (nA) | Samples Used")
    print("-" * 65)
    
    for i in range(25):  # Collect 25 samples
        # Add noise to simulate real conditions
        noisy_sample = simulate_noisy_signal(base_signal, 0.05)  # 5% noise
        avg_system.add_sample(noisy_sample)
        
        display_current, unit = avg_system.get_display_current()
        samples_used = "N/A" if display_current == 0.0 else (AVERAGING_SAMPLES if avg_system.buffer_full else avg_system.sample_count)
        
        print(f"{i+1:6d} | {noisy_sample:9d} | {avg_system.calculate_average():9.1f} | {display_current:10.3f} | {samples_used}")
        
        if i == 7:  # After minimum samples
            print("       | -------- Stable output starts --------")
    
    print()
    print("Noise Reduction Analysis:")
    print("-" * 30)
    
    # Compare with and without averaging for the last 16 samples
    raw_samples = []
    avg_samples = []
    
    # Reset for comparison test
    avg_system = DDC112Averaging()
    avg_system.set_range(1)
    
    for i in range(50):
        noisy_sample = simulate_noisy_signal(base_signal, 0.05)
        
        # Raw calculation (no averaging)
        ifs = IFS_A[1]
        calibration = CALIBRATION_FACTOR[1]
        full_scale = float((1 << 19) - 1)
        raw_current = (noisy_sample / full_scale) * ifs * calibration * current_scale[1]
        
        # Averaged calculation
        avg_system.add_sample(noisy_sample)
        avg_current, _ = avg_system.get_display_current()
        
        if i >= 20:  # After buffer is full
            raw_samples.append(raw_current)
            if avg_current != 0.0:
                avg_samples.append(avg_current)
    
    if raw_samples and avg_samples:
        raw_std = statistics.stdev(raw_samples)
        avg_std = statistics.stdev(avg_samples)
        noise_reduction = (raw_std - avg_std) / raw_std * 100
        
        print(f"Raw readings std dev:  {raw_std:.3f} nA")
        print(f"Averaged readings std dev: {avg_std:.3f} nA")
        print(f"Noise reduction: {noise_reduction:.1f}%")
    
    print()
    print("Calibration Factor Test:")
    print("-" * 25)
    for range_val in range(8):
        print(f"Range {range_val}: Calibration = {CALIBRATION_FACTOR[range_val]:.3f}, "
              f"Full Scale = {IFS_A[range_val] * current_scale[range_val]:.0f} {current_units[range_val]}")

if __name__ == "__main__":
    test_averaging()