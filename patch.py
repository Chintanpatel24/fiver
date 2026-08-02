import re
import os

def patch_web_mirror():
    path = "/home/cachy/github-p/fiver/src/fiver/web_mirror.py"
    with open(path, "r") as f:
        content = f.read()

    # 1. PHONE_HTML
    start_str = '# HTML template for the phone (Matte Black Theme, Instant Tap Permission)'
    end_str = '"""\n\n# HTML template for the Desktop viewer'
    
    new_html = """# HTML template for the phone (Matte Black Theme, Companion App Download)
PHONE_HTML = \"\"\"<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="manifest" href="/manifest.json">
    <title>Fiver Screen Mirror</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        html, body {
            width: 100%;
            height: 100%;
        }
        body {
            font-family: monospace, sans-serif;
            background: #000000;
            color: #ffffff;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 20px;
            text-align: center;
            user-select: none;
            -webkit-user-select: none;
        }
        .card {
            background: #0a0a0a;
            border: 1px solid #222222;
            padding: 28px 24px;
            max-width: 400px;
            width: 100%;
        }
        h1 { font-size: 20px; margin-bottom: 12px; color: #ffffff; text-transform: uppercase; letter-spacing: 1px; }
        p { font-size: 14px; color: #888888; margin-bottom: 24px; line-height: 1.5; }
        button {
            width: 100%;
            padding: 16px;
            background: #ffffff;
            color: #000000;
            border: 1px solid #333333;
            font-family: monospace;
            font-size: 15px;
            font-weight: bold;
            cursor: pointer;
            text-transform: uppercase;
        }
        button:hover { background: #cccccc; }
        .server-url {
            margin-top: 20px;
            font-size: 12px;
            color: #555555;
            word-break: break-all;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>FIVER COMPANION</h1>
        <p>Download the companion app, install it, and open it to start screen sharing.</p>
        <button onclick="window.location.href='/download/companion.apk'">DOWNLOAD &amp; INSTALL</button>
        <div class="server-url">Server: {{LOCAL_SERVER_URL}}</div>
    </div>
</body>
</html>
\"\"\"

# HTML template for the Desktop viewer"""
    
    start_idx = content.find(start_str)
    end_idx = content.find(end_str) + len(end_str)
    
    content = content[:start_idx] + new_html + content[end_idx:]

    # 2. MirrorHandler attributes
    attr_old = """class MirrorHandler(BaseHTTPRequestHandler):
    latest_frame: Optional[bytes] = None
    frame_event = threading.Event()
    accepted = False
    declined = False
    requested = True"""
    attr_new = """class MirrorHandler(BaseHTTPRequestHandler):
    latest_frame: Optional[bytes] = None
    frame_event = threading.Event()
    accepted = False
    declined = False
    requested = True
    apk_path = None"""
    content = content.replace(attr_old, attr_new)

    # 3. do_GET
    doget_old = """    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(PHONE_HTML.encode("utf-8"))"""
    doget_new = """    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            host = self.headers.get("Host", "localhost")
            proto = "https" if isinstance(self.connection, ssl.SSLSocket) else "http"
            html = PHONE_HTML.replace("{{LOCAL_SERVER_URL}}", f"{proto}://{host}")
            self.wfile.write(html.encode("utf-8"))"""
    content = content.replace(doget_old, doget_new)

    # 4. /download/companion.apk endpoint
    desk_old = """        elif self.path == "/desktop":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(DESKTOP_HTML.encode("utf-8"))"""
    desk_new = """        elif self.path == "/download/companion.apk":
            if MirrorHandler.apk_path and os.path.exists(MirrorHandler.apk_path):
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.android.package-archive")
                self.send_header("Content-Disposition", 'attachment; filename="companion.apk"')
                with open(MirrorHandler.apk_path, "rb") as f:
                    apk_data = f.read()
                self.send_header("Content-Length", str(len(apk_data)))
                self.end_headers()
                self.wfile.write(apk_data)
            else:
                self.send_error(404)
        elif self.path == "/desktop":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(DESKTOP_HTML.encode("utf-8"))"""
    content = content.replace(desk_old, desk_new)

    # 5. do_POST
    post_old = """    def do_POST(self):
        if self.path == "/api/frame":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            if "," in body:
                body = body.split(",", 1)[1]
            try:
                MirrorHandler.latest_frame = base64.b64decode(body)
                MirrorHandler.accepted = True
                MirrorHandler.frame_event.set()
                self.send_response(200)
                self.end_headers()
            except Exception:
                self.send_error(400)"""
    post_new = """    def do_POST(self):
        if self.path == "/api/frame":
            content_length = int(self.headers.get("Content-Length", 0))
            content_type = self.headers.get("Content-Type", "")
            if content_type == "image/jpeg":
                MirrorHandler.latest_frame = self.rfile.read(content_length)
                MirrorHandler.accepted = True
                MirrorHandler.frame_event.set()
                self.send_response(200)
                self.end_headers()
            else:
                body = self.rfile.read(content_length).decode("utf-8")
                if "," in body:
                    body = body.split(",", 1)[1]
                try:
                    MirrorHandler.latest_frame = base64.b64decode(body)
                    MirrorHandler.accepted = True
                    MirrorHandler.frame_event.set()
                    self.send_response(200)
                    self.end_headers()
                except Exception:
                    self.send_error(400)"""
    content = content.replace(post_old, post_new)

    # 6. WebMirrorServer.set_apk
    server_old = """class WebMirrorServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.server: Optional[ThreadedHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.tunnel_proc: Optional[subprocess.Popen] = None
        self.public_url: Optional[str] = None
        self.desktop_opened = False
        self.is_ssl = False"""
    server_new = """class WebMirrorServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self.server: Optional[ThreadedHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.tunnel_proc: Optional[subprocess.Popen] = None
        self.public_url: Optional[str] = None
        self.desktop_opened = False
        self.is_ssl = False

    def set_apk(self, path: str):
        MirrorHandler.apk_path = path"""
    content = content.replace(server_old, server_new)

    with open(path, "w") as f:
        f.write(content)


