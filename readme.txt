# Minecraft World Archiver

An automated bot that joins public Minecraft servers, detects player-built structures, and downloads the worlds for preservation.

**Live demo:** https://youtu.be/6s74uC5A6zg

**Companion repository (preservation pipeline):** [minecraft-archive](https://github.com/SF2040/minecraft-archive-AIPUPLOAD)

---

## What it does

1. Reads a list of public Minecraft servers from `servers.json`
2. Joins each server automatically via Direct Connect
3. Monitors Meteor Client logs for player-built structure detections
4. When a build is detected, presses F12 to trigger WorldTools to download the world
5. Disconnects and moves to the next server
6. Logs every attempt to `archival_log.txt`

Downloaded worlds can then be packaged and uploaded using the companion [minecraft-archive](https://github.com/SF2040/minecraft-archive) repository, which follows the ISO 14721 (OAIS) framework.

---

## Requirements

### Software
- **Windows** (scripts use Windows paths and PyAutoGUI)
- **Python 3.12**
- **Minecraft Java Edition 1.21.4** with the **Fabric** mod loader
- **Screen resolution:** 1920x1080 recommended (coordinates may need adjustment otherwise)
- A legitimate Minecraft account

### Python packages
```bash
pip install pyautogui requests
```

### Required Minecraft mods
| Mod | Purpose |
|---|---|
| [Fabric API](https://modrinth.com/mod/fabric-api) | Mod loader dependency |
| [Fabric Language Kotlin](https://modrinth.com/mod/fabric-language-kotlin) | Mod loader dependency |
| [Cloth Config](https://modrinth.com/mod/cloth-config) | Mod loader dependency |
| [Meteor Client](https://meteorclient.com/) | Structure detection via logs |
| [Trouser Streak](https://anticope.pages.dev/addons/?addon=etianl%2FTrouser-Streak) | Meteor addon — provides BaseFinder module |
| [Meteor Addons](https://www.meteoraddons.com/) | Extra Meteor modules |
| [WorldTools](https://www.curseforge.com/minecraft/mc-mods/worldtools) | Downloads the world (F12) |
| [ViaFabricPlus](https://modrinth.com/mod/viafabricplus) | Lets you join servers on other versions |
| [Baritone](https://meteorclient.com/api/downloadBaritone) | Automated pathing |

### Optional (performance)
- [ImmediatelyFast](https://modrinth.com/mod/immediatelyfast) — faster chunk loading
- [Lithium](https://modrinth.com/mod/lithium) — general performance
- [Sodium](https://modrinth.com/mod/sodium) + Sodium Extra — rendering performance

---

## Setup

### 1. Clone this repository
```bash
git clone https://github.com/SF2040/scripts.git
cd scripts
```

### 2. Install Python dependencies
```bash
pip install pyautogui requests
```

### 3. Prepare `servers.json`

Visit the server list API with your filters, for example:
```
https://api.cornbread2100.com/v1/servers?limit=100&skip=0&sort=lastSeen&descending=true&playerLimit=20&version=1.16.5&descriptionVector=A+Minecraft+Server&vanilla=true
```

Copy the full JSON response and save it as `servers.json` in the repo folder.

To add more servers later, repeat with `skip=100`, `skip=200`, etc., and append the results to `servers.json`.

### 4. Configure Minecraft mods

- **Meteor Client → BaseFinder:** enable the module and make sure it outputs to chat.
- **WorldTools:** join any server, press F12, and confirm `[WorldTools] Saved...` appears in chat/logs. If not, check the keybind.
- **Window:** use 1920x1080, windowed or fullscreen.

### 5. Adjust screen coordinates (if not on 1920x1080)

`minecraft_archiver4.py` clicks fixed screen positions. If your resolution differs, update these lines:

```python
pyautogui.click(960, 400)  # Multiplayer button
pyautogui.click(960, 500)  # Direct Connect button
pyautogui.click(960, 500)  # Disconnect button
```

To find the right coordinates, run:
```python
import pyautogui, time
time.sleep(3)
print(pyautogui.position())
```
Hover your mouse over the target button during the 3-second delay.

---

## Usage

1. Launch Minecraft 1.21.4 Fabric with all required mods loaded.
2. Reach the main menu.
3. In a terminal, run:
   ```bash
   python minecraft_archiver4.py
   ```
4. **Do not touch the mouse or keyboard** while it runs.
5. **Keep the Minecraft window visible** — it will not work minimised.

Each attempt is logged to `archival_log.txt` with the IP, port, outcome, and timestamp. Downloaded worlds are saved to `.minecraft\saves\`.

---

## Repository contents

| File | Purpose |
|---|---|
| `minecraft_archiver4.py` | Main bot: joins servers, detects builds, triggers downloads |
| `servers.json` | List of servers to visit |
| `archival_log.txt` | Log of every server attempted and the outcome |
| `fetch_servers.py.txt` | Helper for pulling server lists from the API |
| `prepare_servers.py.txt` | Helper for formatting server lists |
| `path.py.txt` | Path configuration helper |
| `build_aip.py`, `upload_aip.py` | Part 2 preservation scripts — see [minecraft-archive](https://github.com/SF2040/minecraft-archive) |

---

## Known limitations

- Many downloaded worlds are duplicates or incomplete (small builds, partially rendered chunks).
- The block whitelist that triggers "player build" detection can produce false positives (e.g. a single sapling).
- Timing is fixed — slow servers may not finish downloading before disconnect.
- Only tested on Windows at 1920x1080.

### Planned improvements
- Open chests to include their contents in the save
- Refine the block whitelist to cut uninteresting downloads
- Optimise timing and Baritone pathing
- Automate API fetching into `servers.json`

---

## Disclaimer

**NOT AN OFFICIAL MINECRAFT PRODUCT. NOT APPROVED BY OR ASSOCIATED WITH MOJANG OR MICROSOFT.**

This is an independent, non-commercial tool for personal research, education, and data preservation.

- It requires a legitimate, paid Minecraft account and does not support piracy or unauthorised access.
- It does not distribute any Microsoft/Mojang source code, game assets, or modified client binaries. All third-party mods must be obtained by the user in accordance with their own licences and the Minecraft EULA.
- It only connects to publicly accessible servers that have whitelisting disabled (`"cracked": false`) and are configured by their operators to accept global connections.

**References:**
1. [Minecraft EULA](https://www.minecraft.net/en-us/eula)
2. [Minecraft Usage Guidelines](https://www.minecraft.net/en-us/usage-guidelines)
3. [Microsoft Services Agreement](https://www.microsoft.com/en-au/servicesagreement)
