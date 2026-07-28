# KeepWorking 
A script that tells Windows to change how it handles sleep and screen timeout 


## General Description
The **Stay Awake Utility** is a lightweight, background Python script designed to prevent your Windows computer from going to sleep or locking your screen while you are away. Instead of simply jiggling the mouse in place, it dynamically mimics organic human interaction by randomly moving the cursor across multiple monitors and intelligently minimizing/restoring active windows. 

**Core Features:**
*   **Invisible Operation:** Runs silently in the background with a convenient System Tray icon for controls.
*   **Smart Memory:** Tracks which windows it modifies and prevents interacting with the same application repeatedly.
*   **Panic Restore:** Instantly detects when you physically return to your computer (via mouse movement or keystroke) and immediately restores any windows it hid so you can resume work seamlessly.
*   **Admin-Level Access:** Runs with elevated privileges to safely interact with high-security Windows like the Task Manager.

---

## Prerequisites (Installation)
This script relies on standard Windows APIs and a few third-party Python libraries. 

1. Ensure you have **Python 3** installed on your system.
2. Open your Command Prompt or PowerShell and install the required packages by running:

    ```cmd
    pip install pyautogui pystray Pillow
    ```

*(Note: Libraries like `ctypes`, `threading`, `json`, and `os` are built directly into standard Python and do not need to be installed.)*

---

## How to Run at Windows Startup
To have the script automatically start monitoring every time you turn on your computer, you can place a shortcut in your Windows Startup folder.

1. Right-click your `ResetTimer.pyw` file and select **Create shortcut**.
2. Press `Win + R` on your keyboard to open the **Run** dialog box.
3. Type `shell:startup` and press **Enter**. This will open your user Startup folder.
4. Drag and drop the **shortcut** you created in Step 1 into this Startup folder. 

*Your script will now automatically launch in the system tray every time you log in to Windows!*

---

## Tray Icon Menu Settings
Once the script is running, you will see a green circle icon in your System Tray (near the clock on your taskbar). Right-click this icon to access the following persistent settings:

### 1. Action Mode
Determines how the script behaves when it is time to simulate activity.
*   **Mouse Only:** The script will solely move your cursor to random coordinates across your screens. Windows are ignored.
*   **Window Only:** The mouse cursor stays perfectly still. The script will pick a random visible application on your screen, minimize it, and restore it.
*   **Window and Mouse:** The ultimate simulation. The script looks directly at the application under your mouse cursor, toggles it, moves the mouse to a new random location, and brings the newly targeted window to the foreground.

### 2. Set Idle Timeout
Determines how long you must be away from the computer before the script takes over. 
*   **Options:** `10 Seconds`, `30 Seconds`, `1 Minute`, `5 Minutes`, `15 Minutes`.
*   *Example:* If set to 5 minutes, the script will silently count the seconds since your last physical keystroke or mouse movement. Once 5 minutes is reached, it will trigger the selected Action Mode.

### 3. Set Loop Sleep (Interval)
Controls the pacing of the automated actions while you are away. 
*   **Options:** `1 Second`, `3 Seconds`, `5 Seconds`, `10 Seconds`, `Random (3-60s)`.
*   *Example:* If set to 5 Seconds, the script will wait exactly 5 seconds between every automated mouse move or window toggle.
*   *Random Mode:* Highly recommended for avoiding detection. The script will wait a completely unpredictable amount of time (between 3 and 60 seconds) between each action, perfectly mimicking erratic human behavior.

### 4. Exit
Safely terminates the background process, clears the system tray icon, and returns your computer's sleep/power management over to default Windows settings.
