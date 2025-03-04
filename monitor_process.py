#!/usr/bin/env python3
"""
Monitor Process Script - Monitors specified processes and manages Vast.ai instances.
This script runs as a separate process from the GUI to prevent freezing.
"""

import os
import sys
import time
import json
import psutil
import requests
import argparse
import logging
from datetime import datetime, timedelta
import traceback
import glob

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("monitor_process.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
STATUS_DIR = "status"
COMMANDS_DIR = "commands"
CHECK_INTERVAL = 5  # seconds
COMMAND_CHECK_INTERVAL = 1  # seconds

# Ensure directories exist
os.makedirs(STATUS_DIR, exist_ok=True)
os.makedirs(COMMANDS_DIR, exist_ok=True)

def log_message(message, level="info"):
    """Log a message to the log file and update status."""
    if level == "info":
        logger.info(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)
    elif level == "debug":
        logger.debug(message)

def update_status(status, process_running=False, time_remaining=None):
    """Update the status file with current information."""
    status_data = {
        "timestamp": time.time(),
        "status": status,
        "process_running": process_running,
        "time_remaining": time_remaining
    }
    
    # Write to a new status file with timestamp to avoid conflicts
    status_file = os.path.join(STATUS_DIR, f"status_{int(time.time())}.json")
    with open(status_file, "w") as f:
        json.dump(status_data, f)
    
    log_message(f"Status updated: {status}")

def is_process_running(process_names):
    """Check if any of the specified processes are running."""
    process_list = process_names.split(',')
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            for process_name in process_list:
                process_name = process_name.strip()
                if process_name.lower() in proc.info['name'].lower():
                    log_message(f"Process {process_name} is running (PID: {proc.info['pid']})")
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    return False

def get_instances(api_key, identifier=None, is_id=False):
    """
    Get instances from Vast.ai API.
    
    Args:
        api_key (str): The Vast.ai API key
        identifier (str): Either the label to filter by or the instance ID
        is_id (bool): If True, filter by ID instead of label
    
    Returns:
        list: List of matching instances
    """
    try:
        headers = {'Accept': 'application/json'}
        url = f"https://console.vast.ai/api/v0/instances/?api_key={api_key}"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if 'instances' in data:
            instances = data['instances']
            
            # Filter by identifier if provided
            if identifier:
                # Try to convert identifier to integer (meaning it's an ID)
                try:
                    instance_id = int(identifier)
                    # It's a numeric ID, search by ID
                    log_message(f"Searching for instance with ID {instance_id}")
                    instances = [i for i in instances if i.get('id') == instance_id]
                    log_message(f"Found {len(instances)} instance(s) with ID {instance_id}")
                except ValueError:
                    # It's not a numeric ID, treat as a label
                    log_message(f"Searching for instance with label '{identifier}'")
                    instances = [i for i in instances if i.get('label') == identifier]
                    log_message(f"Found {len(instances)} instance(s) with label '{identifier}'")
            else:
                log_message(f"Found {len(instances)} instance(s)")
            
            return instances
        else:
            log_message(f"Unexpected response format from Vast.ai API", "error")
            return []
    except Exception as e:
        log_message(f"Error getting instances: {str(e)}", "error")
        return []

def delete_instance(instance_id, api_key):
    """Delete a specific instance from Vast.ai."""
    try:
        headers = {'Accept': 'application/json'}
        url = f"https://console.vast.ai/api/v0/instances/{instance_id}/?api_key={api_key}"
        response = requests.delete(url, headers=headers)
        response.raise_for_status()
        
        log_message(f"Successfully deleted instance {instance_id}")
        return True
    except Exception as e:
        log_message(f"Error deleting instance {instance_id}: {str(e)}", "error")
        return False

def check_for_commands():
    """Check for command files that control the monitoring process."""
    try:
        # First priority: check for stop command
        stop_files = glob.glob('commands/stop_*.json')
        if stop_files:
            # Found stop command, delete file and return command
            try:
                for file in stop_files:
                    os.remove(file)
                return "stop"
            except Exception as e:
                log_message(f"Error removing stop command file: {str(e)}", "error")
        
        # Second priority: check for delete_now command
        delete_now_files = glob.glob('commands/delete_now_*.json')
        if delete_now_files:
            # Found delete_now command, delete file and return command
            try:
                for file in delete_now_files:
                    os.remove(file)
                return "delete_now"
            except Exception as e:
                log_message(f"Error removing delete_now command file: {str(e)}", "error")
        
        # Third priority: check for pause/resume commands
        pause_files = glob.glob('commands/pause_*.json')
        if pause_files:
            # Found pause command, delete file and return command
            try:
                for file in pause_files:
                    os.remove(file)
                return "pause"
            except Exception as e:
                log_message(f"Error removing pause command file: {str(e)}", "error")
        
        resume_files = glob.glob('commands/resume_*.json')
        if resume_files:
            # Found resume command, delete file and return command
            try:
                for file in resume_files:
                    os.remove(file)
                return "resume"
            except Exception as e:
                log_message(f"Error removing resume command file: {str(e)}", "error")
        
        return None
    except Exception as e:
        log_message(f"Error checking for commands: {str(e)}", "error")
        return None

def main():
    """Main function to monitor processes and manage Vast.ai instances."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Monitor processes and manage Vast.ai instances')
    parser.add_argument('--processes', type=str, required=True, help='Comma-separated list of processes to monitor')
    parser.add_argument('--timeout', type=float, required=True, help='Timeout in minutes')
    parser.add_argument('--api_key', type=str, required=True, help='Vast.ai API key')
    parser.add_argument('--label', type=str, required=True, help='Instance label or ID to filter by')
    
    args = parser.parse_args()
    
    processes_to_monitor = args.processes
    timeout_minutes = args.timeout
    api_key = args.api_key
    instance_identifier = args.label
    
    # Log the identifier type for debugging
    log_message(f"Received instance identifier: '{instance_identifier}'")
    
    log_message(f"Starting monitoring for processes: {processes_to_monitor}")
    log_message(f"Timeout set to {timeout_minutes} minutes")
    
    # Initialize variables
    process_running = False
    last_seen_running = datetime.now()  # Initialize with current time
    paused = False
    
    # Main monitoring loop
    try:
        update_status("Monitoring Started", process_running=False)
        
        while True:
            # Check for commands first - prioritize command processing
            command = check_for_commands()
            if command:
                if command == "stop":
                    log_message("Received stop command, exiting immediately...")
                    update_status("Monitoring Stopped", process_running=process_running)
                    # Force exit to ensure the process terminates
                    sys.exit(0)
                elif command == "pause":
                    log_message("Received pause command, pausing monitoring...")
                    paused = True
                    update_status("Monitoring Paused", process_running=process_running)
                elif command == "resume":
                    log_message("Received resume command, resuming monitoring...")
                    paused = False
                    update_status("Monitoring Resumed", process_running=process_running)
                elif command == "delete_now":
                    log_message("Received delete_now command, deleting instances...")
                    instances = get_instances(api_key, instance_identifier)
                    if instances:
                        for instance in instances:
                            instance_id = instance.get('id')
                            if instance_id:
                                delete_instance(instance_id, api_key)
                    else:
                        log_message("No instances found to delete")
            
            # Skip monitoring if paused
            if paused:
                time.sleep(COMMAND_CHECK_INTERVAL)
                continue
            
            # Check if any of the monitored processes are running
            current_process_running = is_process_running(processes_to_monitor)
            
            # Process state changed
            if current_process_running != process_running:
                process_running = current_process_running
                if process_running:
                    log_message(f"Process started running")
                    last_seen_running = datetime.now()
                    update_status("Process Running", process_running=True)
                else:
                    log_message(f"Process stopped running")
                    last_seen_running = datetime.now()
                    update_status("Process Not Running", process_running=False)
            
            # Always update the time remaining if not running
            if not process_running:
                elapsed = datetime.now() - last_seen_running
                remaining = timedelta(minutes=timeout_minutes) - elapsed
                
                if remaining.total_seconds() <= 0:
                    log_message(f"Timeout reached ({timeout_minutes} minutes), deleting instances...")
                    
                    # Get and delete instances
                    instances = get_instances(api_key, instance_identifier)
                    if instances:
                        deletion_successful = False
                        for instance in instances:
                            instance_id = instance.get('id')
                            if instance_id:
                                if delete_instance(instance_id, api_key):
                                    deletion_successful = True
                        
                        if deletion_successful:
                            log_message("Successfully deleted instances, exiting...")
                            update_status("Instances Deleted, Monitoring Stopped", process_running=False)
                            break
                        else:
                            log_message("Failed to delete instances, will retry later")
                            last_seen_running = datetime.now()  # Reset timer
                    else:
                        log_message("No instances found to delete, will retry in a minute")
                        # Set the timer to a shorter time for retry
                        last_seen_running = datetime.now() - timedelta(minutes=timeout_minutes) + timedelta(minutes=1)
                
                # Update status with time remaining
                minutes, seconds = divmod(int(remaining.total_seconds()), 60)
                hours, minutes = divmod(minutes, 60)
                
                if hours > 0:
                    time_remaining = f"{hours}h {minutes}m {seconds}s"
                else:
                    time_remaining = f"{minutes}m {seconds}s"
                
                status_message = f"Process Not Running - {time_remaining} until deletion"
                update_status(status_message, process_running=False, time_remaining=time_remaining)
            else:
                # If process is running, still send updates occasionally
                update_status("Process Running", process_running=True, time_remaining="N/A - Process Running")
            
            # Sleep before next check
            time.sleep(CHECK_INTERVAL)
    
    except KeyboardInterrupt:
        log_message("Monitoring stopped by user")
        update_status("Monitoring Stopped", process_running=process_running)
    except Exception as e:
        log_message(f"Error in monitoring loop: {str(e)}", "error")
        log_message(traceback.format_exc(), "error")
        update_status(f"Error: {str(e)}", process_running=process_running)
    
    log_message("Monitoring process exiting")

if __name__ == "__main__":
    main() 