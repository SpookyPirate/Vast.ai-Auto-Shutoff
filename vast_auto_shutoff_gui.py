#!/usr/bin/env python3
"""
Vast.ai Auto Shutoff GUI

A graphical user interface for the Vast.ai Auto Shutoff script.
Allows users to configure settings and monitor the status of the application.
"""

import os
import sys
import configparser
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime
import json
import glob
import requests
import psutil
import shutil

# Set HOME environment variable if it doesn't exist (for vastai package on Windows)
if os.name == 'nt' and 'HOME' not in os.environ:
    os.environ['HOME'] = os.environ.get('USERPROFILE', '')

try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
        QLabel, QLineEdit, QPushButton, QTabWidget, QTextEdit, 
        QFormLayout, QGroupBox, QMessageBox, QDialog, QTableWidget, 
        QTableWidgetItem, QHeaderView, QAbstractItemView, QCheckBox,
        QDoubleSpinBox, QProgressBar, QSplitter, QStatusBar
    )
    from PyQt5.QtCore import (
        Qt, QThread, pyqtSignal, QTimer, QDateTime, QProcess
    )
    from PyQt5.QtGui import QColor, QTextCursor, QFont, QPalette
except ImportError as e:
    print(f"Error importing PyQt5: {e}")
    print("Please install PyQt5 with: pip install PyQt5")
    sys.exit(1)

# Define colors for the UI
SUCCESS_COLOR = QColor(76, 175, 80)  # Green
WARNING_COLOR = QColor(255, 152, 0)  # Orange
ERROR_COLOR = QColor(244, 67, 54)    # Red
TEXT_COLOR = QColor(255, 255, 255)   # White
BACKGROUND_COLOR = QColor(33, 33, 33) # Dark gray

# Dark theme colors
DARK_COLOR = QColor(53, 53, 53)
DARKER_COLOR = QColor(35, 35, 35)
DARKEST_COLOR = QColor(25, 25, 25)
ACCENT_COLOR = QColor(42, 130, 218)

class InstanceSelectionDialog(QDialog):
    """Dialog for selecting instances to delete."""
    
    def __init__(self, instances, parent=None):
        super().__init__(parent)
        self.instances = instances
        self.selected_instances = []
        self.initUI()
    
    def initUI(self):
        """Initialize the dialog UI."""
        self.setWindowTitle("Select Instances to Delete")
        self.setMinimumSize(800, 400)
        
        layout = QVBoxLayout(self)
        
        # Instructions label
        instructions = QLabel("Select the instances you want to delete:")
        layout.addWidget(instructions)
        
        # Create table for instances
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Select", "ID", "Label", "Machine", "GPU", "Status"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)  # Make Label column stretch
        
        # Populate table with instances
        self.table.setRowCount(len(self.instances))
        for row, instance in enumerate(self.instances):
            # Checkbox for selection
            checkbox = QCheckBox()
            checkbox.setChecked(True)  # Default to selected
            checkbox_cell = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_cell)
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(row, 0, checkbox_cell)
            
            # Instance details
            instance_id = instance.get('id') or instance.get('instance_id', 'Unknown')
            self.table.setItem(row, 1, QTableWidgetItem(str(instance_id)))
            
            label = instance.get('label', 'No Label')
            self.table.setItem(row, 2, QTableWidgetItem(label))
            
            machine = instance.get('machine_name', 'Unknown')
            self.table.setItem(row, 3, QTableWidgetItem(machine))
            
            gpu = instance.get('gpu_name', 'Unknown')
            self.table.setItem(row, 4, QTableWidgetItem(gpu))
            
            status = instance.get('status', 'Unknown')
            status_item = QTableWidgetItem(status)
            if status.lower() == 'running':
                status_item.setForeground(SUCCESS_COLOR)
            elif status.lower() in ['error', 'failed']:
                status_item.setForeground(ERROR_COLOR)
            self.table.setItem(row, 5, status_item)
        
        layout.addWidget(self.table)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.selectAll)
        button_layout.addWidget(select_all_btn)
        
        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(self.deselectAll)
        button_layout.addWidget(deselect_all_btn)
        
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        delete_btn = QPushButton("Delete Selected")
        delete_btn.clicked.connect(self.acceptSelected)
        delete_btn.setStyleSheet("""
            background-color: #D32F2F;
            color: white;
            font-weight: bold;
        """)
        button_layout.addWidget(delete_btn)
        
        layout.addLayout(button_layout)
    
    def selectAll(self):
        """Select all instances."""
        for row in range(self.table.rowCount()):
            checkbox_cell = self.table.cellWidget(row, 0)
            checkbox = checkbox_cell.findChild(QCheckBox)
            checkbox.setChecked(True)
    
    def deselectAll(self):
        """Deselect all instances."""
        for row in range(self.table.rowCount()):
            checkbox_cell = self.table.cellWidget(row, 0)
            checkbox = checkbox_cell.findChild(QCheckBox)
            checkbox.setChecked(False)
    
    def acceptSelected(self):
        """Accept the dialog with selected instances."""
        self.selected_instances = []
        for row in range(self.table.rowCount()):
            checkbox_cell = self.table.cellWidget(row, 0)
            checkbox = checkbox_cell.findChild(QCheckBox)
            if checkbox.isChecked():
                self.selected_instances.append(self.instances[row])
        
        if not self.selected_instances:
            QMessageBox.warning(self, "No Selection", "Please select at least one instance to delete.")
            return
        
        self.accept()

