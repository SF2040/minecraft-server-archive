import json
import time
import pyautogui
import subprocess
import os
import re
from datetime import datetime
from pathlib import Path

# Configuration
SERVERS_FILE = "servers.json"
LOG_FILE = "archival_log.txt"
MINECRAFT_LOG_PATH = r"C:\Users\NAwork\AppData\Roaming\.minecraft\logs\latest.log"
WAIT_FOR_LOAD = 15  # Seconds to wait after joining server
CHECK_INTERVAL = 2  # Seconds between log checks
MAX_WAIT_TIME = 60  # Max seconds to wait for builds/download

def int_to_ip(ip_int):
    """Convert integer IP to standard format"""
    return f"{(ip_int >> 24) & 0xFF}.{(ip_int >> 16) & 0xFF}.{(ip_int >> 8) & 0xFF}.{ip_int & 0xFF}"

def load_servers():
    """Load server list from JSON file"""
    try:
        with open(SERVERS_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            data = json.loads(content)
        
        # Handle API response format {"data": [...]}
        if isinstance(data, dict) and 'data' in data:
            servers = data['data']
        elif isinstance(data, list):
            servers = data
        else:
            print(f"✗ Error: Unexpected JSON format")
            return []
        
        print(f"✓ Loaded {len(servers)} servers from {SERVERS_FILE}")
        return servers
    except FileNotFoundError:
        print(f"✗ Error: {SERVERS_FILE} not found!")
        print("Create a JSON file with server data from the API")
        return []
    except json.JSONDecodeError as e:
        print(f"✗ Error: {SERVERS_FILE} is not valid JSON!")
        print(f"Details: {e}")
        return []

def log_event(message):
    """Log events to file and console"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    with open(LOG_FILE, 'a') as f:
        f.write(log_line + "\n")

def safe_click(x, y, delay=0.5):
    """Move cursor to position then click - more reliable than instant click"""
    # LINE: Mouse move to (x, y)
    pyautogui.moveTo(x, y, duration=0.3)
    # LINE: Wait 0.2 seconds
    time.sleep(0.2)
    pyautogui.click()
    # LINE: Wait {delay} seconds after click
    time.sleep(delay)

def press_esc_to_menu():
    """Press ESC to open menu (works in-game)"""
    pyautogui.press('esc')
    # LINE: Wait 1 second after ESC
    time.sleep(1)

def disconnect_from_server():
    """Disconnect from current server"""
    log_event("Disconnecting from server...")
    
    # Press ESC to open game menu (if in-game)
    pyautogui.press('esc')
    # LINE: Wait 1 second after ESC
    time.sleep(1)
    
    # Click "Disconnect" button
    # LINE: Mouse move to (950, 515), click, wait 2 seconds
    safe_click(950, 515, delay=2)
    
    # Click center screen to clear any error dialogs or return to menu
    # LINE: Mouse move to (960, 540), click, wait 1 second
    safe_click(960, 540, delay=1)
    ### big error msg handle
    safe_click(960, 550, delay=1)
	
    safe_click(960, 560, delay=1)
	
    safe_click(960, 575, delay=1)
	
    safe_click(960, 586, delay=1)
	
    # Press ESC to ensure we're back at main menu
    pyautogui.press('esc')
    # LINE: Wait 2 seconds after ESC
    time.sleep(2)

def send_goto_command(x, y, z):
    """Send #goto command in Minecraft chat"""
    log_event(f"Sending goto command: #goto {x} {y} {z}")
    
    # Press T to open chat
    pyautogui.press('t')
    # LINE: Wait 0.5 seconds after opening chat
    time.sleep(0.5)
    
    # Type the goto command
    command = f"#goto {x} {y} {z}"
    pyautogui.write(command, interval=0.05)
    # LINE: Wait 0.3 seconds after typing
    time.sleep(0.3)
    
    # Press Enter to send
    pyautogui.press('enter')
    # LINE: Wait 1 second after sending command
    time.sleep(1)

def extract_coordinates(meteor_line):
    """Extract X, Y, Z coordinates from Meteor message"""
    # Pattern to match: X-8, Y67, Z104 (handles negative numbers)
    pattern = r'X(-?\d+),?\s*Y(-?\d+),?\s*Z(-?\d+)'
    match = re.search(pattern, meteor_line)
    
    if match:
        x = match.group(1)
        y = match.group(2)
        z = match.group(3)
        log_event(f"Extracted coordinates: X={x}, Y={y}, Z={z}")
        return x, y, z
    else:
        log_event("Could not extract coordinates from Meteor message")
        return None, None, None

def join_server(ip, port):
    """Join a Minecraft server via Direct Connect"""
    server_address = f"{ip}:{port}"
    log_event(f"Joining server: {server_address}")
    
    # Get initial log position BEFORE joining
    initial_log_pos = 0
    if os.path.exists(MINECRAFT_LOG_PATH):
        with open(MINECRAFT_LOG_PATH, 'r', encoding='utf-8', errors='ignore') as f:
            f.seek(0, 2)
            initial_log_pos = f.tell()
    
    # Press ESC to get to main menu
    pyautogui.press('esc')
    # LINE: Wait 1.5 seconds after ESC
    time.sleep(1.5)
    
    # Press ESC again in case we're in a world
    pyautogui.press('esc')
    # LINE: Wait 1 second after ESC
    time.sleep(1)
    
    # Click Multiplayer button
    # LINE: Mouse move to (950, 450), click, wait 2 seconds
    safe_click(950, 450, delay=2)
    
    # Click Direct Connect
    # LINE: Mouse move to (960, 995), click, wait 1.5 seconds
    safe_click(960, 995, delay=1.5)
    
    # Clear existing text and enter server address
    pyautogui.hotkey('ctrl', 'a')
    # LINE: Wait 0.3 seconds after Ctrl+A
    time.sleep(0.3)
    pyautogui.write(server_address, interval=0.05)
    # LINE: Wait 0.5 seconds after typing
    time.sleep(0.5)
    
    # Click Join Server button
    # LINE: Mouse move to (950, 522), click, wait 3 seconds
    safe_click(950, 522, delay=3)
    
    # Wait additional 4 seconds to reach 7-second mark total
    # LINE: Wait 4 seconds (total 7 seconds after join click)
    time.sleep(8)
    
    ### Move mouse left 10px then right 20px to trigger rendering
    current_x, current_y = pyautogui.position()
    # LINE: Mouse move 10px left
    pyautogui.moveRel(-10, 0, duration=0.2)
    # LINE: Wait 0.2 seconds
    time.sleep(0.2)
    # LINE: Mouse move 20px right
    pyautogui.moveRel(20, 0, duration=0.2)
    # LINE: Wait 0.5 seconds
    time.sleep(0.5)
    
    return initial_log_pos

def check_connection_failed(timeout=15):
    """Check if connection failed - looks for WARN or ERROR in logs"""
    log_event("Checking connection status...")
    
    start_time = time.time()
    last_position = 0
    
    if os.path.exists(MINECRAFT_LOG_PATH):
        with open(MINECRAFT_LOG_PATH, 'r', encoding='utf-8', errors='ignore') as f:
            f.seek(0, 2)
            last_position = f.tell()
    
    while time.time() - start_time < timeout:
        try:
            with open(MINECRAFT_LOG_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(last_position)
                new_lines = f.readlines()
                last_position = f.tell()
                
                for line in new_lines:
                    # Check for WARN or ERROR (any format)
                    if "/WARN]" in line or "/ERROR]" in line:
                        # Make sure it's connection related
                        if any(keyword in line for keyword in [
                            "Couldn't connect",
                            "Client disconnected",
                            "NeoForge",
                            "running Forge",
                            "timed out",
                            "Connection refused",
                            "connect to server"
                        ]):
                            log_event(f"CONNECTION FAILED: {line.strip()}")
                            return True
        except Exception as e:
            pass
        
        # LINE: Wait 0.5 seconds between log checks
        time.sleep(0.5)
    
    # If we waited the full timeout without errors, connection succeeded
    log_event("Connection appears successful")
    return False

def handle_connection_failure():
    """Handle failed connection - click back to server list"""
    log_event("Handling connection failure - returning to server list...")
    
    # Wait a moment for the error screen to fully load
    # LINE: Wait 2 seconds
    time.sleep(2)
    
    # Click "Back to Server List" button
    # LINE: Mouse move to (950, 608), click, wait 2 seconds
    safe_click(950, 608, delay=2)
    
    # Make sure we're back at multiplayer screen
    # LINE: Wait 1 second
    time.sleep(1)

def monitor_log_for_meteor(start_position=0, timeout=MAX_WAIT_TIME):
    log_event("Monitoring for player builds...")
    
    start_time = time.time()
    last_position = start_position
    
 
    
    while time.time() - start_time < timeout:
        try:
            with open(MINECRAFT_LOG_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(last_position)
                new_lines = f.readlines()
                last_position = f.tell()
                
                for line in new_lines:
                    if '[Meteor]' in line:
                        log_event(f"BUILD DETECTED: {line.strip()}")
                        
                        # Extract coordinates and send goto command
                        x, y, z = extract_coordinates(line)
                        if x is not None and y is not None and z is not None:
                            send_goto_command(x, y, z)
                        
                        return True
        except Exception as e:
            log_event(f"Error reading log: {e}")
        
        # LINE: Wait 2 seconds (CHECK_INTERVAL) between log checks
        time.sleep(CHECK_INTERVAL)
    
    log_event("No builds detected within timeout")
    return False

def trigger_world_download():
    """Press F12 to trigger WorldTools download"""
    log_event("Triggering world download (F12)...")
    pyautogui.press('f12')
    # LINE: Wait 2 seconds after F12
    time.sleep(2)

def wait_for_download_complete(timeout=MAX_WAIT_TIME):
    """Monitor log for WorldTools completion message"""
    log_event("Waiting for download to complete...")
    
    start_time = time.time()
    last_position = 0
    
    if os.path.exists(MINECRAFT_LOG_PATH):
        with open(MINECRAFT_LOG_PATH, 'r', encoding='utf-8', errors='ignore') as f:
            f.seek(0, 2)
            last_position = f.tell()
    
    while time.time() - start_time < timeout:
        try:
            with open(MINECRAFT_LOG_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(last_position)
                new_lines = f.readlines()
                last_position = f.tell()
                
                for line in new_lines:
                    if '[WorldTools] Saved' in line:
                        log_event(f"DOWNLOAD COMPLETE: {line.strip()}")
                        return True
        except Exception as e:
            log_event(f"Error reading log: {e}")
        
        # LINE: Wait 2 seconds (CHECK_INTERVAL) between log checks
        time.sleep(CHECK_INTERVAL)
    
    log_event("Download timeout - may still be in progress")
    return False

def process_server(server):
    """Process a single server"""
    ip_int = server.get('ip')
    port = server.get('port', 25565)
    
    if not ip_int:
        log_event("Skipping server: missing IP")
        return {'status': 'error', 'reason': 'missing_ip'}
    
    ip = int_to_ip(ip_int)
    log_event(f"\n{'='*60}")
    log_event(f"Processing: {ip}:{port}")
    log_event(f"Version: {server.get('version', {}).get('name', 'Unknown')}")
    log_event(f"Country: {server.get('geo', {}).get('country', 'Unknown')}")
    
    try:
        # Join server and get initial log position
        initial_log_pos = join_server(ip, port)
        
        # Wait 10 seconds before checking for errors
        log_event("Waiting for connection to establish...")
        # LINE: Wait 10 seconds
        time.sleep(10)
        
        # Check if connection failed (waits up to 5 more seconds)
        if check_connection_failed(timeout=5):
            handle_connection_failure()
            return {
                'status': 'connection_failed',
                'ip': ip,
                'port': port
            }
        
        # Connection successful - already loaded
        log_event("Server connected successfully")
        
        # Monitor for builds - starting from when we joined
        builds_found = monitor_log_for_meteor(start_position=initial_log_pos)
        
        if builds_found:
            # Trigger download
            trigger_world_download()
            
            # Wait for completion
            download_success = wait_for_download_complete()
            
            # Disconnect
            disconnect_from_server()
            
            return {
                'status': 'downloaded',
                'ip': ip,
                'port': port,
                'download_success': download_success
            }
        else:
            # No builds, disconnect
            disconnect_from_server()
            return {
                'status': 'no_builds',
                'ip': ip,
                'port': port
            }
    
    except Exception as e:
        log_event(f"Error processing server: {e}")
        try:
            disconnect_from_server()
        except:
            pass
        return {
            'status': 'error',
            'ip': ip,
            'port': port,
            'reason': str(e)
        }

def main():
    """Main automation loop"""
    print("\n" + "="*60)
    print("MINECRAFT SERVER AUTO ARCHIVER")
    print("="*60)
    print("\nIMPORTANT:")
    print("1. Make sure Minecraft is running with Meteor + WorldTools")
    print("2. Be at the main menu or multiplayer screen")
    print("3. Don't touch mouse/keyboard during automation")
    print("4. Press Ctrl+C to stop at any time")
    print("\nStarting in 5 seconds...")
    print("="*60 + "\n")
    
    # LINE: Wait 5 seconds before starting
    time.sleep(5)
    
    # Load servers
    servers = load_servers()
    if not servers:
        return
    
    # Initialize tracking
    results = {
        'downloaded': 0,
        'no_builds': 0,
        'connection_failed': 0,
        'errors': 0
    }
    
    log_event(f"Starting archival of {len(servers)} servers")
    
    # Process each server
    for i, server in enumerate(servers, 1):
        log_event(f"\n[Server {i}/{len(servers)}]")
        
        result = process_server(server)
        
        # Handle result status
        status = result.get('status', 'error')
        if status in results:
            results[status] += 1
        else:
            results['errors'] += 1
        
        # Brief pause between servers
        # LINE: Wait 3 seconds between servers
        time.sleep(3)
    
    # Final summary
    print("\n" + "="*60)
    print("ARCHIVAL COMPLETE")
    print("="*60)
    print(f"Total servers: {len(servers)}")
    print(f"Downloaded: {results['downloaded']}")
    print(f"No builds: {results['no_builds']}")
    print(f"Connection failed: {results['connection_failed']}")
    print(f"Errors: {results['errors']}")
    print("="*60 + "\n")
    
    log_event("Archival session complete")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✓ Stopped by user")
        log_event("Session stopped by user")