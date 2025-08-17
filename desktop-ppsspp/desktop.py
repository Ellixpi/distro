#!/usr/bin/env python3
# desktop.py — Fixed overlay, glowy popups, carousel/selection, clean CSS

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
import psutil
import os
import time
import subprocess
import fcntl
from evdev import InputDevice, list_devices, ecodes
import shutil
import sys

# ---------- Styling (GTK CSS) ----------
CSS = b"""
window { background-color: #121212; }

#bg { }

.popup-dialog {
    background: linear-gradient(145deg, rgba(155,155,155,0.85) 0%, rgba(120,120,120,0.70) 100%);
    border-radius: 20px;
    border: 1px solid rgba(255,255,255,0.12);
    color: white;
    font-size: 20px;
    font-weight: bold;
    padding: 25px;
    min-width: 400px;
    min-height: 100px;
    box-shadow:
        0 0 25px rgba(255,255,255,0.5),
        inset 0 1px 10px rgba(255,255,255,0.45);
}

.app-button {
  background: linear-gradient(145deg, rgba(255,255,255,0.55) 0%, rgba(220,220,220,0.40) 100%);
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.12);
  color: white;
  font-weight: 600;
  font-size: 20px;
  min-width: 220px;
  min-height: 220px;
  padding: 12px;
}

.app-button:hover {
  background-color: rgba(255,255,255,0.12);
}

.app-button.selected {
  background: linear-gradient(145deg, rgba(255,255,255,0.75) 0%, rgba(220,220,220,0.50) 100%);
  box-shadow:
    inset 0 1px 8px rgba(255,255,255,0.45),
    0 0 18px rgba(255,255,255,0.45);
  color: white;
}

.app-label { color: white; margin-top: 8px; }

#settings-btn {
  background: linear-gradient(145deg, rgba(255,255,255,0.55) 0%, rgba(220,220,220,0.40) 100%);
  border-radius: 12px;
  border: 1px solid rgba(255,255,255,0.12);
  color: white;
  font-size: 18px;
  padding: 10px 14px;
}

#settings-btn.selected {
  background: linear-gradient(145deg, rgba(255,255,255,0.75) 0%, rgba(220,220,220,0.50) 100%);
  box-shadow:
    inset 0 1px 8px rgba(255,255,255,0.45),
    0 0 15px rgba(255,255,255,0.45);
  color: white;
}

#clock {
  color: white;
  background: linear-gradient(145deg, rgba(255,255,255,0.55) 0%, rgba(220,220,220,0.40) 100%);
  padding: 6px 10px;
  border-radius: 8px;
  font-family: monospace;
  font-size: 20px;
}
"""

# ---------- App definitions ----------
APP_LIST = [
    {"name": "Settings", "cmd": ["python3", "settings.py"], "icon": "settings.png"},
    {"name": "Browser", "cmd": ["/usr/bin/firefox-esr"], "icon": "browser.png"},
    {"name": "PPSSPP",  "cmd": ["/usr/local/bin/PPSSPP.AppImage", "--fullscreen"], "icon": "ppsspp.png"},
    {"name": "Files",   "cmd": ["/usr/bin/nautilus"], "icon": "nautilus.png"},
    {"name": "Revolt", "cmd": ["/usr/local/bin/Revolt.AppImage"], "icon": "revolt.png"},
    {"name": "Steam", "cmd": ["steam"], "icon": "steam.png"},
    {"name": "Minecraft", "cmd": ["/usr/local/bin/PrismLauncher.AppImage"], "icon": "prism.png"},
    {"name": "Shutdown System", "cmd": [""], "icon": "shutdown.png"},
]

