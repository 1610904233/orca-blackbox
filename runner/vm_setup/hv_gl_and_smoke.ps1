# hv_gl_and_smoke.ps1 — HOST, ELEVATED. Fix GL probe (mesa dll dir) + run m3j smoke in guest.
Start-Transcript -Path "C:\coil\vm_setup\hv_gl_smoke.log" -Force
$vm = "win11-test"
$cred = New-Object System.Management.Automation.PSCredential("test", (ConvertTo-SecureString "123456" -AsPlainText -Force))
$rel = "C:\coil\Projects\SnapmakerOrca_dev\build\src\Release"

Write-Host "[1] real exe check + fixed GL probe (mesa via add_dll_directory)..."
Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    param($rel)
    "exe present: " + (Test-Path "$rel\snapmaker-orca.exe")
    "mesa dll: " + (Test-Path "$rel\opengl32.dll")
    $probe = @'
import ctypes, os
rel = r"C:\coil\Projects\SnapmakerOrca_dev\build\src\Release"
os.add_dll_directory(rel)
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
wc.hInstance = hInst; wc.lpszClassName = "glprobe2"
u.RegisterClassW(ctypes.byref(wc))
hwnd = u.CreateWindowExW(0, "glprobe2", "gl", WS_OVERLAPPEDWINDOW | WS_VISIBLE, 8, 8, 300, 300, None, None, hInst, None)
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
    Set-Content -Path C:\coil\gl_probe2.py -Value $probe -Encoding UTF8
    & C:\Python311\python.exe C:\coil\gl_probe2.py | Tee-Object -FilePath C:\coil\gl_probe_result.txt
} -ArgumentList $rel

Write-Host "[2] m3j smoke case (in guest, ~2-5 min)..."
Invoke-Command -VMName $vm -Credential $cred -ScriptBlock {
    Set-Location "C:\coil\Projects\SnapmakerOrca_dev\.worktrees\vision-gui-blackbox\sandboxes\vision_gui"
    & C:\Python311\python.exe m3j_mixing_entry.py 2>&1 | Select-Object -Last 15
}
Stop-Transcript
