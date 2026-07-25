"""Fiver Wi-Fi Setup TUI — scan networks, discover devices, mirror screen."""

from __future__ import annotations

import ipaddress
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import List, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    Static,
)

from .adb import ADB, ADBError


# ── Data ─────────────────────────────────────────────────────


@dataclass
class WifiNetwork:
    ssid: str
    signal: int
    security: str
    in_use: bool


@dataclass
class NetworkDevice:
    ip: str
    hostname: str
    mac: str


# ── Scanning helpers ─────────────────────────────────────────


def scan_wifi() -> List[WifiNetwork]:
    """Return visible Wi-Fi networks via nmcli."""
    try:
        proc = subprocess.run(
            [
                "nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,ACTIVE",
                "dev", "wifi", "list", "--rescan", "yes",
            ],
            capture_output=True, text=True, timeout=20,
        )
        nets: List[WifiNetwork] = []
        seen: set = set()
        for raw in proc.stdout.strip().splitlines():
            cols = [c.replace("\\:", ":") for c in re.split(r"(?<!\\):", raw)]
            if len(cols) < 3:
                continue
            ssid = cols[0].strip()
            if not ssid or ssid in seen:
                continue
            seen.add(ssid)
            nets.append(WifiNetwork(
                ssid=ssid,
                signal=int(cols[1]) if cols[1].isdigit() else 0,
                security=cols[2] or "Open",
                in_use=cols[3].strip().lower() == "yes" if len(cols) > 3 else False,
            ))
        nets.sort(key=lambda n: (-n.in_use, -n.signal))
        return nets
    except Exception:
        return []


def _local_subnet() -> tuple:
    """Return (local_ip, subnet_cidr) or (None, None)."""
    try:
        out = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        for line in out.splitlines():
            m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/(\d+)", line)
            if m:
                ip = m.group(1)
                return ip, str(ipaddress.ip_network(
                    "{}/{}".format(ip, m.group(2)), strict=False
                ))
    except Exception:
        pass
    return None, None


def scan_devices() -> List[NetworkDevice]:
    """Discover hosts on the local network."""
    local_ip, subnet = _local_subnet()
    if not subnet:
        return []
    return (
        _nmap_scan(subnet, local_ip)
        or _arp_scan_tool(local_ip)
        or _ping_sweep(subnet, local_ip)
    )


