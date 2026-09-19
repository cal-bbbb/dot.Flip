// Windows 11 top-level context menu for dot.Flip.
//
// Implements IExplorerCommand: a "Convert to" entry with one sub-command per output format.
// Registered through a sparse MSIX package (see AppxManifest.xml.in). Selected paths are handed
// to DotFlip.exe (installed next to this DLL) via a UTF-8 list file, so an entire
// multi-file selection is converted by one process.
#include <windows.h>
#include <shobjidl_core.h>
#include <shlwapi.h>
#include <shlobj.h>
#include <atomic>
#include <string>
#include <vector>

// {8D3A6F52-1B47-4C0E-A9E5-6F2D7B9C3E41}
static const CLSID CLSID_DotFlipCommand =
    {0x8d3a6f52, 0x1b47, 0x4c0e, {0xa9, 0xe5, 0x6f, 0x2d, 0x7b, 0x9c, 0x3e, 0x41}};

static HMODULE g_module = nullptr;
static std::atomic<long> g_objects{0};

struct FormatDef { const wchar_t* id; const wchar_t* label; };
// Keep in sync with dotflip/core/formats.py (writable formats).
static const FormatDef kFormats[] = {
    {L"png", L"PNG"}, {L"jpeg", L"JPEG"}, {L"tiff", L"TIFF"}, {L"gif", L"GIF"},
    {L"webp", L"WebP"}, {L"bmp", L"BMP"}, {L"ico", L"ICO"}, {L"avif", L"AVIF"},
};
static const int kFormatCount = sizeof(kFormats) / sizeof(kFormats[0]);
static const int kMoreOptions = -1;

static const wchar_t* const kReadable[] = {
    L".png", L".jpg", L".jpeg", L".jpe", L".jfif", L".tif", L".tiff", L".gif", L".webp",
    L".bmp", L".dib", L".ico", L".avif", L".heic", L".heif", L".svg",
};

static std::wstring ModuleDir() {
    wchar_t buf[MAX_PATH * 2];
    DWORD n = GetModuleFileNameW(g_module, buf, ARRAYSIZE(buf));
    std::wstring p(buf, n);
    size_t slash = p.find_last_of(L"\\/");
    return slash == std::wstring::npos ? L"." : p.substr(0, slash);
}

static bool IsReadable(const std::wstring& path) {
    const wchar_t* ext = PathFindExtensionW(path.c_str());
    for (const wchar_t* r : kReadable)
        if (_wcsicmp(ext, r) == 0) return true;
    return false;
}

static std::vector<std::wstring> SelectedPaths(IShellItemArray* items) {
    std::vector<std::wstring> out;
    if (!items) return out;
    DWORD count = 0;
    if (FAILED(items->GetCount(&count))) return out;
    for (DWORD i = 0; i < count; ++i) {
        IShellItem* item = nullptr;
        if (FAILED(items->GetItemAt(i, &item))) continue;
        PWSTR name = nullptr;
        if (SUCCEEDED(item->GetDisplayName(SIGDN_FILESYSPATH, &name))) {
            out.emplace_back(name);
            CoTaskMemFree(name);
        }
        item->Release();
    }
    return out;
}

static std::string ToUtf8(const std::wstring& s) {
    if (s.empty()) return {};
    int n = WideCharToMultiByte(CP_UTF8, 0, s.data(), (int)s.size(), nullptr, 0, nullptr, nullptr);
    std::string out(n, '\0');
    WideCharToMultiByte(CP_UTF8, 0, s.data(), (int)s.size(), out.data(), n, nullptr, nullptr);
    return out;
}

static void CleanOldLists(const std::wstring& dir) {
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW((dir + L"\\*.txt").c_str(), &fd);
    if (h == INVALID_HANDLE_VALUE) return;
    FILETIME now;
    GetSystemTimeAsFileTime(&now);
    ULARGE_INTEGER n{{now.dwLowDateTime, now.dwHighDateTime}};
    do {
        ULARGE_INTEGER t{{fd.ftLastWriteTime.dwLowDateTime, fd.ftLastWriteTime.dwHighDateTime}};
        if (n.QuadPart > t.QuadPart && n.QuadPart - t.QuadPart > 24ULL * 3600 * 10000000ULL)
            DeleteFileW((dir + L"\\" + fd.cFileName).c_str());
    } while (FindNextFileW(h, &fd));
    FindClose(h);
}

