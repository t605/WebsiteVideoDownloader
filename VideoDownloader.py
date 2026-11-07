#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  VIDEO DOWNLOADER  v9.13 — 480p  —  single file, no installer        ║
║  Large-text light interface, English / Russian                       ║
║                                                                      ║
║  Everything is in this one file. Users start VideoDownloader.bat,    ║
║  which installs Python if needed; developers can run:                ║
║      python VideoDownloader.py                                       ║
║                                                                      ║
║  It installs what it needs, finds your cookies, and opens the        ║
║  window. Nothing else to download.                                   ║
║                                                                      ║
║  Command line options (all optional):                                ║
║      --selftest          run diagnostics and a test download         ║
║      --shortcut          put a shortcut on the Desktop               ║
║      --url "<link>"      download one link and exit (no window)      ║
║      --dir "<folder>"    where to save (default: Downloads)          ║
║      --insecure          skip certificate checks (last resort)       ║
║                                                                      ║
║  Also: records live webinar rooms (Bizon365, Rutube video) to MP4.   ║
║  Supports 1,700+ sites. Known-tricky ones handled explicitly:        ║
║      VK / vkvideo.ru   session cookie lives on vk.com only, so the   ║
║                        session is copied across all VK domains and   ║
║                        every host variant is tried                   ║
║      YouTube           cookies make yt-dlp pick a broken player      ║
║                        client, so YouTube is tried cookie-free first ║
║      Russian sites     certifi lacks their root CA, so the OS trust  ║
║                        store is used instead                         ║
║      Course platforms  embedded videos are found by scanning the     ║
║                        page, preserving Vimeo privacy hashes         ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os, sys, re, ssl, glob, time, json, shutil, argparse, subprocess, threading
import webbrowser, urllib.request, urllib.parse, urllib.error
import base64, socket, struct, http.cookiejar
from collections import deque
from concurrent.futures import ThreadPoolExecutor

APP_NAME = "Video Downloader"
APP_VER  = "9.13"

# Under pythonw (no console) sys.stdout/stderr are None, and anything that
# prints would crash. Send that output to a log file instead (fresh each start).
if sys.stdout is None or sys.stderr is None:
    try:
        _log_dir = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                                "VideoDownloader")
        os.makedirs(_log_dir, exist_ok=True)
        _log = open(os.path.join(_log_dir, "VideoDownloader.log"), "w",
                    encoding="utf-8", buffering=1)
    except Exception:
        _log = open(os.devnull, "w")
    if sys.stdout is None: sys.stdout = _log
    if sys.stderr is None: sys.stderr = _log

# ══════════════════════════════════════════════════════════════
#  0.  PYTHON GATE  (before tkinter is touched)
# ══════════════════════════════════════════════════════════════
if sys.version_info < (3, 8):
    _m = (f"Python 3.8 or newer is required.\n"
          f"You have {sys.version.split()[0]}.\n\n"
          f"Get it from https://python.org/downloads\n"
          f"On the installer's first screen, tick 'Add Python to PATH'.")
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb
        _r = _tk.Tk(); _r.withdraw(); _mb.showerror("Python too old", _m)
    except Exception:
        print("ERROR:", _m)
    sys.exit(1)

import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# ══════════════════════════════════════════════════════════════
#  2.  BOOTSTRAP
# ══════════════════════════════════════════════════════════════
# Background tools (pip, winget) must not flash a black console window at the
# user when the app runs under pythonw.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

def _pip(*a) -> bool:
    try:
        return subprocess.run([sys.executable, "-m", "pip", "install", *a, "--quiet"],
                              capture_output=True, timeout=240,
                              creationflags=NO_WINDOW).returncode == 0
    except Exception:
        return False

try:
    import yt_dlp
except ImportError:
    print("[setup] Installing yt-dlp …"); _pip("yt-dlp[default]"); import yt_dlp

TRUSTSTORE_OK = False
try:
    import truststore; truststore.inject_into_ssl(); TRUSTSTORE_OK = True
except ImportError:
    if _pip("truststore"):
        try:
            import truststore; truststore.inject_into_ssl(); TRUSTSTORE_OK = True
        except Exception:
            pass

# ══════════════════════════════════════════════════════════════
#  3.  CONSTANTS
# ══════════════════════════════════════════════════════════════
# Light, high-contrast colours: the main user is in her late seventies, and dark
# text on a light background is easier to read than the reverse. Green is the
# one button to press; red is only used for problems.
C = dict(bg="#F7F6F2", panel="#FFFFFF", panel2="#E4E1D8", border="#B4B2A9",
         header="#2C2C2A", text="#1F1F1D", muted="#55534E",
         blue="#185FA5", green="#3B6D11", green_text="#27500A", red="#A32D2D",
         orange="#854F0B", soft_blue="#E6F1FB", disabled="#9A988F",
         pill_ok="#97C459", pill_warn="#EF9F27")
UI = "Segoe UI" if sys.platform == "win32" else "Helvetica"

FORMAT_MERGE  = ("bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/"
                 "bestvideo[height<=480]+bestaudio/"
                 "best[height<=480][ext=mp4]/best[height<=480]/best")
FORMAT_SINGLE = "best[height<=480][ext=mp4]/best[height<=480]/best[ext=mp4]/best"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
MONO = "Consolas" if sys.platform == "win32" else "Menlo"

# YouTube: when a cookie file is supplied, yt-dlp defaults to the
# tv_downgraded client, which currently returns UNPLAYABLE /
# "The page needs to be reloaded". These client sets avoid it.
YT_CLIENT_SETS = [
    None,                        # yt-dlp default (best when cookie-free)
    ["default", "web_embedded"], # the documented workaround when using cookies
    ["android_vr"],              # unaffected by SABR / PO-token walls
    ["web_embedded"],
    ["tv_simply"],
    ["ios"],
    ["mweb"],
]

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
def clean(s) -> str:
    """Strip terminal colour codes and yt-dlp's repeated ERROR: prefixes."""
    s = ANSI.sub("", str(s))
    s = re.sub(r"(?:^|\s)ERROR:\s*", " ", s).strip()
    return re.sub(r"\s+", " ", s)

CHROME_EXT = ("https://chromewebstore.google.com/detail/"
              "get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc")
FIREFOX_EXT = "https://addons.mozilla.org/firefox/addon/get-cookies-txt-locally/"

HOME = os.path.expanduser("~")
COOKIE_DIRS = [os.path.join(HOME, "Downloads"), os.path.join(HOME, "Desktop"),
               os.path.join(HOME, "OneDrive", "Desktop"),
               os.path.join(HOME, "OneDrive", "Downloads"),
               os.path.dirname(os.path.abspath(__file__))]

SITES = [("YouTube", "https://www.youtube.com"), ("VK", "https://vk.com"),
         ("Facebook", "https://www.facebook.com"), ("Vimeo", "https://vimeo.com"),
         ("Instagram", "https://www.instagram.com")]

# ══════════════════════════════════════════════════════════════
#  LOGO  (embedded — no separate image file to lose)
#  White panda on transparent, so it sits on the dark header bar.
# ══════════════════════════════════════════════════════════════
LOGO_HEADER_B64 = (
    "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"
)

LOGO_ICON_B64 = (
    "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"
)

def _logo_image(b64: str):
    """Decode an embedded PNG into a Tk image. Returns None if Tk can't."""
    try:
        import base64 as _b64
        return tk.PhotoImage(data=_b64.b64decode(b64))
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════
#  4.  HELPERS
# ══════════════════════════════════════════════════════════════
def _darken(h, p=0.15):
    h = h.lstrip("#"); r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
    return "#{:02x}{:02x}{:02x}".format(int(r*(1-p)), int(g*(1-p)), int(b*(1-p)))

def _btn(parent, text, cmd, bg, fg="#FFFFFF", font=(UI, 12), **kw):
    """Flat button that darkens on hover. Its colour lives on the widget
    (b._bg) so _recolor can change it without the hover undoing that."""
    b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, font=font,
                  relief=tk.FLAT, bd=0, cursor="hand2", disabledforeground="#F2F1EC",
                  activebackground=_darken(bg), activeforeground=fg, **kw)
    b._bg = bg
    b.bind("<Enter>", lambda _: b["state"] != tk.DISABLED and b.config(bg=_darken(b._bg)))
    b.bind("<Leave>", lambda _: b.config(bg=b._bg))
    return b

def _recolor(b, bg):
    b._bg = bg
    b.config(bg=bg, activebackground=_darken(bg))

def _cardf(parent, bg=None):
    return tk.Frame(parent, bg=bg or C["panel"], highlightthickness=1,
                    highlightbackground=C["border"])

def _dur(s):
    if not s: return ""
    m, s = divmod(int(s), 60); h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def _find_ffmpeg():
    if p := shutil.which("ffmpeg"): return p
    here = os.path.dirname(os.path.abspath(__file__))
    for n in ("ffmpeg.exe", "ffmpeg"):
        p = os.path.join(here, "bin", n)
        if os.path.isfile(p): return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

def valid_cookiefile(p) -> bool:
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f: h = f.read(4096)
        return ("Netscape HTTP Cookie File" in h or "HTTP Cookie File" in h
                or h.count("\t") >= 6)
    except Exception:
        return False

def cookie_domains(p) -> list:
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            return sorted({ln.split("\t")[0].lstrip(".")
                           for ln in f if ln.strip() and not ln.startswith("#") and "\t" in ln})
    except Exception:
        return []

# ── VK domain handling ────────────────────────────────────────────────────────
# VK runs the same videos under vk.com, vk.ru and vkvideo.ru, but the login
# session cookie (remixsid) is only ever set on vk.com / vk.ru. A cookies.txt
# exported while browsing vkvideo.ru therefore contains device tokens but NO
# session, so private videos fail even though the file "has vkvideo.ru".
# Two fixes, applied together:
#   1. try the same video under every VK host
#   2. copy the VK auth cookies across all three domains into a temp file
VK_HOSTS = ("vkvideo.ru", "vk.ru", "vk.com", "m.vk.com", "vkvideo.com")
VK_AUTH  = ("remixsid", "remixnsid", "remixsuc", "remixsid6", "remixdsid",
            "httoken", "remixstid", "remixstlid", "remixdt", "remixlang")

def is_vk(url) -> bool:
    return any(h in (url or "") for h in VK_HOSTS)

def url_variants(url: str) -> list:
    """Same video expressed under each host the site answers on."""
    if is_vk(url):
        # /live-OID_ID is the page of a live broadcast (or its recording). yt-dlp's
        # VK extractor only knows /video-OID_ID, which is the same video.
        m = re.search(r"/(?:video|live)(-?\d+_\d+)", url or "")
        if m:
            vid = m.group(1)
            return [f"https://vk.com/video{vid}",      # carries remixsid
                    f"https://vk.ru/video{vid}",
                    f"https://vkvideo.ru/video{vid}"]
    return [url]

def vk_listing_variants(url: str) -> list:
    """
    VK channel / playlist / album pages, expressed the way yt-dlp's VK
    extractors expect. vkvideo.ru is a JavaScript app whose HTML contains no
    video links, so scanning it with regexes can never work — the page has to
    go through yt-dlp's VK extractor instead.
    """
    u = url or ""
    out = []

    # Channel:  vkvideo.ru/@name   ->  vk.com/video/@name
    m = re.search(r"(?:vkvideo\.ru|vk\.(?:com|ru))/(?:video/)?@([\w.\-]+)", u)
    if m:
        name = m.group(1)
        out += [f"https://vk.com/video/@{name}",
                f"https://vk.ru/video/@{name}",
                f"https://vkvideo.ru/@{name}"]

    # Playlist / album:  .../playlist/-123_45  or  .../video/playlist/-123_45
    m = re.search(r"/(?:video/)?(?:playlist|album)/(-?\d+_\d+)", u)
    if m:
        pid = m.group(1)
        out += [f"https://vk.com/video/playlist/{pid}",
                f"https://vk.com/videos{pid.split('_')[0]}?section=playlist_{pid.split('_')[1]}",
                f"https://vkvideo.ru/playlist/{pid}"]

    # Community video tab:  .../video-123456  (owner only, no item id)
    m = re.search(r"/videos?(-?\d+)(?:$|[?/])", u)
    if m and not re.search(r"/video-?\d+_\d+", u):
        oid = m.group(1)
        out += [f"https://vk.com/video/@club{oid.lstrip('-')}",
                f"https://vk.com/videos{oid}"]

    seen, uniq = set(), []
    for x in out:
        if x not in seen:
            seen.add(x); uniq.append(x)
    return uniq

SETTINGS_PATH = os.path.join(HOME, ".video_downloader.json")

def load_settings() -> dict:
    """Remembered choices from the last session. Never fails — returns {} if unreadable."""
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            s = json.load(f)
        return s if isinstance(s, dict) else {}
    except Exception:
        return {}

def save_settings(**kw):
    """Merge kw into the settings file. Best-effort; a failure is never fatal."""
    try:
        s = load_settings()
        s.update({k: v for k, v in kw.items() if v is not None})
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
    except Exception:
        pass

def find_players(html: str) -> list:
    """(player url, kind) for video players yt-dlp can read once it is given
    their address — used when a page itself is "Unsupported URL".
    kinescope: kinescope.io/embed/<id> (generic extractor, page as Referer).
    getcourse: GetCourse's signed player iframe (.../sign-player/?json=...&s=...).
      Schools serve it from regional proxies (e.g. vh-api-1-de.gceuproxy.com)
      that yt-dlp's GetCourseRuPlayer does not match, so the same signed path
      is sent to player02.getcourse.ru, which it does match."""
    import html as _h
    out, seen = [], set()
    for v in re.findall(r'kinescope\.io/(?:embed/)?([A-Za-z0-9]{10,})', html):
        out.append((f"https://kinescope.io/embed/{v}", "kinescope"))
    for v in re.findall(r'(https?://[^"\'\s<>]+/sign-player/?\?[^"\'\s<>]*json=[^"\'\s<>]+)', html):
        v = _h.unescape(v)
        out.append((re.sub(r"^https?://[^/]+", "https://player02.getcourse.ru", v), "getcourse"))
    uniq = []
    for u, k in out:
        if u not in seen:
            seen.add(u); uniq.append((u, k))
    return uniq

def referer_for(url: str) -> str:
    """The page address without its query string and fragment. Course links carry
    e-mail tracking ids (utm_*, gcmes, gcmlg); those must not travel to the
    player hosts. Kinescope and GetCourse accept the plain page address."""
    if not url:
        return ""
    s = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((s.scheme, s.netloc, s.path, "", ""))

def safe_name(text: str, limit: int = 100) -> str:
    """A title made safe as a Windows file name (no reserved or control
    characters, no trailing dots or spaces, at most `limit` characters)."""
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", text).strip()[:limit].strip(" .")

def kinescope_stream(embed_url: str, referer: str, ctx=None):
    """(stream url, title) read from a Kinescope player page, or None.
    The player page holds the signed HLS address several times: as JSON
    ("\\u0026"), as HTML ("&amp;") and as plain text. yt-dlp's generic extractor
    takes one of them without decoding it, which is a 403. The player is
    domain-locked, so the page must be asked for with the course page as Referer."""
    import html as _h
    try:
        req = urllib.request.Request(embed_url, headers={"User-Agent": UA, "Referer": referer})
        with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
            page = r.read().decode("utf-8", errors="ignore")
    except Exception:
        return None
    # decode the whole page first (JSON escapes, then HTML entities) and match
    # afterwards, so an address written with escaped slashes is found as well
    text = _h.unescape(page.replace("\\u0026", "&").replace("\\u002F", "/").replace("\\/", "/"))
    urls = re.findall(r'https?://[^"\'\s<>]*master\.m3u8[^"\'\s<>]*', text)
    urls.sort(key=lambda u: "sign=" not in u)            # signed address first
    if not urls:
        return None
    m = (re.search(r'og:title"\s+content="([^"]*)"', page)
         or re.search(r"<title>([^<]*)</title>", page))
    return urls[0], (_h.unescape(m.group(1)).strip() if m else "")

def read_link_list(path) -> list:
    """(url, title) pairs from a link list the user made or a script produced.
    .txt: one link per line; any text before the link is its title.
    .json: a list of links, or of {"url", "title"} objects — also accepted
    inside a top-level "links" / "videos" / "items" / "lectures" key."""
    try:
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
            text = f.read()
    except Exception:
        return []
    out = []
    if path.lower().endswith(".json"):
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if isinstance(data, dict):
            data = next((data[k] for k in ("links", "videos", "items", "lectures")
                         if isinstance(data.get(k), list)), [])
        for it in data if isinstance(data, list) else []:
            if isinstance(it, str):
                out.append((it.strip(), ""))
            elif isinstance(it, dict):
                u = it.get("url") or it.get("link") or it.get("href") or ""
                t = it.get("title") or it.get("name") or ""
                out.append((str(u).strip(), str(t).strip()))
    if not out:                          # .txt, or JSON we could not read
        # Two layouts: "Title: link" on one line, or (Coursera Link Collector)
        # "03  Title  (1080p, 3 min)" with the bare link on the next line.
        above = ""
        for ln in text.splitlines():
            m = re.search(r"https?://[^\s\"'<>]+", ln)
            if not m:
                s = ln.strip()
                if s and not s.startswith("==="):
                    above = s
                continue
            prefix = ln[:m.start()].strip(" \t-|:;,\"'")
            if prefix.lower().startswith(("course page", "subtitles", "transcript")):
                continue                 # not a video
            if not prefix and above:
                prefix = re.sub(r"\s*\([^()]*\)\s*$", "", above)   # drop "(1080p, 3 min)"
            above = ""
            out.append((m.group(0).rstrip(",;"), re.sub(r"\s{2,}", " ", prefix).strip()))
    seen, uniq = set(), []
    for u, t in out:
        if u.startswith("http") and u not in seen:
            seen.add(u); uniq.append((u, t))
    return uniq

def remembered_dir() -> str:
    """Last folder the user picked, if it still exists; otherwise Downloads."""
    d = load_settings().get("download_dir", "")
    if d and os.path.isdir(d):
        return d
    return os.path.join(HOME, "Downloads")

def cookie_header_for(path: str, url: str) -> str:
    """
    Build a Cookie header containing only the cookies that belong to this
    host. Sending the whole jar to every site is what makes VK reject the
    request outright, so scope it.
    """
    # Read the Netscape format by hand as UTF-8: http.cookiejar uses the
    # Windows code page and gives up on the whole file at the first Cyrillic
    # cookie value — and then no cookies were sent at all.
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return ""
    host = host_of(url)
    parts = []
    for ln in lines:
        if ln.startswith("#HttpOnly_"):
            ln = ln[len("#HttpOnly_"):]
        elif not ln.strip() or ln.startswith("#"):
            continue
        p = ln.rstrip("\r\n").split("\t")
        if len(p) < 7:
            continue
        d = p[0].lstrip(".")
        if d and (host == d or host.endswith("." + d) or d.endswith("." + host)):
            parts.append(f"{p[5]}={p[6]}")
    return "; ".join(parts)

