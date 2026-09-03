#!/usr/bin/env python3
"""click.py [left|right]: press and release a mouse button through a virtual uinput mouse.
The cursor is placed with hyprctl beforehand; this only clicks where it is."""
import fcntl, os, struct, sys, time
UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_RELBIT = 0x40045564, 0x40045565, 0x40045566
UI_DEV_CREATE, UI_DEV_DESTROY = 0x5501, 0x5502
EV_SYN, EV_KEY, EV_REL = 0, 1, 2
BTN = {"left": 0x110, "right": 0x111}[sys.argv[1] if len(sys.argv) > 1 else "left"]
fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY); fcntl.ioctl(fd, UI_SET_KEYBIT, 0x110); fcntl.ioctl(fd, UI_SET_KEYBIT, 0x111)
fcntl.ioctl(fd, UI_SET_EVBIT, EV_REL); fcntl.ioctl(fd, UI_SET_RELBIT, 0); fcntl.ioctl(fd, UI_SET_RELBIT, 1)
# struct uinput_user_dev: name[80], input_id{bustype,vendor,product,version}, ff_effects_max, absmax/min/fuzz/flat[64] each
os.write(fd, struct.pack("80sHHHHI", b"story-mouse", 0x03, 0x1, 0x1, 1, 0) + b"\0" * (4 * 64 * 4))
fcntl.ioctl(fd, UI_DEV_CREATE); time.sleep(0.25)   # let the compositor pick the device up
def ev(t, c, v): os.write(fd, struct.pack("llHHi", 0, 0, t, c, v))
ev(EV_KEY, BTN, 1); ev(EV_SYN, 0, 0); time.sleep(0.08); ev(EV_KEY, BTN, 0); ev(EV_SYN, 0, 0)
time.sleep(0.15); fcntl.ioctl(fd, UI_DEV_DESTROY); os.close(fd)
