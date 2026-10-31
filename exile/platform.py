"""Small Windows boundary. No injection or game-memory writes."""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass
import os

WINDOWS = os.name == "nt"

def alt_down():
    return bool(WINDOWS and C.windll.user32.GetAsyncKeyState(0x12)&0x8000)
if WINDOWS:
    user32 = C.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = W.HWND
    user32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
    user32.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
    user32.ClientToScreen.argtypes = [W.HWND, C.POINTER(W.POINT)]
    user32.IsWindowVisible.argtypes = [W.HWND]
    user32.IsIconic.argtypes = [W.HWND]


@dataclass
class GameWindow:
    hwnd: int = 0
    pid: int = 0
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    foreground: bool = False


def game_window() -> GameWindow:
    if not WINDOWS:
        return GameWindow()
    result = GameWindow()
    callback_type = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def visit(hwnd, _):
        nonlocal result
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        buffer = C.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buffer, 512)
        # Exact title avoids attaching to a browser with PoE in its tab title.
        if buffer.value != "Path of Exile":
            return True
        pid = W.DWORD()
        user32.GetWindowThreadProcessId(hwnd, C.byref(pid))
        rect, point = W.RECT(), W.POINT()
        user32.GetClientRect(hwnd, C.byref(rect))
        user32.ClientToScreen(hwnd, C.byref(point))
        result = GameWindow(int(hwnd), pid.value, point.x, point.y,
                            rect.right, rect.bottom,
                            hwnd == user32.GetForegroundWindow())
        return False
    callback = callback_type(visit)
    user32.EnumWindows(callback, 0)
    return result


def process_path(pid: int) -> str:
    if not WINDOWS or pid <= 0:
        return ""
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
    kernel.CloseHandle.argtypes = [W.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return ""
    try:
        buffer, size = C.create_unicode_buffer(32768), W.DWORD(32768)
        if kernel.QueryFullProcessImageNameW(handle, 0, buffer, C.byref(size)):
            return buffer.value
        return ""
    finally:
        kernel.CloseHandle(handle)


def window_is_foreground(hwnd):
    return bool(WINDOWS and hwnd and user32.GetForegroundWindow()==hwnd)


class ReadMemory:
    def __init__(self, pid: int):
        if not WINDOWS:
            raise OSError("Windows is required")
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        self.kernel.OpenProcess.restype = W.HANDLE
        self.kernel.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p,
                                                   C.c_size_t, C.POINTER(C.c_size_t)]
        self.kernel.CloseHandle.argtypes = [W.HANDLE]
        self.handle = self.kernel.OpenProcess(0x0010 | 0x1000, False, pid)
        if not self.handle:
            raise OSError(C.get_last_error(), "Cannot open game for reading")

    def read(self, address: int, count: int) -> bytes:
        if not 0x10000 <= address < 0x7FFFFFFFFFFF or not 0 < count <= 16_777_216:
            raise ValueError("Invalid memory read range")
        buffer = C.create_string_buffer(count)
        read = C.c_size_t()
        if not self.kernel.ReadProcessMemory(self.handle, address, buffer, count, C.byref(read)) or read.value != count:
            raise OSError(C.get_last_error(), "Game memory read failed")
        return buffer.raw

    def regions(self):
        class Information(C.Structure):
            _fields_ = [("base", C.c_void_p), ("allocation_base", C.c_void_p),
                        ("allocation_protect", W.DWORD), ("partition", W.WORD),
                        ("size", C.c_size_t), ("state", W.DWORD),
                        ("protect", W.DWORD), ("kind", W.DWORD)]
        self.kernel.VirtualQueryEx.argtypes = [W.HANDLE, C.c_void_p, C.POINTER(Information), C.c_size_t]
        self.kernel.VirtualQueryEx.restype = C.c_size_t
        address = 0x10000
        while address < 0x7FFFFFFFFFFF:
            info = Information()
            if not self.kernel.VirtualQueryEx(self.handle, address, C.byref(info), C.sizeof(info)):
                break
            base, size = int(info.base or 0), info.size
            if size <= 0 or base + size <= address:
                break
            if info.state == 0x1000 and not info.protect & 0x101 and info.protect & 0xEE:
                yield base, size, info.protect, info.kind
            address = base + size

    def main_image(self) -> int:
        class Basic(C.Structure):
            _fields_ = [("reserved", C.c_void_p), ("peb", C.c_void_p),
                        ("reserved2", C.c_void_p * 2), ("pid", C.c_size_t),
                        ("reserved3", C.c_void_p)]
        ntdll = C.WinDLL("ntdll")
        ntdll.NtQueryInformationProcess.argtypes = [W.HANDLE, W.ULONG, C.c_void_p, W.ULONG, C.POINTER(W.ULONG)]
        ntdll.NtQueryInformationProcess.restype = C.c_long
        basic, length = Basic(), W.ULONG()
        status = ntdll.NtQueryInformationProcess(self.handle, 0, C.byref(basic), C.sizeof(basic), C.byref(length))
        if status != 0 or not basic.peb:
            raise OSError(f"Cannot query main image (status {status & 0xffffffff:#x})")
        import struct
        base = struct.unpack("<Q", self.read(int(basic.peb) + 16, 8))[0]
        if self.read(base, 2) != b"MZ":
            raise ValueError("Main image is not a PE executable")
        return base

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def module_base(pid: int, name: str) -> tuple[int, int]:
    if not WINDOWS:
        raise OSError("Windows is required")
    class Module(C.Structure):
        _fields_ = [("size", W.DWORD), ("module_id", W.DWORD), ("process_id", W.DWORD),
                    ("global_count", W.DWORD), ("process_count", W.DWORD),
                    ("base", C.c_void_p), ("module_size", W.DWORD), ("handle", W.HMODULE),
                    ("name", W.WCHAR * 256), ("path", W.WCHAR * 260)]
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = W.HANDLE
    kernel.Module32FirstW.argtypes = [W.HANDLE, C.POINTER(Module)]
    kernel.Module32NextW.argtypes = [W.HANDLE, C.POINTER(Module)]
    kernel.CloseHandle.argtypes = [W.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(0x18, pid)
    if handle == C.c_void_p(-1).value:
        raise OSError(C.get_last_error(), "Cannot enumerate game modules")
    try:
        module = Module()
        module.size = C.sizeof(Module)
        more = kernel.Module32FirstW(handle, C.byref(module))
        while more:
            if module.name.casefold() == name.casefold():
                return int(module.base), module.module_size
            more = kernel.Module32NextW(handle, C.byref(module))
    finally:
        kernel.CloseHandle(handle)
    raise ValueError("Game executable module not found")