def is_bare_domain(url: str) -> bool:
    """A homepage / personalised feed — there is nothing specific to scan."""
    m = re.match(r"https?://[^/]+/?$", (url or "").strip())
    return bool(m)

def native_listing_url(url: str) -> bool:
    """
    True when the page is a video platform's own channel / playlist page.
    These are JavaScript apps: fetch the HTML and you get an empty shell, so
    they must be handed to yt-dlp's extractor rather than scanned.
    """
    u = url or ""
    if is_vk(u):
        return True
    return bool(re.search(
        r"(youtube\.com/(?:@|channel/|c/|playlist|user/))"
        r"|(vimeo\.com/(?:channels/|showcase/|album/|user\d+))"
        r"|(rutube\.ru/(?:channel|plst)/)"
        r"|(ok\.ru/(?:group|profile|video/c))", u))

def widen_vk_cookies(path: str) -> str:
    """
    Return a temp cookies.txt where VK auth cookies exist on every VK domain.
    Returns the original path when nothing needed copying.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return path

    rows, by_dom = [], {}
    for ln in lines:
        if not ln.strip() or ln.startswith("#"):
            continue
        p = ln.rstrip("\n").split("\t")
        if len(p) < 7:
            continue
        rows.append(p)
        by_dom.setdefault(p[0].lstrip("."), {})[p[5]] = p

    vk_doms = [d for d in by_dom if d in VK_HOSTS]
    if not vk_doms:
        return path

    # Collect the best auth cookie of each name from any VK domain
    best = {}
    for d in vk_doms:
        for name, row in by_dom[d].items():
            if name in VK_AUTH and name not in best:
                best[name] = row

    if "remixsid" not in best:
        return path        # nothing worth copying — the export has no session

    extra = []
    for target in ("vk.com", "vk.ru", "vkvideo.ru"):
        have = by_dom.get(target, {})
        for name, row in best.items():
            if name in have:
                continue
            new = list(row)
            new[0] = "." + target
            new[1] = "TRUE"
            extra.append(new)

    if not extra:
        return path

    try:
        import tempfile
        fd, out = tempfile.mkstemp(prefix="vdl_vk_", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n")
            for p in rows + extra:
                f.write("\t".join(p) + "\n")
        return out
    except Exception:
        return path

def discover_cookies() -> list:
    hits, seen = [], set()
    for d in COOKIE_DIRS:
        if not os.path.isdir(d): continue
        for p in glob.glob(os.path.join(d, "*.txt")):
            rp = os.path.realpath(p)
            if rp in seen or not os.path.isfile(rp): continue
            seen.add(rp)
            if valid_cookiefile(rp):
                hits.append((rp, os.path.getmtime(rp), cookie_domains(rp)))
    return sorted(hits, key=lambda x: x[1], reverse=True)

def host_of(url) -> str:
    m = re.search(r"https?://([^/]+)", url or "")
    return re.sub(r"^www\.", "", m.group(1).lower()) if m else ""

def is_youtube(url) -> bool:
    return "youtube.com" in (url or "") or "youtu.be" in (url or "")

def firefox_available() -> bool:
    if sys.platform == "win32":
        base = os.path.expandvars(r"%APPDATA%\Mozilla\Firefox\Profiles")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/Firefox/Profiles")
    else:
        base = os.path.expanduser("~/.mozilla/firefox")
    return os.path.isdir(base) and bool(glob.glob(os.path.join(base, "*", "cookies.sqlite")))

# ══════════════════════════════════════════════════════════════
#  4b.  WEBINAR ROOMS  (Bizon365 rooms, e.g. online.<school>.ru/room/...)
#  Link -> sign in like the room page does -> read the room's live channel
#  (Socket.IO) until the broadcast is on air -> download every HLS segment
#  directly -> one .ts file -> MP4. ffmpeg's own HLS reader is NOT used: it
#  stalled after ~2 h on a long live playlist (see CLAUDE.md).
# ══════════════════════════════════════════════════════════════
class RoomError(Exception):
    """args[0] is a wording key in T (shown to the user); extra info in .info."""
    def __init__(self, key, **info):
        super().__init__(key); self.key = key; self.info = info

ROOM_WS = "wss://ws3.bizon365.ru"          # the room page uses this host
ROOM_FIELDS = ("username", "email", "phone", "param1", "param2", "param3", "cu1", "sup")


def _http(url, data=None, headers=None, timeout=30):
    """(status, bytes). HTTP errors come back as a status, not an exception."""
    if not url.lower().startswith(("http://", "https://")):
        raise OSError("only http and https addresses are used")      # never file:// or ftp://
    h = {"User-Agent": UA}; h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()
        finally:
            e.close()


def room_split_link(link: str):
    """(room address ending in '/', {query values}). RoomError if it is no room link."""
    p = urllib.parse.urlparse((link or "").strip())
    if p.scheme not in ("http", "https") or not re.search(r"/room/[^/]+", p.path):
        raise RoomError("room_err_link")
    room = urllib.parse.urlunparse((p.scheme, p.netloc, p.path.rstrip("/") + "/", "", "", ""))
    return room, dict(urllib.parse.parse_qsl(p.query, keep_blank_values=True))


def room_signin(link: str):
    """Sign in the way the room page does (POST authorize, then loadInitData).
    Returns (room address, connection values from the room). The viewer's name,
    e-mail and phone come from the link itself and are never logged."""
    room, q = room_split_link(link)
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = [("User-Agent", UA)]

    def call(url, data=None):
        req = urllib.request.Request(url, headers={"Referer": room})
        if data is not None:                 # only the page's own AJAX calls carry this header;
            req.data = urllib.parse.urlencode(data).encode()   # on a page request it gives a 404
            req.add_header("X-Requested-With", "XMLHttpRequest")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with op.open(req, timeout=30) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            try:
                return e.code, e.read().decode("utf-8", "replace")
            finally:
                e.close()
        except OSError:
            raise RoomError("room_err_setup")

    call(room + "?" + urllib.parse.urlencode(q))       # first visit sets the session cookie
    st, _ = call(room + "authorize?_csrf=", {f: q.get(f, "") for f in ROOM_FIELDS})
    if st != 200:
        raise RoomError("room_err_signin")
    st, page = call(room)
    if st != 200:
        raise RoomError("room_err_signin")
    if "btnLogin" in page and "login-form" in page:
        raise RoomError("room_err_closed")
    m = re.search(r"ssid:\s*'([^']+)'", page)
    st, body = call(room + "loadInitData", {"_csrf": "", "ssid": m.group(1) if m else "", "lang": 1})
    try:
        init = json.loads(body)
    except ValueError:
        init = None
    if st != 200 or not isinstance(init, dict):
        raise RoomError("room_err_setup")
    return room, init


class WS:
    """Minimal WebSocket client (text frames only) - no extra package needed."""

    def __init__(self, url, origin, timeout=20):
        p = urllib.parse.urlparse(url)
        port = p.port or (443 if p.scheme == "wss" else 80)
        raw = socket.create_connection((p.hostname, port), timeout=timeout)
        self.s = (ssl.create_default_context().wrap_socket(raw, server_hostname=p.hostname)
                  if p.scheme == "wss" else raw)
        key = base64.b64encode(os.urandom(16)).decode()
        path = p.path + ("?" + p.query if p.query else "")
        self.s.sendall((f"GET {path} HTTP/1.1\r\nHost: {p.netloc}\r\nUpgrade: websocket\r\n"
                        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                        f"Sec-WebSocket-Version: 13\r\nOrigin: {origin}\r\nUser-Agent: {UA}\r\n\r\n"
                        ).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            c = self.s.recv(1)
            if not c:
                raise EOFError
            head += c
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise OSError("websocket refused")

    def _read(self, n):
        buf = b""
        while len(buf) < n:
            c = self.s.recv(n - len(buf))
            if not c:
                raise EOFError
            buf += c
        return buf

    def send(self, data, opcode=1):
        data = data.encode() if isinstance(data, str) else data
        mask, n = os.urandom(4), len(data)
        hdr = bytes([0x80 | opcode])
        hdr += (bytes([0x80 | n]) if n < 126 else
                b"\xfe" + struct.pack(">H", n) if n < 65536 else b"\xff" + struct.pack(">Q", n))
        self.s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self, timeout):
        """One text message, None on timeout, EOFError when the other side closed."""
        self.s.settimeout(timeout)
        msg = b""
        while True:
            try:
                b1, b2 = self._read(2)
            except socket.timeout:
                return None
            op, n = b1 & 0x0F, b2 & 0x7F
            self.s.settimeout(20)       # a frame has started: do not cut it off half way
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            if op == 9:
                self.send(payload, 10)
            elif op == 8:
                raise EOFError
            elif op in (0, 1, 2):
                msg += payload
                if b1 & 0x80:
                    return msg.decode("utf-8", "replace")
            self.s.settimeout(timeout)

    def close(self):
        try: self.s.close()
        except OSError: pass


def room_open_channel(init: dict, origin: str, ws_base: str = ROOM_WS):
    """Open the room's Socket.IO v2 channel. Returns (ws, ping seconds)."""
    q = urllib.parse.urlencode({
        "ssid": init.get("ssid", ""), "ssign": init.get("ssign", ""),
        "roomid": init.get("roomid", ""), "group": init.get("groupid", ""),
        "ticketid": init.get("ticketId", ""), "campid": init.get("campid", ""),
        "EIO": "3", "transport": "websocket"})
    ws = WS(f"{ws_base}/socket.io/?{q}", origin)
    first = ws.recv(15) or ""
    if not first.startswith("0"):
        ws.close(); raise RoomError("room_err_channel")
    ws.send("40")                                   # join the default namespace
    return ws, json.loads(first[1:]).get("pingInterval", 25000) / 1000.0


def room_wait_for_stream(init, origin, stop, ws_base=ROOM_WS, on_state=None, reconnects=5):
    """Wait on the live channel until the room is on air with a video address.
    Returns (video type, address, title), or None if `stop` was set first."""
    state, tries = {}, 0
    while not stop.is_set():
        ws = None
        try:
            ws, ping = room_open_channel(init, origin, ws_base)
            next_ping = time.time() + ping
            while not stop.is_set():
                if time.time() >= next_ping:
                    ws.send("2"); next_ping = time.time() + ping
                m = ws.recv(1.0)
                if not m or not m.startswith("42"):
                    continue
                try:
                    arr = json.loads(m[2:])
                except ValueError:
                    continue
                if arr and arr[0] in ("welcome", "newsettings") and len(arr) > 1 \
                        and isinstance(arr[1], dict):
                    room = arr[1].get("room", arr[1])
                    if isinstance(room, dict):
                        state.update(room)
                    if on_state:
                        on_state(state)
                    if state.get("online") and state.get("hangoutsUrl"):
                        return (state.get("videoType") or "", state["hangoutsUrl"],
                                state.get("title") or "")
                tries = 0
        except (OSError, EOFError, ValueError, RoomError):
            tries += 1
            if tries > reconnects:
                raise RoomError("room_err_channel")
            stop.wait(3)
        finally:
            if ws: ws.close()
    return None


def stream_from_setting(video_type: str, ref: str, fetch=None) -> str:
    """The room's video setting -> an HLS playlist address. Rutube (live) and
    direct .m3u8 addresses only; other kinds raise RoomError('room_err_type')."""
    fetch = fetch or (lambda u: _http(u)[1].decode("utf-8", "replace"))
    ref = (ref or "").strip()
    if ref.startswith("//"):
        ref = "https:" + ref
    if ".m3u8" in ref:
        if not ref.lower().startswith(("http://", "https://")):
            raise RoomError("room_err_stream")
        return ref
    vt = (video_type or "").lower()
    if not vt and (re.fullmatch(r"[0-9a-f]{32}", ref) or "rutube.ru" in ref):
        vt = "rutube"
    if vt != "rutube":
        raise RoomError("room_err_type", vt=vt or "?")
    m = re.search(r"[0-9a-f]{32}", ref)
    if not m:
        raise RoomError("room_err_stream")
    try:
        j = json.loads(fetch("https://rutube.ru/api/play/options/%s/?no_404=true&referer=%s"
                             % (m.group(0), urllib.parse.quote("https://rutube.ru/", safe=""))))
    except (ValueError, OSError):
        raise RoomError("room_err_stream")
    b = j.get("video_balancer") or {}
    u = b.get("m3u8") or b.get("default")
    if not u:
        hls = (j.get("live_streams") or {}).get("hls") or []
        u = hls[0].get("url") if hls and isinstance(hls[0], dict) else ""
    if not u:
        raise RoomError("room_err_stream")
    return u


def hls_parse(text: str, base: str) -> dict:
    """A media playlist -> {'segments': [(number, address, seconds)], 'endlist': bool,
    'init': address or ''}. The number is the segment's own sequence number."""
    seq, segs, dur, end, init = 0, [], 0.0, False, ""
    for ln in (l.strip() for l in text.splitlines()):
        if not ln:
            continue
        if ln.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            try: seq = int(ln.split(":", 1)[1])
            except ValueError: pass
        elif ln.startswith("#EXT-X-ENDLIST"):
            end = True
        elif ln.startswith("#EXT-X-MAP:"):
            m = re.search(r'URI="([^"]+)"', ln)
            if m: init = urllib.parse.urljoin(base, m.group(1))
        elif ln.startswith("#EXTINF:"):
            try: dur = float(ln[8:].split(",")[0])
            except ValueError: dur = 0.0
        elif not ln.startswith("#"):
            url = urllib.parse.urljoin(base, ln)
            if url.lower().startswith(("http://", "https://")):    # never file:// or ftp://
                segs.append((seq + len(segs), url, dur))
            dur = 0.0
    return {"segments": segs, "endlist": end, "init": init}


def hls_best_variant(text: str, base: str) -> str:
    """For a master playlist: the address of the highest-bandwidth stream, else ''."""
    best, best_bw, lines = "", -1, [l.strip() for l in text.splitlines()]
    for i, ln in enumerate(lines):
        if ln.startswith("#EXT-X-STREAM-INF"):
            m = re.search(r"BANDWIDTH=(\d+)", ln)
            bw = int(m.group(1)) if m else 0
            for nxt in lines[i + 1:]:
                if nxt and not nxt.startswith("#"):
                    if bw > best_bw:
                        best, best_bw = urllib.parse.urljoin(base, nxt), bw
                    break
    return best


def unique_path(folder: str, stem: str, ext: str) -> str:
    """folder/stem.ext, or 'stem (2).ext' ... - an existing file is never overwritten."""
    out, n = os.path.join(folder, stem + ext), 2
    while os.path.exists(out):
        out = os.path.join(folder, f"{stem} ({n}){ext}"); n += 1
    return out


