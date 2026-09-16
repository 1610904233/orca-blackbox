# hv_provision4.ps1 — guest, elevated. Extract bundle.7z (unicode-safe) then provision.
$ErrorActionPreference = "Continue"
Start-Transcript -Path C:\coil\provision.log -Append
New-Item -ItemType Directory -Force -Path C:\coil | Out-Null

Write-Host "[0] extracting bundle.7z (22770 files)..."
if (Test-Path C:\coil\bx) { Remove-Item C:\coil\bx -Recurse -Force }
Copy-Item C:\coil\src_bundle\7zr.exe C:\coil\7zr.exe -Force
& C:\coil\7zr.exe x C:\coil\src_bundle\bundle.7z -oC:\coil\bx -y | Select-Object -Last 2
Write-Host ("    extracted: " + [math]::Round(((Get-ChildItem C:\coil\bx -Recurse | Measure-Object Length -Sum).Sum)/1MB) + " MB")

Write-Host "[1] laying out tree..."
New-Item -ItemType Directory -Force -Path C:\coil\Projects\SnapmakerOrca_dev\build\src | Out-Null
Move-Item C:\coil\bx\app\Release C:\coil\Projects\SnapmakerOrca_dev\build\src\Release -Force
New-Item -ItemType Directory -Force -Path C:\coil\Projects\SnapmakerOrca_dev\.worktrees | Out-Null
Move-Item C:\coil\bx\wb C:\coil\Projects\SnapmakerOrca_dev\.worktrees\vision-gui-blackbox -Force
New-Item -ItemType Directory -Force -Path C:\coil\Projects\SnapmakerOrca_dev\.worktrees\vision-gui-blackbox\sandboxes | Out-Null
Copy-Item C:\coil\bx\7zr.exe C:\coil\7zr.exe -Force
Copy-Item C:\coil\bx\mesa-dist-win.7z C:\coil\mesa-dist-win.7z -Force
Write-Host "    Release exe: $(Test-Path C:\coil\Projects\SnapmakerOrca_dev\build\src\Release\Snapmaker_Orca.exe)"

Write-Host "[2] python..."
Start-Process -FilePath C:\coil\bx\python311-installer.exe -ArgumentList "/quiet","InstallAllUsers=1","PrependPath=1","TargetDir=C:\Python311" -Wait
$py = "C:\Python311\python.exe"
Write-Host ("    python: " + (& $py --version))

Write-Host "[3] tesseract..."
Start-Process -FilePath C:\coil\bx\tesseract-setup.exe -ArgumentList "/S" -Wait
Write-Host ("    tesseract: " + (Test-Path 'C:\Program Files\Tesseract-OCR\tesseract.exe'))

Write-Host "[4] pip deps..."
& $py -m pip install --quiet opencv-python numpy pytesseract 2>&1 | Select-Object -Last 3

Write-Host "[5] mesa GL..."
& C:\coil\7zr.exe x C:\coil\mesa-dist-win.7z -oC:\coil\mesa -y | Out-Null
$gl = Get-ChildItem C:\coil\mesa -Recurse -Filter opengl32.dll | Where-Object { $_.FullName -match "x64" } | Select-Object -First 1
Copy-Item $gl.FullName C:\coil\Projects\SnapmakerOrca_dev\build\src\Release\opengl32.dll -Force
Write-Host ("    opengl32.dll from: " + $gl.FullName)

Write-Host "[6] GL probe..."
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

powercfg /change monitor-timeout-ac 0
powercfg /change standby-timeout-ac 0
Set-Content -Path C:\provision_done.txt -Value "ok"
Write-Host "PROVISION DONE"
Stop-Transcript