def _nmap_scan(subnet, local_ip):
    """Try nmap host discovery (fastest and most reliable)."""
    try:
        out = subprocess.run(
            ["nmap", "-sn", "-T4", subnet],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    devs = []
    for block in re.split(r"Nmap scan report for ", out)[1:]:
        m = re.search(r"(?:(\S+) \()?(\d+\.\d+\.\d+\.\d+)", block)
        if not m:
            continue
        ip = m.group(2)
        if ip == local_ip:
            continue
        host = m.group(1) or ""
        mm = re.search(r"MAC Address: ([\dA-Fa-f:]+)\s*(.*)", block)
        mac = mm.group(1) if mm else ""
        vendor = mm.group(2).strip("() ") if mm else ""
        devs.append(NetworkDevice(
            ip=ip, hostname=host or vendor or _resolve(ip), mac=mac
        ))
    return devs or None


def _arp_scan_tool(local_ip):
    """Try arp-scan (needs root usually, but worth trying)."""
    try:
        out = subprocess.run(
            ["arp-scan", "-l", "-q"],
            capture_output=True, text=True, timeout=15,
        ).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    devs = []
    for line in out.strip().splitlines():
        cols = line.split("\t")
        if len(cols) >= 2:
            ip = cols[0].strip()
            mac = cols[1].strip() if len(cols) > 1 else ""
            vendor = cols[2].strip() if len(cols) > 2 else ""
            if ip != local_ip:
                devs.append(NetworkDevice(
                    ip=ip, hostname=vendor or _resolve(ip), mac=mac
                ))
    return devs or None


def _ping_sweep(subnet, local_ip):
    """Parallel ping sweep + read ARP neighbour table."""
    net = ipaddress.ip_network(subnet, strict=False)
    hosts = [str(h) for h in list(net.hosts())[:254] if str(h) != local_ip]

    def _ping(ip):
        subprocess.run(
            ["ping", "-c", "1", "-W", "1", ip],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    with ThreadPoolExecutor(max_workers=60) as pool:
        list(pool.map(_ping, hosts))

    devs = []
    try:
        out = subprocess.run(
            ["ip", "neigh", "show"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            state = parts[-1]
            if state not in ("REACHABLE", "STALE", "DELAY"):
                continue
            ip = parts[0]
            # Skip IPv6 and self
            if ":" in ip and "." not in ip:
                continue
            if ip == local_ip:
                continue
            mac = ""
            if "lladdr" in parts:
                idx = parts.index("lladdr")
                if idx + 1 < len(parts):
                    mac = parts[idx + 1]
            devs.append(NetworkDevice(ip=ip, hostname=_resolve(ip), mac=mac))
    except Exception:
        pass
    return devs


def _resolve(ip):
    """Reverse-DNS lookup for an IP."""
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return "Unknown"


def _bars(sig):
    """Signal-strength bar characters."""
    if sig >= 75:
        return "▰▰▰▰"
    if sig >= 50:
        return "▰▰▰▱"
    if sig >= 25:
        return "▰▰▱▱"
    return "▰▱▱▱"


# ── TUI list items ───────────────────────────────────────────


class WifiItem(ListItem):
    """One Wi-Fi network in the list."""

    def __init__(self, net):
        super().__init__()
        self.net = net

    def compose(self):
        n = self.net
        mark = "✦" if n.in_use else " "
        lock = "🔒" if n.security not in ("", "--", "Open") else "🔓"
        yield Label(
            " {}  {:<26} {} {:>3}%  {} {}".format(
                mark, n.ssid, _bars(n.signal), n.signal, lock, n.security,
            )
        )


class DeviceItem(ListItem):
    """One network device in the list."""

    def __init__(self, dev):
        super().__init__()
        self.dev = dev

    def compose(self):
        d = self.dev
        yield Label(
            "   📱  {:<18}{:<26}{}".format(d.ip, d.hostname, d.mac)
        )


# ── Main TUI application ────────────────────────────────────


class FiverSetupTUI(App):
    """Two-phase TUI: Wi-Fi list → device list → send request → mirror."""

    TITLE = "fiver"
    SUB_TITLE = "wireless setup"

    CSS = """
Screen {
    background: #0f1117;
}

#banner {
    dock: top;
    height: 3;
    padding: 1 2;
    background: #1a1b26;
    color: #7aa2f7;
    text-style: bold;
}

#hint {
    padding: 0 2;
    color: #565f89;
    height: 2;
}

#phase {
    padding: 0 2;
    color: #9ece6a;
    text-style: bold;
    height: 2;
}

#wifi-lv, #dev-lv {
    margin: 0 2;
    border: round #3b4261;
    padding: 0 1;
    height: 1fr;
    background: #1a1b26;
}

.hidden {
    display: none;
}

#bar {
    dock: bottom;
    height: 3;
    padding: 0 2;
    layout: horizontal;
    background: #1a1b26;
}

#bar Button {
    margin: 0 1;
}

#status {
    dock: bottom;
    height: 2;
    padding: 0 2;
    background: #1a1b26;
    color: #e0af68;
}

WifiItem {
    height: auto;
}

DeviceItem {
    height: auto;
}

WifiItem:hover, DeviceItem:hover {
    background: #292e42;
}

ListView:focus > ListItem.--highlight {
    background: #3b4261;
}
"""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("escape", "back", "Back"),
    ]

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.adb = ADB(cfg.adb_path)
        self._phase = "wifi"
        self._net = None  # type: Optional[WifiNetwork]

    def compose(self):
        yield Header(show_clock=True)
        yield Static("", id="banner")
        yield Label("", id="hint")
        yield Label("", id="phase")
        yield ListView(id="wifi-lv")
        yield ListView(id="dev-lv", classes="hidden")
        with Horizontal(id="bar", classes="hidden"):
            yield Button("⬅ Back", id="b-back")
            yield Button("🔄 Refresh", id="b-ref", variant="primary")
            yield Button("📡 Send Request", id="b-send", variant="success")
        yield Static("", id="status")
        yield Footer()

    # ── lifecycle ─────────────────────────────────────────────

    def on_mount(self):
        self.adb.start_server()
        self._go_wifi()

    # ── phase: Wi-Fi list ─────────────────────────────────────

    def _go_wifi(self):
        self._phase = "wifi"
        self._update_status("Scanning Wi-Fi networks…")
        self.query_one("#banner", Static).update("📶  FIVER — Wi-Fi Setup")
        self.query_one("#hint", Label).update(
            "Select your Wi-Fi network to scan for devices.  ✦ = connected"
        )
        self.query_one("#phase", Label).update("Scanning…")
        self.query_one("#wifi-lv").remove_class("hidden")
        self.query_one("#dev-lv").add_class("hidden")
        self.query_one("#bar").add_class("hidden")
        self.run_worker(self._load_wifi, thread=True)

    def _load_wifi(self):
        nets = scan_wifi()
        self.call_from_thread(self._fill_wifi, nets)

    def _fill_wifi(self, nets):
        lv = self.query_one("#wifi-lv", ListView)
        lv.clear()
        for n in nets:
            lv.append(WifiItem(n))
        self.query_one("#phase", Label).update(
            "Wi-Fi Networks ({})".format(len(nets))
        )
        self._update_status(
            "  {} networks found — select one and press Enter ↵".format(len(nets))
        )

    # ── phase: device list ────────────────────────────────────

    def _go_devices(self, net):
        self._phase = "devices"
        self._net = net
        self.query_one("#banner", Static).update(
            '📱  Devices on "{}"'.format(net.ssid)
        )
        self.query_one("#hint", Label).update(
            "Select a device → press Enter or click Send Request"
        )
        self.query_one("#phase", Label).update("Scanning network…")
        self.query_one("#wifi-lv").add_class("hidden")
        self.query_one("#dev-lv").remove_class("hidden")
        self.query_one("#bar").remove_class("hidden")
        self._update_status("  Scanning… this may take a moment")
        self.run_worker(self._load_devs, thread=True)

    def _load_devs(self):
        devs = scan_devices()
        self.call_from_thread(self._fill_devs, devs)

    def _fill_devs(self, devs):
        lv = self.query_one("#dev-lv", ListView)
        lv.clear()
        for d in devs:
            lv.append(DeviceItem(d))
        name = self._net.ssid if self._net else "network"
        self.query_one("#phase", Label).update(
            'Devices on "{}" ({})'.format(name, len(devs))
        )
        self._update_status(
            "  {} devices — select one → Send Request".format(len(devs))
        )

    # ── events ────────────────────────────────────────────────

    def on_list_view_selected(self, ev):
        if self._phase == "wifi" and isinstance(ev.item, WifiItem):
            self._go_devices(ev.item.net)
        elif self._phase == "devices" and isinstance(ev.item, DeviceItem):
            self._send(ev.item.dev)

    def on_button_pressed(self, ev):
        bid = ev.button.id
        if bid == "b-back":
            self.action_back()
        elif bid == "b-ref":
            self.action_refresh()
        elif bid == "b-send":
            lv = self.query_one("#dev-lv", ListView)
            ch = lv.highlighted_child
            if isinstance(ch, DeviceItem):
                self._send(ch.dev)
            else:
                self._update_status("  ⚠ Select a device first")

    def _send(self, dev):
        self._update_status("  📡 Sending request to {}…".format(dev.ip))
        self.run_worker(lambda: self._try_connect(dev), thread=True)

    def _try_connect(self, dev):
        ports = sorted(set([5555, self.cfg.adb_port]))
        for port in ports:
            tgt = "{}:{}".format(dev.ip, port)
            self.call_from_thread(
                self._update_status,
                "  📡 Trying {}… Accept prompt on phone".format(tgt),
            )
            try:
                if self.adb.connect(tgt, timeout=6.0):
                    self.call_from_thread(self.exit, tgt)
                    return
            except ADBError:
                continue
        self.call_from_thread(
            self._update_status,
            "  ❌ {} did not respond. Enable Wireless Debugging on phone "
            "(Settings → Developer → Wireless Debugging).".format(dev.ip),
        )

    # ── helpers ───────────────────────────────────────────────

    def _update_status(self, msg):
        self.query_one("#status", Static).update(msg)

    def action_back(self):
        if self._phase == "devices":
            self._go_wifi()

    def action_refresh(self):
        if self._phase == "wifi":
            self._go_wifi()
        elif self._net:
            self._go_devices(self._net)


def run_tui(cfg):
    """Launch the TUI; returns device address on success, None on quit."""
    app = FiverSetupTUI(cfg)
    return app.run()