// Writes the selection to a list file and starts DotFlip.exe. `format` is null for the GUI.
static HRESULT Launch(const wchar_t* format, IShellItemArray* items) {
    std::vector<std::wstring> paths = SelectedPaths(items);
    if (paths.empty()) return S_OK;

    wchar_t temp[MAX_PATH];
    GetTempPathW(ARRAYSIZE(temp), temp);
    std::wstring dir = std::wstring(temp) + L"DotFlip";
    CreateDirectoryW(dir.c_str(), nullptr);
    CleanOldLists(dir);
    std::wstring list = dir + L"\\" + std::to_wstring(GetTickCount64()) + L"-" +
                        std::to_wstring(GetCurrentProcessId()) + L".txt";

    std::string data;
    for (auto& p : paths) data += ToUtf8(p) + "\n";
    HANDLE f = CreateFileW(list.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (f == INVALID_HANDLE_VALUE) return HRESULT_FROM_WIN32(GetLastError());
    DWORD written = 0;
    WriteFile(f, data.data(), (DWORD)data.size(), &written, nullptr);
    CloseHandle(f);

    std::wstring exe = ModuleDir() + L"\\DotFlip.exe";
    std::wstring cmd = L"\"" + exe + L"\" ";
    cmd += format ? (std::wstring(L"--to ") + format) : std::wstring(L"--gui");
    cmd += L" --list \"" + list + L"\"";

    STARTUPINFOW si{sizeof(si)};
    PROCESS_INFORMATION pi{};
    std::vector<wchar_t> mutableCmd(cmd.begin(), cmd.end());
    mutableCmd.push_back(L'\0');
    if (!CreateProcessW(exe.c_str(), mutableCmd.data(), nullptr, nullptr, FALSE, 0, nullptr,
                        ModuleDir().c_str(), &si, &pi))
        return HRESULT_FROM_WIN32(GetLastError());
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return S_OK;
}

// ---- COM plumbing --------------------------------------------------------------------------

template <class T, class Iface>
class ComBase : public Iface {
public:
    ComBase() { ++g_objects; }
    virtual ~ComBase() { --g_objects; }
    IFACEMETHODIMP_(ULONG) AddRef() override { return ++refs_; }
    IFACEMETHODIMP_(ULONG) Release() override {
        ULONG r = --refs_;
        if (r == 0) delete static_cast<T*>(this);
        return r;
    }
    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        if (riid == IID_IUnknown || riid == __uuidof(Iface)) {
            *ppv = static_cast<Iface*>(this);
            AddRef();
            return S_OK;
        }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }
private:
    std::atomic<ULONG> refs_{1};
};

class SubCommand : public ComBase<SubCommand, IExplorerCommand> {
public:
    explicit SubCommand(int index) : index_(index) {}
    IFACEMETHODIMP GetTitle(IShellItemArray*, PWSTR* name) override {
        return SHStrDupW(index_ == kMoreOptions ? L"More options..." : kFormats[index_].label, name);
    }
    IFACEMETHODIMP GetIcon(IShellItemArray*, PWSTR* icon) override { *icon = nullptr; return E_NOTIMPL; }
    IFACEMETHODIMP GetToolTip(IShellItemArray*, PWSTR* tip) override { *tip = nullptr; return E_NOTIMPL; }
    IFACEMETHODIMP GetCanonicalName(GUID* guid) override { *guid = GUID_NULL; return S_OK; }
    IFACEMETHODIMP GetState(IShellItemArray*, BOOL, EXPCMDSTATE* state) override {
        *state = ECS_ENABLED;
        return S_OK;
    }
    IFACEMETHODIMP Invoke(IShellItemArray* items, IBindCtx*) override {
        return Launch(index_ == kMoreOptions ? nullptr : kFormats[index_].id, items);
    }
    IFACEMETHODIMP GetFlags(EXPCMDFLAGS* flags) override {
        *flags = index_ == kMoreOptions ? ECF_SEPARATORBEFORE : ECF_DEFAULT;
        return S_OK;
    }
    IFACEMETHODIMP EnumSubCommands(IEnumExplorerCommand** e) override { *e = nullptr; return E_NOTIMPL; }
private:
    int index_;
};