class MonitorThread(QThread):
    """Thread for monitoring processes and updating the UI."""
    update_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str, str)  # status, color
    process_status_signal = pyqtSignal(bool)  # is_running
    instances_signal = pyqtSignal(list)  # list of instances
    
    def __init__(self, config):
        """Initialize the monitoring thread."""
        super().__init__()
        self.config = config
        self.running = True
        self.paused = False
        self.last_active_time = time.time()
        self.instances_terminated = False
    
    def run(self):
        """Main monitoring loop."""
        # Emit a signal that we're starting
        self.update_signal.emit("Monitor thread started")
        
        # Get configuration values outside the loop to avoid repeated access
        try:
            check_interval = int(self.config.get('general', 'check_interval_seconds', 
                                fallback=DEFAULT_CONFIG['general']['check_interval_seconds']))
            timeout_minutes = float(self.config.get('general', 'timeout_minutes', 
                                 fallback=DEFAULT_CONFIG['general']['timeout_minutes']))
            process_names_str = self.config.get('processes', 'process_names', 
                                         fallback=DEFAULT_CONFIG['processes']['process_names'])
            process_names = [name.strip() for name in process_names_str.split(',')]
            api_key = self.config.get('vast_ai', 'api_key', fallback='')
            instance_label = self.config.get('vast_ai', 'instance_label', 
                                          fallback=DEFAULT_CONFIG['vast_ai']['instance_label'])
            
            if not api_key:
                self.update_signal.emit("No Vast.ai API key provided. Please set it in the configuration.")
                self.status_signal.emit("Error: No API key", "error")
                return
            
            self.update_signal.emit(f"Monitoring for processes: {', '.join(process_names)}")
            self.update_signal.emit(f"Timeout: {timeout_minutes} minutes")
            self.update_signal.emit(f"Check interval: {check_interval} seconds")
            self.status_signal.emit("Monitoring", "normal")
            
            # Main monitoring loop
            while self.running:
                # Skip processing if paused
                if self.paused:
                    time.sleep(1)  # Short sleep when paused to reduce CPU usage
                    continue
                
                # Check if any of the monitored processes are running
                try:
                    process_running = False
                    for proc in psutil.process_iter(['pid', 'name']):
                        try:
                            process_name = proc.info['name'].lower()
                            if any(p.lower() == process_name for p in process_names):
                                process_running = True
                                break
                        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                            continue
                    
                    if process_running:
                        # Process is running - reset timer
                        current_time = time.time()
                        if current_time - self.last_active_time > timeout_minutes * 60:
                            self.update_signal.emit("Process detected after being inactive. Resetting timer.")
                        self.last_active_time = current_time
                        self.update_signal.emit(f"Monitored process is running. Last active time: {time.strftime('%H:%M:%S', time.localtime(self.last_active_time))}")
                        self.status_signal.emit("Process Running", "success")
                        self.process_status_signal.emit(True)
                        self.instances_terminated = False
                    else:
                        # Process is not running - check timeout
                        current_time = time.time()
                        inactive_duration = current_time - self.last_active_time
                        inactive_minutes = inactive_duration / 60
                        
                        self.update_signal.emit(f"No monitored process running. Inactive for {inactive_minutes:.2f} minutes.")
                        self.status_signal.emit(f"Inactive: {inactive_minutes:.1f}m", "warning")
                        self.process_status_signal.emit(False)
                        
                        # Check if timeout has been reached and instances haven't been terminated yet
                        if inactive_minutes >= timeout_minutes and not self.instances_terminated:
                            self.update_signal.emit(f"Timeout reached ({timeout_minutes} minutes). Terminating Vast.ai instances...")
                            
                            try:
                                # Get instances using REST API
                                headers = {'Accept': 'application/json'}
                                url = f"https://console.vast.ai/api/v0/instances/?api_key={api_key}"
                                response = requests.get(url, headers=headers)
                                response.raise_for_status()
                                data = response.json()
                                
                                if 'instances' in data:
                                    instances = data['instances']
                                    if instance_label:
                                        instances = [i for i in instances if instance_label.lower() in i.get('label', '').lower()]
                                    
                                    if not instances:
                                        self.update_signal.emit("No matching Vast.ai instances found.")
                                    else:
                                        self.update_signal.emit(f"Found {len(instances)} matching instance(s).")
                                        
                                        # Delete each instance
                                        for instance in instances:
                                            instance_id = instance.get('id') or instance.get('instance_id')
                                            if instance_id:
                                                self.update_signal.emit(f"Terminating instance {instance_id}...")
                                                
                                                # Delete instance using REST API
                                                try:
                                                    delete_url = f"https://console.vast.ai/api/v0/instances/{instance_id}/?api_key={api_key}"
                                                    delete_response = requests.delete(delete_url, headers=headers)
                                                    delete_response.raise_for_status()
                                                    
                                                    message = f"Vast.ai instance {instance_id} terminated after {inactive_minutes:.2f} minutes of inactivity"
                                                    self.update_signal.emit(message)
                                                    self.status_signal.emit("Instance Terminated", "error")
                                                except Exception as delete_error:
                                                    self.update_signal.emit(f"Failed to terminate instance {instance_id}: {str(delete_error)}")
                                            else:
                                                self.update_signal.emit(f"Could not determine instance ID from: {instance}")
                                        
                                        self.instances_terminated = True
                                        
                                        # Continue monitoring after termination
                                        self.update_signal.emit("Instance(s) terminated. Continuing to monitor for process activity...")
                                        self.status_signal.emit("Monitoring", "normal")
                                else:
                                    self.update_signal.emit(f"Unexpected response format from Vast.ai API")
                            except Exception as e:
                                self.update_signal.emit(f"Error during instance termination: {str(e)}")
                
                except Exception as e:
                    self.update_signal.emit(f"Error in monitoring loop: {str(e)}")
                
                # Sleep for the specified interval
                time.sleep(check_interval)
        
        except Exception as e:
            self.update_signal.emit(f"An error occurred in the monitoring thread: {str(e)}")
            self.status_signal.emit("Error", "error")
    
    def stop(self):
        """Stop the monitoring thread."""
        self.running = False
    
    def pause(self):
        """Pause the monitoring."""
        self.paused = True
        self.status_signal.emit("Paused", "warning")
    
    def resume(self):
        """Resume the monitoring."""
        self.paused = False
        self.status_signal.emit("Monitoring", "normal")
    
    def delete_instances_now(self):
        """Immediately delete instances based on current configuration."""
        try:
            api_key = self.config.get('vast_ai', 'api_key', fallback='')
            instance_label = self.config.get('vast_ai', 'instance_label', 
                                          fallback=DEFAULT_CONFIG['vast_ai']['instance_label'])
            
            if not api_key:
                self.update_signal.emit("No Vast.ai API key provided. Please set it in the configuration.")
                self.status_signal.emit("Error: No API key", "error")
                return False
            
            self.update_signal.emit(f"Manually triggered instance deletion...")
            
            # Get instances using REST API directly
            try:
                headers = {'Accept': 'application/json'}
                url = f"https://console.vast.ai/api/v0/instances/?api_key={api_key}"
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                if 'instances' in data:
                    instances = data['instances']
                    if instance_label:
                        instances = [i for i in instances if instance_label.lower() in i.get('label', '').lower()]
                    
                    if not instances:
                        self.update_signal.emit("No matching Vast.ai instances found.")
                        return False
                    else:
                        self.update_signal.emit(f"Found {len(instances)} matching instance(s).")
                        
                        success_count = 0
                        # Delete each instance
                        for instance in instances:
                            instance_id = instance.get('id') or instance.get('instance_id')
                            if instance_id:
                                self.update_signal.emit(f"Terminating instance {instance_id}...")
                                
                                # Delete instance using REST API
                                try:
                                    delete_url = f"https://console.vast.ai/api/v0/instances/{instance_id}/?api_key={api_key}"
                                    delete_response = requests.delete(delete_url, headers=headers)
                                    delete_response.raise_for_status()
                                    
                                    message = f"Vast.ai instance {instance_id} terminated manually"
                                    self.update_signal.emit(message)
                                    self.status_signal.emit("Instance Terminated", "error")
                                    success_count += 1
                                except Exception as delete_error:
                                    self.update_signal.emit(f"Failed to terminate instance {instance_id}: {str(delete_error)}")
                            else:
                                self.update_signal.emit(f"Could not determine instance ID from: {instance}")
                        
                        self.instances_terminated = True
                        return success_count > 0
                else:
                    self.update_signal.emit(f"Unexpected response format from Vast.ai API")
                    return False
            except Exception as e:
                self.update_signal.emit(f"Error getting instances: {str(e)}")
                return False
            
        except Exception as e:
            self.update_signal.emit(f"An error occurred during manual deletion: {str(e)}")
            self.status_signal.emit("Error", "error")
            return False
    
    def get_all_instances(self):
        """Get all instances without filtering by label."""
        try:
            api_key = self.config.get('vast_ai', 'api_key', fallback='')
            
            if not api_key:
                self.update_signal.emit("No Vast.ai API key provided. Please set it in the configuration.")
                self.status_signal.emit("Error: No API key", "error")
                return []
            
            self.update_signal.emit("Fetching all Vast.ai instances...")
            
            # Get instances using REST API directly
            try:
                headers = {'Accept': 'application/json'}
                url = f"https://console.vast.ai/api/v0/instances/?api_key={api_key}"
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                if 'instances' in data:
                    instances = data['instances']
                    self.update_signal.emit(f"Found {len(instances)} instance(s).")
                    self.instances_signal.emit(instances)
                    return instances
                else:
                    self.update_signal.emit(f"Unexpected response format from Vast.ai API")
                    return []
            except Exception as e:
                self.update_signal.emit(f"Error getting instances: {str(e)}")
                return []
            
        except Exception as e:
            self.update_signal.emit(f"An error occurred while fetching instances: {str(e)}")
            self.status_signal.emit("Error", "error")
            return []
    
    def delete_specific_instances(self, instances_to_delete):
        """Delete specific instances."""
        try:
            api_key = self.config.get('vast_ai', 'api_key', fallback='')
            
            if not api_key:
                self.update_signal.emit("No Vast.ai API key provided. Please set it in the configuration.")
                self.status_signal.emit("Error: No API key", "error")
                return False
            
            if not instances_to_delete:
                self.update_signal.emit("No instances selected for deletion.")
                return False
            
            self.update_signal.emit(f"Deleting {len(instances_to_delete)} selected instance(s)...")
            
            success_count = 0
            headers = {'Accept': 'application/json'}
            
            # Delete each selected instance
            for instance in instances_to_delete:
                instance_id = instance.get('id') or instance.get('instance_id')
                if instance_id:
                    self.update_signal.emit(f"Terminating instance {instance_id}...")
                    
                    # Delete instance using REST API directly
                    try:
                        delete_url = f"https://console.vast.ai/api/v0/instances/{instance_id}/?api_key={api_key}"
                        delete_response = requests.delete(delete_url, headers=headers)
                        delete_response.raise_for_status()
                        
                        message = f"Vast.ai instance {instance_id} terminated manually"
                        self.update_signal.emit(message)
                        success_count += 1
                    except Exception as delete_error:
                        self.update_signal.emit(f"Failed to terminate instance {instance_id}: {str(delete_error)}")
                else:
                    self.update_signal.emit(f"Could not determine instance ID from: {instance}")
            
            if success_count > 0:
                self.status_signal.emit(f"{success_count} Instance(s) Terminated", "error")
                return True
            
        except Exception as e:
            self.update_signal.emit(f"An error occurred during deletion: {str(e)}")
            self.status_signal.emit("Error", "error")
            return False