def fmt_hms(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


class RoomRecorder:
    """Download a live HLS broadcast into one .ts file, segment by segment.
    The playlist keeps the whole broadcast, so we start at its first segment.
    The end is the #EXT-X-ENDLIST marker, the Stop button (`stop` event), or - the
    stream may simply stop with no marker - `idle_end` seconds without a new segment."""

    def __init__(self, playlist, out_path, stop, log=None, progress=None, fetch=None,
                 workers=8, poll=4.0, idle_end=180.0, retries=5, sleep=None):
        self.playlist, self.out, self.stop = playlist, out_path, stop
        self.log = log or (lambda m: None)
        self.progress = progress or (lambda n, secs, failed: None)
        self.fetch = fetch or (lambda u: self._net(u))
        self.workers, self.poll, self.idle_end, self.retries = workers, poll, idle_end, retries
        self.sleep = sleep or (lambda s: self.stop.wait(s))
        self.master_checked = False

    @staticmethod
    def _net(url):
        st, body = _http(url, timeout=30)
        if st != 200:
            raise OSError(f"HTTP {st}")
        return body

    def _segment(self, url):
        for attempt in range(self.retries):
            try:
                return self.fetch(url)
            except Exception:
                if attempt + 1 < self.retries:
                    self.sleep(min(2 ** attempt, 8))
        return None

    def run(self) -> dict:
        """Returns {'segments','seconds','failed','reason'}; reason is one of
        'endlist', 'stopped', 'stalled', 'disk' (the file could not be written: disk full,
        folder gone)."""
        r = {"segments": 0, "seconds": 0.0, "failed": 0, "reason": "stalled"}
        try:
            self._run(r)
        except OSError as e:
            self.log(f"   Could not write the recording: {clean(e)[:150]}")
            r["reason"] = "disk"
        return r

    def _run(self, r):
        done = failed = 0
        secs = 0.0
        nxt = None                          # number of the next segment to download
        todo = deque()
        last_growth = last_ok = time.time()
        reason = "stalled"
        with open(self.out, "wb") as f, ThreadPoolExecutor(self.workers) as pool:
            while True:
                if self.stop.is_set():
                    reason = "stopped"; break
                endlist = False
                try:
                    text = self.fetch(self.playlist).decode("utf-8", "replace")
                    if not self.master_checked:             # a master list: take its best stream
                        self.master_checked = True
                        best = hls_best_variant(text, self.playlist)
                        if best:
                            self.log("   Master playlist; using the best stream")
                            self.playlist = best
                            text = self.fetch(self.playlist).decode("utf-8", "replace")
                    pl = hls_parse(text, self.playlist)
                    last_ok = time.time()
                    segs = pl["segments"]
                    if nxt is None and segs:
                        nxt = segs[0][0]
                        if pl["init"]:
                            data = self._segment(pl["init"])
                            if data: f.write(data)
                    if nxt is not None:
                        fresh = [s for s in segs if s[0] >= nxt]
                        if fresh and fresh[0][0] > nxt:
                            self.log(f"   Playlist moved on: {fresh[0][0] - nxt} segment(s) skipped")
                        if fresh:
                            todo.extend(fresh); nxt = fresh[-1][0] + 1; last_growth = time.time()
                    endlist = pl["endlist"]
                except Exception as e:
                    if time.time() - last_ok > self.idle_end:
                        self.log(f"   Playlist unreachable for {int(self.idle_end)} s: {clean(e)[:100]}")
                        reason = "stalled"; break
                while todo:
                    if self.stop.is_set():
                        break
                    batch = [todo.popleft() for _ in range(min(len(todo), self.workers * 2))]
                    futs = [pool.submit(self._segment, s[1]) for s in batch]
                    for s, fu in zip(batch, futs):          # written strictly in order
                        data = fu.result()
                        if data is None:
                            failed += 1; r["failed"] = failed
                            self.log(f"   Segment {s[0]} could not be downloaded - skipped")
                        else:
                            f.write(data); done += 1; secs += s[2]
                            r["segments"], r["seconds"] = done, secs   # survives a later write error
                    self.progress(done, secs, failed)
                    last_ok = time.time()
                if self.stop.is_set():
                    reason = "stopped"; break
                if endlist and not todo:
                    reason = "endlist"; break
                if time.time() - last_growth > self.idle_end:
                    reason = "stalled"; break
                self.sleep(self.poll)
        r.update(segments=done, seconds=secs, failed=failed, reason=reason)


# ══════════════════════════════════════════════════════════════
#  5.  WORDING  (English / Russian — every text the user reads)
#  The activity log stays English: it is for the helper, not the user.
# ══════════════════════════════════════════════════════════════
T = {
"en": dict(
    app_title="Video Downloader", ready="Ready", attention="Needs attention",
    lang_switch="Русский",
    step1="1.  Copy the video's address in your browser, then press",
    paste="Paste link", clear="Clear",
    step2="2.  Choose what to save:",
    download="Download video", downloading="Downloading...",
    download_audio="Download sound", mode_video="Video", mode_audio="Sound only (MP3)",
    st_done_audio="Done! The sound is saved as an MP3 file.",
    saved_in="Videos are saved in:", downloads_folder="Downloads",
    open_folder="Open folder", change="Change", pick_folder="Where should videos be saved?",
    more="More:", nav_scan="Several videos on one page", nav_cookies="Log in to websites",
    nav_details="Details for helper", back="←  Back",
    checking="Checking the link...", found="Found: {title}",
    n_videos="{n} videos on this page — all will be downloaded",
    st_ready="Ready. Copy a video's address and press “Paste link”.",
    st_link_ok="The link is fine. Press the green button “{btn}”.",
    st_starting="Starting...", st_downloading="Downloading...  {pct}%",
    st_downloading_nopct="Downloading...", st_batch="Video {i} of {n}:  {pct}%",
    st_finishing="Almost done — putting the video together...",
    st_finishing_audio="Almost done — making the MP3 file... please wait",
    convert="Convert to MP4", converting="Converting...",
    conv_hint="Recorded a live webinar (a .mkv or .ts file)? Make it a normal MP4:",
    conv_pick="Choose the recording to convert", conv_types="Video files",
    st_converting="Converting to MP4...  {pct}%", st_converting_nopct="Converting to MP4...",
    st_converted="Done! The MP4 file is saved next to the original.",
    st_conv_failed="The conversion did not work. The original file is untouched.",
    nav_room="Record a webinar room", room_title="Record a webinar room",
    room_help="Paste the link of a webinar room (the address contains /room/). The program "
              "waits until the broadcast starts, records it, and when you press “Stop and "
              "save” — or the broadcast ends — makes an MP4 video. Keep this window open and "
              "do not let the computer go to sleep (do not close the laptop lid) until it "
              "says Done. A 2-hour webinar needs about 8 GB of free disk space. While the "
              "program is only waiting, “Stop and save” simply cancels.",
    room_start="Start recording", room_stop="Stop and save", recording="Recording...",
    st_room_signin="Entering the webinar room...",
    st_room_wait="Waiting for the broadcast to begin. Keep this window open.",
    st_room_rec="Recording the broadcast...  recorded so far: {t} (hours:minutes:seconds)",
    st_room_stopping="Stopping — saving what was recorded...",
    st_room_converting="Making the MP4... For a long recording this can take a few minutes. "
                       "Do not close the window.",
    st_room_cancel="Stopped. Nothing was recorded.",
    st_room_nothing="Nothing could be recorded from this room. The broadcast may not have "
                    "started yet. Try again when the webinar is on air.",
    st_room_done="Done! The recording ({t}) is saved as an MP4 in your download folder.",
    st_room_done_kept="Done! The recording ({t}) is saved as an MP4 in your download folder. "
                      "The unprocessed copy (.ts) was kept too; delete it once the MP4 plays well.",
    st_room_done_skipped="Done, but {n} short pieces could not be downloaded, so the video "
                         "may jump. The MP4 is in your download folder. The unprocessed "
                         "copy (.ts) was kept too.",
    st_room_done_check="Done, but the length of the video ({t}) does not match what was "
                       "downloaded. Check that the MP4 plays to the end. The unprocessed "
                       "copy (.ts) was kept too.",
    st_room_done_stalled="The broadcast sent no video for 3 minutes, so the recording ended "
                         "there. The MP4 ({t}) is in your download folder. The unprocessed "
                         "copy (.ts) was kept too.",
    room_close_title="Recording in progress",
    room_close_ask="A recording is running. If you close the program now, the recording "
                   "stops and no MP4 is made. Close anyway?",
    room_err_link="This link does not look like a webinar room. The address must contain "
                  "/room/. Copy the link you received for the webinar.",
    room_err_signin="The room did not let the program in. Open the link in your browser to "
                    "check that it still works. If it does not, ask the school for a new link.",
    room_err_closed="The room still shows its entry form. The link may be old or "
                    "incomplete — copy the whole address again, or ask the school for a new link.",
    room_err_setup="The room did not answer. Check your internet connection and try again.",
    room_err_channel="Could not connect to the room's broadcast. Wait one minute, then press "
                     "“Start recording” again.",
    room_err_type="This room plays its video from a source the program cannot record yet. "
                  "Tell the person who helps you and give them this code: {vt}",
    room_err_stream="The room gave a link to the video that the program could not open. "
                    "Tell the person who helps you and say the video link did not open.",
    room_err_disk="The recording could not be written. The disk may be full. Free some "
                  "space (a 2-hour webinar needs about 8 GB), then press “Start recording” again.",
    room_err_disk_part="The disk is full or the folder cannot be written. What was recorded "
                       "so far is in the file “{name}” in your download folder. Free some "
                       "space, then use “Convert to MP4” on that file.",
    room_err_unexpected="Something in the program failed. Open “Details for helper” and tell "
                        "the person who helps you.",
    st_done="Done! The video is saved.", st_done_n="Done! {ok} of {n} videos saved.",
    st_done_n_audio="Done! {ok} of {n} sound files saved.",
    st_none_saved="None of the videos could be downloaded.",
    left_lt_min="Less than a minute left", left_min="About {n} {unit} left",
    no_link="First copy a video's address in your browser, then press “Paste link”.",
    not_link="What you copied is not a web address. Copy the address from the bar "
             "at the top of the browser.",
    busy="Please wait — a download is already running.",
    wait_lang="Please wait until the download has finished.",
    st_updating="Updating the download engine... This can take a minute.",
    st_updated="Updated. Close the program, open it again, and try once more.",
    st_update_failed="The update did not work. Check the internet connection.",
    st_installing="Installing the helper module (FFmpeg)... This can take a few minutes.",
    st_helper_ready="The helper module (FFmpeg) is installed.",
    st_helper_failed="The helper module (FFmpeg) could not be installed. Ask your helper.",
    act_update="Update now", act_install="Install helper",
    d_youtube="YouTube refused the download. YouTube changes often — updating "
              "the program usually fixes this.",
    d_browser="The browser keeps its logins locked. Set up “Log in to websites” once.",
    d_bot="YouTube wants proof you are a person. Log in to YouTube and set up "
          "“Log in to websites”.",
    d_cert="Secure-connection problem. Ask your helper to look at “Details for helper”.",
    d_ffmpeg="A helper module (FFmpeg) is missing. Press “Install helper”.",
    d_ffmpeg_audio="The sound file cannot be made yet: the helper module (FFmpeg) is missing. Nothing was downloaded. Press “Install helper”, then press “Download sound” again.",
    page_video_only="This page always saves video, not sound.",
    d_private="This video is private — the website needs to know you are logged in. "
              "Set up “Log in to websites”.",
    d_not_video="This address is not a video page, or this website is not supported.",
    d_no_player="No video was found on this page. If it is a private lesson, set up "
                "“Log in to websites” first; otherwise this website may not be supported.",
    d_network="No internet connection, or the website is not answering. "
              "Try again in a minute.",
    d_other="Something went wrong. Your helper can see the details under "
            "“Details for helper”.",
    scan_title="Several videos on one page",
    scan_help="For a course lesson or any page with several videos. Copy the page's "
              "address, press “Paste link”, then “Find videos”.",
    find="Find videos", looking="Looking...",
    open_list="Open list file...", list_pick="Choose a .txt or .json file with video links",
    list_loaded="Loaded {n} links from the file. Untick any you don't want, then press "
                "the green button.",
    list_empty="No web addresses found in that file.",
    scan_list_hdr="Videos found — click a line to tick or untick it",
    tick_all="Tick all", untick_all="Untick all",
    dl_ticked="Download ticked videos", downloading_n="Downloading {n} videos...",
    scan_none="No videos found. If the page needs a login, set up "
              "“Log in to websites” and try again.",
    scan_front="This is the website's front page. Open the lesson or channel you want "
               "and copy that address.",
    scan_found="Found {n} videos. Untick any you don't want, then press the green button.",
    no_page="First copy the page's address, then press “Paste link”.",
    nothing_ticked="Tick at least one video first (click on its line).",
    ck_title="Log in to websites",
    ck_help="Only needed for private videos, paid courses and age-restricted videos. "
            "Do it once — it then works for months. The program finds the exported "
            "file by itself.",
    ck_step1="Install the free browser add-on", ck_btn1="Open add-on page",
    ck_step2="Log in to the websites you use", ck_btn2="Open websites",
    ck_step3="Click the add-on's icon and press “Export”", ck_btn3="I exported it",
    ck_files="Login files found on this computer",
    ck_browse="Choose file...", ck_rescan="Look again", ck_forget="Stop using",
    ck_forget_q="Stop using the login file?\n\nThe file stays on the computer.",
    ck_list_none="   None yet — public videos work without it. "
                 "Follow the steps above when needed.",
    ck_sites="{n} websites", ck_imported="Login file found: {name}",
    ck_bad_file="That file is not a login (cookies.txt) file.",
    ck_pick="Choose the cookies.txt file",
    sites_title="Open a website and log in", sites_open="Open {name}", close="Close",
    dt_title="Details for helper",
    dt_ssl="Certificate check:", ssl_auto="Automatic (Windows certificates)",
    ssl_strict="Strict (certifi)", ssl_skip="Skip the check (last resort)",
    dt_yt="YouTube: try without login first (avoids “page needs to be reloaded”)",
    dt_update="Update download engine", dt_ffmpeg="Install helper module (FFmpeg)",
    dt_log="Activity log", dt_clear_log="Clear log",
    sys_ssl="Secure connections", sys_ffmpeg="Helper module (FFmpeg)",
    sys_cookies="Login file", sys_engine="Download engine", sys_version="Program version",
    sys_ok="working", sys_missing="missing", sys_none="none",
),
"ru": dict(
    app_title="Загрузчик видео", ready="Готово к работе", attention="Нужна помощь",
    lang_switch="English",
    step1="1.  Скопируйте адрес видео в браузере и нажмите",
    paste="Вставить ссылку", clear="Очистить",
    step2="2.  Выберите, что сохранить:",
    download="Скачать видео", downloading="Скачиваю...",
    download_audio="Скачать звук", mode_video="Видео", mode_audio="Только звук (файл MP3)",
    st_done_audio="Готово! Звук сохранён в файл MP3.",
    saved_in="Видео сохраняются в папку:", downloads_folder="Загрузки",
    open_folder="Открыть папку", change="Изменить", pick_folder="Куда сохранять видео?",
    more="Ещё:", nav_scan="Несколько видео на странице", nav_cookies="Вход на сайты",
    nav_details="Для помощника", back="←  Назад",
    checking="Проверяю ссылку...", found="Найдено: {title}",
    n_videos="Видео на странице: {n} — скачаются все",
    st_ready="Готово. Скопируйте адрес видео и нажмите «Вставить ссылку».",
    st_link_ok="Ссылка в порядке. Нажмите зелёную кнопку «{btn}».",
    st_starting="Начинаю...", st_downloading="Скачиваю...  {pct}%",
    st_downloading_nopct="Скачиваю...", st_batch="Видео {i} из {n}:  {pct}%",
    st_finishing="Почти готово — собираю видео...",
    st_finishing_audio="Почти готово — делаю файл MP3... подождите",
    convert="Сделать MP4", converting="Преобразую...",
    conv_hint="Записали прямой эфир (файл .mkv или .ts)? Сделайте из него обычный MP4:",
    conv_pick="Выберите запись для преобразования", conv_types="Видеофайлы",
    st_converting="Преобразую в MP4...  {pct}%", st_converting_nopct="Преобразую в MP4...",
    st_converted="Готово! Файл MP4 сохранён рядом с исходным.",
    st_conv_failed="Преобразовать не получилось. Исходный файл не тронут.",
    nav_room="Записать вебинарную комнату", room_title="Записать вебинарную комнату",
    room_help="Вставьте ссылку на вебинарную комнату (в адресе есть /room/). Программа "
              "дождётся начала трансляции, запишет её, а когда вы нажмёте «Остановить и "
              "сохранить» или трансляция закончится, сделает видео MP4. Не закрывайте окно "
              "и не давайте компьютеру заснуть (не закрывайте крышку ноутбука), пока не "
              "появится «Готово». Для двухчасового вебинара нужно около 8 ГБ свободного "
              "места на диске. Пока программа только ждёт, кнопка «Остановить и сохранить» "
              "просто отменяет ожидание.",
    room_start="Начать запись", room_stop="Остановить и сохранить", recording="Запись...",
    st_room_signin="Захожу в комнату вебинара...",
    st_room_wait="Жду начала трансляции. Не закрывайте это окно.",
    st_room_rec="Идёт запись трансляции...  записано: {t} (часы:минуты:секунды)",
    st_room_stopping="Останавливаю — сохраняю записанное...",
    st_room_converting="Делаю MP4... Для длинной записи это может занять несколько минут. "
                       "Не закрывайте окно.",
    st_room_cancel="Остановлено. Ничего не записано.",
    st_room_nothing="Из этой комнаты ничего не удалось записать. Возможно, трансляция ещё не "
                    "началась. Попробуйте ещё раз, когда вебинар идёт.",
    st_room_done="Готово! Запись ({t}) сохранена в MP4 в вашей папке загрузок.",
    st_room_done_kept="Готово! Запись ({t}) сохранена в MP4 в вашей папке загрузок. Исходная "
                      "копия (.ts) тоже оставлена; удалите её, когда убедитесь, что MP4 "
                      "воспроизводится.",
    st_room_done_skipped="Готово, но {n} коротких фрагментов не удалось загрузить, поэтому в "
                         "видео могут быть скачки. Файл MP4 лежит в папке загрузок. Исходная "
                         "копия (.ts) тоже оставлена.",
    st_room_done_check="Готово, но длина видео ({t}) не совпадает с загруженным. Проверьте, "
                       "что MP4 воспроизводится до конца. Исходная копия (.ts) тоже оставлена.",
    st_room_done_stalled="Трансляция не передавала видео 3 минуты, поэтому запись закончена "
                         "на этом месте. Файл MP4 ({t}) лежит в папке загрузок. Исходная "
                         "копия (.ts) тоже оставлена.",
    room_close_title="Идёт запись",
    room_close_ask="Идёт запись. Если закрыть программу сейчас, запись остановится и MP4 не "
                   "будет создан. Всё равно закрыть?",
    room_err_link="Эта ссылка не похожа на вебинарную комнату. В адресе должно быть /room/. "
                  "Скопируйте ссылку, которую вы получили для вебинара.",
    room_err_signin="Комната не пустила программу. Откройте ссылку в браузере и проверьте, "
                    "что она ещё работает. Если нет — попросите у школы новую ссылку.",
    room_err_closed="Комната всё ещё показывает форму входа. Возможно, ссылка устарела или "
                    "скопирована не полностью — скопируйте весь адрес снова или попросите у "
                    "школы новую ссылку.",
    room_err_setup="Комната не отвечает. Проверьте интернет и попробуйте ещё раз.",
    room_err_channel="Не удалось подключиться к трансляции комнаты. Подождите минуту и снова "
                     "нажмите «Начать запись».",
    room_err_type="Эта комната показывает видео из источника, который программа пока не умеет "
                  "записывать. Сообщите тому, кто вам помогает, и назовите ему этот код: {vt}",
    room_err_stream="Комната дала ссылку на видео, которую программа не смогла открыть. "
                    "Сообщите тому, кто вам помогает, что ссылка на видео не открылась.",
    room_err_disk="Не удалось записать файл. Возможно, на диске нет места. Освободите место "
                  "(для двухчасового вебинара нужно около 8 ГБ) и снова нажмите «Начать запись».",
    room_err_disk_part="На диске нет места или в папку нельзя записать. Всё записанное до этого "
                       "лежит в файле «{name}» в папке загрузок. Освободите место и "
                       "воспользуйтесь кнопкой «Сделать MP4» для этого файла.",
    room_err_unexpected="В программе произошла ошибка. Откройте «Для помощника» и сообщите "
                        "тому, кто вам помогает.",
    st_done="Готово! Видео сохранено.", st_done_n="Готово! Сохранено видео: {ok} из {n}.",
    st_done_n_audio="Готово! Сохранено файлов со звуком: {ok} из {n}.",
    st_none_saved="Не удалось скачать ни одного видео.",
    left_lt_min="Осталось меньше минуты", left_min="Осталось примерно: {n} {unit}",
    no_link="Сначала скопируйте адрес видео в браузере, потом нажмите "
            "«Вставить ссылку».",
    not_link="Скопированный текст — не адрес страницы. Скопируйте адрес из строки "
             "вверху браузера.",
    busy="Подождите — видео уже скачивается.",
    wait_lang="Подождите, пока закончится скачивание.",
    st_updating="Обновляю программу скачивания... Это может занять минуту.",
    st_updated="Обновлено. Закройте программу, откройте её снова и попробуйте ещё раз.",
    st_update_failed="Обновить не удалось. Проверьте подключение к интернету.",
    st_installing="Устанавливаю модуль (FFmpeg)... Это может занять несколько минут.",
    st_helper_ready="Модуль (FFmpeg) установлен.",
    st_helper_failed="Не удалось установить модуль (FFmpeg). Обратитесь к помощнику.",
    act_update="Обновить", act_install="Установить модуль",
    d_youtube="YouTube не отдал видео. YouTube часто меняется — обычно помогает "
              "обновление программы.",
    d_browser="Браузер не даёт доступ к входу на сайты. Один раз настройте "
              "«Вход на сайты».",
    d_bot="YouTube просит подтвердить, что вы не робот. Войдите в YouTube и настройте "
          "«Вход на сайты».",
    d_cert="Проблема с защищённым соединением. Попросите помощника открыть "
           "«Для помощника».",
    d_ffmpeg="Не хватает модуля (FFmpeg). Нажмите «Установить модуль».",
    d_ffmpeg_audio="Чтобы сделать файл MP3, нужен модуль (FFmpeg). Он не установлен, ничего не скачано. Нажмите «Установить модуль», потом снова «Скачать звук».",
    page_video_only="Эта страница всегда сохраняет видео, не звук.",
    d_private="Это закрытое видео — сайту нужно знать, что вы вошли. Настройте "
              "«Вход на сайты».",
    d_not_video="По этому адресу нет видео, или этот сайт не поддерживается.",
    d_no_player="На этой странице не найдено видео. Если это закрытый урок, сначала настройте "
                "«Вход на сайты»; иначе этот сайт может не поддерживаться.",
    d_network="Нет интернета, или сайт не отвечает. Попробуйте через минуту.",
    d_other="Что-то пошло не так. Помощник увидит подробности в разделе "
            "«Для помощника».",
    scan_title="Несколько видео на странице",
    scan_help="Для урока курса или любой страницы с несколькими видео. Скопируйте адрес "
              "страницы, нажмите «Вставить ссылку», затем «Найти видео».",
    find="Найти видео", looking="Ищу...",
    open_list="Открыть список...", list_pick="Выберите файл .txt или .json со ссылками на видео",
    list_loaded="Загружено ссылок из файла: {n}. Снимите отметку с ненужных и нажмите "
                "зелёную кнопку.",
    list_empty="В этом файле не найдено ни одного адреса.",
    scan_list_hdr="Найденные видео — щёлкните по строке, чтобы отметить или снять отметку",
    tick_all="Отметить все", untick_all="Снять все",
    dl_ticked="Скачать отмеченные", downloading_n="Скачиваю видео: {n}...",
    scan_none="Видео не найдены. Если на странице нужен вход, настройте "
              "«Вход на сайты» и попробуйте снова.",
    scan_front="Это главная страница сайта. Откройте нужный урок или канал и "
               "скопируйте его адрес.",
    scan_found="Найдено видео: {n}. Снимите отметку с ненужных и нажмите зелёную кнопку.",
    no_page="Сначала скопируйте адрес страницы и нажмите «Вставить ссылку».",
    nothing_ticked="Сначала отметьте хотя бы одно видео (щёлкните по строке).",
    ck_title="Вход на сайты",
    ck_help="Нужно только для закрытых видео, платных курсов и видео с ограничением "
            "по возрасту. Делается один раз и работает месяцами. Программа сама "
            "найдёт сохранённый файл.",
    ck_step1="Установите бесплатное дополнение для браузера", ck_btn1="Открыть дополнение",
    ck_step2="Войдите на сайты, которыми пользуетесь", ck_btn2="Открыть сайты",
    ck_step3="Нажмите значок дополнения, затем «Export»", ck_btn3="Готово, сохранено",
    ck_files="Файлы входа на этом компьютере",
    ck_browse="Выбрать файл...", ck_rescan="Искать снова", ck_forget="Не использовать",
    ck_forget_q="Перестать использовать файл входа?\n\nСам файл останется на компьютере.",
    ck_list_none="   Пока нет — открытые видео скачиваются и без него. "
                 "При необходимости выполните шаги выше.",
    ck_sites="сайтов: {n}", ck_imported="Найден файл входа: {name}",
    ck_bad_file="Этот файл — не файл входа (cookies.txt).",
    ck_pick="Выберите файл cookies.txt",
    sites_title="Откройте сайт и войдите", sites_open="Открыть {name}", close="Закрыть",
    dt_title="Для помощника",
    dt_ssl="Проверка сертификатов:", ssl_auto="Автоматически (сертификаты Windows)",
    ssl_strict="Строго (certifi)", ssl_skip="Без проверки (крайняя мера)",
    dt_yt="YouTube: сначала без входа (помогает при «page needs to be reloaded»)",
    dt_update="Обновить программу скачивания", dt_ffmpeg="Установить модуль (FFmpeg)",
    dt_log="Журнал", dt_clear_log="Очистить журнал",
    sys_ssl="Защищённые соединения", sys_ffmpeg="Модуль (FFmpeg)",
    sys_cookies="Файл входа", sys_engine="Программа скачивания",
    sys_version="Версия программы",
    sys_ok="работает", sys_missing="нет", sys_none="нет",
),
}

def default_lang() -> str:
    """The saved choice; otherwise Russian when Windows is Russian, else English."""
    s = load_settings().get("lang")
    if s in T:
        return s
    if sys.platform == "win32":
        try:
            import ctypes
            if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x19:
                return "ru"
        except Exception:
            pass
    return "en"

def ru_plural(n, one, few, many):
    n = abs(n) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    return one if n == 1 else few if 2 <= n <= 4 else many

# ══════════════════════════════════════════════════════════════
#  6.  CHECK-LISTBOX
# ══════════════════════════════════════════════════════════════
class CheckListbox(tk.Frame):
    """Click a row to tick / untick. Works on an outside list so the items
    survive a rebuild of the window (language switch)."""
    def __init__(self, parent, items, **kw):
        super().__init__(parent, bg=C["panel"], highlightthickness=1,
                         highlightbackground=C["border"], **kw)
        self._items = items
        self._lb = tk.Listbox(self, font=(UI, 13), bg=C["panel"], fg=C["text"],
                              selectmode=tk.BROWSE, selectbackground=C["panel"],
                              selectforeground=C["text"], activestyle="none",
                              relief=tk.FLAT, bd=0, height=4)
        self._lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=6)
        self._lb.bind("<Button-1>", self._toggle)
        sb = ttk.Scrollbar(self, command=self._lb.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y, pady=4)
        self._lb["yscrollcommand"] = sb.set
        for i in range(len(self._items)):
            self._lb.insert(tk.END, ""); self._redraw(i)

    def _row(self, it):
        return f"  {'☑' if it['checked'] else '☐'}   {it['title'][:80]}    ({it['site']})"

    def _redraw(self, i):
        self._lb.delete(i); self._lb.insert(i, self._row(self._items[i]))
        self._lb.itemconfig(i, fg=C["text"] if self._items[i]["checked"] else C["muted"])

    def _toggle(self, e):
        i = self._lb.nearest(e.y)
        if 0 <= i < len(self._items):
            self._items[i]["checked"] ^= True; self._redraw(i)

    def add(self, url, site, title, checked=True, **extra):
        self._items.append(dict(url=url, site=site, title=title, checked=checked, **extra))
        self._lb.insert(tk.END, ""); self._redraw(len(self._items) - 1)

    def select_all(self, v=True):
        for i, it in enumerate(self._items): it["checked"] = v; self._redraw(i)

    def selected(self): return [i for i in self._items if i["checked"]]
    def clear(self): self._items.clear(); self._lb.delete(0, tk.END)