class EnumCommands : public ComBase<EnumCommands, IEnumExplorerCommand> {
public:
    IFACEMETHODIMP Next(ULONG count, IExplorerCommand** out, ULONG* fetched) override {
        ULONG n = 0;
        while (n < count && pos_ <= kFormatCount) {
            out[n++] = new SubCommand(pos_ == kFormatCount ? kMoreOptions : pos_);
            ++pos_;
        }
        if (fetched) *fetched = n;
        return n == count ? S_OK : S_FALSE;
    }
    IFACEMETHODIMP Skip(ULONG count) override { pos_ += count; return S_OK; }
    IFACEMETHODIMP Reset() override { pos_ = 0; return S_OK; }
    IFACEMETHODIMP Clone(IEnumExplorerCommand** out) override {
        auto* c = new EnumCommands();
        c->pos_ = pos_;
        *out = c;
        return S_OK;
    }
private:
    ULONG pos_ = 0;
};

class RootCommand : public ComBase<RootCommand, IExplorerCommand> {
public:
    IFACEMETHODIMP GetTitle(IShellItemArray*, PWSTR* name) override { return SHStrDupW(L"Convert to", name); }
    IFACEMETHODIMP GetIcon(IShellItemArray*, PWSTR* icon) override {
        std::wstring p = ModuleDir() + L"\\DotFlip.exe,0";
        return SHStrDupW(p.c_str(), icon);
    }
    IFACEMETHODIMP GetToolTip(IShellItemArray*, PWSTR* tip) override { *tip = nullptr; return E_NOTIMPL; }
    IFACEMETHODIMP GetCanonicalName(GUID* guid) override { *guid = CLSID_DotFlipCommand; return S_OK; }
    IFACEMETHODIMP GetState(IShellItemArray* items, BOOL, EXPCMDSTATE* state) override {
        *state = ECS_HIDDEN;
        std::vector<std::wstring> paths = SelectedPaths(items);
        if (paths.empty()) return S_OK;
        for (auto& p : paths)
            if (!IsReadable(p)) return S_OK;  // hide unless every selected file is an image we read
        *state = ECS_ENABLED;
        return S_OK;
    }
    IFACEMETHODIMP Invoke(IShellItemArray*, IBindCtx*) override { return E_NOTIMPL; }
    IFACEMETHODIMP GetFlags(EXPCMDFLAGS* flags) override { *flags = ECF_HASSUBCOMMANDS; return S_OK; }
    IFACEMETHODIMP EnumSubCommands(IEnumExplorerCommand** e) override {
        *e = new EnumCommands();
        return S_OK;
    }
};

class Factory : public IClassFactory {
public:
    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (riid == IID_IUnknown || riid == IID_IClassFactory) {
            *ppv = static_cast<IClassFactory*>(this);
            AddRef();
            return S_OK;
        }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }
    IFACEMETHODIMP_(ULONG) AddRef() override { return 2; }   // static lifetime
    IFACEMETHODIMP_(ULONG) Release() override { return 1; }
    IFACEMETHODIMP CreateInstance(IUnknown* outer, REFIID riid, void** ppv) override {
        if (outer) return CLASS_E_NOAGGREGATION;
        auto* cmd = new (std::nothrow) RootCommand();
        if (!cmd) return E_OUTOFMEMORY;
        HRESULT hr = cmd->QueryInterface(riid, ppv);
        cmd->Release();
        return hr;
    }
    IFACEMETHODIMP LockServer(BOOL lock) override { lock ? ++g_objects : --g_objects; return S_OK; }
};

static Factory g_factory;

STDAPI DllGetClassObject(REFCLSID clsid, REFIID riid, void** ppv) {
    if (clsid == CLSID_DotFlipCommand) return g_factory.QueryInterface(riid, ppv);
    *ppv = nullptr;
    return CLASS_E_CLASSNOTAVAILABLE;
}

STDAPI DllCanUnloadNow() { return g_objects.load() == 0 ? S_OK : S_FALSE; }

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        g_module = module;
        DisableThreadLibraryCalls(module);
    }
    return TRUE;
}