def patch_tui():
    path = "/home/cachy/github-p/fiver/src/fiver/tui.py"
    with open(path, "r") as f:
        content = f.read()
    
    tui_old = '''        # Non-developer phone mode fallback (No USB debugging / no dev options needed)
        self.call_from_thread(
            self._update_status,
            "  [WEB MODE] ADB unavailable on {} - Starting Web Server & Cloudflare HTTPS Tunnel...".format(dev.ip),
        )

        from .web_mirror import WebMirrorServer, generate_ascii_qr, MirrorHandler

        local_ip, _ = _local_subnet()
        local_ip = local_ip or "127.0.0.1"

        if self.web_server:
            self.web_server.stop()

        self.web_server = WebMirrorServer(port=8080)
        self.web_server.start()

        self.call_from_thread(
            self._update_status,
            "  [CLOUDFLARE TUNNEL] Deploying secure HTTPS tunnel...",
        )

        public_url = self.web_server.start_cloudflare_tunnel()
        proto = "https" if self.web_server.is_ssl else "http"
        phone_url = public_url or f"{proto}://{local_ip}:{self.web_server.port}"

        qr_box = generate_ascii_qr(phone_url)

        # Open desktop viewer immediately so it's ready on PC
        self.web_server.open_desktop_viewer(local_ip)

        self.call_from_thread(
            self._show_web_request,
            dev,
            phone_url,
            qr_box,
        )

        # Poll until phone accepts or declines
        while not MirrorHandler.accepted and not MirrorHandler.declined:
            time.sleep(0.5)

        if MirrorHandler.accepted:
            self.call_from_thread(
                self._update_status,
                "  [SUCCESS] Request accepted! Live mobile screen stream is active on desktop.",
            )
        else:
            self.call_from_thread(
                self._update_status,
                "  [DECLINED] Request declined by phone user.",
            )'''

    tui_new = '''        # Non-developer phone fallback — build companion APK and serve it
        self.call_from_thread(
            self._update_status,
            "  [COMPANION MODE] ADB unavailable — building companion app...",
        )

        from .web_mirror import WebMirrorServer, generate_ascii_qr, MirrorHandler
        from .apk_builder import APKBuilder

        local_ip, _ = _local_subnet()
        local_ip = local_ip or "127.0.0.1"

        # Start web server first to get the port
        if self.web_server:
            self.web_server.stop()

        self.web_server = WebMirrorServer(port=8080)
        server_addr = self.web_server.start()

        # Build companion APK with server address embedded
        server_url = f"http://{local_ip}:{self.web_server.port}"
        try:
            self.call_from_thread(
                self._update_status,
                "  [BUILDING APK] Compiling companion app (first time may take a moment)...",
            )
            builder = APKBuilder()
            apk_path = builder.build_apk(server_url)
            self.web_server.set_apk(apk_path)
            self.call_from_thread(
                self._update_status,
                "  [APK READY] Companion app built successfully.",
            )
        except RuntimeError as e:
            self.call_from_thread(
                self._update_status,
                f"  [ERROR] Failed to build companion app: {e}",
            )
            return

        # Start Cloudflare tunnel for QR code access
        self.call_from_thread(
            self._update_status,
            "  [CLOUDFLARE TUNNEL] Deploying secure HTTPS tunnel...",
        )

        public_url = self.web_server.start_cloudflare_tunnel()
        phone_url = public_url or server_url

        qr_box = generate_ascii_qr(phone_url)

        # Open desktop viewer
        self.web_server.open_desktop_viewer(local_ip)

        self.call_from_thread(
            self._show_web_request,
            dev,
            phone_url,
            qr_box,
        )

        # Poll until phone starts streaming or user exits
        while not MirrorHandler.accepted and not MirrorHandler.declined:
            time.sleep(0.5)

        if MirrorHandler.accepted:
            self.call_from_thread(
                self._update_status,
                "  [SUCCESS] Companion app connected! Live screen stream active.",
            )
        else:
            self.call_from_thread(
                self._update_status,
                "  [DECLINED] Request declined by phone user.",
            )'''
    content = content.replace(tui_old, tui_new)

    # 7. update _show_web_request
    show_old = '''    def _show_web_request(self, dev, url: str, qr_box: str):
        self.query_one("#banner", Static).update("NON-DEVELOPER PHONE REQUEST SENT")
        self.query_one("#hint", Label).update(f"Request sent to {dev.ip}! Open link on phone: {url}")
        self.query_one("#phase", Label).update("Waiting for phone user to tap ACCEPT...")'''
    show_new = '''    def _show_web_request(self, dev, url: str, qr_box: str):
        self.query_one("#banner", Static).update("COMPANION APP")
        self.query_one("#hint", Label).update(f"Scan QR code to download companion app for {dev.ip}!")
        self.query_one("#phase", Label).update("Waiting for phone user to install and open app...")'''
    content = content.replace(show_old, show_new)
    
    with open(path, "w") as f:
        f.write(content)

patch_web_mirror()
patch_tui()
print("Patching complete.")
