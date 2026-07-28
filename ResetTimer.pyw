#! python3
import ctypes
import random
import sys
import threading
import os
import json
import time
from time import sleep
import pyautogui
import pystray
from PIL import Image, ImageDraw

# --- Request Administrator Privileges ---
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if not is_admin():
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{__file__}"', None, 1)
    sys.exit() 

# --- Windows API Constants & Structs ---
ES_CONTINUOUS        = 0x80000000
ES_SYSTEM_REQUIRED   = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040
ES_DISPLAY_REQUIRED  = 0x00000002
ERROR_ALREADY_EXISTS = 183

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

SW_MINIMIZE = 6
SW_RESTORE = 9
GA_ROOT = 2

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwTime", ctypes.c_uint)
    ]

class POINT(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long)
    ]

ctypes.windll.user32.WindowFromPoint.argtypes = [POINT]
ctypes.windll.user32.WindowFromPoint.restype = ctypes.c_void_p
ctypes.windll.user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
ctypes.windll.user32.GetAncestor.restype = ctypes.c_void_p

# --- Config Management ---
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stay_awake_settings.json")

def load_settings():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                return (
                    data.get("idle_threshold", 30.0),
                    data.get("action_mode", "Window and Mouse"),
                    data.get("loop_interval", 1.0)
                )
        except Exception:
            pass
    return 30.0, "Window and Mouse", 1.0

def save_settings():
    data = {
        "idle_threshold": idle_threshold,
        "action_mode": action_mode,
        "loop_interval": loop_interval
    }
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass

# --- Global Variables ---
script_running = True 
idle_threshold, action_mode, loop_interval = load_settings()

# --- Helper Functions ---
def get_idle_time():
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    ctypes.windll.kernel32.GetTickCount.restype = ctypes.c_uint
    
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        current_time = ctypes.windll.kernel32.GetTickCount()
        idle_milliseconds = (current_time - lii.dwTime) & 0xFFFFFFFF
        return idle_milliseconds / 1000.0
    return 0.0

def get_visible_windows():
    hwnds = []
    def foreach_window(hwnd, lParam):
        if (
            ctypes.windll.user32.IsWindowVisible(hwnd)
            and not ctypes.windll.user32.IsIconic(hwnd)
        ):
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value
                #print(repr(buff.value), ctypes.windll.user32.IsIconic(hwnd))
                if title not in ["Program Manager", "Settings", "Microsoft Text Input Application"]:
                    hwnds.append(hwnd)
        return True
    
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    ctypes.windll.user32.EnumWindows(EnumWindowsProc(foreach_window), 0)
    return hwnds

def get_window_under_cursor():
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    hwnd = ctypes.windll.user32.WindowFromPoint(pt)
    
    if hwnd:
        root_hwnd = ctypes.windll.user32.GetAncestor(hwnd, GA_ROOT)
        target_hwnd = root_hwnd if root_hwnd else hwnd
        length = ctypes.windll.user32.GetWindowTextLengthW(target_hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(target_hwnd, buff, length + 1)
        title = buff.value
        if title not in ["Program Manager"]:
            return target_hwnd
    return None

# --- Single Instance (Mutex) Check ---
mutex_name = "Global\\StayAwakeScript_Mutex_12345"
mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
    ctypes.windll.user32.MessageBoxW(0, "The Stay Awake script is already running in the tray.", "Already Running", 0x30 | 0x0)
    sys.exit()

# --- Background Monitoring Thread ---
def monitoring_loop():
    global idle_threshold, action_mode, loop_interval
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED | ES_DISPLAY_REQUIRED)
    pyautogui.FAILSAFE = False
    
    # Advanced Memory tracking
    minimized_windows = []
    last_toggled_hwnd = None 
    expected_x, expected_y = -1, -1
    last_action_was_ours = False
    previous_idle_seconds = 0
    next_action_time = time.time()
    phase = "minimize"

    while script_running:
        try:
            now = time.time()
            idle_seconds = get_idle_time()
            current_mouse = pyautogui.position()
            
            # --- 1. USER RETURN DETECTION ---
            user_interrupted = False
            
            # Did the mouse physically deviate from where the script parked it?
            if expected_x != -1:
                if abs(current_mouse.x - expected_x) > 10 or abs(current_mouse.y - expected_y) > 10:
                    user_interrupted = True
                    expected_x, expected_y = -1, -1
            
            # Did the idle timer reset from a keystroke or real mouse click?
            if idle_seconds < previous_idle_seconds - 0.1:
                if last_action_was_ours:
                    last_action_was_ours = False # Ignore our own reset
                else:
                    user_interrupted = True
            
            if user_interrupted:
                # Instantly snap all hidden windows back to the screen
                if minimized_windows:
                    for hwnd in minimized_windows:
                        ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
                    minimized_windows.clear()
                    last_toggled_hwnd = None
                
                expected_x, expected_y = -1, -1
                last_action_was_ours = False
            
            previous_idle_seconds = idle_seconds

            # --- 2. AUTOMATION EXECUTION ---
            if idle_seconds >= idle_threshold and now >= next_action_time:
            
                visible_windows = get_visible_windows()
                print(f"Phase={phase}")
                # ==========================================================
                # MINIMIZE PHASE
                # ==========================================================
                if phase == "minimize":
                
                    
                    # No visible windows left -> start restoring
                    if not visible_windows:
                        phase = "restore"
                
                    else:
                        moved_mouse = False
                
                        if action_mode in ["Window Only", "Window and Mouse"]:
                
                            target_hwnd = None
                
                            if action_mode == "Window Only":
                                target_hwnd = random.choice(visible_windows)
                
                            elif action_mode == "Window and Mouse":
                                target_hwnd = get_window_under_cursor()
                
                            if (
                                target_hwnd
                                and target_hwnd in visible_windows
                                and target_hwnd not in minimized_windows
                            ):
                                ctypes.windll.user32.ShowWindow(target_hwnd, SW_MINIMIZE)
                                minimized_windows.append(target_hwnd)
                
                        if action_mode in ["Mouse Only", "Window and Mouse"]:
                
                            x_start = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
                            y_start = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
                            virtual_width = ctypes.windll.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
                            virtual_height = ctypes.windll.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
                
                            target_x = random.randint(x_start, x_start + virtual_width - 1)
                            target_y = random.randint(y_start, y_start + virtual_height - 1)
                
                            pyautogui.moveTo(target_x, target_y, 0.5)
                
                            moved_mouse = True
                            expected_x, expected_y = target_x, target_y
                
                            new_target = get_window_under_cursor()
                            if new_target:
                                ctypes.windll.user32.SetForegroundWindow(new_target)
                
                        if moved_mouse:
                            last_action_was_ours = True
                
                # ==========================================================
                # RESTORE PHASE
                # ==========================================================
                elif phase == "restore":
                
                    if minimized_windows:
                
                        hwnd = minimized_windows.pop()
                
                        ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
                
                    else:
                        phase = "minimize"
                        last_toggled_hwnd = None
                
                delay = random.uniform(3.0, 60.0) if loop_interval == "random" else float(loop_interval)
                next_action_time = now + delay
            # Extremely fast sleep ensures instant reaction if the user touches the mouse
            sleep(0.5) 
                
        except Exception:
            sleep(5) 
            
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)

