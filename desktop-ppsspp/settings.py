#!/usr/bin/env python3
# desktop.py — Launcher with WiFi selection, password prompt, focused window

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
import psutil
import os
import time
import subprocess
import fcntl
import threading
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
    {"name": "Internet Settings", "cmd": [""], "icon": "internet.png"},
    {"name": "Check for Update", "cmd": [""], "icon": "updates.png"},
    {"name": "Close all Apps",  "cmd": [""], "icon": "closeall.png"},
    {"name": "Advanced Settings", "cmd": [""], "icon": "advanced.png"},
    {"name": "Launch Task Manager", "cmd": [""], "icon": "terminal.png"},
    {"name": "Close", "cmd": [""], "icon": "prism.png"},
]

# ---------- Launcher Window ----------
class LauncherWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Launcher")
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_keep_above(True)
        self.set_focus_on_map(True)

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
        
        self.connect("delete-event", Gtk.main_quit)

        # Background
        bg_path = os.path.join(os.path.dirname(__file__), "blue.png")
        if os.path.exists(bg_path):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file(bg_path)
                scaled = pb.scale_simple(monitor.width, monitor.height, GdkPixbuf.InterpType.BILINEAR)
                self.bg = Gtk.Image.new_from_pixbuf(scaled)
                self.bg.set_name("bg")
                overlay.add(self.bg)
            except:
                self.bg = None
        else:
            self.bg = None

        # Buttons container
        self.button_box = Gtk.Box(spacing=30)
        self.button_box.set_halign(Gtk.Align.CENTER)
        self.button_box.set_valign(Gtk.Align.CENTER)
        overlay.add_overlay(self.button_box)

        # Topbar
        self.topbar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.topbar_box.set_halign(Gtk.Align.FILL)
        self.topbar_box.set_valign(Gtk.Align.START)
        self.topbar_box.set_margin_top(16)
        self.topbar_box.set_margin_start(16)
        self.topbar_box.set_margin_end(16)
        overlay.add_overlay(self.topbar_box)

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

        # Selection
        self.selected = None
        self.selection_enabled = False
        GLib.timeout_add(500, self._enable_selection_delay)

        # Events
        self.connect("key-press-event", self._on_key)

        # Show and force focus
        self.show_all()
        self.present()
        self.grab_focus()
        GLib.timeout_add(200, self.force_focus)
        
        self.joystick = None
        self._find_joystick()
        self.joystick_last = 0
        self.joystick_move_delay = 0.25
        GLib.timeout_add(30, self._poll_joystick)

    def force_focus(self):
        self.present()
        self.grab_focus()
        return False

    # ---------- Clock ----------
    def _tick_clock(self):
        import datetime
        self.clock.set_text(datetime.datetime.now().strftime("%H:%M:%S"))
        return True

    # ---------- Selection ----------
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

    # ---------- Buttons ----------
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
            except:
                pass

        lbl = Gtk.Label(label=app["name"])
        lbl.set_name("app-label")
        v.pack_start(lbl, False, False, 0)

        btn.add(v)
        btn.connect("clicked", lambda w: self.launch_app(app))
        return btn

    def launch_app(self, app):
        if app["name"] == "Internet Settings":
            self.show_internet_popup()
            return
        if app["name"] == "Close":
            Gtk.main_quit()
            sys.exit()

    # ---------- Key navigation ----------
    def _on_key(self, widget, event):
        if not self.selection_enabled:
            return False
        if event.keyval in (Gdk.KEY_Left, Gdk.KEY_h):
            self._move_selection(-1)
        elif event.keyval in (Gdk.KEY_Right, Gdk.KEY_l):
            self._move_selection(1)
        elif event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.selected is not None:
                self.app_buttons[self.selected].emit("clicked")
        return True

    # ---------- Internet popup ----------
    def show_internet_popup(self):
        self.internet_popup = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.internet_popup.set_transient_for(self)
        self.internet_popup.set_modal(True)
        self.internet_popup.set_decorated(False)
        self.internet_popup.set_keep_above(True)
        self.internet_popup.set_app_paintable(True)

        screen = self.internet_popup.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.internet_popup.set_visual(visual)

        # Block input to underlying window
        self.internet_popup.set_type_hint(Gdk.WindowTypeHint.DIALOG)

        box = Gtk.EventBox()
        box.get_style_context().add_class("popup-dialog")
        self.internet_popup.add(box)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.set_margin_top(16)
        vbox.set_margin_bottom(16)
        vbox.set_margin_start(24)
        vbox.set_margin_end(24)
        box.add(vbox)

        title = Gtk.Label(label="Select WiFi Network")
        title.set_name("app-label")
        vbox.pack_start(title, False, False, 0)

        self.wifi_listbox = Gtk.ListBox()
        vbox.pack_start(self.wifi_listbox, True, True, 0)

        hint = Gtk.Label(label="Use arrows + Enter. Esc to close.")
        hint.set_name("app-label")
        vbox.pack_start(hint, False, False, 0)

        self.internet_popup.show_all()
        self._center_popup(self.internet_popup)

        threading.Thread(target=self._scan_wifi_networks, daemon=True).start()
        self.internet_popup.connect("key-press-event", self._on_internet_key)

        self.internet_selected = 0
        GLib.timeout_add(100, self._poll_internet_selection)

    def _scan_wifi_networks(self):
        try:
            output = subprocess.check_output(["nmcli", "-t", "-f", "SSID", "device", "wifi", "list"], universal_newlines=True)
            networks = [line.strip() for line in output.splitlines() if line.strip()]
        except Exception as e:
            networks = ["No networks"]
        GLib.idle_add(self._populate_wifi_list, networks)

    def _populate_wifi_list(self, networks):
        self.wifi_listbox.foreach(lambda w: self.wifi_listbox.remove(w))
        for ssid in networks:
            lbl = Gtk.Label(label=ssid)
            row = Gtk.ListBoxRow()
            row.add(lbl)
            self.wifi_listbox.add(row)
        self.wifi_listbox.show_all()

    def _center_popup(self, popup):
        screen = self.get_screen()
        monitor = screen.get_monitor_geometry(screen.get_primary_monitor())
        popup.set_size_request(400, 300)
        x = monitor.x + (monitor.width - 400)//2
        y = monitor.y + (monitor.height - 300)//2
        popup.move(x, y)

    def _on_internet_key(self, widget, event):
        if event.keyval in (Gdk.KEY_Up, Gdk.KEY_k):
            self.internet_selected = max(0, self.internet_selected - 1)
        elif event.keyval in (Gdk.KEY_Down, Gdk.KEY_j):
            self.internet_selected += 1
            if self.internet_selected >= len(self.wifi_listbox.get_children()):
                self.internet_selected = len(self.wifi_listbox.get_children()) -1
        elif event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._prompt_password()
        elif event.keyval == Gdk.KEY_Escape:
            self.internet_popup.destroy()
        return True

    def _poll_internet_selection(self):
        children = self.wifi_listbox.get_children()
        for i, row in enumerate(children):
            ctx = row.get_style_context()
            if i == self.internet_selected:
                ctx.add_class("selected")
            else:
                ctx.remove_class("selected")
        return True

    def _prompt_password(self):
        children = self.wifi_listbox.get_children()
        if not children:
            return
        row = children[self.internet_selected]
        ssid = row.get_child().get_text()

        password_dialog = Gtk.Dialog(title=f"Password for {ssid}", parent=self.internet_popup, flags=Gtk.DialogFlags.MODAL)
        password_dialog.set_default_size(400, 100)
        box = password_dialog.get_content_area()
        entry = Gtk.Entry()
        entry.set_visibility(False)
        entry.set_placeholder_text("Enter WiFi password")
        box.add(entry)
        password_dialog.add_button("Connect", Gtk.ResponseType.OK)
        password_dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        password_dialog.show_all()

        response = password_dialog.run()
        if response == Gtk.ResponseType.OK:
            pwd = entry.get_text()
            threading.Thread(target=self._connect_wifi, args=(ssid, pwd), daemon=True).start()
        password_dialog.destroy()
        self.internet_popup.destroy()

    def _connect_wifi(self, ssid, password):
        try:
            subprocess.run(["nmcli", "device", "wifi", "connect", ssid, "password", password])
            play_sound("open.mp3")
        except Exception as e:
            print("Failed to connect:", e)
            play_sound("error.mp3")
            
            
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
    Gtk.main()
