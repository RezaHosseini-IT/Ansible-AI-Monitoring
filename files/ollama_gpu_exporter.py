#!/usr/bin/env python3

import argparse
import json
import os
import re
import requests
import time
from datetime import datetime

def escape_label_value(value):
    """Escape label values for Prometheus text format."""
    return value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

def parse_iso8601_timestamp(timestamp_str):
    """Parse ISO 8601 timestamp and convert to Unix seconds."""
    try:
        # Remove fractional seconds if present
        timestamp_str = re.sub(r'\.\d+', '', timestamp_str)
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return int(dt.timestamp())
    except Exception:
        return None

def get_ollama_metrics(ollama_url):
    """Get Ollama metrics from /api/ps endpoint."""
    metrics = {
        'ollama_up': 0,
        'ollama_models_loaded': 0,
        'ollama_model_size_bytes': {},
        'ollama_model_size_vram_bytes': {},
        'ollama_model_context_length': {},
        'ollama_model_expires_timestamp_seconds': {}
    }
    
    try:
        response = requests.get(f"{ollama_url}/api/ps", timeout=3)
        if response.status_code == 200:
            data = response.json()
            metrics['ollama_up'] = 1
            models = data.get('models', [])
            metrics['ollama_models_loaded'] = len(models)
            
            for model in models:
                model_name = escape_label_value(model.get('name', ''))
                if not model_name:
                    continue
                    
                # Model size metrics
                size = model.get('size')
                if size is not None:
                    metrics['ollama_model_size_bytes'][model_name] = size
                    
                size_vram = model.get('size_vram')
                if size_vram is not None:
                    metrics['ollama_model_size_vram_bytes'][model_name] = size_vram
                    
                # Context length
                context_length = model.get('context_length')
                if context_length is not None:
                    metrics['ollama_model_context_length'][model_name] = context_length
                    
                # Expires timestamp
                expires_at = model.get('expires_at')
                if expires_at:
                    expires_seconds = parse_iso8601_timestamp(expires_at)
                    if expires_seconds is not None:
                        metrics['ollama_model_expires_timestamp_seconds'][model_name] = expires_seconds
    except Exception:
        pass
    
    return metrics

def get_gpu_metrics():
    """Get GPU metrics from /sys/class/drm."""
    metrics = {
        'gpu_card_info': {},
        'gpu_pcie_link_width': {},
        'gpu_pcie_link_speed_gts': {}
    }
    
    try:
        # Find all card directories
        cards = []
        for item in os.listdir('/sys/class/drm'):
            if re.match(r'^card[0-9]+$', item):
                cards.append(item)
        
        for card in sorted(cards):
            card_path = f'/sys/class/drm/{card}'
            
            # Get chip info
            try:
                device_path = os.path.join(card_path, 'device')
                if os.path.exists(device_path):
                    real_path = os.path.realpath(device_path)
                    if real_path.startswith('/sys/devices/'):
                        chip = real_path[len('/sys/devices/'):]
                        # Keep only last two path components and replace dots with underscores
                        parts = chip.split('/')
                        if len(parts) >= 2:
                            chip = '_'.join(parts[-2:]).replace('.', '_')
                        else:
                            chip = chip.replace('/', '_').replace('.', '_')
                        metrics['gpu_card_info'][card] = chip
            except Exception:
                pass
            
            # Get PCIe link width
            try:
                link_width_file = os.path.join(card_path, 'device', 'current_link_width')
                if os.path.exists(link_width_file):
                    with open(link_width_file, 'r') as f:
                        width = f.read().strip()
                        if width.isdigit():
                            metrics['gpu_pcie_link_width'][card] = int(width)
            except Exception:
                pass
            
            # Get PCIe link speed
            try:
                link_speed_file = os.path.join(card_path, 'device', 'current_link_speed')
                if os.path.exists(link_speed_file):
                    with open(link_speed_file, 'r') as f:
                        speed_line = f.read().strip()
                        match = re.match(r'^(\d+(?:\.\d+)?)\s*GT/s', speed_line)
                        if match:
                            speed = float(match.group(1))
                            metrics['gpu_pcie_link_speed_gts'][card] = speed
            except Exception:
                pass
                
    except Exception:
        pass
    
    return metrics