# ---------- Launcher Window ----------
class LauncherWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Launcher")
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)

        screen = self.get_screen()
        monitor_num = screen.get_primary_monitor()
        monitor = screen.get_monitor_geometry(monitor_num)
        self.set_default_size(monitor.width, monitor.height)
        self.move(monitor.x, monitor.y)

        style = Gtk.CssProvider()
        style.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(screen, style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        overlay = Gtk.Overlay()
        self.add(overlay)
        
        self.connect("delete-event", self.on_delete)
        # Background
        bg_path = os.path.join(os.path.dirname(__file__), "purple-ppsspp-bg.jpg")
        if os.path.exists(bg_path):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file(bg_path)
                scaled = pb.scale_simple(monitor.width, monitor.height, GdkPixbuf.InterpType.BILINEAR)
                self.bg = Gtk.Image.new_from_pixbuf(scaled)
                self.bg.set_name("bg")
                overlay.add(self.bg)
            except Exception as e:
                print("bg load failed:", e)
                self.bg = None
        else:
            self.bg = None

        # Buttons container (horizontal box)
        self.button_box = Gtk.Box(spacing=30)
        self.button_box.set_halign(Gtk.Align.CENTER)
        self.button_box.set_valign(Gtk.Align.CENTER)
        overlay.add_overlay(self.button_box)

        # Topbar container
        self.topbar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.topbar_box.set_halign(Gtk.Align.FILL)
        self.topbar_box.set_valign(Gtk.Align.START)
        self.topbar_box.set_margin_top(16)
        self.topbar_box.set_margin_start(16)
        self.topbar_box.set_margin_end(16)
        overlay.add_overlay(self.topbar_box)

        #self.settings_btn = Gtk.Button(label="Settings")
        #self.settings_btn.set_name("settings-btn")
        #self.settings_btn.connect("clicked", self.on_settings)
        #self.settings_btn.set_can_focus(True)
        #self.topbar_box.pack_start(self.settings_btn, False, False, 0)

        self.topbar_box.pack_start(Gtk.Label(), True, True, 0)

        self.clock = Gtk.Label(label="")
        self.clock.set_name("clock")
        self.topbar_box.pack_end(self.clock, False, False, 0)
        GLib.timeout_add_seconds(1, self._tick_clock)
        self._tick_clock()

        # Create buttons
        self.app_buttons = []
        for app in APP_LIST:
            btn = self._make_app_button(app)
            self.app_buttons.append(btn)
            self.button_box.pack_start(btn, False, False, 0)

        # Selection + joystick
        self.selected = None
        self.selection_enabled = False
        GLib.timeout_add(500, self._enable_selection_delay)

        self.joystick = None
        self._find_joystick()
        self.joystick_last = 0
        self.joystick_move_delay = 0.25
        GLib.timeout_add(30, self._poll_joystick)

        # Events
        self.connect("key-press-event", self._on_key)

        self.show_all()

    # ---------- Selection helpers ----------
    def _apply_selection_styles(self):
        for i, btn in enumerate(self.app_buttons):
            ctx = btn.get_style_context()
            if i == self.selected:
                ctx.add_class("selected")
            else:
                ctx.remove_class("selected")

    def _enable_selection_delay(self):
        self.selection_enabled = True
        if self.selected is None and self.app_buttons:
            self._set_selection(0)
        return False

    def _set_selection(self, idx):
        if not self.app_buttons:
            self.selected = None
            return
        idx = idx % len(self.app_buttons)
        self.selected = idx
        self._apply_selection_styles()

    def _move_selection(self, delta):
        if self.selected is None:
            if self.app_buttons:
                self._set_selection(0)
            return
        self._set_selection(self.selected + delta)

    # ---------- Button creation / launching ----------
    def _make_app_button(self, app):
        btn = Gtk.Button()
        btn.get_style_context().add_class("app-button")
        btn.set_can_focus(False)
        btn.set_size_request(220, 220)

        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        v.set_halign(Gtk.Align.CENTER)
        v.set_valign(Gtk.Align.CENTER)

        icon_path = os.path.join(os.path.dirname(__file__), app["icon"])
        if os.path.exists(icon_path):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file(icon_path)
                pb = pb.scale_simple(128, 128, GdkPixbuf.InterpType.BILINEAR)
                img = Gtk.Image.new_from_pixbuf(pb)
                v.pack_start(img, False, False, 0)
            except Exception as e:
                print("icon load failed:", e)

        lbl = Gtk.Label(label=app["name"])
        lbl.set_name("app-label")
        v.pack_start(lbl, False, False, 0)

        btn.add(v)
        btn.connect("clicked", lambda w: self.launch_app(app))
        return btn
    
    
    def launch_app(self, app, options=None):
        """
        self: LauncherWindow instance
        app: dict from APP_LIST
        """
        if app["name"] == "Shutdown System":
            play_sound("quit.mp3")
            self._show_popup("Shutting Down. Please Wait")
            time.sleep(5)
            os.system("shutdown now -h")
            Gtk.main_quit()
            sys.exit()
        
        try:
            cmd_name = app["cmd"][0]  # access dict key instead of attribute
            # List all windows
            output = subprocess.getoutput("wmctrl -lx").splitlines()
            win_id = None

            for line in output:
                parts = line.split()
                if len(parts) < 3:
                    continue
                wid, wclass = parts[0], parts[2]
                if cmd_name.lower() in wclass.lower():
                    win_id = wid
                    break

            if win_id:
                subprocess.run(["xdotool", "windowmap", win_id])
                subprocess.run(["xdotool", "windowactivate", win_id])
                print(f"{app['name']} focused")
            else:
                subprocess.Popen(app["cmd"])
                print(f"Launching {app['name']}")
            
            play_sound("open.mp3")
        except Exception as e:
            print(f"Error in launch_app: {e}")
            play_sound("error.mp3")




    # ---------- Popups ----------
    def _show_popup(self, text, duration=1500):
        popup = Gtk.Window(type=Gtk.WindowType.POPUP)
        popup.set_transient_for(self)
        popup.set_decorated(False)
        popup.set_keep_above(True)
        popup.set_app_paintable(True)

        # Transparent window support
        screen = popup.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            popup.set_visual(visual)

        # Use an EventBox to hold the label so CSS can style the background
        box = Gtk.EventBox()
        box.get_style_context().add_class("popup-dialog")  # Apply CSS here

        label = Gtk.Label(label=text)
        label.set_margin_top(16)
        label.set_margin_bottom(16)
        label.set_margin_start(24)
        label.set_margin_end(24)
        box.add(label)

        popup.add(box)
        popup.show_all()

        self._center_popup(popup)
        GLib.timeout_add(duration, popup.destroy)



    def _center_popup(self, popup):
        parent_width, parent_height = self.get_size()
        popup_width, popup_height = popup.get_size_request()
        if popup_width <= 1: popup_width = 400
        if popup_height <= 1: popup_height = 100
        x = (parent_width - popup_width)//2
        y = (parent_height - popup_height)//2
        popup.move(x, y)

    # ---------- Clock ----------
    def _tick_clock(self):
        self.clock.set_text(time.strftime("%H:%M:%S"))
        return True

    # ---------- Settings ----------
    def on_settings(self, btn):
        self._show_popup("Settings not implemented yet")

    # ---------- Keyboard ----------
    def _on_key(self, win, event):
        if not self.selection_enabled: return
        key = event.keyval
        if key in [65361, 104]:  # left / h
            self._move_selection(-1)
        elif key in [65363, 108]:  # right / l
            self._move_selection(1)
        elif key in [65293, 32]:  # enter / space
            if self.selected is not None:
                self.app_buttons[self.selected].clicked()
        elif key in [65307]:  # esc
            Gtk.main_quit()

    # ---------- Joystick ----------
    def _find_joystick(self):
        from evdev import ecodes

        for dev_path in list_devices():
            dev = InputDevice(dev_path)
            caps = dev.capabilities()
            
            # Debug: print capabilities for each device
            print(f"Checking device: {dev.name} ({dev.path})")
            print(f"Capabilities: {caps.keys()}")

            # Look for ABS axes (analog stick) and BTN keys (buttons)
            has_axes = any(code in [ecodes.ABS_X, ecodes.ABS_Y] for code, _ in caps.get(ecodes.EV_ABS, []))
            has_buttons = ecodes.EV_KEY in caps

            if has_axes or has_buttons:
                self.joystick = dev
                fcntl.fcntl(dev.fd, fcntl.F_SETFL, os.O_NONBLOCK)
                print("Joystick/gamepad found:", dev.name, dev.path)
                break

        if not self.joystick:
            print("No joystick/gamepad detected")


    def _poll_joystick(self):
        if not self.joystick or not self.selection_enabled:
            return True

        try:
            while True:
                e = self.joystick.read_one()
                if e is None:
                    break

                # Debug: print all events
                print(f"Joystick event: type={e.type}, code={e.code}, value={e.value}")

                if e.type == ecodes.EV_ABS:
                    now = time.time()
                    if now - self.joystick_last < self.joystick_move_delay:
                        continue

                    if e.code == ecodes.ABS_X:
                        if e.value < -1000:
                            print("Move left detected")
                            self._move_selection(-1)
                            self.joystick_last = now
                        elif e.value > 1000:
                            print("Move right detected")
                            self._move_selection(1)
                            self.joystick_last = now

                    elif e.code == ecodes.ABS_Y:
                        if e.value < -1000:
                            print("Move up detected")
                            self._move_selection(-1)
                            self.joystick_last = now
                        elif e.value > 1000:
                            print("Move down detected")
                            self._move_selection(1)
                            self.joystick_last = now

                elif e.type == ecodes.EV_KEY and e.value == 1:  # button press
                    if e.code == ecodes.BTN_SOUTH:
                        print("Button A pressed")
                        if self.selected is not None:
                            self.app_buttons[self.selected].clicked()
                            self.joystick_last = now
                    elif e.code == ecodes.BTN_EAST:
                        print("Button X pressed")
                        if self.selected is not None:
                            self.app_buttons[self.selected].clicked()
                            self.joystick_last = now

        except BlockingIOError:
            pass
        except Exception as exc:
            print("Joystick error:", exc)

        return True

    def on_delete(self, widget, event):
        # Ignore all delete events
        print("Close attempt blocked!")
        return True  # returning True prevents GTK from destroying the window
    

    
def play_sound(file_path):
    """Play a WAV or MP3 file asynchronously."""
    if shutil.which("mpg123") and file_path.endswith(".mp3"):
        subprocess.Popen(["mpg123", file_path])
    elif shutil.which("aplay") and file_path.endswith(".wav"):
        subprocess.Popen(["aplay", file_path])
    else:
        print("No suitable audio player found")


# ---------- Run ----------
if __name__ == "__main__":
    win = LauncherWindow()
    win.connect("destroy", Gtk.main_quit)
    play_sound("start.mp3")
    Gtk.main()




