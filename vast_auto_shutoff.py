#!/usr/bin/env python3
"""
Vast.ai Auto Shutoff Script

This script monitors specified processes (skyrimvr.exe and skyrim.exe by default)
and automatically shuts down Vast.ai GPU instances when these processes are not running
for a specified period of time.

Usage:
    python vast_auto_shutoff.py

Configuration:
    - API key for Vast.ai can be set in config.ini or as an environment variable VAST_API_KEY
    - Process names to monitor can be configured in config.ini
    - Timeout duration can be configured in config.ini
    - Instance identification parameters can be configured in config.ini
"""

import os
import time
import logging
import configparser
import psutil
from datetime import datetime, timedelta
import requests
import sys
import json
from pathlib import Path
try:
    from vastai import VastAI
    VASTAI_SDK_AVAILABLE = True
except ImportError:
    VASTAI_SDK_AVAILABLE = False

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("vast_auto_shutoff.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_CONFIG = {
    'general': {
        'check_interval_seconds': '60',
        'timeout_minutes': '15',
    },
    'processes': {
        'process_names': 'skyrimvr.exe,skyrim.exe',
    },
    'vast_ai': {
        'api_key': '',
        'instance_label': 'XTTS',  # Label to identify the instance
    }
}

def load_config():
    """Load configuration from config.ini file or create with defaults if not exists."""
    config = configparser.ConfigParser()
    config_path = Path('config.ini')
    
    if config_path.exists():
        config.read(config_path)
        logger.info("Configuration loaded from config.ini")
    else:
        # Create default config
        for section, options in DEFAULT_CONFIG.items():
            if not config.has_section(section):
                config.add_section(section)
            for option, value in options.items():
                config.set(section, option, value)
        
        # Write default config to file
        with open(config_path, 'w') as f:
            config.write(f)
        logger.info("Created default configuration in config.ini")
    
    # Override API key with environment variable if set
    if os.environ.get('VAST_API_KEY'):
        if not config.has_section('vast_ai'):
            config.add_section('vast_ai')
        config.set('vast_ai', 'api_key', os.environ.get('VAST_API_KEY'))
        logger.info("Using API key from environment variable")
    
    return config

def is_process_running(process_names):
    """Check if any of the specified processes are running."""
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            process_name = proc.info['name'].lower()
            if any(p.lower() == process_name for p in process_names):
                logger.debug(f"Found running process: {process_name}")
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False

def get_vast_ai_client(api_key):
    """Get Vast.ai client using the SDK if available, otherwise return None."""
    if not VASTAI_SDK_AVAILABLE:
        logger.warning("Vast.ai SDK not available. Using REST API instead.")
        return None
    
    try:
        return VastAI(api_key=api_key)
    except Exception as e:
        logger.error(f"Failed to initialize Vast.ai client: {e}")
        return None

def get_instances(api_key, instance_label=None):
    """Get list of running instances, optionally filtered by label."""
    if VASTAI_SDK_AVAILABLE:
        try:
            client = get_vast_ai_client(api_key)
            if client:
                instances = client.show_instances()
                if instance_label:
                    # Filter instances by label if provided
                    return [i for i in instances if instance_label.lower() in i.get('label', '').lower()]
                return instances
        except Exception as e:
            logger.error(f"Error getting instances via SDK: {e}")
    
    # Fallback to REST API
    try:
        headers = {'Accept': 'application/json'}
        url = f"https://console.vast.ai/api/v0/instances/?api_key={api_key}"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if 'instances' in data:
            instances = data['instances']
            if instance_label:
                return [i for i in instances if instance_label.lower() in i.get('label', '').lower()]
            return instances
        else:
            logger.error(f"Unexpected response format: {data}")
            return []
    except Exception as e:
        logger.error(f"Error getting instances via REST API: {e}")
        return []