# ══════════════════════════════════════════════════════════════
#  7.  APPLICATION
#  One simple main screen for the user; everything else is a page reached
#  from the links at the bottom. Big text, light colours, one green button.
# ══════════════════════════════════════════════════════════════
class App(tk.Tk):

    def __init__(self):
        if sys.platform == "win32":
            try:
                import ctypes
                # Own taskbar identity, so Windows shows the logo instead of Python's icon
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "MY.VideoDownloader")
                # Sharp text on scaled screens (125 % / 150 %) instead of blurry
                # bitmap stretching. Window sizes are scaled by hand below.
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass
        super().__init__()
        self._lang = default_lang()

        s = self.winfo_fpixels("1i") / 96.0          # 1.0 at 100 %, 1.5 at 150 %
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(int(980 * s), sw - 40), min(int(760 * s), sh - 90)
        self.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")
        self.minsize(min(int(760 * s), sw - 40), min(int(680 * s), sh - 90))
        self.configure(bg=C["bg"])

        # Window / taskbar icon
        self._icon_img = _logo_image(LOGO_ICON_B64)
        if self._icon_img is not None:
            try:
                self.iconphoto(True, self._icon_img)
            except Exception:
                pass

        self._dl_dir = remembered_dir()
        self._cookies_file = ""; self._auto_cookie = ""; self._cookie_files = []
        self._running = self._scanning = self._url_checking = False
        self._url_check_id = None
        self._ffmpeg = _find_ffmpeg()
        self._page_url = ""
        self._watch_seen = set(); self._watching = True
        self._engine_ver = ""
        self._lookup_cache = {}             # short-lived page / player lookups (_cached)
        self._last_conv = ""                # last file made by "Convert to MP4"
        self._page = "main"
        self._batch = None                  # (i, n) while downloading ticked videos
        self._last_clip = ""                # last link taken from the clipboard
        self._last_hook = 0.0

        # State kept outside the widgets, so a language switch rebuilds the
        # window without losing anything
        self._url_var = tk.StringVar(); self._page_var = tk.StringVar()
        self._mode_var = tk.StringVar(value="video")    # "video" | "audio" (main screen only)
        self._audio_run = False             # the mode the running download started with
        self._room_var = tk.StringVar()
        self._room_active = False           # a webinar room is being waited for / recorded
        self._room_stop = threading.Event()
        self._room_shown = 0.0              # when the recording time was last shown
        self._done_note = None              # final message of a room recording (see _conv_done)
        self._yt_nocookie = tk.BooleanVar(value=True)
        self._prog = tk.DoubleVar()
        self._ssl_mode = "auto"
        self._log_lines = []
        self._scan_items = []
        self._status_state = ("idle", "st_ready", None, {})
        self._url_state = None
        self._scan_state = ("", {})
        self._url_var.trace_add("write", self._url_changed)

        self._build()
        self.after(300,  self._rescan_cookies)
        self.after(700,  self._startup_report)
        self.after(900,  self._auto_paste)
        self.after(1200, self._bg_update)
        self.after(1800, self._refresh_ffmpeg)
        self.bind("<Activate>", self._on_activate)
        threading.Thread(target=self._cookie_watcher, daemon=True).start()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _close(self):
        if self._room_active or self._done_note:           # a webinar room is being recorded / made into MP4
            if not messagebox.askyesno(self.t("room_close_title"), self.t("room_close_ask"),
                                       icon="warning", default="no", parent=self):
                return
            self._room_stop.set()
        self._watching = False; self.destroy()

    def t(self, key, **kw):
        s = T[self._lang].get(key) or T["en"][key]
        return s.format(**kw) if kw else s

    # ══════════════════════════════════════════════════════════
    #  LAYOUT
    #  row0 header · row1 pages (grows) · row2 STATUS PANEL (always
    #  visible, never clipped) · row3 links to the other pages
    # ══════════════════════════════════════════════════════════

    def _build(self):
        self.title(self.t("app_title"))
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._style()

        self._header().grid(row=0, column=0, sticky="ew")
        self._body = tk.Frame(self, bg=C["bg"])
        self._body.grid(row=1, column=0, sticky="nsew", padx=24, pady=(16, 8))
        self._body.grid_rowconfigure(0, weight=1); self._body.grid_columnconfigure(0, weight=1)
        self._pages = {"main": self._page_main(), "scan": self._page_scan(),
                       "room": self._page_room(),
                       "cookies": self._page_cookies(), "details": self._page_details()}
        for f in self._pages.values():
            f.grid(row=0, column=0, sticky="nsew")
        self._statuspanel().grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 10))
        self._footer().grid(row=3, column=0, sticky="ew")

        # Re-show everything that was on screen before a rebuild
        for text, tag in self._log_lines:
            self._log_insert(text, tag)
        kind, key, action, kw = self._status_state
        self._set_status(kind, key, action, **kw)
        self._render_url_info(); self._render_scan_info()
        self._refresh_cookie_list()
        self._startup_report(quiet=True)
        self._show(self._page)

    def _style(self):
        st = ttk.Style(); st.theme_use("clam")
        st.configure("Big.Horizontal.TProgressbar", troughcolor=C["panel2"],
                     background=C["green"], darkcolor=C["green"], lightcolor=C["green"],
                     bordercolor=C["border"], thickness=22)
        st.configure("D.TCombobox", fieldbackground=C["panel"], background=C["panel2"],
                     foreground=C["text"], arrowcolor=C["text"])
        self.option_add("*TCombobox*Listbox.font", (UI, 12))

    def _label(self, parent, text="", size=13, bold=False, fg=None, bg=None, wrap=False,
               **kw):
        l = tk.Label(parent, text=text, font=(UI, size, "bold") if bold else (UI, size),
                     fg=fg or C["text"], bg=bg or C["bg"], anchor=tk.W, justify=tk.LEFT,
                     **kw)
        if wrap:        # wrap to whatever width the layout gives the label
            l.bind("<Configure>", lambda e: l.config(wraplength=max(100, e.width - 4)))
        return l

    def _header(self):
        h = tk.Frame(self, bg=C["header"])
        # Logo, upper left. Kept as an attribute or Tk garbage-collects it
        # and the label renders blank.
        self._logo_img = _logo_image(LOGO_HEADER_B64)
        if self._logo_img is not None:
            tk.Label(h, image=self._logo_img, bg=C["header"], bd=0
                     ).pack(side=tk.LEFT, padx=(16, 10), pady=8)
        tk.Label(h, text=self.t("app_title"), font=(UI, 20, "bold"), fg="#FFFFFF",
                 bg=C["header"]).pack(side=tk.LEFT, padx=(0 if self._logo_img else 20, 0),
                                       pady=12)
        _btn(h, self.t("lang_switch"), self._switch_lang, bg="#4A4945", fg="#FFFFFF",
             font=(UI, 12)).pack(side=tk.RIGHT, padx=(8, 16), ipadx=12, ipady=4)
        self._pill = tk.Label(h, text="", font=(UI, 13, "bold"), bg=C["header"],
                              fg=C["pill_ok"], cursor="hand2")
        self._pill.pack(side=tk.RIGHT, padx=10)
        self._pill.bind("<Button-1>", lambda _: self._show("details"))
        return h

    def _footer(self):
        f = tk.Frame(self, bg=C["panel2"])
        tk.Label(f, text=self.t("more"), font=(UI, 12), fg=C["muted"], bg=C["panel2"]
                 ).pack(side=tk.LEFT, padx=(24, 4), pady=10)
        for key, page in (("nav_scan", "scan"), ("nav_room", "room"),
                          ("nav_cookies", "cookies"), ("nav_details", "details")):
            l = tk.Label(f, text=self.t(key), font=(UI, 12, "underline"), fg=C["blue"],
                         bg=C["panel2"], cursor="hand2")
            l.pack(side=tk.LEFT, padx=10)
            l.bind("<Button-1>", lambda _, pg=page: self._show(pg))
        return f

    def _show(self, name):
        self._page = name
        self._pages[name].tkraise()

    def _page_top(self, parent, title_key):
        """'<- Back' and the page title on one row (saves height on small screens)."""
        f = tk.Frame(parent, bg=C["bg"])
        _btn(f, self.t("back"), lambda: self._show("main"), bg=C["panel2"], fg=C["text"],
             font=(UI, 13, "bold")).pack(side=tk.LEFT, ipadx=10, ipady=3)
        self._label(f, self.t(title_key), 17, True).pack(side=tk.LEFT, padx=(16, 0))
        return f

    def _entry(self, parent, var, on_return):
        cf = _cardf(parent)
        e = tk.Entry(cf, textvariable=var, font=(UI, 13), bg=C["panel"], fg=C["text"],
                     insertbackground=C["text"], relief=tk.FLAT, bd=0)
        e.pack(fill=tk.BOTH, expand=True, ipady=10, ipadx=10)
        e.bind("<FocusIn>",  lambda _: cf.config(highlightbackground=C["blue"]))
        e.bind("<FocusOut>", lambda _: cf.config(highlightbackground=C["border"]))
        e.bind("<Return>",   lambda _: on_return())
        return cf

    def _dir_name(self):
        """'Downloads' for the usual folder, the full path otherwise."""
        d = os.path.normpath(self._dl_dir)
        if d == os.path.normpath(os.path.join(HOME, "Downloads")):
            return self.t("downloads_folder")
        return d

    # ── MAIN PAGE ──────────────────────────────────────────────────────────

    def _dl_text(self):
        return self.t("download_audio" if self._mode_var.get() == "audio" else "download")

    def _mode_changed(self):
        if not self._running:
            self._dl_btn.config(text="⬇   " + self._dl_text())
            if self._status_state[1] == "st_link_ok":       # keep the hint naming the right button
                self._set_status("idle", "st_link_ok", btn=self._dl_text())

    def _page_main(self):
        p = tk.Frame(self._body, bg=C["bg"]); p.grid_columnconfigure(0, weight=1)

        self._label(p, self.t("step1"), 15, True, wrap=True).grid(row=0, column=0,
                                                                   sticky="ew")
        row = tk.Frame(p, bg=C["bg"]); row.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        row.grid_columnconfigure(1, weight=1)
        _btn(row, self.t("paste"), self._paste, bg=C["blue"], font=(UI, 16, "bold")
             ).grid(row=0, column=0, sticky="ns", ipadx=18, ipady=10)
        self._entry(row, self._url_var, self._start_download
                    ).grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        _btn(row, self.t("clear"), self._clear_url, bg=C["panel2"], fg=C["text"],
             font=(UI, 12)).grid(row=0, column=2, sticky="ns", padx=(8, 0), ipadx=10)

        self._url_lbl = self._label(p, "", 14, True, wrap=True)
        self._url_lbl.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        md = tk.Frame(p, bg=C["bg"]); md.grid(row=3, column=0, sticky="w", pady=(10, 4))
        self._label(md, self.t("step2"), 15, True).pack(side=tk.LEFT, padx=(0, 18))
        self._mode_radios = []
        for val, key in (("video", "mode_video"), ("audio", "mode_audio")):
            rb = tk.Radiobutton(md, text=self.t(key), variable=self._mode_var, value=val,
                           command=self._mode_changed, font=(UI, 14), bg=C["bg"],
                           fg=C["text"], activebackground=C["bg"], selectcolor=C["panel"],
                           anchor="w")
            rb.pack(side=tk.LEFT, padx=(0, 24)); self._mode_radios.append(rb)
        self._dl_btn = _btn(p, "⬇   " + self._dl_text(), self._start_download,
                            bg=C["green"], font=(UI, 22, "bold"))
        self._dl_btn.grid(row=4, column=0, sticky="ew", ipady=12)

        fr = tk.Frame(p, bg=C["bg"]); fr.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        fr.grid_columnconfigure(1, weight=1)
        self._label(fr, self.t("saved_in"), 13, fg=C["muted"]).grid(row=0, column=0, sticky="w")
        self._dir_lbl = self._label(fr, self._dir_name(), 13, True)
        self._dir_lbl.grid(row=0, column=1, sticky="ew", padx=8)
        _btn(fr, self.t("open_folder"), lambda: self._open_folder(self._dl_dir),
             bg=C["panel2"], fg=C["text"], font=(UI, 12)
             ).grid(row=0, column=2, padx=(0, 6), ipadx=10, ipady=4)
        _btn(fr, self.t("change"), self._browse_dir, bg=C["panel2"], fg=C["text"],
             font=(UI, 12)).grid(row=0, column=3, ipadx=10, ipady=4)

        cv = tk.Frame(p, bg=C["bg"]); cv.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        cv.grid_columnconfigure(0, weight=1)
        self._label(cv, self.t("conv_hint"), 13, fg=C["muted"], wrap=True
                    ).grid(row=0, column=0, sticky="ew")
        self._conv_btn = _btn(cv, self.t("convert"), self._convert_mp4, bg=C["panel2"],
                              fg=C["text"], font=(UI, 12))
        self._conv_btn.grid(row=0, column=1, padx=(8, 0), ipadx=10, ipady=4)
        return p

    # ── WEBINAR ROOM PAGE ──────────────────────────────────────────────────

    def _page_room(self):
        p = tk.Frame(self._body, bg=C["bg"]); p.grid_columnconfigure(0, weight=1)
        self._page_top(p, "room_title").grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self._label(p, self.t("room_help"), 13, fg=C["muted"], wrap=True
                    ).grid(row=1, column=0, sticky="ew")
        row = tk.Frame(p, bg=C["bg"]); row.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        row.grid_columnconfigure(1, weight=1)
        _btn(row, self.t("paste"), lambda: self._paste_into(self._room_var), bg=C["blue"],
             font=(UI, 14, "bold")).grid(row=0, column=0, sticky="ns", ipadx=12)
        self._entry(row, self._room_var, self._start_room
                    ).grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self._label(p, self.t("page_video_only"), 13, fg=C["muted"], wrap=True
                    ).grid(row=5, column=0, sticky="ew", pady=(14, 0))
        self._room_btn = _btn(p, "●   " + self.t("room_start"), self._start_room,
                              bg=C["green"], font=(UI, 20, "bold"))
        self._room_btn.grid(row=3, column=0, sticky="ew", pady=(14, 0), ipady=10)
        self._room_stop_btn = _btn(p, "■   " + self.t("room_stop"), self._stop_room,
                                   bg=C["disabled"], font=(UI, 16, "bold"))
        self._room_stop_btn.config(state=tk.DISABLED)
        self._room_stop_btn.grid(row=4, column=0, sticky="ew", pady=(10, 0), ipady=6)
        return p

    def _room_buttons(self, busy):
        """Start only when idle; Stop only while waiting for / recording a room."""
        stop_on = busy and self._room_active
        _recolor(self._room_btn, C["disabled"] if busy else C["green"])
        self._room_btn.config(state=tk.DISABLED if busy else tk.NORMAL)
        _recolor(self._room_stop_btn, C["red"] if stop_on else C["disabled"])
        self._room_stop_btn.config(state=tk.NORMAL if stop_on else tk.DISABLED)

    # ── SCAN PAGE ──────────────────────────────────────────────────────────

    def _page_scan(self):
        p = tk.Frame(self._body, bg=C["bg"])
        p.grid_columnconfigure(0, weight=1); p.grid_rowconfigure(6, weight=1)
        self._page_top(p, "scan_title").grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self._label(p, self.t("page_video_only"), 12, fg=C["muted"], wrap=True
                    ).grid(row=1, column=0, sticky="ew")
        self._label(p, self.t("scan_help"), 13, fg=C["muted"], wrap=True
                    ).grid(row=2, column=0, sticky="ew")

        row = tk.Frame(p, bg=C["bg"]); row.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        row.grid_columnconfigure(1, weight=1)
        _btn(row, self.t("paste"), lambda: self._paste_into(self._page_var), bg=C["blue"],
             font=(UI, 14, "bold")).grid(row=0, column=0, sticky="ns", ipadx=12)
        self._entry(row, self._page_var, self._start_scan
                    ).grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self._scan_btn = _btn(row, self.t("find"), self._start_scan, bg=C["blue"],
                              font=(UI, 14, "bold"))
        self._scan_btn.grid(row=0, column=2, sticky="ns", padx=(10, 0), ipadx=12)

        self._scan_lbl = self._label(p, "", 13, True, wrap=True)
        self._scan_lbl.grid(row=4, column=0, sticky="ew", pady=(8, 4))

        hdr = tk.Frame(p, bg=C["bg"]); hdr.grid(row=5, column=0, sticky="ew", pady=(0, 4))
        hdr.grid_columnconfigure(0, weight=1)     # the hint wraps; the buttons never move
        self._label(hdr, self.t("scan_list_hdr"), 12, fg=C["muted"], wrap=True
                    ).grid(row=0, column=0, sticky="ew")
        _btn(hdr, self.t("open_list"), self._open_list, bg=C["blue"], font=(UI, 11, "bold")
             ).grid(row=0, column=1, padx=(8, 12), ipadx=8, ipady=2)
        _btn(hdr, self.t("tick_all"), lambda: self._scan_list.select_all(True),
             bg=C["panel2"], fg=C["text"], font=(UI, 11)
             ).grid(row=0, column=2, padx=(0, 6), ipadx=8, ipady=2)
        _btn(hdr, self.t("untick_all"), lambda: self._scan_list.select_all(False),
             bg=C["panel2"], fg=C["text"], font=(UI, 11)
             ).grid(row=0, column=3, ipadx=8, ipady=2)
        self._scan_list = CheckListbox(p, self._scan_items)
        self._scan_list.grid(row=6, column=0, sticky="nsew")
        p.grid_rowconfigure(6, weight=1, minsize=80)   # at least two rows visible

        self._dl_sel_btn = _btn(p, "⬇   " + self.t("dl_ticked"), self._download_selected,
                                bg=C["green"], font=(UI, 18, "bold"))
        self._dl_sel_btn.grid(row=7, column=0, sticky="ew", pady=(10, 0), ipady=10)
        return p

    # ── COOKIES PAGE ───────────────────────────────────────────────────────

    def _page_cookies(self):
        p = tk.Frame(self._body, bg=C["bg"])
        p.grid_columnconfigure(0, weight=1); p.grid_rowconfigure(6, weight=1)
        self._page_top(p, "ck_title").grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self._label(p, self.t("ck_help"), 13, fg=C["muted"], wrap=True
                    ).grid(row=2, column=0, sticky="ew")

        wiz = tk.Frame(p, bg=C["panel"], padx=16, pady=10, highlightthickness=1,
                       highlightbackground=C["border"])
        wiz.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        wiz.grid_columnconfigure(1, weight=1)
        for i, (desc, btxt, cmd, col) in enumerate([
                ("ck_step1", "ck_btn1", self._open_extension, C["blue"]),
                ("ck_step2", "ck_btn2", self._open_sites, C["blue"]),
                ("ck_step3", "ck_btn3", self._rescan_cookies, C["green"])]):
            self._label(wiz, f"{i + 1}.", 15, True, bg=C["panel"]
                        ).grid(row=i, column=0, sticky="w", pady=3)
            self._label(wiz, self.t(desc), 13, bg=C["panel"], wrap=True
                        ).grid(row=i, column=1, sticky="ew", padx=10)
            _btn(wiz, self.t(btxt), cmd, bg=col, font=(UI, 12, "bold")
                 ).grid(row=i, column=2, sticky="ew", pady=3, ipadx=10, ipady=3)

        bar = tk.Frame(p, bg=C["bg"]); bar.grid(row=5, column=0, sticky="ew", pady=(10, 4))
        self._label(bar, self.t("ck_files"), 13, True).pack(side=tk.LEFT)
        for key, cmd in (("ck_forget", self._clear_cookies), ("ck_rescan", self._rescan_cookies),
                         ("ck_browse", self._browse_cookies)):
            _btn(bar, self.t(key), cmd, bg=C["panel2"], fg=C["text"], font=(UI, 11)
                 ).pack(side=tk.RIGHT, padx=(6, 0), ipadx=8, ipady=2)

        card = _cardf(p); card.grid(row=6, column=0, sticky="nsew")
        sb = ttk.Scrollbar(card); sb.pack(side=tk.RIGHT, fill=tk.Y, pady=4)
        self._cookie_list = tk.Listbox(card, font=(UI, 12), bg=C["panel"], fg=C["text"],
                                       selectbackground=C["soft_blue"],
                                       selectforeground=C["text"], activestyle="none",
                                       relief=tk.FLAT, bd=0, height=3, yscrollcommand=sb.set)
        self._cookie_list.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        sb.config(command=self._cookie_list.yview)
        self._cookie_list.bind("<<ListboxSelect>>", self._pick_cookie)
        p.grid_rowconfigure(6, weight=1, minsize=64)   # the list never shrinks to nothing
        return p

    # ── DETAILS PAGE (for the helper) ──────────────────────────────────────

    def _page_details(self):
        p = tk.Frame(self._body, bg=C["bg"])
        p.grid_columnconfigure(0, weight=1); p.grid_rowconfigure(6, weight=1)
        self._page_top(p, "dt_title").grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._sys_lbl = tk.Label(p, text="", font=(MONO, 11), fg=C["text"], bg=C["bg"],
                                 anchor=tk.W, justify=tk.LEFT)
        self._sys_lbl.grid(row=2, column=0, sticky="ew")

        opt = tk.Frame(p, bg=C["bg"]); opt.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self._label(opt, self.t("dt_ssl"), 12, True).grid(row=0, column=0, sticky="w")
        modes = ["auto", "strict", "skip"]
        cb = ttk.Combobox(opt, values=[self.t("ssl_" + m) for m in modes], state="readonly",
                          width=34, font=(UI, 12), style="D.TCombobox")
        cb.current(modes.index(self._ssl_mode))
        cb.bind("<<ComboboxSelected>>",
                lambda _: setattr(self, "_ssl_mode", modes[cb.current()]))
        cb.grid(row=0, column=1, sticky="w", padx=8)
        tk.Checkbutton(opt, text=self.t("dt_yt"), variable=self._yt_nocookie, font=(UI, 12),
                       bg=C["bg"], fg=C["text"], selectcolor=C["panel"],
                       activebackground=C["bg"], activeforeground=C["text"],
                       relief=tk.FLAT, bd=0, highlightthickness=0
                       ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        btns = tk.Frame(p, bg=C["bg"]); btns.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        _btn(btns, self.t("dt_update"), self._force_update, bg=C["panel2"], fg=C["text"],
             font=(UI, 12)).pack(side=tk.LEFT, ipadx=10, ipady=4)
        self._ffmpeg_btn = _btn(btns, self.t("dt_ffmpeg"), self._install_ffmpeg,
                                bg=C["panel2"], fg=C["text"], font=(UI, 12))

        top = tk.Frame(p, bg=C["bg"]); top.grid(row=5, column=0, sticky="ew", pady=(14, 4))
        self._label(top, self.t("dt_log"), 13, True).pack(side=tk.LEFT)
        _btn(top, self.t("dt_clear_log"), self._clear_log, bg=C["panel2"], fg=C["text"],
             font=(UI, 11)).pack(side=tk.RIGHT, ipadx=8)
        card = _cardf(p); card.grid(row=6, column=0, sticky="nsew")
        card.grid_rowconfigure(0, weight=1); card.grid_columnconfigure(0, weight=1)
        self._log_box = tk.Text(card, font=(MONO, 10), bg=C["panel"], fg=C["text"],
                                insertbackground=C["text"], relief=tk.FLAT, bd=0, height=6,
                                wrap=tk.WORD, state=tk.DISABLED, padx=10, pady=6)
        self._log_box.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(card, orient="vertical", command=self._log_box.yview)
        vsb.grid(row=0, column=1, sticky="ns", pady=4)
        self._log_box["yscrollcommand"] = vsb.set
        for tg, fg in [("ok", C["green_text"]), ("err", C["red"]), ("info", C["blue"]),
                       ("warn", C["orange"]), ("plain", C["muted"])]:
            self._log_box.tag_config(tg, foreground=fg)
        return p

    # ── STATUS PANEL (outside the pages — never clipped) ───────────────────

    STATUS_FG = {"idle": "text", "busy": "blue", "ok": "green_text", "warn": "orange",
                 "err": "red"}

    def _statuspanel(self):
        w = tk.Frame(self, bg=C["panel"], padx=16, pady=12, highlightthickness=1,
                     highlightbackground=C["border"])
        w.grid_columnconfigure(0, weight=1)
        self._st_main = self._label(w, "", 16, True, bg=C["panel"], wrap=True)
        self._st_main.grid(row=0, column=0, sticky="ew")
        self._st_sub = self._label(w, "", 13, fg=C["muted"], bg=C["panel"])
        self._st_sub.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self._st_btn = _btn(w, "", None, bg=C["blue"], font=(UI, 13, "bold"))
        self._st_btn.grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0),
                          ipadx=12, ipady=6)
        self._st_btn.grid_remove()
        ttk.Progressbar(w, variable=self._prog, maximum=100,
                        style="Big.Horizontal.TProgressbar"
                        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        return w

    def _actions(self):
        return {"folder":  (self.t("open_folder"), lambda: self._open_folder(self._dl_dir)),
                "cookies": (self.t("nav_cookies"), lambda: self._show("cookies")),
                "update":  (self.t("act_update"), self._force_update),
                "ffmpeg":  (self.t("act_install"), self._install_ffmpeg),
                "details": (self.t("nav_details"), lambda: self._show("details")),
                "convfolder": (self.t("open_folder"), lambda: self._open_folder(
                    os.path.dirname(self._last_conv) if self._last_conv else self._dl_dir))}

    def _set_status(self, kind, key, action=None, sub="", **kw):
        """The one place the user reads what is happening. Stored as keys, so it
        can be shown again in the other language."""
        self._status_state = (kind, key, action, kw)
        icon = {"ok": "✓  ", "warn": "⚠  ", "err": "✗  "}.get(kind, "")
        self._st_main.config(text=icon + self.t(key, **kw), fg=C[self.STATUS_FG[kind]])
        self._st_sub.config(text=sub)
        if sub: self._st_sub.grid()             # no empty line when there is nothing to say
        else:   self._st_sub.grid_remove()
        if action:
            label, cmd = self._actions()[action]
            self._st_btn.config(text=label, command=cmd)
            self._st_btn.grid()
        else:
            self._st_btn.grid_remove()

    def _time_left(self, eta):
        if eta is None:
            return ""
        if eta < 60:
            return self.t("left_lt_min")
        n = int(round(eta / 60))
        unit = (ru_plural(n, "минута", "минуты", "минут") if self._lang == "ru"
                else "minute" if n == 1 else "minutes")
        return self.t("left_min", n=n, unit=unit)

    # ── LOG (on the Details page) ──────────────────────────────────────────

    def _log(self, msg, tag="plain"):
        text = clean(msg)
        self._log_lines.append((text, tag))
        del self._log_lines[:-2000]
        self._log_insert(text, tag)

    def _log_insert(self, text, tag):
        self._log_box.config(state=tk.NORMAL)
        self._log_box.insert(tk.END, text + "\n", tag)
        self._log_box.see(tk.END); self._log_box.config(state=tk.DISABLED)

    def _clear_log(self):
        self._log_lines.clear()
        self._log_box.config(state=tk.NORMAL); self._log_box.delete("1.0", tk.END)
        self._log_box.config(state=tk.DISABLED)

    # ── LANGUAGE ───────────────────────────────────────────────────────────

    def _switch_lang(self):
        if self._running or self._scanning:
            self._set_status("warn", "wait_lang"); return
        self._lang = "ru" if self._lang == "en" else "en"
        save_settings(lang=self._lang)
        for w in self.winfo_children():
            w.destroy()
        self._build()

    # ══════════════════════════════════════════════════════════
    #  COOKIES
    # ══════════════════════════════════════════════════════════

    def _cookie_watcher(self):
        dirs = [d for d in COOKIE_DIRS if os.path.isdir(d)]
        for d in dirs:
            for p in glob.glob(os.path.join(d, "*.txt")):
                self._watch_seen.add(os.path.realpath(p))
        while self._watching:
            time.sleep(2)
            try:
                for d in dirs:
                    for p in glob.glob(os.path.join(d, "*.txt")):
                        rp = os.path.realpath(p)
                        if rp in self._watch_seen: continue
                        self._watch_seen.add(rp); time.sleep(0.6)
                        if valid_cookiefile(rp):
                            self.after(0, lambda x=rp: self._auto_import(x))
            except Exception:
                pass

    def _auto_import(self, path):
        self._cookies_file = path
        doms = cookie_domains(path)
        self._log(f"Cookies imported: {os.path.basename(path)} ({len(doms)} sites)", "ok")
        self._rescan_cookies()
        if not self._running:
            self._set_status("ok", "ck_imported", name=os.path.basename(path))

    def _open_extension(self):
        webbrowser.open(CHROME_EXT)
        self._log("Opened the add-on page.", "info")

    def _open_sites(self):
        d = tk.Toplevel(self); d.title(self.t("nav_cookies"))
        d.configure(bg=C["bg"], padx=30, pady=16); d.transient(self); d.grab_set()
        self._label(d, self.t("sites_title"), 15, True).pack(pady=(0, 12))
        for name, url in SITES:
            _btn(d, self.t("sites_open", name=name), lambda u=url: webbrowser.open(u),
                 bg=C["blue"], font=(UI, 13, "bold")).pack(fill=tk.X, pady=4, ipady=8)
        _btn(d, self.t("close"), d.destroy, bg=C["panel2"], fg=C["text"],
             font=(UI, 12)).pack(pady=(14, 0), ipadx=24, ipady=5)

    def _rescan_cookies(self):
        self._cookie_files = discover_cookies()
        self._auto_cookie = self._cookie_files[0][0] if self._cookie_files else ""
        self._refresh_cookie_list()
        self._startup_report(quiet=True)

    def _refresh_cookie_list(self):
        self._cookie_list.delete(0, tk.END)
        if not self._cookie_files:
            self._cookie_list.insert(tk.END, self.t("ck_list_none"))
            self._cookie_list.itemconfig(0, fg=C["muted"]); return
        act = self._cookies_file or self._auto_cookie
        for p, mt, doms in self._cookie_files:
            key = [d for d in doms if any(k in d for k in
                   ("youtube", "vk.", "vimeo", "facebook", "instagram"))]
            self._cookie_list.insert(
                tk.END, f" {'►' if p == act else '  '} {os.path.basename(p)[:28]}   ·   "
                        f"{self.t('ck_sites', n=len(doms))}   ·   "
                        f"{time.strftime('%d.%m.%Y', time.localtime(mt))}   "
                        f"{', '.join(key[:3])}")
            if p == act: self._cookie_list.itemconfig(tk.END, fg=C["green_text"])

    def _pick_cookie(self, _=None):
        s = self._cookie_list.curselection()
        if s and self._cookie_files and s[0] < len(self._cookie_files):
            self._cookies_file = self._cookie_files[s[0]][0]
            self._log(f"Using {os.path.basename(self._cookies_file)}", "info")
            self._rescan_cookies()

    def _clear_cookies(self):
        if not (self._cookies_file or self._auto_cookie):
            return
        if messagebox.askyesno(self.t("ck_forget"), self.t("ck_forget_q"), parent=self):
            self._cookies_file = ""; self._cookie_files = []; self._auto_cookie = ""
            self._refresh_cookie_list()
            self._startup_report(quiet=True)
            self._log("Cookies cleared", "warn")

    def _browse_cookies(self):
        p = filedialog.askopenfilename(parent=self, title=self.t("ck_pick"),
                                       initialdir=os.path.join(HOME, "Downloads"),
                                       filetypes=[("Cookies", "*.txt"), ("All", "*.*")])
        if p:
            if not valid_cookiefile(p):
                messagebox.showwarning(self.t("ck_title"), self.t("ck_bad_file"),
                                       parent=self); return
            self._cookies_file = p
            self._log(f"Cookies loaded: {os.path.basename(p)}", "info")
            self._rescan_cookies()

    # ══════════════════════════════════════════════════════════
    #  OPTIONS + ATTEMPT CHAIN
    # ══════════════════════════════════════════════════════════

    def _skip_ssl(self): return self._ssl_mode == "skip"

    def _ssl_ctx(self):
        if self._skip_ssl():
            c = ssl.create_default_context()
            c.check_hostname = False; c.verify_mode = ssl.CERT_NONE
            return c
        return ssl.create_default_context()

    def _base_opts(self, out_dir=None, referer=None, info_only=False, audio=False):
        o = dict(quiet=True, no_warnings=True, socket_timeout=30,
                 http_headers={"User-Agent": UA})
        if referer: o["http_headers"]["Referer"] = referer
        if self._skip_ssl(): o["nocheckcertificate"] = True
        elif self._ssl_mode == "auto": o["compat_opts"] = {"no-certifi"}
        if info_only: return o
        o["format"]  = FORMAT_MERGE if self._ffmpeg else FORMAT_SINGLE
        o["outtmpl"] = os.path.join(out_dir or self._dl_dir, "%(title).80s.%(ext)s")
        if self._ffmpeg:
            o["ffmpeg_location"] = self._ffmpeg
            o["merge_output_format"] = "mp4"
        if audio and self._ffmpeg:          # sound only: best audio stream -> MP3 (192 kbit/s)
            o["format"] = "bestaudio/best"
            o.pop("merge_output_format", None)
            o["postprocessors"] = [{"key": "FFmpegExtractAudio",
                                    "preferredcodec": "mp3", "preferredquality": "192"}]
        return o

    def _cookie_chain(self, url="") -> list:
        host = host_of(url)
        cands = []
        if self._cookies_file and os.path.isfile(self._cookies_file):
            cands.append(self._cookies_file)
        cands += [p for p, _, _ in self._cookie_files if p not in cands]

        scored = []
        for p in cands:
            doms = cookie_domains(p)
            if is_vk(url):
                # any VK domain counts — we widen the session across them below
                hit = any(d in VK_HOSTS for d in doms)
            else:
                hit = any(host and (host in d or d in host) for d in doms)
            scored.append((0 if hit else 1, p, hit))

        chain = []
        for _, p, hit in sorted(scored, key=lambda x: x[0]):
            use = widen_vk_cookies(p) if is_vk(url) else p
            tag = "✓" if hit else ""
            if use != p:
                tag += " (VK session copied across domains)"
            chain.append((f"cookies[{os.path.basename(p)}]{tag}", {"cookiefile": use}))

        if firefox_available():
            chain.append(("Firefox", {"cookiesfrombrowser": ("firefox", None, None, None)}))
        chain.append(("no cookies", {}))

        # YouTube: cookies make yt-dlp pick the broken tv_downgraded client,
        # so put the cookie-free attempt FIRST for youtube URLs.
        if is_youtube(url) and self._yt_nocookie.get():
            chain = [("no cookies", {})] + [c for c in chain if c[0] != "no cookies"]
        return chain

    SOFT = ("could not copy", "cookie database", "could not find", "unsupported browser",
            "failed to decrypt", "logged-in", "login", "sign in", "private", "403",
            "forbidden", "members only", "not a bot", "confirm you",
            "page needs to be reloaded", "unplayable", "no video formats",
            "requested format is not available", "sabr")

    def _attempt(self, fn, base, url="", note=True):
        """
        Walk (url variant × cookie source × player client) until one works.
        fn is called as fn(opts, url) so a site that answers on several hosts
        (VK) can be retried under each.
        """
        client_sets = YT_CLIENT_SETS if is_youtube(url) else [None]
        variants = url_variants(url) if url else [url]
        last = None
        for u in variants:
            for desc, frag in self._cookie_chain(u):
                for cs in client_sets:
                    o = dict(base); o.update(frag)
                    if cs:
                        o["extractor_args"] = {"youtube": {"player_client": list(cs)}}
                    try:
                        res = fn(o, u)
                        label = desc + (f" + {'/'.join(cs)}" if cs else "")
                        if u != url:
                            label += f"  [via {host_of(u)}]"
                        if note:
                            self.after(0, lambda l=label:
                                       self._log(f"   ✓ worked via {l}", "ok"))
                        return res, label
                    except Exception as e:
                        last = e
                        if any(k in clean(e).lower() for k in self.SOFT):
                            continue
                        if len(variants) > 1:
                            break      # try the next host rather than giving up
                        raise
        raise last if last else RuntimeError("all attempts failed")

    def _diagnose(self, err):
        """Map an error to (message key, 'warn'|'err', action) for the user.
        The raw error goes to the log for the helper."""
        e = clean(err).lower()
        if "page needs to be reloaded" in e or "unplayable" in e:
            return "d_youtube", "warn", "update"
        if "could not copy" in e or "cookie database" in e:
            return "d_browser", "warn", "cookies"
        if "not a bot" in e or "confirm you" in e:
            return "d_bot", "warn", "cookies"
        if "certificate" in e:
            return "d_cert", "warn", "details"
        if "ffmpeg is not installed" in e:
            return "d_ffmpeg", "warn", "ffmpeg"
        if any(k in e for k in ("logged-in", "login", "sign in", "private", "403")):
            return "d_private", "warn", "cookies"
        if "no video players" in e:
            return "d_no_player", "warn", "cookies"
        if "unsupported url" in e or "unable to extract" in e:
            return "d_not_video", "err", None
        if any(k in e for k in ("timed out", "getaddrinfo", "urlopen error",
                                "connection refused", "connection reset",
                                "network is unreachable", "failed to resolve")):
            return "d_network", "err", None
        return "d_other", "err", "details"

    # ══════════════════════════════════════════════════════════
    #  DOWNLOAD
    # ══════════════════════════════════════════════════════════

    def _read_clip(self):
        try:
            return self.clipboard_get().strip()
        except tk.TclError:
            return ""

    @staticmethod
    def _is_link(s):
        return bool(re.match(r"https?://\S+$", s or "")) and len(s) < 2000

    def _paste(self):
        clip = self._read_clip()
        if not self._is_link(clip):
            self._set_status("warn", "not_link"); return
        self._last_clip = clip
        self._url_var.set(clip)

    def _paste_into(self, var):
        clip = self._read_clip()
        if not self._is_link(clip):
            self._set_status("warn", "not_link"); return
        var.set(clip)

    def _on_activate(self, e):
        if e.widget is self:
            self.after(200, self._auto_paste)

    def _auto_paste(self):
        """A link copied in the browser is filled in by itself when the user
        comes back to the window. Only web addresses, only new ones, never
        while downloading — and it still waits for the Download button."""
        if self._page != "main" or self._running:
            return
        cur = self._url_var.get().strip()
        if cur and cur != self._last_clip:
            return                      # something typed by hand — leave it alone
        clip = self._read_clip()
        if clip != self._last_clip and self._is_link(clip):
            self._last_clip = clip
            self._url_var.set(clip)
            self._log(f"Link taken from the clipboard: {clip[:100]}", "info")

    def _clear_url(self):
        self._last_clip = self._read_clip()     # don't paste the same link straight back
        self._url_var.set(""); self._url_state = None; self._render_url_info()
        if not self._running:
            self._set_status("idle", "st_ready")

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self._dl_dir, parent=self,
                                    title=self.t("pick_folder"))
        if d:
            self._dl_dir = d
            self._dir_lbl.config(text=self._dir_name())
            save_settings(download_dir=d)          # remembered next launch
            self._log(f"Saving to: {d}", "info")

    def _url_changed(self, *_):
        if self._url_check_id: self.after_cancel(self._url_check_id)
        if self._url_var.get().strip().startswith("http"):
            self._url_state = ("checking",)
            self._url_check_id = self.after(900, self._check_url)
        else:
            self._url_state = None
        self._render_url_info()

    def _render_url_info(self):
        s = self._url_state
        if not s:
            self._url_lbl.config(text="")
        elif s[0] == "checking":
            self._url_lbl.config(text=self.t("checking"), fg=C["muted"])
        elif s[0] == "ok":
            self._url_lbl.config(text=self.t("found", title=s[1]) + s[2], fg=C["green_text"])
        else:
            self._url_lbl.config(text="⚠  " + self.t(s[1]),
                                 fg=C["orange"] if s[2] == "warn" else C["red"])

    def _check_url(self):
        u = self._url_var.get().strip()
        if u and not self._url_checking:
            self._url_checking = True
            threading.Thread(target=self._url_worker, args=(u,), daemon=True).start()

    def _url_worker(self, url):
        def probe(o, u):
            with yt_dlp.YoutubeDL(o) as y: return y.extract_info(u, download=False)
        try:
            meta = {}
            i, _ = self._with_embed(probe, lambda ref: self._base_opts(referer=ref,
                                                                       info_only=True),
                                    url, note=False, meta=meta)
            n = meta["count"]
            title = meta["title"] or i.get("title") or "?"
            # a GetCourse hash, or several videos (part 1's title would mislead):
            # show the page's own name instead
            if n > 1 or re.fullmatch(r"[0-9a-f]{32}", title):
                title = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1] or title
            parts = [host_of(url) if n else host_of(i.get("webpage_url") or url),
                     _dur(i.get("duration", 0)) if n <= 1 else self.t("n_videos", n=n)]
            det = "    ·    ".join(x for x in parts if x)
            self.after(0, lambda: self._url_ok(title, ("\n" + det) if det else ""))
        except Exception as e:
            self.after(0, lambda err=str(e): self._url_fail(err))

    def _url_ok(self, title, det):
        self._url_checking = False
        self._url_state = ("ok", title, det); self._render_url_info()
        if not self._running:
            self._set_status("idle", "st_link_ok", btn=self._dl_text())

    def _url_fail(self, err):
        self._url_checking = False
        key, tag, _ = self._diagnose(err)
        self._log(f"Link check failed: {clean(err)[:200]}", "warn")
        self._url_state = ("fail", key, tag); self._render_url_info()

    def _hook(self, d):
        """yt-dlp progress — runs in the worker thread, so only post to the GUI."""
        if d["status"] == "downloading":
            now = time.time()
            if now - self._last_hook < 0.25:
                return
            self._last_hook = now
            done = d.get("downloaded_bytes") or 0
            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            pct = min(100, int(done * 100 / tot)) if tot else None
            eta = d.get("eta")
            self.after(0, lambda: self._show_progress(pct, eta))
        elif d["status"] == "finished":
            name = os.path.basename(d.get("filename", ""))
            aud = self._audio_run
            self.after(0, lambda: (self._prog.set(100),
                                   self._set_status("busy", "st_finishing_audio" if aud
                                                    else "st_finishing"),
                                   self._log(f"✔  Downloaded: {name} - now making the MP3 file"
                                             if aud else f"✔  Saved: {name}", "ok")))

    def _show_progress(self, pct, eta):
        if not self._running:
            return
        if pct is not None:
            self._prog.set(pct)
        sub = self._time_left(eta)
        if self._batch:
            i, n = self._batch
            self._set_status("busy", "st_batch", sub=sub, i=i, n=n,
                             pct=pct if pct is not None else "...")
        elif pct is None:
            self._set_status("busy", "st_downloading_nopct", sub=sub)
        else:
            self._set_status("busy", "st_downloading", sub=sub, pct=pct)

    def _set_busy(self, busy, label="downloading"):
        """Grey out both download buttons (and Convert) while anything is running."""
        for b, key in ((self._dl_btn, self._dl_text()), (self._dl_sel_btn, self.t("dl_ticked"))):
            if busy:
                _recolor(b, C["disabled"]); b.config(state=tk.DISABLED)
            else:
                _recolor(b, C["green"])
                b.config(state=tk.NORMAL, text="⬇   " + key)
        self._conv_btn.config(state=tk.DISABLED if busy else tk.NORMAL)
        for rb in self._mode_radios:                # the mode cannot change during a job
            rb.config(state=tk.DISABLED if busy else tk.NORMAL)
        if busy:
            self._dl_btn.config(text="⏳   " + self.t(label))
        self._room_buttons(busy)

    # ── WEBINAR ROOM: record until the end, then MP4 ───────────────────────

    def _start_room(self):
        link = self._room_var.get().strip()
        if self._running:
            self._set_status("warn", "busy"); return
        if not link:
            self._set_status("warn", "no_link"); return
        try:
            room_split_link(link)
        except RoomError as e:
            self._set_status("warn", e.key); return
        if not self._ffmpeg:                       # needed for the MP4 at the end
            self._set_status("warn", "d_ffmpeg", action="ffmpeg"); return
        self._running = True; self._room_active = True
        self._room_stop = threading.Event()
        self._set_busy(True, "recording")
        self._prog.set(0); self._set_status("busy", "st_room_signin")
        self._log("─" * 70); self._log("Webinar room: starting", "info")
        threading.Thread(target=self._room_worker, args=(link, self._room_stop),
                         daemon=True).start()

    def _stop_room(self):
        if self._room_active and not self._room_stop.is_set():
            self._room_stop.set()
            self._set_status("busy", "st_room_stopping")

    def _room_end(self, key, kind="warn", **kw):
        self._running = False; self._room_active = False
        self._set_busy(False); self._prog.set(0)
        self._set_status(kind, key, **kw)

    def _room_fail(self, key, **info):
        try:
            text = T["en"][key].format(**info)
        except Exception:
            text = key
        self._log("✘  Webinar room: " + text, "err")
        self._room_end(key, "err", **info)

    def _room_progress(self, secs):
        """The status line changes at most every 3 seconds (a calm screen)."""
        now = time.time()
        if self._room_active and not self._room_stop.is_set() \
                and (secs == 0 or now - self._room_shown >= 3):
            self._room_shown = now
            self._set_status("busy", "st_room_rec", t=fmt_hms(secs))

    def _room_converting(self):
        self._room_active = False
        self._room_buttons(True)
        self._prog.set(0); self._set_status("busy", "st_room_converting")

    def _room_done_note(self, res, length_ok, real):
        """How the recording ended -> (status kind, wording key, values)."""
        t = fmt_hms(real or res["seconds"])
        if res["failed"]:
            return "warn", "st_room_done_skipped", {"n": res["failed"]}
        if not length_ok:
            return "warn", "st_room_done_check", {"t": t}
        if res["reason"] == "stalled":
            return "warn", "st_room_done_stalled", {"t": t}
        return "ok", "st_room_done_kept", {"t": t}      # becomes st_room_done once the .ts is removed

    def _room_clean_ts(self, ts, mp4, say):
        """After a clean recording: if the MP4 is as long as the .ts, remove the .ts
        (two files with one name confuse the main user). Anything doubtful keeps it."""
        note = self._done_note
        if not note or note[0] != "ok":
            return
        a, b = self._media_seconds(ts), self._media_seconds(mp4)
        if a and b and abs(a - b) <= max(2.0, a * 0.01) and os.path.getsize(mp4) > 0:
            try:
                os.remove(ts)
            except OSError as e:
                say(f"   Could not remove the .ts file: {clean(e)[:100]}", "warn"); return
            say("   MP4 checked (same length as the recording); the .ts file was removed", "ok")
            self._done_note = ("ok", "st_room_done", note[2])
        else:
            say(f"   MP4 length {fmt_hms(b)} vs recording {fmt_hms(a)}: the .ts file was kept", "warn")

    @staticmethod
    def _keep_awake(on):
        """Ask Windows not to go to sleep (the call belongs to the calling thread)."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(
                0x80000000 | (0x00000001 if on else 0))      # ES_CONTINUOUS [| ES_SYSTEM_REQUIRED]
        except Exception:
            pass

    def _media_seconds(self, path):
        try:
            r = subprocess.run([self._ffmpeg, "-hide_banner", "-i", path], capture_output=True,
                               text=True, errors="replace", timeout=120, creationflags=NO_WINDOW)
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
            return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0
        except Exception:
            return 0.0

    def _room_worker(self, link, stop):
        self._keep_awake(True)                  # no sleep while waiting, recording or converting
        try:
            self._room_worker_body(link, stop)
        finally:
            self._keep_awake(False)

    def _room_worker_body(self, link, stop):
        say = lambda m, tag="plain": self.after(0, lambda: self._log(m, tag))
        out = ""
        try:
            room, init = room_signin(link)
            say("   Signed in to the room")
            if stop.is_set():                                  # Stop was pressed while signing in
                self.after(0, lambda: self._room_end("st_room_cancel")); return
            self.after(0, lambda: self._set_status("busy", "st_room_wait"))
            origin = "https://" + urllib.parse.urlparse(room).netloc
            got = room_wait_for_stream(init, origin, stop)
            if got is None:
                self.after(0, lambda: self._room_end("st_room_cancel")); return
            vt, ref, title = got
            say(f"   On air. Video type: {vt or '(none)'}")
            url = stream_from_setting(vt, ref)
            say("   Stream: " + urllib.parse.urlparse(url).netloc + urllib.parse.urlparse(url).path)
            stem = safe_name(title) or "webinar"
            out = unique_path(self._dl_dir, stem, ".ts")
            say("   Recording to: " + os.path.basename(out))
            self.after(0, lambda: self._room_progress(0))
            rec = RoomRecorder(url, out, stop, log=say,
                               progress=lambda n, s, f: self.after(0, lambda: self._room_progress(s)))
            res = rec.run()
        except RoomError as e:
            if stop.is_set():                              # the user already said stop: no red error
                self.after(0, lambda: self._room_end("st_room_cancel")); return
            self.after(0, lambda e=e: self._room_fail(e.key, **e.info)); return
        except Exception as e:
            say("   Unexpected error: " + clean(e)[:200], "err")
            self.after(0, lambda: self._room_fail("room_err_unexpected")); return
        say(f"   Recording finished ({res['reason']}): {res['segments']} segments, "
            f"{fmt_hms(res['seconds'])}, {res['failed']} failed", "info")
        if res["reason"] == "disk":                    # a write error is not an internet problem
            if res["segments"]:
                name = os.path.basename(out)
                self.after(0, lambda: self._room_fail("room_err_disk_part", name=name))
            else:
                try: os.remove(out)
                except OSError: pass
                self.after(0, lambda: self._room_fail("room_err_disk"))
            return
        if res["segments"] == 0:
            try: os.remove(out)
            except OSError: pass
            if res["reason"] == "stopped":             # stopped before any video: not an error
                self.after(0, lambda: self._room_end("st_room_cancel"))
            else:
                self.after(0, lambda: self._room_fail("st_room_nothing"))
            return
        self.after(0, self._room_converting)
        mp4 = unique_path(self._dl_dir, os.path.splitext(os.path.basename(out))[0], ".mp4")
        real = self._media_seconds(out)             # the file's length must match the segments
        length_ok = not (real and abs(real - res["seconds"]) > max(5.0, res["seconds"] * 0.01))
        if length_ok:
            say(f"   Length check OK: {fmt_hms(real or res['seconds'])}", "ok")
        else:
            say(f"   WARNING: file length {fmt_hms(real)} differs from the segments' "
                f"{fmt_hms(res['seconds'])}", "warn")
        self._done_note = self._room_done_note(res, length_ok, real)
        self._convert_worker(out, mp4, after_ok=lambda m: self._room_clean_ts(out, m, say))

    # ── CONVERT TO MP4 ─────────────────────────────────────────────────────

    def _convert_mp4(self):
        """Turn a recording (.mkv / .ts ...) into .mp4 without re-encoding, so a
        live-webinar recording plays everywhere. The original is never touched
        and an existing file is never overwritten."""
        if self._running:
            self._set_status("warn", "busy"); return
        if not self._ffmpeg:
            self._set_status("warn", "d_ffmpeg", action="ffmpeg"); return
        src = filedialog.askopenfilename(
            parent=self, title=self.t("conv_pick"), initialdir=self._dl_dir,
            filetypes=[(self.t("conv_types"), "*.mkv *.ts *.flv *.webm *.mov *.avi *.m4v *.wmv"),
                       ("All", "*.*")])
        if not src:
            return
        stem = os.path.splitext(src)[0]
        out, n = stem + ".mp4", 1
        while os.path.exists(out):                # never overwrite (also covers an .mp4 source)
            out = f"{stem} ({n}).mp4"; n += 1
        self._running = True
        self._set_busy(True, "converting")
        self._prog.set(0); self._set_status("busy", "st_converting_nopct")
        self._log("─" * 70); self._log(f"Convert to MP4: {os.path.basename(src)}", "info")
        threading.Thread(target=self._convert_worker, args=(src, out), daemon=True).start()

    def _convert_worker(self, src, out, after_ok=None):
        ff = self._ffmpeg
        total = 0.0
        try:                                       # length of the video, from ffmpeg's own banner
            r = subprocess.run([ff, "-hide_banner", "-i", src], capture_output=True, text=True,
                               errors="replace", timeout=60, creationflags=NO_WINDOW)
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
            if m:
                total = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
        except Exception:
            pass
        tmp = out + ".part"
        err, last = "", 0.0
        # 1st try: copy picture and sound untouched (fast, no loss);
        # 2nd try: copy the picture, re-encode only the sound (e.g. Opus -> AAC)
        for audio in (["-c:a", "copy"], ["-c:a", "aac", "-b:a", "160k"]):
            cmd = [ff, "-hide_banner", "-nostats", "-loglevel", "error", "-progress", "pipe:1",
                   "-i", src, "-map", "0:v:0?", "-map", "0:a:0?", "-c:v", "copy", *audio,
                   "-movflags", "+faststart", "-f", "mp4", "-y", tmp]
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, errors="replace", creationflags=NO_WINDOW)
                for line in p.stdout:
                    if total and line.startswith(("out_time_us=", "out_time_ms=")):
                        try:
                            pct = min(99, int(int(line.split("=")[1]) / 1e6 * 100 / total))
                        except ValueError:
                            continue
                        if time.time() - last > 0.4:
                            last = time.time()
                            self.after(0, lambda v=pct: self._conv_progress(v))
                err = p.stderr.read(); code = p.wait()
            except Exception as e:
                err, code = str(e), 1
            if code == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
                try:
                    os.replace(tmp, out)
                except OSError as e:
                    err, code = str(e), 1
                else:
                    if after_ok:                           # runs here, before the result is shown
                        try: after_ok(out)
                        except Exception as e: self.after(0, lambda e=e: self._log(f"   after-conversion step failed: {clean(e)[:120]}", "warn"))
                    self.after(0, lambda: self._conv_done(out)); return
        try:
            if os.path.exists(tmp): os.remove(tmp)
        except OSError:
            pass
        self.after(0, lambda e=err: self._conv_fail(e))

    def _conv_progress(self, pct):
        if self._running:
            self._prog.set(pct); self._set_status("busy", "st_converting", pct=pct)

    def _conv_done(self, out):
        self._running = False
        self._set_busy(False); self._prog.set(100)
        self._last_conv = out
        self._log(f"✔  Converted: {os.path.basename(out)}", "ok")
        note, self._done_note = self._done_note, None
        if note:                                   # a room recording says how it ended
            self._set_status(note[0], note[1], action="convfolder", **note[2])
        else:
            self._set_status("ok", "st_converted", action="convfolder")

    def _conv_fail(self, err):
        self._done_note = None
        self._running = False
        self._set_busy(False); self._prog.set(0)
        self._log("✘  Conversion failed: " + clean(err)[:300], "err")
        self._set_status("err", "st_conv_failed", action="details")

    def _start_download(self):
        url = self._url_var.get().strip()
        if not url:
            self._set_status("warn", "no_link"); return
        if not url.startswith("http"):
            self._set_status("warn", "not_link"); return
        if self._running:
            self._set_status("warn", "busy"); return
        audio = self._mode_var.get() == "audio"
        if audio and not self._ffmpeg:              # the MP3 is made by ffmpeg
            self._set_status("warn", "d_ffmpeg_audio", action="ffmpeg"); return
        self._audio_run = audio
        self._running = True; self._batch = None
        self._set_busy(True)
        self._prog.set(0); self._set_status("busy", "st_starting"); self._log("─" * 70)
        threading.Thread(target=self._dl_worker, args=(url,), daemon=True).start()

    def _cached(self, key, make, ttl=90):
        """Keep a lookup for a short time: the link check and the download that
        follows it ask for the same page and the same players."""
        hit = self._lookup_cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        val = make()
        if val:
            self._lookup_cache[key] = (time.time(), val)
        return val

    def _find_embeds(self, page_url):
        """Players in a page the extractors don't know (see find_players).
        The page is fetched with this site's cookies: course pages show their
        players only to a logged-in user. A failed fetch is logged."""
        def fetch():
            hdrs = {"User-Agent": UA}
            ck = self._cookies_file or self._auto_cookie
            if ck and os.path.isfile(ck):
                h = cookie_header_for(ck, page_url)
                if h:
                    hdrs["Cookie"] = h
            try:
                req = urllib.request.Request(page_url, headers=hdrs)
                with urllib.request.urlopen(req, timeout=25, context=self._ssl_ctx()) as r:
                    return find_players(r.read().decode("utf-8", errors="ignore"))
            except Exception as e:
                self.after(0, lambda err=clean(e)[:160]:
                           self._log(f"   Could not read the page: {err}", "warn"))
                return []
        return self._cached(("page", page_url), fetch)

    def _resolve_player(self, target, referer):
        """(address, title) to give yt-dlp for a player address. The one place
        that knows the Kinescope trap: yt-dlp takes the stream address out of
        the player page without decoding its HTML / JSON escapes, so the
        signature is wrong and Kinescope answers 403. A Kinescope embed is
        therefore replaced by its decoded stream address. Anything else is
        returned unchanged."""
        if "kinescope.io/embed/" not in target:
            return target, ""
        got = self._cached(("kin", target, referer), lambda: kinescope_stream(
            target, referer or "https://kinescope.io/", self._ssl_ctx()))
        if not got:
            self.after(0, lambda: self._log("   Kinescope: no stream address in the player "
                                            "page - trying the player address itself", "warn"))
            return target, ""
        self.after(0, lambda t=got[1]: self._log(f"   Kinescope: {t}", "info"))
        return got

    def _with_embed(self, fn, make_base, url, note=True, meta=None):
        """_attempt on the address; if the site isn't supported, retry with the
        players embedded in the page (all of them), sending the page as Referer.
        Returns the first success. `meta` (a dict, optional) receives
        meta["count"] = players found, meta["title"] = the first one's name,
        meta["failed"] = players that failed. A player that fails does not stop
        the others; the error is raised only when none worked."""
        meta = meta if meta is not None else {}
        meta["count"] = 0; meta["title"] = ""; meta["failed"] = 0
        if "kinescope.io/embed/" in url:                 # a player address pasted directly
            embs, ref = [(url, "kinescope")], None
        else:
            try:
                return self._attempt(fn, make_base(None), url, note)
            except Exception as e:
                if "unsupported url" not in clean(e).lower() or find_players(url):
                    raise
                embs, ref = self._find_embeds(url), referer_for(url)
                if not embs:
                    # no login (private lesson) or not a video page: _diagnose says both
                    raise RuntimeError("no video players found in the page") from e
                self.after(0, lambda: self._log(f"   {len(embs)} player(s) found in the page",
                                                "info"))
        meta["count"] = len(embs)
        # GetCourse's own "title" is a hash, and several parts would overwrite
        # each other's names: name them after the page instead
        slug = safe_name(url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]) or "video"
        first, used, last_err = None, set(), None
        for k, (emb, kind) in enumerate(embs, 1):
            base = make_base(ref)
            target, title = self._resolve_player(emb, ref) if kind == "kinescope" else (emb, "")
            if k == 1:
                meta["title"] = title
            if "outtmpl" in base:
                name = ""
                if title:
                    name = safe_name(title)
                elif kind == "getcourse" or len(embs) > 1:
                    name = f"{slug} - {k}" if len(embs) > 1 else slug
                if name:
                    if name in used:
                        name = f"{name} - {k}"
                    used.add(name)
                    base["outtmpl"] = os.path.join(os.path.dirname(base["outtmpl"]),
                                                   name + ".%(ext)s")
            try:
                res = self._attempt(fn, base, target, note)
            except Exception as e:
                meta["failed"] += 1; last_err = e
                self.after(0, lambda k=k, err=clean(e)[:160]:
                           self._log(f"   Player {k} failed: {err}", "warn"))
                continue
            if first is None:
                first = res
            if "outtmpl" not in base:
                break               # a link check only needs the first one
        if first is None:
            raise last_err
        return first

    def _dl_worker(self, url):
        def make_base(ref):
            b = self._base_opts(referer=ref, audio=self._audio_run)
            b["progress_hooks"] = [self._hook]
            return b
        self.after(0, lambda: self._log(f"►  {url}", "info"))
        def go(o, u):
            with yt_dlp.YoutubeDL(o) as y:
                i = y.extract_info(u, download=True)    # one extraction: info and download
                self.after(0, lambda t=(i or {}).get("title", "?"): self._log(f"   {t}"))
            return True
        meta = {}
        try:
            self._with_embed(go, make_base, url, meta=meta)
            ok, n = meta["count"] - meta["failed"], meta["count"]
            self.after(0, lambda: self._dl_done(ok, n))
        except Exception as e:
            self.after(0, lambda err=str(e): self._dl_fail(err))

    def _dl_done(self, ok=0, n=0):
        audio, self._audio_run = self._audio_run, False
        self._running = False
        self._set_busy(False)
        self._prog.set(100)
        if n and ok < n:                    # some players of the page failed
            self._set_status("warn", "st_done_n_audio" if audio else "st_done_n",
                             action="folder", ok=ok, n=n)
        else:
            self._set_status("ok", "st_done_audio" if audio else "st_done",
                             action="folder")

    def _open_folder(self, path):
        try:
            if sys.platform == "win32": os.startfile(path)
            elif sys.platform == "darwin": subprocess.run(["open", path])
            else: subprocess.run(["xdg-open", path])
        except Exception:
            pass

    def _dl_fail(self, msg):
        self._audio_run = False
        self._running = False
        self._set_busy(False)
        self._prog.set(0)
        key, tag, action = self._diagnose(msg)
        self._log("✘  " + T["en"][key], "err")
        self._log("   " + clean(msg)[:300], "plain")
        self._set_status(tag, key, action=action)

    # ══════════════════════════════════════════════════════════
    #  SCANNER
    # ══════════════════════════════════════════════════════════

    def _render_scan_info(self):
        key, kw = self._scan_state
        ok = key in ("scan_found", "list_loaded")
        self._scan_lbl.config(text=self.t(key, **kw) if key else "",
                              fg=C["green_text"] if ok else
                                 C["muted"] if key == "looking" else C["orange"])

    def _set_scan_info(self, key, **kw):
        self._scan_state = (key, kw); self._render_scan_info()

    def _start_scan(self):
        url = self._page_var.get().strip()
        if not url:
            self._set_scan_info("no_page"); return
        if self._scanning: return
        self._page_url = url; self._scanning = True
        _recolor(self._scan_btn, C["disabled"])
        self._scan_btn.config(state=tk.DISABLED, text=self.t("looking"))
        self._scan_list.clear(); self._set_scan_info("looking")
        self._log("─" * 70); self._log(f"Scan: {url}", "info")
        threading.Thread(target=self._scan_worker, args=(url,), daemon=True).start()

    def _scan_worker(self, page_url):
        found, seen = [], set()
        def add(u, s, t, **extra):
            u = u.replace("&amp;", "&")
            if u not in seen: seen.add(u); found.append(dict(url=u, site=s, title=t, **extra))

        # ── Guard: a homepage / feed has nothing specific to scan ────────────
        if is_bare_domain(page_url):
            self.after(0, lambda: self._log(
                "This is the site's front page, not a video page.", "warn"))
            self.after(0, lambda: self._scan_done([], "scan_front"))
            return

        # ── Native platform pages go straight to yt-dlp ─────────────────────
        # VK, YouTube channels, Vimeo showcases etc. are JavaScript apps: the
        # HTML you get over HTTP is an empty shell, so regexes find nothing
        # no matter how good they are. yt-dlp's extractors understand them.
        if native_listing_url(page_url):
            self.after(0, lambda: self._log(
                "Video-platform page — using the site extractor instead of "
                "reading the HTML", "info"))
            targets = vk_listing_variants(page_url) if is_vk(page_url) else []
            targets = targets or url_variants(page_url) or [page_url]

            for tgt in targets:
                try:
                    o = self._base_opts(info_only=True)
                    ck0 = self._cookies_file or self._auto_cookie
                    if ck0 and os.path.isfile(ck0):
                        o["cookiefile"] = widen_vk_cookies(ck0) if is_vk(tgt) else ck0
                    o.update(extract_flat="in_playlist", ignoreerrors=True,
                             playlistend=200)
                    with yt_dlp.YoutubeDL(o) as y:
                        info = y.extract_info(tgt, download=False)
                    if not info:
                        continue
                    entries = info.get("entries")
                    if entries is None:
                        entries = [info]
                    for e in entries:
                        if not e:
                            continue
                        u = e.get("url") or e.get("webpage_url") or e.get("id")
                        if not u:
                            continue
                        if not str(u).startswith("http") and is_vk(tgt):
                            u = f"https://vk.com/video{u}"
                        add(str(u), e.get("extractor_key", "Video"),
                            e.get("title") or str(u)[:56])
                    if found:
                        self.after(0, lambda n=len(found), h=host_of(tgt):
                                   self._log(f"✔  {n} video(s) listed via {h}", "ok"))
                        break
                except Exception as e:
                    self.after(0, lambda err=clean(e)[:120]:
                               self._log(f"   ⤷ {err}", "warn"))

            if found:
                self.after(0, lambda f=found[:]: self._scan_done(f))
                return
            self.after(0, lambda: self._log(
                "The site extractor returned nothing — falling back to reading "
                "the page HTML", "warn"))

        # ── Generic pages: fetch HTML and pattern-match embeds ───────────────
        hdrs = {"User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"}
        ck = self._cookies_file or self._auto_cookie
        if ck and os.path.isfile(ck):
            use = widen_vk_cookies(ck) if is_vk(page_url) else ck
            hdr = cookie_header_for(use, page_url)
            if hdr:
                hdrs["Cookie"] = hdr
                ncook = hdr.count("=")
                self.after(0, lambda n=ncook:
                           self._log(f"Sending {n} cookie(s) scoped to this site", "info"))

        html = ""
        try:
            req = urllib.request.Request(page_url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=25, context=self._ssl_ctx()) as r:
                html = r.read().decode("utf-8", errors="ignore")
            self.after(0, lambda n=len(html): self._log(f"✔  Page loaded ({n:,} bytes)", "ok"))
        except Exception as e:
            key, tag, _ = self._diagnose(str(e))
            self.after(0, lambda mm=f"{T['en'][key]}  ({clean(e)[:120]})", tt=tag:
                       self._log(mm, tt))

        if html:
            for src in re.findall(
                    r'(?:src|data-src)=["\']([^"\']*player\.vimeo\.com/video/[^"\']+)["\']', html):
                v = re.search(r'/video/(\d+)', src)
                add(src, "Vimeo", f"Vimeo {v.group(1)}" if v else "Vimeo")
            for vid, h in re.findall(
                    r'vimeo(?:\.com)?[/_-]?(?:video/)?(\d{8,12})'
                    r'(?:[/?&](?:h=)?([0-9a-f]{8,12}))?', html):
                add(f"https://vimeo.com/{vid}/{h}" if h else f"https://vimeo.com/{vid}",
                    "Vimeo", f"Vimeo {vid}")
            for v in re.findall(r'data-vimeo-id=["\'](\d+)["\']', html):
                add(f"https://vimeo.com/{v}", "Vimeo", f"Vimeo {v}")
            for v in re.findall(r'youtube\.com/embed/([a-zA-Z0-9_-]{11})', html):
                add(f"https://www.youtube.com/watch?v={v}", "YouTube", f"YouTube {v}")
            for v in re.findall(r'youtu\.be/([a-zA-Z0-9_-]{11})', html):
                add(f"https://www.youtube.com/watch?v={v}", "YouTube", f"YouTube {v}")
            for v in re.findall(r'["\']([^"\']+\.(?:mp4|m3u8|webm)(?:\?[^"\']*)?)["\']', html):
                if v.startswith("http"):
                    add(v, "Direct", v.split("/")[-1].split("?")[0][:56])
            for v in re.findall(r'vk(?:video)?\.(?:com|ru)/(?:video|live)(-?\d+_\d+)', html):
                add(f"https://vk.com/video{v}", "VK", f"VK {v}")
            for v in re.findall(r'(https?://[^"\']*video_ext\.php[^"\']+)', html):
                add(v, "VK", "VK embed")
            slug = page_url.split("?")[0].rstrip("/").rsplit("/", 1)[-1] or "video"
            for k, (v, kind) in enumerate(find_players(html), 1):
                if kind == "getcourse":     # its own title is a hash: name it after the page
                    add(v, "GetCourse", f"{k:02d} {slug}", named=True, pos=k)
                else:
                    add(v, "Kinescope", f"Kinescope {v.rsplit('/', 1)[-1]}")

        if not found:
            try:
                def gen(o, u):
                    o = dict(o); o.update(extract_flat=True, ignoreerrors=True)
                    with yt_dlp.YoutubeDL(o) as y:
                        return y.extract_info(u, download=False)
                i, _ = self._attempt(gen, self._base_opts(info_only=True), page_url, note=False)
                if i:
                    for e in i.get("entries", [i]):
                        if e and e.get("url"):
                            add(e["url"], e.get("extractor_key", "?"),
                                e.get("title", e["url"][:56]))
            except Exception:
                pass

        self.after(0, lambda f=found[:]: self._scan_done(f))

    def _scan_done(self, found, reason=None):
        self._scanning = False
        _recolor(self._scan_btn, C["blue"])
        self._scan_btn.config(state=tk.NORMAL, text=self.t("find"))
        if not found:
            self._set_scan_info(reason or "scan_none")
            self._log("✘  Nothing found", "warn")
        else:
            self._set_scan_info("scan_found", n=len(found))
            self._log(f"✔  {len(found)} video(s) found", "ok")
            for v in found:
                self._scan_list.add(v["url"], v["site"], v["title"],
                                    **{k: v[k] for k in ("named", "pos") if k in v})

    def _open_list(self):
        """Fill the tick-list from a .txt / .json file of links instead of a scan."""
        if self._scanning or self._running:
            self._set_status("warn", "busy"); return
        p = filedialog.askopenfilename(parent=self, title=self.t("list_pick"),
                                       initialdir=os.path.join(HOME, "Downloads"),
                                       filetypes=[("Text / JSON", "*.txt *.json"),
                                                  ("All", "*.*")])
        if not p:
            return
        links = read_link_list(p)
        if not links:
            self._set_scan_info("list_empty"); return
        self._scan_list.clear(); self._page_url = ""     # no page to send as Referer
        for pos, (u, t) in enumerate(links, 1):
            name = t or u.split("?")[0].rstrip("/").rsplit("/", 1)[-1][:60] or u[:60]
            self._scan_list.add(u, host_of(u) or "?", name, named=bool(t), pos=pos)
        self._set_scan_info("list_loaded", n=len(links))
        self._log(f"List loaded: {os.path.basename(p)} ({len(links)} links)", "info")

    def _download_selected(self):
        sel = self._scan_list.selected()
        if not sel:
            self._set_scan_info("nothing_ticked"); return
        if self._running:
            self._set_status("warn", "busy"); return
        self._running = True; self._batch = (1, len(sel))
        self._set_busy(True)
        self._dl_sel_btn.config(text="⏳   " + self.t("downloading_n", n=len(sel)))
        self._prog.set(0); self._set_status("busy", "st_starting")
        threading.Thread(target=self._sel_worker,
                         args=(sel, self._dl_dir, self._page_url), daemon=True).start()

    def _sel_worker(self, sel, out_dir, referer):
        ok = fail = 0; reasons = []
        referer = referer_for(referer)          # no query string / tracking ids
        for n, it in enumerate(sel, 1):
            def start(t=it["title"], i=n, N=len(sel)):
                self._batch = (i, N); self._prog.set(0)
                self._log(f"[{i}/{N}]  {t}", "info")
                self._set_status("busy", "st_batch", i=i, n=N, pct=0)
            self.after(0, start)
            base = self._base_opts(out_dir, referer or None)
            base["progress_hooks"] = [self._hook]
            if it.get("named"):         # title from a link list: keep the course order
                safe = safe_name(it["title"], 80) or "video"
                # number = place in the file (unticking doesn't shift it); a title
                # that already starts with its own number ("03 Installing...") keeps it
                if not re.match(r"\d+\b", safe):
                    safe = f"{it.get('pos', n):02d} - {safe}"
                base["outtmpl"] = os.path.join(out_dir, f"{safe}.%(ext)s")
            def go(o, u):
                with yt_dlp.YoutubeDL(o) as y: y.download([u]); return True
            target, title = self._resolve_player(it["url"], referer)
            if title and not it.get("named"):
                base["outtmpl"] = os.path.join(out_dir, safe_name(title) + ".%(ext)s")
            try:
                self._attempt(go, base, target, note=False); ok += 1
            except Exception as e:
                fail += 1
                key, tag, action = self._diagnose(str(e)); reasons.append((key, tag, action))
                self.after(0, lambda mm=T["en"][key], raw=clean(e)[:200], tt=tag:
                           (self._log(f"   ✘  {mm}", tt), self._log(f"      {raw}")))

        def done():
            self._running = False; self._batch = None
            self._set_busy(False)
            if ok:
                self._prog.set(100)
                self._set_status("ok", "st_done_n", action="folder", ok=ok, n=ok + fail)
            else:
                self._prog.set(0)
                key, tag, action = reasons[0] if reasons else ("st_none_saved", "err", None)
                self._set_status(tag, key, action=action)
        self.after(0, done)

    # ══════════════════════════════════════════════════════════
    #  MAINTENANCE
    # ══════════════════════════════════════════════════════════

    def _startup_report(self, quiet=False):
        good = bool(self._ffmpeg) and TRUSTSTORE_OK
        self._pill.config(text=("✓  " + self.t("ready")) if good
                          else ("⚠  " + self.t("attention")),
                          fg=C["pill_ok"] if good else C["pill_warn"])
        ck = self._cookies_file or self._auto_cookie
        rows = [(self.t("sys_ssl"), self.t("sys_ok") if TRUSTSTORE_OK else self.t("sys_missing")),
                (self.t("sys_ffmpeg"), self.t("sys_ok") if self._ffmpeg else self.t("sys_missing")),
                (self.t("sys_cookies"), os.path.basename(ck) if ck else self.t("sys_none")),
                (self.t("sys_engine"), self._engine_ver or yt_dlp.version.__version__),
                (self.t("sys_version"), APP_VER)]
        width = max(len(k) for k, _ in rows) + 3
        self._sys_lbl.config(text="\n".join(f"{k:<{width}}{v}" for k, v in rows))
        if self._ffmpeg:
            self._ffmpeg_btn.pack_forget()
        else:
            self._ffmpeg_btn.pack(side=tk.LEFT, padx=(8, 0), ipadx=10, ipady=4)
        if quiet or self._running:
            return
        if not self._ffmpeg:
            self._set_status("warn", "d_ffmpeg", action="ffmpeg")
        elif self._status_state[0] in ("idle", "warn") and \
                self._status_state[1] in ("st_ready", "d_ffmpeg"):
            self._set_status("idle", "st_ready")

    def _refresh_ffmpeg(self):
        self._ffmpeg = _find_ffmpeg()
        self._startup_report()

    def _install_ffmpeg(self):
        if self._running:
            self._set_status("warn", "busy"); return
        self._running = True
        self._set_status("busy", "st_installing")
        self._log("Installing FFmpeg …", "info")
        def work():
            ok = False
            if sys.platform == "win32" and shutil.which("winget"):
                subprocess.run(["winget", "install", "Gyan.FFmpeg", "--silent",
                                "--accept-package-agreements", "--accept-source-agreements"],
                               capture_output=True, creationflags=NO_WINDOW)
                ok = bool(shutil.which("ffmpeg"))
            elif sys.platform == "darwin" and shutil.which("brew"):
                subprocess.run(["brew", "install", "ffmpeg"], capture_output=True)
                ok = bool(shutil.which("ffmpeg"))
            if not ok and _pip("imageio-ffmpeg"): ok = bool(_find_ffmpeg())
            def fin():
                self._running = False
                self._ffmpeg = _find_ffmpeg()
                self._startup_report(quiet=True)
                self._log("✔  FFmpeg ready" if ok else "✘  FFmpeg install failed",
                          "ok" if ok else "err")
                if ok: self._set_status("ok", "st_helper_ready")
                else:  self._set_status("err", "st_helper_failed", action="details")
            self.after(0, fin)
        threading.Thread(target=work, daemon=True).start()

    def _engine_version(self):
        try:
            r = subprocess.run([sys.executable, "-c",
                                "import yt_dlp;print(yt_dlp.version.__version__)"],
                               capture_output=True, text=True, timeout=15,
                               creationflags=NO_WINDOW)
            return r.stdout.strip()
        except Exception:
            return ""

    def _force_update(self):
        """Pull the newest engine — YouTube fixes land weekly."""
        if self._running:
            self._set_status("warn", "busy"); return
        self._running = True
        self._log("Updating the downloader engine …", "info")
        self._set_status("busy", "st_updating")
        def work():
            ok = _pip("-U", "--force-reinstall", "yt-dlp[default]") or _pip("-U", "yt-dlp")
            ver = self._engine_version()
            def fin():
                self._running = False
                if ok:
                    self._engine_ver = ver or self._engine_ver
                    self._startup_report(quiet=True)
                    self._log(f"✔  Engine updated to {ver} — restart the app, then retry", "ok")
                    self._set_status("ok", "st_updated")
                else:
                    self._log("✘  Update failed", "err")
                    self._set_status("err", "st_update_failed")
            self.after(0, fin)
        threading.Thread(target=work, daemon=True).start()

    def _bg_update(self):
        def run():
            if _pip("-U", "yt-dlp[default]") or _pip("-U", "yt-dlp"):
                v = self._engine_version()
                if v:
                    def fin():
                        self._engine_ver = v
                        self._log(f"Engine version {v}", "plain")
                        self._startup_report(quiet=True)
                    self.after(0, fin)
        threading.Thread(target=run, daemon=True).start()


# ══════════════════════════════════════════════════════════════
#  8.  COMMAND-LINE MODES  (all optional — the GUI is the default)
# ══════════════════════════════════════════════════════════════

def _cli_opts(out_dir, insecure=False, cookiefile=None, url=""):
    """Build yt-dlp options outside the GUI, using the same rules the app uses."""
    ff = _find_ffmpeg()
    o = dict(quiet=True, no_warnings=True, socket_timeout=30,
             http_headers={"User-Agent": UA},
             format=FORMAT_MERGE if ff else FORMAT_SINGLE,
             outtmpl=os.path.join(out_dir, "%(title).80s.%(ext)s"))
    if ff:
        o["ffmpeg_location"] = ff
        o["merge_output_format"] = "mp4"
    if insecure:
        o["nocheckcertificate"] = True
    elif TRUSTSTORE_OK:
        o["compat_opts"] = {"no-certifi"}
    if cookiefile and os.path.isfile(cookiefile):
        o["cookiefile"] = widen_vk_cookies(cookiefile) if is_vk(url) else cookiefile
    return o


def _cli_attempt(url, out_dir, insecure=False, download=True, verbose=True):
    """
    Headless version of the GUI's strategy chain: walk
    (url variant x cookie source x player client) until something works.
    """
    files = discover_cookies()
    sources = [(f"cookies[{os.path.basename(p)}]", p) for p, _, _ in files]
    sources.append(("no cookies", None))
    if is_youtube(url):                      # cookie-free first for YouTube
        sources = [s for s in sources if s[1] is None] + \
                  [s for s in sources if s[1] is not None]

    clients = YT_CLIENT_SETS if is_youtube(url) else [None]
    variants = url_variants(url)
    last = None

    for u in variants:
        for sname, cpath in sources:
            for cs in clients:
                o = _cli_opts(out_dir, insecure, cpath, u)
                if cs:
                    o["extractor_args"] = {"youtube": {"player_client": list(cs)}}
                try:
                    with yt_dlp.YoutubeDL(o) as y:
                        info = y.extract_info(u, download=download)
                    label = sname + (f" + {'/'.join(cs)}" if cs else "")
                    if u != url:
                        label += f" [via {host_of(u)}]"
                    if verbose:
                        print(f"    ok via {label}")
                    return info, label
                except Exception as e:
                    last = e
                    msg = clean(e).lower()
                    if any(k in msg for k in App.SOFT):
                        continue
                    break
    raise last if last else RuntimeError("no strategy worked")


def run_selftest():
    """Diagnose the machine, then try a real download."""
    line = "=" * 70
    print(f"\n{line}\n  {APP_NAME} {APP_VER} — self test\n{line}\n")

    print("  Environment")
    print(f"    python      {sys.version.split()[0]}")
    print(f"    yt-dlp      {yt_dlp.version.__version__}")
    print(f"    truststore  {'active' if TRUSTSTORE_OK else 'MISSING - run: pip install truststore'}")
    ff = _find_ffmpeg()
    print(f"    ffmpeg      {os.path.basename(ff) if ff else 'MISSING - quality will be capped'}")
    if sys.platform == "win32":
        print("    browsers    Chrome/Edge cookies unreadable (App-Bound Encryption);"
              " export cookies.txt instead")
    print(f"    firefox     {'profile found' if firefox_available() else 'not installed'}")

    print("\n  Cookie files")
    files = discover_cookies()
    if not files:
        print("    none found in Downloads / Desktop / OneDrive / app folder")
    for p, mt, doms in files:
        age = (time.time() - mt) / 3600
        key = [d for d in doms if any(k in d for k in
               ("youtube", "vk.", "vkvideo", "vimeo", "facebook", "instagram"))]
        print(f"    {os.path.basename(p)[:30]:<30} {len(doms):>3} sites  {age:>5.1f}h old")
        if key:
            print(f"      relevant: {', '.join(sorted(key)[:8])}")
        vk_sess = [d for d in ("vk.com", "vk.ru", "vkvideo.ru") if d in doms]
        if vk_sess:
            widened = widen_vk_cookies(p)
            note = "session copied across VK domains" if widened != p \
                   else "VK session already on every VK domain (or absent)"
            print(f"      VK: {note}")
            if widened != p:
                try: os.unlink(widened)
                except Exception: pass

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selftest_downloads")
    os.makedirs(out, exist_ok=True)
    print(f"\n  Test download  ->  {out}")
    test_url = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"   # Big Buck Bunny, public
    try:
        info, how = _cli_attempt(test_url, out, download=True)
        print(f"    PASS  {info.get('title','?')[:50]}")
    except Exception as e:
        print(f"    FAIL  {clean(e)[:100]}")

    print(f"\n{line}\n  Done. Run without --selftest to open the window.\n{line}\n")


def make_shortcut():
    """Put a Desktop shortcut on the user's machine so they never see a terminal."""
    script = os.path.abspath(__file__)
    desk = os.path.join(HOME, "Desktop")
    if not os.path.isdir(desk):
        desk = os.path.join(HOME, "OneDrive", "Desktop")
    if not os.path.isdir(desk):
        print(f"Could not find a Desktop folder under {HOME}"); return

    if sys.platform == "win32":
        pyw = sys.executable.replace("python.exe", "pythonw.exe")
        if not os.path.isfile(pyw):
            pyw = sys.executable
        target = os.path.join(desk, f"{APP_NAME}.bat")
        with open(target, "w", encoding="utf-8") as f:
            f.write(f'@echo off\nstart "" "{pyw}" "{script}"\n')
    elif sys.platform == "darwin":
        target = os.path.join(desk, f"{APP_NAME}.command")
        with open(target, "w", encoding="utf-8") as f:
            f.write(f'#!/bin/bash\n"{sys.executable}" "{script}"\n')
        os.chmod(target, 0o755)
    else:
        target = os.path.join(desk, f"{APP_NAME}.desktop")
        with open(target, "w", encoding="utf-8") as f:
            f.write("[Desktop Entry]\nType=Application\n"
                    f"Name={APP_NAME}\n"
                    f"Exec={sys.executable} \"{script}\"\n"
                    "Terminal=false\n")
        os.chmod(target, 0o755)
    print(f"Shortcut created:\n  {target}")


