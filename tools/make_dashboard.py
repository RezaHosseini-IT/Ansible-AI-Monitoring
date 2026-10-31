#!/usr/bin/env python3

import json
import os
import sys

# Constants
PCT = [(None, "green"), (70, "orange"), (90, "red")]
TEMP = [(None, "green"), (70, "orange"), (85, "red")]

# Row definitions
ROWS = [
    # System row
    (
        "System", 5, [
            {
                "title": "CPU usage",
                "type": "gauge",
                "unit": "percent",
                "min": 0,
                "max": 100,
                "thresholds": PCT,
                "targets": [("100 - (avg(rate(node_cpu_seconds_total{mode=\"idle\"}[1m])) * 100)", "{{mode}}")]
            },
            {
                "title": "Memory used",
                "type": "gauge",
                "unit": "percent",
                "min": 0,
                "max": 100,
                "thresholds": PCT,
                "targets": [("(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100", "{{mode}}")]
            },
            {
                "title": "Disk used (/)",
                "type": "gauge",
                "unit": "percent",
                "min": 0,
                "max": 100,
                "thresholds": PCT,
                "targets": [("max(100 - (node_filesystem_avail_bytes{mountpoint=\"/\",fstype!=\"rootfs\"} / node_filesystem_size_bytes{mountpoint=\"/\",fstype!=\"rootfs\"} * 100))", "{{device}}")]
            },
            {
                "title": "Load 1m",
                "type": "stat",
                "unit": "none",
                "targets": [("node_load1", "{{mode}}")]
            },
            {
                "title": "Uptime",
                "type": "stat",
                "unit": "s",
                "targets": [("time() - node_boot_time_seconds", "{{mode}}")]
            }
        ]
    ),
    
    # System over time row
    (
        "System over time", 8, [
            {
                "title": "CPU by mode",
                "type": "timeseries",
                "unit": "percent",
                "targets": [("sum by (mode) (rate(node_cpu_seconds_total{mode!=\"idle\"}[1m])) * 100", "{{mode}}")]
            },
            {
                "title": "Memory",
                "type": "timeseries",
                "unit": "bytes",
                "targets": [
                    ("node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes", "Used"),
                    ("node_memory_MemTotal_bytes", "Total")
                ]
            },
            {
                "title": "Disk I/O",
                "type": "timeseries",
                "unit": "Bps",
                "targets": [
                    ("rate(node_disk_read_bytes_total[1m])", "{{device}} read"),
                    ("rate(node_disk_written_bytes_total[1m])", "{{device}} write")
                ]
            },
            {
                "title": "CPU temperature",
                "type": "timeseries",
                "unit": "celsius",
                "thresholds": TEMP,
                "targets": [("node_hwmon_temp_celsius * on(chip) group_left(chip_name) node_hwmon_chip_names{chip_name=~\"k10temp|coretemp\"}", "{{chip_name}} {{sensor}}")]
            }
        ]
    ),
    
    # GPU load and memory row
    (
        "GPU load and memory", 8, [
            {
                "title": "GPU utilization",
                "type": "timeseries",
                "unit": "percent",
                "min": 0,
                "max": 100,
                "targets": [("node_drm_gpu_busy_percent", "{{card}}")]
            },
            {
                "title": "VRAM",
                "type": "timeseries",
                "unit": "bytes",
                "targets": [
                    ("node_drm_memory_vram_used_bytes", "{{card}} used"),
                    ("node_drm_memory_vram_size_bytes", "{{card}} total")
                ]
            },
            {
                "title": "VRAM used %",
                "type": "bargauge",
                "unit": "percent",
                "min": 0,
                "max": 100,
                "thresholds": PCT,
                "targets": [("node_drm_memory_vram_used_bytes / node_drm_memory_vram_size_bytes * 100", "{{card}}")]
            }
        ]
    ),
    
    # GPU thermals and power row
    (
        "GPU thermals and power", 8, [
            {
                "title": "GPU temperature",
                "type": "timeseries",
                "unit": "celsius",
                "thresholds": TEMP,
                "targets": [("node_hwmon_temp_celsius{sensor=\"temp1\"} * on(chip) group_left(card) gpu_card_info", "{{card}}")]
            },
            {
                "title": "GPU power",
                "type": "timeseries",
                "unit": "watt",
                "targets": [("node_hwmon_power_watt * on(chip) group_left(card) gpu_card_info", "{{card}}")]
            },
            {
                "title": "GPU fan",
                "type": "timeseries",
                "unit": "rotrpm",
                "targets": [("node_hwmon_fan_rpm * on(chip) group_left(card) gpu_card_info", "{{card}}")]
            }
        ]
    ),
    
    # GPU clocks and PCIe row
    (
        "GPU clocks and PCIe", 6, [
            {
                "title": "GPU clocks (MHz)",
                "type": "timeseries",
                "targets": [("node_hwmon_freq_freq_mhz * on(chip) group_left(card) gpu_card_info", "{{card}} {{sensor}}")]
            },
            {
                "title": "PCIe link width",
                "type": "stat",
                "targets": [("gpu_pcie_link_width", "{{card}}")]
            },
            {
                "title": "PCIe link speed (GT/s)",
                "type": "stat",
                "targets": [("gpu_pcie_link_speed_gts", "{{card}}")]
            }
        ]
    ),
    
    # Ollama row
    (
        "Ollama", 5, [
            {
                "title": "Ollama API up",
                "type": "stat",
                "targets": [("ollama_up", "up")]
            },
            {
                "title": "Models loaded",
                "type": "stat",
                "targets": [("ollama_models_loaded", "")]
            },
            {
                "title": "GPU offload %",
                "type": "gauge",
                "unit": "percent",
                "min": 0,
                "max": 100,
                "targets": [("ollama_model_size_vram_bytes / ollama_model_size_bytes * 100", "{{model}}")]
            },
            {
                "title": "Context length",
                "type": "stat",
                "targets": [("ollama_model_context_length", "{{model}}")]
            },
            {
                "title": "Unloads in",
                "type": "stat",
                "unit": "s",
                "targets": [("ollama_model_expires_timestamp_seconds - time()", "{{model}}")]
            }
        ]
    ),
    
    # Ollama resources row
    (
        "Ollama resources", 8, [
            {
                "title": "Model size",
                "type": "timeseries",
                "unit": "bytes",
                "targets": [
                    ("ollama_model_size_bytes", "{{model}} total"),
                    ("ollama_model_size_vram_bytes", "{{model}} in VRAM")
                ]
            },
            {
                "title": "Ollama service CPU",
                "type": "timeseries",
                "unit": "percent",
                "targets": [("sum(rate(container_cpu_usage_seconds_total{id=\"/system.slice/ollama.service\"}[1m])) * 100", "ollama")]
            },
            {
                "title": "Ollama service memory",
                "type": "timeseries",
                "unit": "bytes",
                "targets": [("container_memory_working_set_bytes{id=\"/system.slice/ollama.service\"}", "ollama")]
            }
        ]
    ),
    
    # Docker containers row
    (
        "Docker containers", 5, [
            {
                "title": "Running containers",
                "type": "stat",
                "targets": [("count(container_memory_working_set_bytes{name!=\"\"})", "")]
            },
            {
                "title": "Containers CPU total",
                "type": "stat",
                "unit": "percent",
                "targets": [("sum(rate(container_cpu_usage_seconds_total{name!=\"\"}[1m])) * 100", "")]
            },
            {
                "title": "Containers memory total",
                "type": "stat",
                "unit": "bytes",
                "targets": [("sum(container_memory_working_set_bytes{name!=\"\"})", "")]
            }
        ]
    ),
    
    # Docker CPU and memory row
    (
        "Docker CPU and memory", 8, [
            {
                "title": "CPU per container",
                "type": "timeseries",
                "unit": "percent",
                "targets": [("sum by (name) (rate(container_cpu_usage_seconds_total{name!=\"\"}[1m])) * 100", "{{name}}")]
            },
            {
                "title": "Memory per container",
                "type": "timeseries",
                "unit": "bytes",
                "targets": [("sum by (name) (container_memory_working_set_bytes{name!=\"\"})", "{{name}}")]
            }
        ]
    ),
    
    # Docker network and disk row
    (
        "Docker network and disk", 8, [
            {
                "title": "Network per container",
                "type": "timeseries",
                "unit": "Bps",
                "targets": [
                    ("sum by (name) (rate(container_network_receive_bytes_total{name!=\"\"}[1m]))", "{{name}} rx"),
                    ("sum by (name) (rate(container_network_transmit_bytes_total{name!=\"\"}[1m]))", "{{name}} tx")
                ]
            },
            {
                "title": "Disk I/O per container",
                "type": "timeseries",
                "unit": "Bps",
                "targets": [
                    ("sum by (name) (rate(container_fs_reads_bytes_total{name!=\"\"}[1m]))", "{{name}} read"),
                    ("sum by (name) (rate(container_fs_writes_bytes_total{name!=\"\"}[1m]))", "{{name}} write")
                ]
            },
            {
                "title": "Container uptime",
                "type": "bargauge",
                "unit": "s",
                "targets": [("time() - container_start_time_seconds{name!=\"\"}", "{{name}}")]
            }
        ]
    ),
    
    # Prometheus row
    (
        "Prometheus", 5, [
            {
                "title": "Scrape targets",
                "type": "stat",
                "targets": [("up", "{{job}}")]
            },
            {
                "title": "Time series in head",
                "type": "stat",
                "targets": [("prometheus_tsdb_head_series", "")]
            },
            {
                "title": "Prometheus memory",
                "type": "stat",
                "unit": "bytes",
                "targets": [("process_resident_memory_bytes{job=\"prometheus\"}", "")]
            }
        ]
    )
]