def write_metrics(out_path, ollama_metrics, gpu_metrics):
    """Write metrics to file in Prometheus text format."""
    lines = []
    
    # Add HELP and TYPE comments for each metric
    lines.append('# HELP ollama_up Whether Ollama is up')
    lines.append('# TYPE ollama_up gauge')
    lines.append(f'ollama_up {ollama_metrics["ollama_up"]}')
    
    lines.append('# HELP ollama_models_loaded Number of models loaded')
    lines.append('# TYPE ollama_models_loaded gauge')
    lines.append(f'ollama_models_loaded {ollama_metrics["ollama_models_loaded"]}')
    
    lines.append('# HELP ollama_model_size_bytes Size of loaded model in bytes')
    lines.append('# TYPE ollama_model_size_bytes gauge')
    for model, size in ollama_metrics['ollama_model_size_bytes'].items():
        lines.append(f'ollama_model_size_bytes{{model="{model}"}} {size}')
    
    lines.append('# HELP ollama_model_size_vram_bytes Size of model in VRAM bytes')
    lines.append('# TYPE ollama_model_size_vram_bytes gauge')
    for model, size in ollama_metrics['ollama_model_size_vram_bytes'].items():
        lines.append(f'ollama_model_size_vram_bytes{{model="{model}"}} {size}')
    
    lines.append('# HELP ollama_model_context_length Context length of loaded model')
    lines.append('# TYPE ollama_model_context_length gauge')
    for model, length in ollama_metrics['ollama_model_context_length'].items():
        lines.append(f'ollama_model_context_length{{model="{model}"}} {length}')
    
    lines.append('# HELP ollama_model_expires_timestamp_seconds Unix timestamp when model expires')
    lines.append('# TYPE ollama_model_expires_timestamp_seconds gauge')
    for model, timestamp in ollama_metrics['ollama_model_expires_timestamp_seconds'].items():
        lines.append(f'ollama_model_expires_timestamp_seconds{{model="{model}"}} {timestamp}')
    
    lines.append('# HELP gpu_card_info GPU card information')
    lines.append('# TYPE gpu_card_info gauge')
    for card, chip in gpu_metrics['gpu_card_info'].items():
        lines.append(f'gpu_card_info{{card="{card}",chip="{chip}"}} 1')
    
    lines.append('# HELP gpu_pcie_link_width Current PCIe link width')
    lines.append('# TYPE gpu_pcie_link_width gauge')
    for card, width in gpu_metrics['gpu_pcie_link_width'].items():
        lines.append(f'gpu_pcie_link_width{{card="{card}"}} {width}')
    
    lines.append('# HELP gpu_pcie_link_speed_gts Current PCIe link speed in GT/s')
    lines.append('# TYPE gpu_pcie_link_speed_gts gauge')
    for card, speed in gpu_metrics['gpu_pcie_link_speed_gts'].items():
        lines.append(f'gpu_pcie_link_speed_gts{{card="{card}"}} {speed}')
    
    # Write atomically
    tmp_path = f"{out_path}.tmp"
    with open(tmp_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    os.replace(tmp_path, out_path)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True, help='Output file path')
    parser.add_argument('--loops', type=int, default=1, help='Number of loops (default: 1)')
    parser.add_argument('--interval', type=int, default=15, help='Interval between loops in seconds (default: 15)')
    parser.add_argument('--ollama', default='http://127.0.0.1:11434', help='Ollama API URL (default: http://127.0.0.1:11434)')
    
    args = parser.parse_args()
    
    for i in range(args.loops):
        try:
            ollama_metrics = get_ollama_metrics(args.ollama)
            gpu_metrics = get_gpu_metrics()
            write_metrics(args.out, ollama_metrics, gpu_metrics)
        except Exception:
            # Skip on any error
            pass
        
        # Sleep between loops (except after the last one)
        if i < args.loops - 1:
            time.sleep(args.interval)

if __name__ == '__main__':
    main()