def delete_instance(api_key, instance_id):
    """Delete a Vast.ai instance by ID."""
    if VASTAI_SDK_AVAILABLE:
        try:
            client = get_vast_ai_client(api_key)
            if client:
                result = client.destroy_instance(ID=instance_id)
                logger.info(f"Instance {instance_id} deletion result: {result}")
                return True
        except Exception as e:
            logger.error(f"Error deleting instance via SDK: {e}")
    
    # Fallback to REST API
    try:
        headers = {'Accept': 'application/json'}
        url = f"https://console.vast.ai/api/v0/instances/{instance_id}/?api_key={api_key}"
        response = requests.delete(url, headers=headers)
        response.raise_for_status()
        logger.info(f"Instance {instance_id} deleted successfully via REST API")
        return True
    except Exception as e:
        logger.error(f"Error deleting instance via REST API: {e}")
        return False

def show_notification(title, message):
    """Show a desktop notification."""
    try:
        # Try to use Windows toast notifications
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(title, message, duration=10)
        return
    except ImportError:
        pass
    
    try:
        # Try to use plyer for cross-platform notifications
        from plyer import notification
        notification.notify(title=title, message=message)
        return
    except ImportError:
        pass
    
    # If all else fails, just log it
    logger.info(f"Notification: {title} - {message}")

def main():
    """Main function to monitor processes and manage Vast.ai instances."""
    config = load_config()
    
    # Get configuration values
    check_interval = int(config.get('general', 'check_interval_seconds', fallback=DEFAULT_CONFIG['general']['check_interval_seconds']))
    timeout_minutes = int(config.get('general', 'timeout_minutes', fallback=DEFAULT_CONFIG['general']['timeout_minutes']))
    process_names = config.get('processes', 'process_names', fallback=DEFAULT_CONFIG['processes']['process_names']).split(',')
    api_key = config.get('vast_ai', 'api_key', fallback='')
    instance_label = config.get('vast_ai', 'instance_label', fallback=DEFAULT_CONFIG['vast_ai']['instance_label'])
    
    # Validate API key
    if not api_key:
        logger.error("No Vast.ai API key provided. Please set it in config.ini or as VAST_API_KEY environment variable.")
        return
    
    logger.info(f"Starting Vast.ai Auto Shutoff")
    logger.info(f"Monitoring processes: {', '.join(process_names)}")
    logger.info(f"Timeout: {timeout_minutes} minutes")
    logger.info(f"Check interval: {check_interval} seconds")
    
    last_active_time = datetime.now()
    instances_terminated = False
    
    try:
        while True:
            if is_process_running(process_names):
                if datetime.now() - last_active_time > timedelta(minutes=timeout_minutes):
                    logger.info(f"Process detected after being inactive. Resetting timer.")
                last_active_time = datetime.now()
                logger.info(f"Monitored process is running. Last active time: {last_active_time}")
                instances_terminated = False
            else:
                inactive_duration = datetime.now() - last_active_time
                inactive_minutes = inactive_duration.total_seconds() / 60
                
                logger.info(f"No monitored process running. Inactive for {inactive_minutes:.2f} minutes.")
                
                # Check if timeout has been reached and instances haven't been terminated yet
                if inactive_minutes >= timeout_minutes and not instances_terminated:
                    logger.info(f"Timeout reached ({timeout_minutes} minutes). Terminating Vast.ai instances...")
                    
                    # Get instances
                    instances = get_instances(api_key, instance_label)
                    
                    if not instances:
                        logger.info("No matching Vast.ai instances found.")
                    else:
                        logger.info(f"Found {len(instances)} matching instance(s).")
                        
                        # Delete each instance
                        for instance in instances:
                            instance_id = instance.get('id') or instance.get('instance_id')
                            if instance_id:
                                logger.info(f"Terminating instance {instance_id}...")
                                success = delete_instance(api_key, instance_id)
                                
                                if success:
                                    message = f"Vast.ai instance {instance_id} terminated after {inactive_minutes:.2f} minutes of inactivity"
                                    logger.info(message)
                                    show_notification("Vast.ai Auto Shutoff", message)
                                else:
                                    logger.error(f"Failed to terminate instance {instance_id}")
                            else:
                                logger.error(f"Could not determine instance ID from: {instance}")
                        
                        instances_terminated = True
            
            # Sleep for the specified interval
            time.sleep(check_interval)
    
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user.")
    except Exception as e:
        logger.exception(f"An error occurred: {e}")

if __name__ == "__main__":
    main() 