def create_panel(panel_def, panel_id, ref_id):
    """Create a Grafana panel JSON structure."""
    panel = {
        "id": panel_id,
        "title": panel_def["title"],
        "type": panel_def["type"],
        "datasource": {"type": "prometheus", "uid": "${datasource}"},
        "targets": []
    }
    
    # Add targets
    for i, (expr, legend) in enumerate(panel_def["targets"]):
        target = {
            "refId": chr(ord('A') + i),
            "expr": expr,
            "legendFormat": legend,
            "datasource": {"type": "prometheus", "uid": "${datasource}"},
            "editorMode": "code",
            "range": True
        }
        panel["targets"].append(target)
    
    # Set fieldConfig
    field_config = {
        "defaults": {}
    }
    
    if "unit" in panel_def:
        field_config["defaults"]["unit"] = panel_def["unit"]
    
    if "min" in panel_def:
        field_config["defaults"]["min"] = panel_def["min"]
        
    if "max" in panel_def:
        field_config["defaults"]["max"] = panel_def["max"]
    
    if "thresholds" in panel_def:
        steps = []
        for value, color in panel_def["thresholds"]:
            step = {"color": color}
            if value is not None:
                step["value"] = value
            else:
                step["value"] = None
            steps.append(step)
        field_config["defaults"]["thresholds"] = {
            "mode": "absolute",
            "steps": steps
        }
    
    panel["fieldConfig"] = field_config
    
    # Set options based on panel type
    if panel_def["type"] == "timeseries":
        panel["options"] = {
            "legend": {
                "displayMode": "table",
                "placement": "bottom",
                "calcs": ["lastNotNull", "max"]
            },
            "tooltip": {
                "mode": "multi",
                "sort": "desc"
            }
        }
    elif panel_def["type"] in ["stat", "gauge", "bargauge"]:
        panel["options"] = {
            "reduceOptions": {
                "calcs": ["lastNotNull"],
                "fields": "",
                "values": False
            }
        }
    
    # Set grid position
    panel["gridPos"] = {"h": 0, "w": 0, "x": 0, "y": 0}
    
    return panel