def run_headless(url, out_dir, insecure=False):
    os.makedirs(out_dir, exist_ok=True)
    print(f"Downloading: {url}")
    try:
        info, how = _cli_attempt(url, out_dir, insecure, download=True)
        print(f"Saved '{info.get('title','?')}' to {out_dir}")
        return 0
    except Exception as e:
        print(f"Failed: {clean(e)[:200]}")
        return 1


def main():
    ap = argparse.ArgumentParser(
        prog="VideoDownloader",
        description=f"{APP_NAME} {APP_VER} — download videos at 480p")
    ap.add_argument("--selftest", action="store_true",
                    help="check the setup and try a test download")
    ap.add_argument("--shortcut", action="store_true",
                    help="create a Desktop shortcut and exit")
    ap.add_argument("--url", default="", help="download one link without opening the window")
    ap.add_argument("--dir", default=os.path.join(HOME, "Downloads"),
                    help="where to save (default: Downloads)")
    ap.add_argument("--insecure", action="store_true",
                    help="skip certificate verification (last resort)")
    args, _unknown = ap.parse_known_args()

    if args.shortcut:
        make_shortcut(); return 0
    if args.selftest:
        run_selftest(); return 0
    if args.url:
        return run_headless(args.url, args.dir, args.insecure)

    App().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
