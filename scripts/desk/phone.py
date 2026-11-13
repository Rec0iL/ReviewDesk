"""The phone's way in: when you turn it on, a second listener on this computer's home-network
address, with its own secret (new each time, in the QR code), closed again after eight hours or
when you turn it off. It never runs commands. The firewall is only checked, never changed.
"""
import ipaddress
import shutil
import socket
import subprocess

HOURS = 8


def lan_address():
    """This computer's address on the network it reaches the world through (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def home_network(ip):
    """Is `ip` a home-network address (not the internet, not this computer alone)?"""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.is_private and not (a.is_loopback or a.is_link_local)


def interface_of(ip):
    """The network interface that has `ip` (Linux), or None."""
    try:
        out = subprocess.run(["ip", "-o", "-4", "addr", "show"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) > 3 and parts[3].split("/")[0] == ip:
            return parts[1]
    return None


def firewall(port, ip):
    """Would firewalld let a phone reach `port`? Only asks; changing it is the user's call."""
    cmd = shutil.which("firewall-cmd")
    if not cmd:
        return {"checked": False}

    def ask(*args):
        try:
            return subprocess.run([cmd, *args], capture_output=True, text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    if ask("--state") != "running":
        return {"checked": True, "open": True}
    iface = interface_of(ip)
    zone = (ask(f"--get-zone-of-interface={iface}") if iface else "") or ask("--get-default-zone")
    if not zone:
        return {"checked": False}
    open_ = ask(f"--zone={zone}", f"--query-port={port}/tcp") == "yes"
    return {"checked": True, "open": open_, "zone": zone, "fix": f"sudo firewall-cmd --zone={zone} --add-port={port}/tcp"}