def create_dashboard(out_path):
    """Create the dashboard JSON file."""
    # Create dashboard structure
    dashboard = {
        "uid": "homelab-overview",
        "title": "Homelab Overview",
        "tags": ["homelab"],
        "timezone": "browser",
        "refresh": "15s",
        "time": {
            "from": "now-1h",
            "to": "now"
        },
        "schemaVersion": 39,
        "editable": True,
        "templating": {
            "list": [
                {
                    "name": "datasource",
                    "label": "Datasource",
                    "type": "datasource",
                    "query": "prometheus",
                    "current": {},
                    "hide": 0
                }
            ]
        },
        "panels": []
    }
    
    # Add row panels and their content panels
    panel_id = 1
    for row_title, height, panels in ROWS:
        # Add row panel
        row_panel = {
            "id": panel_id,
            "title": row_title,
            "type": "row",
            "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0}
        }
        dashboard["panels"].append(row_panel)
        panel_id += 1
        
        # Calculate panel width
        if panels:
            panel_width = 24 // len(panels)
        else:
            panel_width = 24
            
        # Add content panels
        for i, panel_def in enumerate(panels):
            # Create the panel
            panel = create_panel(panel_def, panel_id, chr(ord('A') + i))
            
            # Set grid position
            panel["gridPos"]["h"] = height
            panel["gridPos"]["w"] = panel_width
            panel["gridPos"]["x"] = i * panel_width
            panel["gridPos"]["y"] = 0
            
            dashboard["panels"].append(panel)
            panel_id += 1
    
    # Serialize to JSON
    json_content = json.dumps(dashboard, indent=2, sort_keys=True) + '\n'
    
    # Create parent directories if needed
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    
    # Check if file already exists with same content
    try:
        with open(out_path, 'r') as f:
            existing_content = f.read()
    except FileNotFoundError:
        existing_content = None
    
    # Write only if content differs
    if existing_content != json_content:
        with open(out_path, 'w') as f:
            f.write(json_content)
        print("changed")
    else:
        print("unchanged")

if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--out":
        print("Usage: make_dashboard.py --out PATH")
        sys.exit(1)
    
    out_path = sys.argv[2]
    create_dashboard(out_path)