# --- System Tray Menu Logic ---
def create_icon_image():
    image = Image.new('RGB', (64, 64), color=(40, 40, 40))
    dc = ImageDraw.Draw(image)
    dc.ellipse((12, 12, 52, 52), fill=(0, 200, 0))
    return image

def exit_action(icon, item):
    global script_running
    script_running = False  
    icon.stop()             

def set_time_threshold(seconds):
    def action(icon, item):
        global idle_threshold
        idle_threshold = seconds
        save_settings()
    return action

def is_time_checked(seconds):
    def checked(item):
        global idle_threshold
        return idle_threshold == seconds
    return checked

def set_action_mode(mode_name):
    def action(icon, item):
        global action_mode
        action_mode = mode_name
        save_settings()
    return action

def is_mode_checked(mode_name):
    def checked(item):
        global action_mode
        return action_mode == mode_name
    return checked

def set_loop_interval(val):
    def action(icon, item):
        global loop_interval
        loop_interval = val
        save_settings()
    return action

def is_loop_interval_checked(val):
    def checked(item):
        global loop_interval
        return loop_interval == val
    return checked

menu = pystray.Menu(
    pystray.MenuItem(
        "Action Mode",
        pystray.Menu(
            pystray.MenuItem("Mouse Only", set_action_mode("Mouse Only"), checked=is_mode_checked("Mouse Only"), radio=True),
            pystray.MenuItem("Window Only", set_action_mode("Window Only"), checked=is_mode_checked("Window Only"), radio=True),
            pystray.MenuItem("Window and Mouse", set_action_mode("Window and Mouse"), checked=is_mode_checked("Window and Mouse"), radio=True)
        )
    ),
    pystray.MenuItem(
        "Set Idle Timeout",
        pystray.Menu(
            pystray.MenuItem("10 Seconds", set_time_threshold(10.0), checked=is_time_checked(10.0), radio=True),
            pystray.MenuItem("30 Seconds", set_time_threshold(30.0), checked=is_time_checked(30.0), radio=True),
            pystray.MenuItem("1 Minute", set_time_threshold(60.0), checked=is_time_checked(60.0), radio=True),
            pystray.MenuItem("5 Minutes", set_time_threshold(300.0), checked=is_time_checked(300.0), radio=True),
            pystray.MenuItem("15 Minutes", set_time_threshold(900.0), checked=is_time_checked(900.0), radio=True)
        )
    ),
    pystray.MenuItem(
        "Set Loop Sleep (Interval)",
        pystray.Menu(
            pystray.MenuItem("1 Second", set_loop_interval(1.0), checked=is_loop_interval_checked(1.0), radio=True),
            pystray.MenuItem("3 Seconds", set_loop_interval(3.0), checked=is_loop_interval_checked(3.0), radio=True),
            pystray.MenuItem("5 Seconds", set_loop_interval(5.0), checked=is_loop_interval_checked(5.0), radio=True),
            pystray.MenuItem("10 Seconds", set_loop_interval(10.0), checked=is_loop_interval_checked(10.0), radio=True),
            pystray.MenuItem("Random (3-60s)", set_loop_interval("random"), checked=is_loop_interval_checked("random"), radio=True)
        )
    ),
    pystray.MenuItem("Exit", exit_action)
)

tray_icon = pystray.Icon("StayAwake", create_icon_image(), "Stay Awake: Running", menu=menu)

monitor_thread = threading.Thread(target=monitoring_loop, daemon=True)
monitor_thread.start()
tray_icon.run()
os._exit(0)
