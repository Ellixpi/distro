#!/usr/bin/env python3
# joystick_mouse.py — continuous smooth mouse from right stick + X/O buttons

import time
import fcntl
import os
from evdev import InputDevice, list_devices, ecodes
import uinput

# ---------- Find joystick ----------
joystick = None
for dev_path in list_devices():
    dev = InputDevice(dev_path)
    caps = dev.capabilities()
    if ecodes.EV_ABS in caps and ecodes.EV_KEY in caps:
        joystick = dev
        fcntl.fcntl(dev.fd, fcntl.F_SETFL, os.O_NONBLOCK)
        print("Using joystick:", dev.name, dev.path)
        break

if joystick is None:
    print("No joystick found!")
    exit(1)

# ---------- Create virtual mouse ----------
device = uinput.Device([
    uinput.REL_X,
    uinput.REL_Y,
    uinput.BTN_LEFT,
    uinput.BTN_RIGHT,
])

# ---------- Settings ----------
SENSITIVITY = 0.15   # tweak speed
DEADZONE = 8000     # ignore tiny movements

# Button mappings
LEFT_CLICK = ecodes.BTN_SOUTH    # X on PS / A on Xbox
RIGHT_CLICK = ecodes.BTN_EAST    # O on PS / B on Xbox

# Right stick axes
AXIS_X = ecodes.ABS_RX
AXIS_Y = ecodes.ABS_RY

# Track last stick values
stick_x = 0
stick_y = 0
buttons = {}

# ---------- Main loop ----------
while True:
    # Read events (non-blocking)
    try:
        for e in joystick.read():
            if e.type == ecodes.EV_ABS:
                if e.code == AXIS_X:
                    stick_x = e.value
                elif e.code == AXIS_Y:
                    stick_y = e.value
            elif e.type == ecodes.EV_KEY:
                buttons[e.code] = e.value
    except BlockingIOError:
        pass

    # Calculate mouse movement continuously
    dx = dy = 0
    if abs(stick_x) > DEADZONE:
        dx = int((stick_x / 32767) * SENSITIVITY * 50)
    if abs(stick_y) > DEADZONE:
        dy = int((stick_y / 32767) * SENSITIVITY * 50)

    if dx != 0 or dy != 0:
        device.emit(uinput.REL_X, dx, syn=False)
        device.emit(uinput.REL_Y, dy)

    # Handle mouse buttons (continuous hold)
    device.emit(uinput.BTN_LEFT, buttons.get(LEFT_CLICK, 0))
    device.emit(uinput.BTN_RIGHT, buttons.get(RIGHT_CLICK, 0))

    time.sleep(0.01)
