"""Command line entry point. The Explorer context menu calls this."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core.batch import run_batch
from .core.convert import ConvertOptions
from .core.formats import FORMATS, WRITABLE, get_format


def _collect(paths) -> list[Path]:
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files.extend(sorted(x for x in p.iterdir() if x.is_file()))
        else:
            files.append(p)
    return files


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dotflip", description="Convert images between formats.")
    p.add_argument("files", nargs="*", type=Path)
    p.add_argument("--to", "-t", help="target format: " + ", ".join(f.name for f in WRITABLE))
    p.add_argument("--quality", type=int, help="quality for JPEG/WebP/AVIF")
    p.add_argument("--resize-percent", type=float)
    p.add_argument("--max-size", metavar="WxH", help="fit within WxH, keeping aspect ratio (never upscales)")
    p.add_argument("--background", default="#ffffff", help="color used when flattening transparency")
    p.add_argument("--strip-metadata", action="store_true")
    p.add_argument("--out", type=Path, help="output folder (default: next to source)")
    p.add_argument("--name", default="{name}", help="filename template, e.g. {name}_converted")
    p.add_argument("--on-conflict", choices=["rename", "overwrite", "skip"], default="rename")
    p.add_argument("--delete-original", action="store_true")
    p.add_argument("--gui", action="store_true", help="open the GUI with these files preloaded")
    p.add_argument("--list-formats", action="store_true")
    p.add_argument("--collect", action="store_true", help="merge parallel launches from Explorer multi-select")
    p.add_argument("--list", type=Path, metavar="FILE", help="read input paths (UTF-8, one per line) from FILE, then delete it")
    p.add_argument("--register", action="store_true", help="install the Explorer right-click menu")
    p.add_argument("--unregister", action="store_true", help="remove the Explorer right-click menu")
    p.add_argument("--quiet", "-q", action="store_true")
    return p


def _hex(s: str) -> tuple:
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def main(argv=None) -> int:
    if sys.stdout is None or sys.stderr is None:  # windowed exe has no console
        sys.stdout = sys.stderr = open("nul", "w")
    args = build_parser().parse_args(argv)

    if args.list_formats:
        for f in FORMATS.values():
            print(f"{f.name:6} {'read/write' if f.writable else 'read only'}  {' '.join(f.read_extensions)}")
        return 0
    if args.list:  # used by the Windows 11 shell extension, which hands over the whole selection at once
        try:
            args.files += [Path(l) for l in args.list.read_text(encoding="utf-8").splitlines() if l.strip()]
        finally:
            args.list.unlink(missing_ok=True)
    if args.register or args.unregister:
        from .shell import register

        n = register.install() if args.register else register.uninstall()
        print(f"Context menu {'installed for' if args.register else 'removed from'} {n} file types.")
        return 0
    if args.collect:
        from .shell.collector import collect

        merged = collect([f"{'gui' if args.gui else args.to}\t{f}" for f in args.files])
        if merged is None:
            return 0  # another process is handling the whole selection
        args.files = [Path(m.split("\t", 1)[1]) for m in merged]
        args.quiet = True
    if args.gui or not args.to:
        from .gui.app import main as gui_main

        return gui_main([str(f) for f in args.files])

    try:
        get_format(args.to)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2

    fmt_opts = {}
    if args.quality is not None:
        fmt_opts["quality"] = args.quality
    resize = None
    if args.resize_percent:
        resize = ("percent", args.resize_percent)
    elif args.max_size:
        w, _, h = args.max_size.lower().partition("x")
        resize = ("fit", (int(w or 0) or None, int(h or 0) or None))

    opts = ConvertOptions(
        target=args.to, format_options=fmt_opts, resize=resize, background=_hex(args.background),
        keep_metadata=not args.strip_metadata, output_dir=args.out, name_template=args.name,
        collision=args.on_conflict, delete_original=args.delete_original,
    )
    files = _collect(args.files)
    if not files:
        print("No input files.", file=sys.stderr)
        return 2

    def progress(done, total, r):
        if args.quiet:
            return
        if r.error:
            print(f"[{done}/{total}] FAILED {r.source.name}: {r.error}", file=sys.stderr)
        elif r.skipped:
            print(f"[{done}/{total}] skipped {r.source.name}")
        else:
            print(f"[{done}/{total}] {r.source.name} -> {r.output.name}")

    results = run_batch(files, opts, on_progress=progress)
    failed = [r for r in results if not r.ok]
    if failed and (args.collect or args.list):  # launched without a console, so surface errors in a dialog
        import ctypes

        text = "\n".join(f"{r.source.name}: {r.error}" for r in failed[:10])
        ctypes.windll.user32.MessageBoxW(0, text, f"dot.Flip: {len(failed)} failed", 0x10)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
