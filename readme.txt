Live run: https://youtu.be/6s74uC5A6zg

COMPLETE SETUP GUIDE
Prerequisites:
bashpip install pyautogui requests
Step 1: Prepare Server List
Manual paste from API:

Visit your API URL with filters
Copy the JSON response
Save as servers.json in the script folder


Step 2: Configure Minecraft

Launch Minecraft 1.21.4 with these mods:

(*) = REQUIRED

    *Language: Python 3.12
    *Automation: PyAutoGUI (mouse/keyboard control)
    *Minecraft Java Edition (1.21.4) Fabric
    Mods:
        *Meteor Client (structure detection via logs)
            https://anticope.pages.dev/addons/? *https://anticope.pages.dev/addons/?addon=etianl%2FTrouser-Streak (Basefinder Module) https://www.meteoraddons.com/ (Meteor Addons)
            *WorldTools (World downloader)
            *ViaFabricPlus (cross-version compatibility, this archiver can download worlds on MOST versions but may lead to corruption)
            *Baritone
            ImmediatelyFast (Chunk loading performance for faster detections)
            Lithium (performance)
            *Fabric-api
            *Fabric-language-koltin
            *Cloth-config
            Sodium (performance) Sodium Extra (performance)



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
The script uses screen coordinates that may need adjustment for your screen resolution:
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
Don't touch mouse/keyboard while running
Screen must stay visible (won't work minimized)
Check latest.log path is correct for your system

QUESTIONS FOR YOU:

What's your screen resolution? (I assumed 1920x1080)
Fullscreen or windowed mode?

SUPER SIMPLE SETUP:
Step 1: Get Your Servers

Go to your API URL with your filters:

   https://api.cornbread2100.com/v1/servers?limit=100&skip=0&sort=lastSeen&descending=true&playerLimit=20&version=1.16.5&descriptionVector=A+Minecraft+Server&vanilla=true

Copy the ENTIRE JSON response from your browser
Create a file called servers.json in the same folder as the script
Paste the JSON into servers.json
Save it

Step 2: Run
bashpip install pyautogui
python minecraft_archiver.py

To Add More Servers Later:
Just go to the API URL again with skip=100, skip=200, etc., copy the JSON, and paste it into servers.json (as an array).
