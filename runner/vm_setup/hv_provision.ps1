# hv_provision.ps1 — runs INSIDE the guest (elevated), after first logon.
# Extracts the bundle, installs python/tesseract, pip deps, mesa software
# GL, writes the GL probe, and marks completion.

$ErrorActionPreference = "Continue"
Start-Transcript -Path C:\coil\provision.log -Append

# 1) extract bundle into C:\coil (contains app\Release + wb\ tree)
Expand-Archive -Path C:\guest_bundle.zip -DestinationPath C:\coil\bundle_x -Force
New-Item -ItemType Directory -Force -Path C:\coil\Projects\SnapmakerOrca_dev\.worktrees\vision-gui-blackbox\sandboxes, C:\coil\Projects\SnapmakerOrca_dev\build\src | Out-Null
Move-Item C:\coil\bundle_x\app\Release C:\coil\Projects\SnapmakerOrca_dev\build\src\Release
Move-Item C:\coil\bundle_x\wb C:\coil\Projects\SnapmakerOrca_dev\.worktrees\vision-gui-blackbox

# 2) python silent
Start-Process -FilePath C:\coilundle_x\python311-installer.exe -ArgumentList "/quiet","InstallAllUsers=1","PrependPath=1","TargetDir=C:\Python311" -Wait
$py = "C:\Python311\python.exe"

# 3) tesseract silent (NSIS) — installs to C:\Program Files\Tesseract-OCR
Start-Process -FilePath C:\guest_bundle\tesseract-setup.exe -ArgumentList "/S" -Wait

# 4) pip deps
& $py -m pip install --quiet opencv-python numpy pytesseract

# 5) mesa software GL: extract + place opengl32.dll next to the app exe
& C:\coil\7zr.exe x C:\coil\mesa-dist-win.7z -oC:\coil\mesa -y
$gl = Get-ChildItem C:\coil\mesa -Recurse -Filter opengl32.dll | Where-Object { $_.FullName -match "x64" } | Select-Object -First 1
Copy-Item $gl.FullName C:\coil\Projects\SnapmakerOrca_dev\build\src\Release\opengl32.dll -Force

# 6) GL probe
$probe = @'
import ctypes
u = ctypes.WinDLL("user32"); g = ctypes.WinDLL("gdi32"); o = ctypes.WinDLL("opengl32"); k = ctypes.WinDLL("kernel32")
WS_OVERLAPPEDWINDOW = 0x00CF0000; WS_VISIBLE = 0x10000000
class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", ctypes.c_void_p), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", ctypes.c_void_p), ("hIcon", ctypes.c_void_p),
                ("hCursor", ctypes.c_void_p), ("hbrBackground", ctypes.c_void_p), ("lpszMenuName", ctypes.c_wchar_p),
                ("lpszClassName", ctypes.c_wchar_p)]
hInst = k.GetModuleHandleW(None)
WC = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_longlong)
wc = WNDCLASSW(); wc.lpfnWndProc = ctypes.cast(WC(lambda h, m, w, l: u.DefWindowProcW(h, m, w, l)), ctypes.c_void_p)
wc.hInstance = hInst; wc.lpszClassName = "glprobe"
u.RegisterClassW(ctypes.byref(wc))
hwnd = u.CreateWindowExW(0, "glprobe", "gl", WS_OVERLAPPEDWINDOW | WS_VISIBLE, 8, 8, 300, 300, None, None, hInst, None)
hdc = u.GetDC(hwnd)
class PFD(ctypes.Structure):
    _fields_ = [(n, t) for n, t in [("nSize", ctypes.c_ushort), ("nVersion", ctypes.c_ushort), ("dwFlags", ctypes.c_uint),
                ("iPixelType", ctypes.c_ubyte), ("cColorBits", ctypes.c_ubyte), ("cRedBits", ctypes.c_ubyte), ("cRedShift", ctypes.c_ubyte),
                ("cGreenBits", ctypes.c_ubyte), ("cGreenShift", ctypes.c_ubyte), ("cBlueBits", ctypes.c_ubyte), ("cBlueShift", ctypes.c_ubyte),
                ("cAlphaBits", ctypes.c_ubyte), ("cAlphaShift", ctypes.c_ubyte), ("cAccumBits", ctypes.c_ubyte), ("cAccumRedBits", ctypes.c_ubyte),
                ("cAccumGreenBits", ctypes.c_ubyte), ("cAccumBlueBits", ctypes.c_ubyte), ("cAccumAlphaBits", ctypes.c_ubyte),
                ("cDepthBits", ctypes.c_ubyte), ("cStencilBits", ctypes.c_ubyte), ("cAuxBuffers", ctypes.c_ubyte),
                ("iLayerType", ctypes.c_ubyte), ("bReserved", ctypes.c_ubyte), ("dwLayerMask", ctypes.c_uint),
                ("dwVisibleMask", ctypes.c_uint), ("dwDamageMask", ctypes.c_uint)]]
pfd = PFD(); pfd.nSize = ctypes.sizeof(PFD); pfd.nVersion = 1; pfd.dwFlags = 0x25; pfd.cColorBits = 32; pfd.cDepthBits = 24
pf = g.ChoosePixelFormat(hdc, ctypes.byref(pfd)); g.SetPixelFormat(hdc, pf, ctypes.byref(pfd))
hglrc = o.wglCreateContext(hdc); o.wglMakeCurrent(hdc, hglrc)
o.glGetString.restype = ctypes.c_char_p
print("GL_VERSION:", o.glGetString(0x1F02).decode())
print("GL_RENDERER:", o.glGetString(0x1F01).decode())
'@
Set-Content -Path C:\coil\gl_probe.py -Value $probe -Encoding UTF8
& $py C:\coil\gl_probe.py | Tee-Object -FilePath C:\coil\gl_probe_result.txt

# 7) done marker
Set-Content -Path C:\provision_done.txt -Value "ok"
Stop-Transcript
