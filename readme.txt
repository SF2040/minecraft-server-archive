COMPLETE SETUP GUIDE
Prerequisites:
bashpip install pyautogui requests
Step 1: Prepare Server List
Option A - Manual paste from API:

Visit your API URL with filters
Copy the JSON response
Save as servers.json in the script folder

Option B - Use helper script:
bashpython prepare_servers.py
Edit the filters in the script first, then run it.

Step 2: Configure Minecraft

Launch Minecraft 1.16.5 with these mods:

Meteor Client (with BaseFinder enabled)
WorldTools
ViaFabric
Baritone


Configure Meteor BaseFinder:

Open Meteor menu
Enable BaseFinder module
Make sure it outputs to chat


Test WorldTools:

Join any server
Press F12
Confirm it says "[WorldTools] Saved..." in chat/logs


Position window:

1920x1080 resolution recommended
Windowed or fullscreen




Step 3: Adjust Screen Coordinates (IMPORTANT!)
The script uses screen coordinates that may need adjustment for your setup:
Edit minecraft_archiver.py and update these lines:
python# Line ~78: Click Multiplayer button
pyautogui.click(960, 400)  # Adjust Y coordinate

# Line ~82: Click Direct Connect  
pyautogui.click(960, 500)  # Adjust Y coordinate

# Line ~53: Disconnect button
pyautogui.click(960, 500)  # Adjust coordinates
To find coordinates:

Run this test:

pythonimport pyautogui
import time
time.sleep(3)
print(pyautogui.position())  # Hover mouse and check position

Step 4: Run The Archiver
bashpython minecraft_archiver.py
What happens:

Loads servers from servers.json
For each server:

Joins via Direct Connect
Waits 15 seconds
Monitors logs for [Meteor] messages
If builds found → Presses F12
Waits for download complete
Disconnects


Logs everything to archival_log.txt


Important Notes:
⚠️ Don't touch mouse/keyboard while running
⚠️ Screen must stay visible (automation won't work minimized)
⚠️ Test with 1-2 servers first to verify coordinates
⚠️ Check latest.log path is correct for your system

QUESTIONS FOR YOU:

What's your screen resolution? (I assumed 1920x1080)
Fullscreen or windowed mode?
Do you want to test it on a single server first?

Once you confirm these, we can do a test run together!prepare_servers is too complex, this needs to be as simple as possible. I can view the json from my custom api link. All i want to do it paste them all somewhere manually where the server archiver can access. We can automate this step in the future16 DecPerfect! Let's make it dead simple:servers.json - Paste Your API Response HereCode ∙ Version 2 [
  {
    "ip": 3586601036,
    "port": 35565,
    "version": {"name": "1.16.5", "protocol": 754},
    "description": "A Minecraft Server"
  }
]SUPER SIMPLE SETUP:
Step 1: Get Your Servers

Go to your API URL with your filters:

   https://api.cornbread2100.com/v1/servers?limit=100&skip=0&sort=lastSeen&descending=true&playerLimit=20&version=1.16.5&descriptionVector=A+Minecraft+Server&vanilla=true

Copy the ENTIRE JSON response from your browser
Create a file called servers.json in the same folder as the script
Paste the JSON into servers.json
Save it

That's it!

Step 2: Run
bashpip install pyautogui
python minecraft_archiver.py

To Add More Servers Later:
Just go to the API URL again with skip=100, skip=200, etc., copy the JSON, and paste it into servers.json (as an array).