class VastAutoShutoffGUI(QMainWindow):
    """Main GUI window for Vast.ai Auto Shutoff."""
    
    def __init__(self):
        """Initialize the GUI."""
        super().__init__()
        self.setWindowTitle("Vast.ai Auto Shutoff")
        self.setMinimumSize(800, 600)
        
        # Initialize log widgets to None
        self.log_text = None
        self.mini_log_text = None
        
        # Determine if we're running from frozen executable
        self.is_frozen = getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')
        if self.is_frozen:
            print("Running from frozen executable")
            # Get the directory where the executable is located
            self.app_dir = os.path.dirname(sys.executable)
        else:
            print("Running from source")
            self.app_dir = os.path.dirname(os.path.abspath(__file__))
            
        # Create required directories
        os.makedirs('status', exist_ok=True)
        os.makedirs('commands', exist_ok=True)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        
        # Tab widget
        self.tabs = QTabWidget()
        self.monitoring_tab = QWidget()
        self.config_tab = QWidget()
        self.log_tab = QWidget()
        
        self.tabs.addTab(self.monitoring_tab, "Monitoring")
        self.tabs.addTab(self.config_tab, "Configuration")
        self.tabs.addTab(self.log_tab, "Log")
        
        main_layout.addWidget(self.tabs)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Status label
        self.status_label = QLabel("Ready")
        self.status_bar.addWidget(self.status_label)
        
        # Initialize variables
        self.monitor_process = None
        self.config = configparser.ConfigParser()
        self.monitor_qprocess = None
        self.status_timer = None
        
        # Direct countdown timer implementation
        self.countdown_active = False
        self.countdown_end_time = None  # When the countdown should end
        self.last_ui_update = 0  # Last time we updated the UI
        
        # Extremely short interval timer for countdown updates (25ms = 40fps)
        self.direct_timer = QTimer()
        self.direct_timer.setInterval(25)  
        self.direct_timer.timeout.connect(self.updateCountdownDirectly)
        
        # Set up UI
        self.initUI()
        
        # Load configuration
        self.loadConfig()
        
        # Clear instance selection on startup (requires fresh selection each session)
        self.clearInstanceSelection()
        
        # Apply dark theme
        self.applyDarkTheme()
        
        self.log("Application started")

    def initUI(self):
        """Initialize the UI."""
        # Set up tabs
        self.setupMonitoringTab()
        self.setupConfigTab()
        self.setupLogTab()

    def setupMonitoringTab(self):
        """Set up the monitoring tab with essential controls only."""
        layout = QVBoxLayout(self.monitoring_tab)
        
        # Control section
        control_group = QGroupBox("Monitoring Controls")
        control_layout = QVBoxLayout(control_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("Start Monitoring")
        self.start_btn.clicked.connect(self.startMonitoring)
        self.start_btn.setStyleSheet("""
            background-color: #4CAF50;
            color: white;
            font-weight: bold;
        """)
        button_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("Stop Monitoring")
        self.stop_btn.clicked.connect(self.stopMonitoring)
        self.stop_btn.setStyleSheet("""
            background-color: #F44336;
            color: white;
            font-weight: bold;
        """)
        self.stop_btn.setEnabled(False)
        button_layout.addWidget(self.stop_btn)
        
        self.pause_btn = QPushButton("Pause Monitoring")
        self.pause_btn.clicked.connect(self.pauseMonitoring)
        self.pause_btn.setStyleSheet("""
            background-color: #FF9800;
            color: white;
            font-weight: bold;
        """)
        self.pause_btn.setEnabled(False)
        button_layout.addWidget(self.pause_btn)
        
        control_layout.addLayout(button_layout)
        
        # Status section
        status_layout = QHBoxLayout()
        
        status_label = QLabel("Status:")
        status_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(status_label)
        
        self.process_status_label = QLabel("Not Monitoring")
        status_layout.addWidget(self.process_status_label)
        
        status_layout.addStretch()
        
        # Countdown timer
        timer_label = QLabel("Time until deletion:")
        timer_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(timer_label)
        
        self.time_remaining_label = QLabel("N/A")
        self.time_remaining_label.setStyleSheet("font-weight: bold; color: #FF9800;")
        status_layout.addWidget(self.time_remaining_label)
        
        control_layout.addLayout(status_layout)
        
        layout.addWidget(control_group)
        
        # Instance management section
        instance_group = QGroupBox("Instance Management")
        instance_layout = QVBoxLayout(instance_group)
        
        # Instance selection
        instance_selection_layout = QHBoxLayout()
        
        self.select_instance_btn = QPushButton("Select Instance to Monitor")
        self.select_instance_btn.clicked.connect(self.selectInstanceToMonitor)
        self.select_instance_btn.setStyleSheet("""
            background-color: #2A82DA;
            color: white;
            font-weight: bold;
        """)
        instance_selection_layout.addWidget(self.select_instance_btn)
        
        self.delete_instance_btn = QPushButton("Delete Instance Now")
        self.delete_instance_btn.clicked.connect(self.deleteInstanceNow)
        self.delete_instance_btn.setStyleSheet("""
            background-color: #F44336;
            color: white;
            font-weight: bold;
        """)
        instance_selection_layout.addWidget(self.delete_instance_btn)
        
        instance_layout.addLayout(instance_selection_layout)
        
        # Selected instance display
        selected_instance_header = QLabel("Selected Instance:")
        selected_instance_header.setStyleSheet("font-weight: bold;")
        instance_layout.addWidget(selected_instance_header)
        
        self.selected_instance_label = QLabel("None selected")
        instance_layout.addWidget(self.selected_instance_label)
        
        layout.addWidget(instance_group)
        
        # Recent activity section
        activity_group = QGroupBox("Recent Activity")
        activity_layout = QVBoxLayout(activity_group)
        
        self.mini_log_text = QTextEdit()
        self.mini_log_text.setReadOnly(True)
        self.mini_log_text.setMaximumHeight(150)
        activity_layout.addWidget(self.mini_log_text)
        
        layout.addWidget(activity_group)
        
        # Add stretch to push everything to the top
        layout.addStretch()

    def applyDarkTheme(self):
        """Apply dark theme to the application."""
        app = QApplication.instance()
        
        # Set fusion style for a modern look
        app.setStyle("Fusion")
        
        # Create a dark palette
        palette = QPalette()
        palette.setColor(QPalette.Window, DARKER_COLOR)
        palette.setColor(QPalette.WindowText, TEXT_COLOR)
        palette.setColor(QPalette.Base, DARKEST_COLOR)
        palette.setColor(QPalette.AlternateBase, DARK_COLOR)
        palette.setColor(QPalette.ToolTipBase, ACCENT_COLOR)
        palette.setColor(QPalette.ToolTipText, TEXT_COLOR)
        palette.setColor(QPalette.Text, TEXT_COLOR)
        palette.setColor(QPalette.Button, DARK_COLOR)
        palette.setColor(QPalette.ButtonText, TEXT_COLOR)
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Link, ACCENT_COLOR)
        palette.setColor(QPalette.Highlight, ACCENT_COLOR)
        palette.setColor(QPalette.HighlightedText, Qt.white)
        
        # Apply the palette
        app.setPalette(palette)
        
        # Additional stylesheet for fine-tuning
        app.setStyleSheet("""
            QGroupBox {
                border: 1px solid #3A3A3A;
                border-radius: 5px;
                margin-top: 1em;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
            }
            QPushButton {
                background-color: #2A82DA;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3A92EA;
            }
            QPushButton:pressed {
                background-color: #1A72CA;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
            QLineEdit, QSpinBox, QComboBox {
                border: 1px solid #3A3A3A;
                border-radius: 4px;
                padding: 4px;
                background-color: #2A2A2A;
            }
            QTextEdit {
                background-color: #232323;
                border: 1px solid #3A3A3A;
                border-radius: 4px;
            }
            QTabWidget::pane {
                border: 1px solid #3A3A3A;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #2A2A2A;
                border: 1px solid #3A3A3A;
                border-bottom-color: #3A3A3A;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 6px 12px;
            }
            QTabBar::tab:selected {
                background-color: #3A3A3A;
                border-bottom-color: #3A3A3A;
            }
            QTabBar::tab:!selected {
                margin-top: 2px;
            }
        """)
    
    def loadConfig(self):
        """Load configuration from config.ini."""
        self.config = configparser.ConfigParser()
        config_path = Path('config.ini')
        
        if config_path.exists():
            self.config.read(config_path)
            self.log("Configuration loaded from config.ini")
            
            # Load Vast.ai settings
            if 'vast_ai' in self.config:
                self.api_key_input.setText(self.config.get('vast_ai', 'api_key', fallback=''))
                self.instance_label_input.setText(self.config.get('vast_ai', 'instance_label', fallback=''))
            
            # Load monitoring settings
            if 'monitoring' in self.config:
                self.processes_input.setText(self.config.get('monitoring', 'processes_to_monitor', fallback=''))
                
                try:
                    timeout = float(self.config.get('monitoring', 'timeout_minutes', fallback='30'))
                    self.timeout_input.setValue(timeout)
                except ValueError:
                    self.log("Invalid timeout value in config, using default")
                    self.timeout_input.setValue(30)
        else:
            self.log("No configuration file found, using default settings")
            
            # Create default configuration
            self.config.add_section('vast_ai')
            self.config.set('vast_ai', 'api_key', '')
            self.config.set('vast_ai', 'instance_label', '')
            
            self.config.add_section('monitoring')
            self.config.set('monitoring', 'processes_to_monitor', 'skyrimvr.exe,skyrim.exe')
            self.config.set('monitoring', 'timeout_minutes', '30')
            
            # Set default values in UI
            self.processes_input.setText('skyrimvr.exe,skyrim.exe')
            self.timeout_input.setValue(30)

    def saveConfig(self):
        """Save configuration to config.ini."""
        # Update config object with current UI values
        
        # Vast.ai settings
        if 'vast_ai' not in self.config:
            self.config.add_section('vast_ai')
        
        self.config.set('vast_ai', 'api_key', self.api_key_input.text())
        self.config.set('vast_ai', 'instance_label', self.instance_label_input.text())
        
        # Monitoring settings
        if 'monitoring' not in self.config:
            self.config.add_section('monitoring')
        
        self.config.set('monitoring', 'processes_to_monitor', self.processes_input.text())
        self.config.set('monitoring', 'timeout_minutes', str(self.timeout_input.value()))
        
        # Save to file
        with open('config.ini', 'w') as f:
            self.config.write(f)
        
        self.log("Configuration saved to config.ini")

    def clearInstanceSelection(self):
        """Clear the instance selection to ensure users explicitly select an instance each session."""
        # Clear from config
        if 'vast_ai' in self.config and 'instance_label' in self.config['vast_ai']:
            self.config.set('vast_ai', 'instance_label', '')
            # Write the updated config back to file
            with open('config.ini', 'w') as f:
                self.config.write(f)
        
        # Clear from UI
        self.instance_label_input.setText('')
        self.selected_instance_label.setText('None selected')
        
        self.log("Instance selection cleared - please select an instance before monitoring")

    def startMonitoring(self):
        """Start monitoring the specified processes."""
        # Save current configuration
        self.saveConfig()
        
        # Check if monitoring is already running
        if hasattr(self, 'monitor_qprocess') and self.monitor_qprocess is not None and self.monitor_qprocess.state() == QProcess.Running:
            self.log("Monitoring is already running.")
            return
        
        # Get configuration values
        processes_to_monitor = self.config.get('monitoring', 'processes_to_monitor', fallback='')
        if not processes_to_monitor:
            QMessageBox.warning(
                self,
                "No Processes Specified",
                "No processes specified for monitoring. Please configure in the settings tab."
            )
            self.log("No processes specified for monitoring. Please configure in the settings tab.")
            return
        
        # Get timeout value
        try:
            timeout_minutes = float(self.config.get('monitoring', 'timeout_minutes', fallback='30'))
        except ValueError:
            self.log("Invalid timeout value. Using default of 30 minutes.")
            timeout_minutes = 30
        
        # Get API key
        api_key = self.config.get('vast_ai', 'api_key', fallback='')
        if not api_key:
            QMessageBox.warning(
                self,
                "No API Key",
                "No Vast.ai API key provided. Please set it in the configuration tab."
            )
            self.log("No Vast.ai API key provided. Please set it in the configuration.")
            return
        
        # Get instance identifier (ID or label) - check both config and UI input field
        instance_identifier = self.config.get('vast_ai', 'instance_label', fallback='')
        if not instance_identifier:
            # Try to get from UI input field
            instance_identifier = self.instance_label_input.text().strip()
            if instance_identifier:
                # Save to config
                self.config.set('vast_ai', 'instance_label', instance_identifier)
                with open('config.ini', 'w') as f:
                    self.config.write(f)
        
        # Check if an instance has been explicitly selected
        if not instance_identifier or self.selected_instance_label.text() == 'None selected':
            # Display a warning message box
            QMessageBox.warning(
                self,
                "No Instance Selected",
                "Please select an instance to monitor before starting.\n\nUse the 'Select Instance to Monitor' button to choose an instance."
            )
            self.log("Monitoring not started: No instance selected. Please select an instance first.")
            return
        
        # Save timeout for the countdown timer to use
        self.monitoring_timeout_minutes = timeout_minutes
        
        # Create command file directory if it doesn't exist
        os.makedirs('commands', exist_ok=True)
        
        # Clear any existing command files
        for file in glob.glob('commands/*.json'):
            try:
                os.remove(file)
            except Exception as e:
                self.log(f"Error clearing command file {file}: {str(e)}")
        
        # Create status file directory if it doesn't exist
        os.makedirs('status', exist_ok=True)
        
        # Start the monitoring process
        try:
            self.log("Starting monitoring process...")
            
            # Use QProcess to avoid blocking the UI
            if hasattr(self, 'monitor_qprocess') and self.monitor_qprocess is not None:
                self.monitor_qprocess.kill()
                self.monitor_qprocess = None
            
            self.monitor_qprocess = QProcess()
            self.monitor_qprocess.readyReadStandardOutput.connect(self.handleProcessOutput)
            self.monitor_qprocess.readyReadStandardError.connect(self.handleProcessError)
            self.monitor_qprocess.finished.connect(self.handleProcessFinished)
            
            # Determine if the monitor_process.exe exists in the same directory as the application
            monitor_exe_path = os.path.join(self.app_dir, 'monitor_process.exe')
            monitor_py_path = os.path.join(self.app_dir, 'monitor_process.py')
            batch_launcher_path = os.path.join(self.app_dir, 'monitor_launcher.bat')
            
            self.log(f"Looking for monitor executable at: {monitor_exe_path}")
            
            if self.is_frozen and os.path.exists(monitor_exe_path):
                # If running from frozen executable and monitor_process.exe exists
                self.log(f"Found monitor executable at {monitor_exe_path}")
                
                # Start the monitor process directly with proper command line flags
                self.monitor_qprocess.start(monitor_exe_path, [
                    "--processes", processes_to_monitor,
                    "--timeout", str(timeout_minutes),
                    "--api_key", api_key,
                    "--label", instance_identifier
                ])
                
            elif self.is_frozen and os.path.exists(batch_launcher_path):
                # If running from frozen executable and the batch launcher exists
                self.log(f"Using batch launcher at {batch_launcher_path}")
                
                # Update to use proper command line arguments in the batch file
                with open(batch_launcher_path, 'w') as f:
                    f.write('@echo off\n')
                    f.write('echo Starting Vast.ai Auto Shutoff Monitor\n')
                    f.write('echo Processes to monitor: %~1\n')
                    f.write('echo Timeout: %~2 minutes\n')
                    f.write('echo Instance ID: %~4\n\n')
                    f.write(':: Get the directory where the batch file is located\n')
                    f.write('set "BATCH_DIR=%~dp0"\n\n')
                    f.write(':: Check if the monitor_process.exe exists in the same directory\n')
                    f.write('if exist "%BATCH_DIR%monitor_process.exe" (\n')
                    f.write('    echo Running monitor_process.exe...\n')
                    f.write('    start "" "%BATCH_DIR%monitor_process.exe" --processes "%~1" --timeout "%~2" --api_key "%~3" --label "%~4"\n')
                    f.write(') else (\n')
                    f.write('    echo ERROR: monitor_process.exe not found in %BATCH_DIR%\n')
                    f.write('    echo This feature requires the monitor_process.exe to be in the same directory as this batch file.\n')
                    f.write('    exit /b 1\n')
                    f.write(')\n\n')
                    f.write('echo Monitor process started successfully.\n')
                    f.write('exit /b 0\n')
                
                # Start the monitor process with the batch launcher
                self.monitor_qprocess.start(batch_launcher_path, [
                    processes_to_monitor,
                    str(timeout_minutes),
                    api_key,
                    instance_identifier
                ])
                
            else:
                # Running from source code or no monitor executable found
                self.log("Starting monitor from Python source")
                
                if not os.path.exists(monitor_py_path) and self.is_frozen:
                    # If monitor_process.py doesn't exist but we're in a frozen environment,
                    # extract it from the PyInstaller bundle
                    self.log("Looking for monitor_process.py in frozen resources")
                    if hasattr(sys, '_MEIPASS'):
                        bundled_monitor_path = os.path.join(sys._MEIPASS, 'monitor_process.py')
                        if os.path.exists(bundled_monitor_path):
                            shutil.copy(bundled_monitor_path, monitor_py_path)
                            self.log(f"Extracted monitor_process.py from bundle to {monitor_py_path}")
                
                # Start the monitor process using the Python executable with proper command line flags
                self.monitor_qprocess.start(sys.executable, [
                    "monitor_process.py",
                    "--processes", processes_to_monitor,
                    "--timeout", str(timeout_minutes),
                    "--api_key", api_key,
                    "--label", instance_identifier
                ])
            
            # Update UI
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.pause_btn.setEnabled(True)
            self.updateStatus("Monitoring Started", "success")
            
            # Track the last known process state (initially None)
            self.last_process_state = None
            
            # Start timer to check status
            if self.status_timer is None:
                self.status_timer = QTimer()
                self.status_timer.timeout.connect(self.checkMonitorStatus)
            
            if not self.status_timer.isActive():
                self.status_timer.start(1000)  # Check every second
            
            self.log(f"Monitoring started for processes: {processes_to_monitor}")
            self.log(f"Timeout set to {timeout_minutes} minutes")
            
            # Determine if identifier is numeric (likely an ID) or string (likely a label)
            try:
                int(instance_identifier)
                self.log(f"Instance ID to monitor: {instance_identifier}")
            except ValueError:
                self.log(f"Instance label to monitor: {instance_identifier}")
            
            self.time_remaining_label.setText("Waiting for status update...")
            
        except Exception as e:
            self.log(f"Error starting monitoring process: {str(e)}")
            self.updateStatus("Error Starting Monitoring", "error")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)

    def handleProcessOutput(self):
        """Handle standard output from the QProcess."""
        if not hasattr(self, 'monitor_qprocess') or self.monitor_qprocess is None:
            return
        
        try:
            data = self.monitor_qprocess.readAllStandardOutput()
            text = bytes(data).decode('utf-8')
            for line in text.strip().split('\n'):
                if line:
                    self.log(line)
        except Exception as e:
            # Silently ignore errors during shutdown
            pass

    def handleProcessError(self):
        """Handle standard error from the QProcess."""
        if not hasattr(self, 'monitor_qprocess') or self.monitor_qprocess is None:
            return
        
        try:
            data = self.monitor_qprocess.readAllStandardError()
            text = bytes(data).decode('utf-8')
            for line in text.strip().split('\n'):
                if line:
                    # Check if it's an INFO message from the monitoring process
                    if " - INFO - " in line:
                        # This is an informational message, not an error
                        if "Process " in line and " is running " in line:
                            # Process detection message
                            parts = line.split(" - INFO - ", 1)
                            if len(parts) > 1:
                                self.log(f"Process detected: {parts[1]}")
                            else:
                                self.log(line)  # Fallback if parsing fails
                        elif "Status updated:" in line:
                            # Status update message, extract the status part
                            parts = line.split(" - INFO - ", 1)
                            if len(parts) > 1:
                                self.log(parts[1])  # Just log the status update without the timestamp prefix
                            else:
                                self.log(line)  # Fallback if parsing fails
                        else:
                            # Other INFO message, just log it without the "Error:" prefix
                            self.log(line)
                    else:
                        # Actual error or other stderr output
                        self.log(f"Error: {line}")
        except Exception as e:
            # Silently ignore errors during shutdown
            pass

    def handleProcessFinished(self, exit_code, exit_status):
        """Handle process finished event."""
        try:
            if exit_status == QProcess.NormalExit:
                self.log(f"Monitoring process finished with exit code {exit_code}")
            else:
                self.log("Monitoring process was terminated")
            
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            self.updateStatus("Monitoring Stopped", "warning")
            self.time_remaining_label.setText("N/A")
            
            # Clear references to the process
            self.monitor_qprocess = None
        except Exception as e:
            self.log(f"Error handling process finished: {str(e)}")

    def readProcessOutput(self):
        """Read output from the monitoring process."""
        if self.monitor_process is None or self.monitor_process.poll() is not None:
            return
        
        try:
            # Read output line by line
            while True:
                line = self.monitor_process.stdout.readline()
                if not line:
                    break
                
                # Log the output
                self.log(line.strip())
        except Exception as e:
            self.log(f"Error reading process output: {str(e)}")

    def checkMonitorStatus(self):
        """Check the status of the monitoring process."""
        # Check if process is still running
        if not hasattr(self, 'monitor_qprocess') or self.monitor_qprocess is None or self.monitor_qprocess.state() != QProcess.Running:
            # Process is not running
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            self.updateStatus("Monitoring Not Running", "warning")
            
            # Stop status timer
            if self.status_timer is not None and self.status_timer.isActive():
                self.status_timer.stop()
            
            return
        
        # Check status files
        try:
            status_files = glob.glob('status/*.json')
            if status_files:
                # Get the most recent status file
                latest_file = max(status_files, key=os.path.getmtime)
                
                with open(latest_file, 'r') as f:
                    status_data = json.load(f)
                    
                    # Update UI based on status
                    if 'status' in status_data:
                        status = status_data['status']
                        self.updateStatus(status)
                    
                    # Update process status and manage countdown
                    if 'process_running' in status_data:
                        process_running = status_data['process_running']
                        
                        # Handle process state changes
                        self.handleProcessStateChange(process_running)
                
        except Exception as e:
            self.log(f"Error checking monitor status: {str(e)}")

    def handleProcessStateChange(self, process_running):
        """Handle process state changes and start/stop countdown appropriately."""
        # Update process status display
        if process_running:
            self.process_status_label.setText("Process Status: Running")
            self.process_status_label.setStyleSheet(f"color: {SUCCESS_COLOR.name()};")
            
            # Process is running, so stop any active countdown
            if self.countdown_active:
                self.log("Process detected as running - stopping countdown")
                self.stopCountdown()
        else:
            self.process_status_label.setText("Process Status: Not Running")
            self.process_status_label.setStyleSheet(f"color: {ERROR_COLOR.name()};")
            
            # Process is not running, start countdown if not already active
            if not self.countdown_active:
                # Get timeout value that was saved during startMonitoring
                try:
                    timeout_minutes = getattr(self, 'monitoring_timeout_minutes', 30)
                    total_seconds = int(timeout_minutes * 60)
                    self.log(f"Process not running - starting {timeout_minutes}m countdown to instance deletion")
                    
                    # Force stop any potentially running timer that didn't get cleaned up
                    if self.direct_timer.isActive():
                        self.direct_timer.stop()
                        
                    # Start a fresh countdown with the full timeout duration
                    self.startCountdown(total_seconds)
                except Exception as e:
                    self.log(f"Error starting countdown: {str(e)}")
        
        # Store this state for next comparison
        self.last_process_state = process_running

    def startCountdown(self, seconds):
        """Start a direct countdown timer."""
        if seconds <= 0:
            self.log("Cannot start countdown with zero or negative seconds")
            return
            
        # Stop any existing countdown first
        if self.countdown_active:
            self.stopCountdown()
            
        # Log starting countdown
        self.log(f"Starting countdown for {seconds} seconds ({int(seconds // 60)}m {int(seconds % 60)}s)")
        
        # Set countdown parameters
        self.countdown_active = True
        self.countdown_end_time = time.time() + seconds
        self.last_ui_update = 0  # Force immediate update
        
        # Make initial update
        self.updateCountdownDirectly()
        
        # Start the direct timer if not already running
        if not self.direct_timer.isActive():
            self.direct_timer.start()
        
        self.log("Direct countdown timer started")

    def stopCountdown(self):
        """Stop the countdown timer."""
        if self.countdown_active:
            self.log("Stopping countdown timer")
            self.countdown_active = False
            
            # Only stop the timer if no other countdown is active
            if self.direct_timer.isActive():
                self.direct_timer.stop()
                
            # Reset display
            self.time_remaining_label.setText("N/A")

    def updateCountdownDirectly(self):
        """Update the countdown display directly."""
        if not self.countdown_active or self.countdown_end_time is None:
            return
        
        # Current time
        now = time.time()
        
        # Only update UI once per second to reduce overhead
        if now - self.last_ui_update < 1.0 and self.last_ui_update > 0:
            return
            
        # Update our last UI update time
        self.last_ui_update = now
        
        # Calculate remaining time
        remaining = max(0, self.countdown_end_time - now)
        
        # Calculate minutes and seconds
        minutes = int(remaining // 60)
        seconds = int(remaining % 60)
        
        # Format countdown string with visual update indicator
        update_char = "•" if int(now) % 2 == 0 else "◦"
        countdown_str = f"Process Not Running {update_char} {minutes}m {seconds}s until deletion"
        
        # Update the display
        self.time_remaining_label.setText(countdown_str)
        
        # Add debug log entry every 10 seconds to avoid flooding the log
        if seconds % 10 == 0 and seconds > 0:
            self.log(f"Countdown: {minutes}m {seconds}s remaining", log_to_mini=False)
        
        # If countdown has reached zero
        if remaining <= 0:
            self.time_remaining_label.setText("Process Not Running • Deletion imminent...")
            self.log("Countdown reached zero - deletion imminent")
            self.countdown_active = False
            
            # Stop the timer
            if self.direct_timer.isActive():
                self.direct_timer.stop()

    def stopMonitoring(self):
        """Stop the monitoring process."""
        if not hasattr(self, 'monitor_qprocess') or self.monitor_qprocess is None or self.monitor_qprocess.state() != QProcess.Running:
            self.log("Monitoring is not running.")
            return
        
        self.log("Stopping monitoring...")
        
        # Send stop command to the monitoring process
        self.sendCommand("stop")
        
        # Disconnect signal handlers to avoid error messages during shutdown
        if self.monitor_qprocess is not None:
            try:
                self.monitor_qprocess.readyReadStandardOutput.disconnect()
                self.monitor_qprocess.readyReadStandardError.disconnect()
            except:
                pass  # In case they're not connected
        
        # Give some time for the process to gracefully terminate
        for i in range(3):  # Wait up to 3 seconds
            self.log(f"Waiting for process to terminate... ({i+1}/3)")
            QApplication.processEvents()  # Keep the UI responsive
            time.sleep(1)
            if not hasattr(self, 'monitor_qprocess') or self.monitor_qprocess is None or self.monitor_qprocess.state() != QProcess.Running:
                self.log("Process terminated gracefully")
                break
        
        # Terminate the process if it's still running
        if hasattr(self, 'monitor_qprocess') and self.monitor_qprocess is not None and self.monitor_qprocess.state() == QProcess.Running:
            self.log("Process did not terminate gracefully, forcing termination...")
            try:
                self.monitor_qprocess.kill()  # Use kill directly for a more forceful termination
                self.log("Process terminated")
            except Exception as e:
                self.log(f"Error terminating process: {str(e)}")
        
        # Reset UI
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.updateStatus("Monitoring Stopped", "warning")
        self.time_remaining_label.setText("N/A")
        
        # Stop timers
        if self.status_timer is not None and self.status_timer.isActive():
            self.status_timer.stop()
        
        # Stop countdown
        self.stopCountdown()
        
        self.log("Monitoring stopped")

    def pauseMonitoring(self):
        """Pause or resume the monitoring process."""
        # Check if monitoring is running
        if not hasattr(self, 'monitor_qprocess') or self.monitor_qprocess is None or self.monitor_qprocess.state() != QProcess.Running:
            self.log("Monitoring is not running.")
            return
        
        try:
            # Check current state
            if self.pause_btn.text() == "Pause Monitoring":
                # Currently running, pause it
                self.log("Pausing monitoring...")
                self.sendCommand("pause")
                self.pause_btn.setText("Resume Monitoring")
                self.updateStatus("Monitoring Paused", "warning")
                
                # Pause the countdown timer
                self.stopCountdown()
            else:
                # Currently paused, resume it
                self.log("Resuming monitoring...")
                self.sendCommand("resume")
                self.pause_btn.setText("Pause Monitoring")
                self.updateStatus("Monitoring Resumed", "success")
                
                # The countdown will be restarted on the next status update
        except Exception as e:
            self.log(f"Error pausing/resuming monitoring: {str(e)}")

    def sendCommand(self, command):
        """Send a command to the monitoring process."""
        try:
            # Use command-specific file naming pattern that matches what monitor_process.py expects
            timestamp = int(time.time())
            if command == "stop":
                command_file = os.path.join('commands', f'stop_{timestamp}.json')
            elif command == "pause":
                command_file = os.path.join('commands', f'pause_{timestamp}.json')
            elif command == "resume":
                command_file = os.path.join('commands', f'resume_{timestamp}.json')
            elif command == "delete_now":
                command_file = os.path.join('commands', f'delete_now_{timestamp}.json')
            else:
                # Fallback for any unexpected commands
                command_file = os.path.join('commands', f'command_{timestamp}.json')
            
            with open(command_file, 'w') as f:
                json.dump({'command': command}, f)
            self.log(f"Sent {command} command to monitoring process")
        except Exception as e:
            self.log(f"Error sending {command} command: {str(e)}")

    def deleteInstanceNow(self):
        """Delete the Vast.ai instance immediately."""
        # Save current configuration
        self.saveConfig()
        
        # Get the instance label from configuration
        instance_label = self.config.get('vast_ai', 'instance_label', fallback='')
        
        if not instance_label:
            QMessageBox.warning(self, "Missing Label", 
                              "Please set an instance label in the configuration tab first.")
            return
        
        # Confirm deletion
        reply = QMessageBox.question(
            self, 
            'Confirm Deletion',
            f"Are you sure you want to delete all instances with label '{instance_label}'?",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.log(f"Manually deleting instances with label '{instance_label}'...")
            
            # If monitoring is running, send delete command to the monitoring process
            if (hasattr(self, 'monitor_qprocess') and self.monitor_qprocess is not None) or (self.monitor_process is not None and self.monitor_process.poll() is None):
                self.log("Sending delete command to monitoring process...")
                self.sendCommand("delete_now")
            else:
                # Otherwise, delete directly
                self.log("Monitoring not running, deleting instances directly...")
                # Get all instances
                instances = self.get_all_instances()
                if not instances:
                    self.log("No instances found or unable to fetch instances.")
                    return
                
                # Filter instances by label
                instances_to_delete = [i for i in instances if i.get('label') == instance_label]
                
                if not instances_to_delete:
                    self.log(f"No instances found with label '{instance_label}'.")
                    return
                
                # Delete the instances
                self.delete_specific_instances(instances_to_delete)

    def viewInstances(self):
        """Show a dialog with all instances and allow selection for deletion."""
        instances = self.get_all_instances()
        
        if not instances:
            QMessageBox.information(self, "No Instances", "No instances found or unable to fetch instances.")
            return
        
        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Vast.ai Instances")
        dialog.setMinimumWidth(700)
        dialog.setMinimumHeight(400)
        
        # Create layout
        layout = QVBoxLayout(dialog)
        
        # Create table
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["ID", "Label", "Machine", "Status", "Cost/hr", "Select"])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        
        # Populate table
        table.setRowCount(len(instances))
        selected_instances = []
        
        for row, instance in enumerate(instances):
            # ID
            id_item = QTableWidgetItem(str(instance.get('id', 'N/A')))
            id_item.setFlags(id_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 0, id_item)
            
            # Label
            label = instance.get('label', 'N/A')
            label_item = QTableWidgetItem(label)
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 1, label_item)
            
            # Machine
            machine = instance.get('machine_id', 'N/A')
            machine_item = QTableWidgetItem(str(machine))
            machine_item.setFlags(machine_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 2, machine_item)
            
            # Status
            status = instance.get('actual_status', 'N/A')
            status_item = QTableWidgetItem(status)
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 3, status_item)
            
            # Cost/hr
            cost = instance.get('dph_total', 0)
            cost_item = QTableWidgetItem(f"${cost:.4f}")
            cost_item.setFlags(cost_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 4, cost_item)
            
            # Checkbox for selection
            checkbox = QCheckBox()
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            table.setCellWidget(row, 5, checkbox_widget)
            
            # Store instance reference with checkbox
            checkbox.instance = instance
            checkbox.stateChanged.connect(lambda state, cb=checkbox: 
                                         selected_instances.append(cb.instance) if state == Qt.Checked 
                                         else selected_instances.remove(cb.instance) if cb.instance in selected_instances else None)
        
        layout.addWidget(table)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(lambda: dialog.reject() or QTimer.singleShot(100, self.viewInstances))
        
        delete_button = QPushButton("Delete Selected")
        delete_button.setStyleSheet(f"background-color: {ERROR_COLOR.name()}; color: white; font-weight: bold;")
        
        cancel_button = QPushButton("Cancel")
        
        button_layout.addWidget(refresh_button)
        button_layout.addStretch()
        button_layout.addWidget(delete_button)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        # Connect buttons
        cancel_button.clicked.connect(dialog.reject)
        delete_button.clicked.connect(lambda: self.confirmDeleteInstances(selected_instances, dialog))
        
        # Show dialog
        dialog.exec_()

    def confirmDeleteInstances(self, instances, parent_dialog=None):
        """Confirm deletion of selected instances."""
        if not instances:
            QMessageBox.information(self, "No Selection", "No instances selected for deletion.")
            return
        
        # Create confirmation dialog
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Confirm Deletion")
        msg.setText(f"Are you sure you want to delete {len(instances)} instance(s)?")
        msg.setInformativeText("This action cannot be undone.")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)
        
        # Show dialog and process result
        if msg.exec_() == QMessageBox.Yes:
            success = self.delete_specific_instances(instances)
            if success and parent_dialog:
                parent_dialog.accept()
            elif success:
                QMessageBox.information(self, "Success", f"Successfully deleted {len(instances)} instance(s).")

    def selectInstanceToMonitor(self):
        """Select an instance to monitor for auto-shutdown."""
        self.log("Fetching Vast.ai instances for monitoring selection...")
        self.saveConfig()  # Make sure config is saved
        
        # Get all instances
        instances = self.get_all_instances()
        
        if not instances:
            QMessageBox.information(self, "No Instances", "No Vast.ai instances were found.")
            return
        
        # Create a dialog to select an instance
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Instance to Monitor")
        dialog.setMinimumSize(700, 400)
        
        layout = QVBoxLayout(dialog)
        
        # Instructions label
        instructions = QLabel("Select the instance you want to monitor for auto-shutdown:")
        layout.addWidget(instructions)
        
        # Create table for instances
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["ID", "Label", "Machine", "GPU", "Status"])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)  # Only one instance can be selected
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)  # Make Label column stretch
        
        # Populate table with instances
        table.setRowCount(len(instances))
        for row, instance in enumerate(instances):
            # Instance details
            instance_id = instance.get('id', 'Unknown')
            id_item = QTableWidgetItem(str(instance_id))
            id_item.setFlags(id_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 0, id_item)
            
            # Use ID as label if label is None or empty
            label = instance.get('label')
            if not label:
                label = f"Instance-{instance_id}"
            label_item = QTableWidgetItem(label)
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 1, label_item)
            
            machine = instance.get('machine_id', 'Unknown')
            machine_item = QTableWidgetItem(str(machine))
            machine_item.setFlags(machine_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 2, machine_item)
            
            gpu = instance.get('gpu_name', 'Unknown')
            gpu_item = QTableWidgetItem(str(gpu))
            gpu_item.setFlags(gpu_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 3, gpu_item)
            
            status = instance.get('actual_status', 'Unknown')
            status_item = QTableWidgetItem(status)
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            if status.lower() == 'running':
                status_item.setForeground(SUCCESS_COLOR)
            elif status.lower() in ['error', 'failed']:
                status_item.setForeground(ERROR_COLOR)
            table.setItem(row, 4, status_item)
        
        layout.addWidget(table)
        
        # Select the first row by default
        if table.rowCount() > 0:
            table.selectRow(0)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)
        
        select_btn = QPushButton("Select for Monitoring")
        select_btn.clicked.connect(dialog.accept)
        select_btn.setStyleSheet("""
            background-color: #2A82DA;
            color: white;
            font-weight: bold;
        """)
        button_layout.addWidget(select_btn)
        
        layout.addLayout(button_layout)
        
        # Show dialog and process result
        if dialog.exec_() == QDialog.Accepted:
            selected_rows = table.selectionModel().selectedRows()
            if selected_rows:
                selected_row = selected_rows[0].row()
                selected_instance = instances[selected_row]
                
                # Get instance details
                instance_id = selected_instance.get('id', 'Unknown')
                
                # Use ID as label if label is None or empty
                instance_label = selected_instance.get('label')
                if not instance_label:
                    instance_label = f"Instance-{instance_id}"
                
                # Update the instance label input (hidden field)
                self.instance_label_input.setText(str(instance_id))  # Store ID directly
                
                # Update the selected instance label with details
                machine = selected_instance.get('machine_id', 'Unknown')
                gpu = selected_instance.get('gpu_name', 'Unknown')
                status = selected_instance.get('actual_status', 'Unknown')
                
                instance_details = f"ID: {instance_id} | Label: {instance_label} | Machine: {machine} | GPU: {gpu} | Status: {status}"
                self.selected_instance_label.setText(instance_details)
                
                # Make sure to switch to the monitoring tab
                self.tabs.setCurrentIndex(0)
                
                self.log(f"Selected instance '{instance_label}' (ID: {instance_id}) for monitoring")
                self.saveConfig()
            else:
                self.log("No instance was selected")

    def setupConfigTab(self):
        """Set up the configuration tab with only essential settings."""
        layout = QVBoxLayout(self.config_tab)
        
        # Vast.ai configuration
        vast_group = QGroupBox("Vast.ai Configuration")
        vast_layout = QFormLayout(vast_group)
        
        # API Key
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        vast_layout.addRow("API Key:", self.api_key_input)
        
        # Hidden instance label input for compatibility
        self.instance_label_input = QLineEdit()
        self.instance_label_input.setVisible(False)
        
        layout.addWidget(vast_group)
        
        # Process monitoring configuration
        process_group = QGroupBox("Process Monitoring")
        process_layout = QFormLayout(process_group)
        
        # Processes to monitor
        self.processes_input = QLineEdit()
        process_layout.addRow("Processes to Monitor (comma-separated):", self.processes_input)
        
        # Timeout
        self.timeout_input = QDoubleSpinBox()
        self.timeout_input.setRange(0.1, 1440)  # 0.1 minute to 24 hours
        self.timeout_input.setValue(30)
        self.timeout_input.setSuffix(" minutes")
        process_layout.addRow("Timeout After Process Ends:", self.timeout_input)
        
        layout.addWidget(process_group)
        
        # Save button
        save_btn = QPushButton("Save Configuration")
        save_btn.clicked.connect(self.saveConfig)
        save_btn.setStyleSheet("""
            background-color: #4CAF50;
            color: white;
            font-weight: bold;
        """)
        layout.addWidget(save_btn)
        
        # Add stretch to push everything to the top
        layout.addStretch()

    def setupLogTab(self):
        """Set up the log tab with just the log display."""
        layout = QVBoxLayout(self.log_tab)
        
        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)
        
        # Clear log button
        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(self.clearLog)
        clear_btn.setStyleSheet("""
            background-color: #757575;
            color: white;
        """)
        layout.addWidget(clear_btn)

    def clearLog(self):
        """Clear the log text area."""
        self.log_text.clear()
        self.mini_log_text.clear()
        self.log("Log cleared")

    def log(self, message, log_to_mini=True):
        """Add a message to the log."""
        # Format with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # If the message is prefixed with "Process detected:", handle it specially
        if message.startswith("Process detected:"):
            # Format it as a clean process detection message
            log_message = f"[{timestamp}] {message}"
        # If the message is a status update from the monitor process
        elif message.startswith("Status updated:"):
            # Format it as a clean status update
            log_message = f"[{timestamp}] {message}"
        else:
            log_message = f"[{timestamp}] {message}"
        
        # Only append to the log_text if it has been initialized
        if hasattr(self, 'log_text') and self.log_text is not None:
            # Add to main log
            self.log_text.append(log_message)
            self.log_text.moveCursor(QTextCursor.End)
        else:
            # If log_text is not available yet, print to console instead
            print(log_message)
        
        if log_to_mini and hasattr(self, 'mini_log_text') and self.mini_log_text is not None:
            # Filter conditions for mini log
            # Skip status update countdown messages and monitoring process status updates
            should_filter = (
                # Skip countdown timer updates
                (message.startswith("Status updated: Process") and " until deletion" in message) or
                # Skip INFO status updates from monitor_process
                (message.startswith("Status updated:") and "Process" in message) or
                # Skip process detection messages in mini log to reduce spam
                message.startswith("Process detected:") or
                # Skip other status update messages
                ("Status updated:" in message and any(x in message for x in ["Process Running", "Process Not Running", "until deletion"]))
            )
            
            if not should_filter:
                # Add to mini log (limited to recent entries)
                self.mini_log_text.append(log_message)
                self.mini_log_text.moveCursor(QTextCursor.End)
                
                # Limit mini log to last 5 entries
                document = self.mini_log_text.document()
                if document.blockCount() > 5:
                    cursor = QTextCursor(document.firstBlock())
                    cursor.select(QTextCursor.BlockUnderCursor)
                    cursor.removeSelectedText()
                    cursor.deleteChar()  # Delete the newline

    def updateStatus(self, status, status_type="normal"):
        """Update the status bar with the given status."""
        self.status_label.setText(status)
        
        # Set color based on status type
        if status_type == "success":
            self.status_label.setStyleSheet(f"color: {SUCCESS_COLOR.name()};")
        elif status_type == "warning":
            self.status_label.setStyleSheet(f"color: {WARNING_COLOR.name()};")
        elif status_type == "error":
            self.status_label.setStyleSheet(f"color: {ERROR_COLOR.name()};")
        else:
            self.status_label.setStyleSheet(f"color: {TEXT_COLOR.name()};")

    def get_all_instances(self):
        """Get all instances from the Vast.ai API."""
        api_key = self.config.get('vast_ai', 'api_key', fallback='')
        
        if not api_key:
            self.log("No Vast.ai API key provided. Please set it in the configuration.")
            return []
        
        self.log("Fetching all Vast.ai instances...")
        
        try:
            headers = {'Accept': 'application/json'}
            url = f"https://console.vast.ai/api/v0/instances/?api_key={api_key}"
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            if 'instances' in data:
                instances = data['instances']
                self.log(f"Found {len(instances)} instance(s).")
                return instances
            else:
                self.log(f"Unexpected response format from Vast.ai API")
                return []
        except Exception as e:
            self.log(f"Error getting instances: {str(e)}")
            return []

    def delete_specific_instances(self, instances_to_delete):
        """Delete specific instances."""
        api_key = self.config.get('vast_ai', 'api_key', fallback='')
        
        if not api_key:
            self.log("No Vast.ai API key provided. Please set it in the configuration.")
            return False
        
        if not instances_to_delete:
            self.log("No instances selected for deletion.")
            return False
        
        self.log(f"Deleting {len(instances_to_delete)} selected instance(s)...")
        
        success_count = 0
        headers = {'Accept': 'application/json'}
        
        # Delete each selected instance
        for instance in instances_to_delete:
            instance_id = instance.get('id') or instance.get('instance_id')
            if instance_id:
                self.log(f"Terminating instance {instance_id}...")
                
                # Delete instance using REST API directly
                try:
                    delete_url = f"https://console.vast.ai/api/v0/instances/{instance_id}/?api_key={api_key}"
                    delete_response = requests.delete(delete_url, headers=headers)
                    delete_response.raise_for_status()
                    
                    message = f"Vast.ai instance {instance_id} terminated manually"
                    self.log(message)
                    success_count += 1
                except Exception as delete_error:
                    self.log(f"Failed to terminate instance {instance_id}: {str(delete_error)}")
            else:
                self.log(f"Could not determine instance ID from: {instance}")
        
        if success_count > 0:
            self.updateStatus(f"{success_count} Instance(s) Terminated", "error")
            return True
        else:
            return False

def main():
    """Main function to start the GUI application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Vast.ai Auto Shutoff")
    
    window = VastAutoShutoffGUI()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 