#!/usr/bin/env python3
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
import subprocess
import threading
import time

# Keyboard mapping (example)
KEYS = [
    ['Q','W','E','R','T','Y','U','I','O','P'],
    ['A','S','D','F','G','H','J','K','L'],
    ['Z','X','C','V','B','N','M','SPACE']
]

DEBUG = True

def debug(msg):
    if DEBUG:
        print(f"[DEBUG] {msg}")

# Get the currently active window using X11
def get_active_window():
    try:
        wid = subprocess.check_output(["xdotool", "getactivewindow"]).decode().strip()
        name = subprocess.check_output(["xdotool", "getwindowname", wid]).decode().strip()
        cls = subprocess.check_output(["xprop", "-id", wid, "WM_CLASS"]).decode().strip()
        return name, cls
    except Exception as e:
        return "<unknown>", "<noclass>"

# Send a keypress using xdotool
def send_key(key):
    if key == "SPACE":
        subprocess.call(["xdotool", "key", "space"])
    else:
        subprocess.call(["xdotool", "key", key.lower()])

class KeyboardOverlay(Gtk.Window):
    def __init__(self):
        super().__init__(title="Keyboard Overlay")
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_keep_above(True)
        self.set_decorated(False)
        self.set_app_paintable(True)
        self.modify_bg(Gtk.StateType.NORMAL, Gdk.color_parse("black"))
        self.set_opacity(0.7)
        self.set_default_size(800, 200)
        self.connect("destroy", Gtk.main_quit)

        grid = Gtk.Grid()
        grid.set_row_spacing(5)
        grid.set_column_spacing(5)
        self.add(grid)

        for r, row in enumerate(KEYS):
            for c, key in enumerate(row):
                button = Gtk.Button(label=key)
                button.connect("clicked", self.on_key_click, key)
                grid.attach(button, c, r, 1, 1)

        self.show_all()

    def on_key_click(self, widget, key):
        debug(f"Sending key: {key}")
        send_key(key)

# Periodically check active window
def monitor_active_window(win):
    last_name = None
    while True:
        name, cls = get_active_window()
        if name != last_name:
            debug(f"Active window: {name}, class: {cls}")
            last_name = name
        time.sleep(0.5)

if __name__ == "__main__":
    debug("Application activated")
    win = KeyboardOverlay()

    # Run window monitor in background thread
    threading.Thread(target=monitor_active_window, args=(win,), daemon=True).start()

    Gtk.main()
