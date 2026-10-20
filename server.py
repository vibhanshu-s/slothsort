"""SlothSort: a local-first file tidy-up assistant powered by Ollama."""
from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("SLOTHSORT_MODEL", "gemma3:1b")
MAX_FILES = 120
ALLOWED_CATEGORIES = {"Documents", "Images", "Audio", "Video", "Archives", "Code", "Spreadsheets", "Design", "Other"}
scans: dict[str, dict] = {}
operations: dict[str, dict] = {}


def ollama_json(path: str, payload: dict | None = None, timeout: int = 20) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(f"{OLLAMA_URL}{path}", data=data, headers={"Content-Type": "application/json"} if data else {})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def model_names() -> list[str]:
    try:
        payload = ollama_json("/api/tags", timeout=3)
        return sorted({model["name"] for model in payload.get("models", []) if model.get("name")})
    except (OSError, URLError, HTTPError, ValueError):
        return []


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(body)


def safe_filename(name: str, original: str) -> str:
    """Keep an AI suggestion to one safe filename and preserve the original extension."""
    name = str(name or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", name).strip(" .")[:150]
    original_suffix = Path(original).suffix
    if not name or name in {".", ".."}:
        return original
    if Path(name).suffix.casefold() != original_suffix.casefold():
        return original
    stem = Path(name).stem.strip(" .")
    if not stem or stem.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        return original
    return stem + original_suffix


def fallback_category(filename: str) -> str:
    ext = Path(filename).suffix.casefold()
    if ext in {".pdf", ".doc", ".docx", ".txt", ".rtf", ".md"}: return "Documents"
    if ext in {".xls", ".xlsx", ".csv", ".ods"}: return "Spreadsheets"
    if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp"}: return "Images"
    if ext in {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg"}: return "Audio"
    if ext in {".mp4", ".mov", ".mkv", ".avi", ".webm"}: return "Video"
    if ext in {".zip", ".7z", ".rar", ".tar", ".gz"}: return "Archives"
    if ext in {".py", ".js", ".ts", ".html", ".css", ".json", ".java", ".cpp", ".go", ".rs"}: return "Code"
    if ext in {".psd", ".ai", ".fig", ".sketch", ".svg"}: return "Design"
    return "Other"


def conservative_filename(filename: str) -> str:
    """Remove only obvious trailing copy/version markers if the model omits an item."""
    suffix = Path(filename).suffix
    stem = Path(filename).stem
    cleaned = re.sub(r"(?:[\s._-]+(?:copy(?:[\s_-]?\d+)?|final(?:[\s_-]?\d+)?|draft|duplicate(?:[\s_-]?\d+)?|v\d+(?:\.\d+)*|\(\d+\)))+$", "", stem, flags=re.IGNORECASE).strip(" ._-")
    cleaned = re.sub(r"[\s_]+", "-", cleaned)
    cleaned = re.sub(r"-+", "-", cleaned)
    return (cleaned or stem) + suffix


class Handler(BaseHTTPRequestHandler):
    server_version = "SlothSort/1.0"
    sys_version = ""

    def log_message(self, fmt: str, *args) -> None:
        # Avoid writing private folder paths and filenames to the terminal log.
        print(f"{self.log_date_time_string()} {self.command} {self.path.split('?')[0]}")

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        super().end_headers()

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Invalid request length.")
        if length < 2 or length > 200_000:
            raise ValueError("Request body is empty or too large.")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object.")
        return payload

    def _check_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:  # CLI requests have no browser origin.
            return True
        parsed = urlsplit(origin)
        host = self.headers.get("Host", "")
        return parsed.scheme == "http" and parsed.netloc.casefold() == host.casefold() and parsed.hostname in {"127.0.0.1", "localhost", "::1"}

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/api/health":
            models = model_names()
            home = Path.home() / "Downloads"
            json_response(self, 200, {"models": models, "default_model": DEFAULT_MODEL, "suggested_folder": str(home) if home.is_dir() else str(Path.home())})
            return
        self._serve_static(parsed.path)

    def _serve_static(self, raw_path: str) -> None:
        path = unquote(raw_path)
        if path in {"", "/"}:
            path = "/index.html"
        target = (BASE_DIR / path.lstrip("/")).resolve()
        if BASE_DIR not in target.parents and target != BASE_DIR:
            self.send_error(403)
            return
        if not target.is_file():
            self.send_error(404)
            return
        content = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix == ".svg": content_type = "image/svg+xml"
        if target.suffix in {".html", ".css", ".js", ".md"}: content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        if not self._check_origin():
            json_response(self, 403, {"error": "Requests must come from this local SlothSort page."})
            return
        try:
            payload = self._read_json()
            route = urlsplit(self.path).path
            if route == "/api/scan": result = self._scan(payload)
            elif route == "/api/plan": result = self._plan(payload)
            elif route == "/api/apply": result = self._apply(payload)
            elif route == "/api/undo": result = self._undo(payload)
            else:
                json_response(self, 404, {"error": "Unknown endpoint."})
                return
            json_response(self, 200, result)
        except FileNotFoundError as exc:
            json_response(self, 404, {"error": str(exc) or "That folder or file could not be found."})
        except PermissionError as exc:
            json_response(self, 403, {"error": str(exc) or "SlothSort does not have permission to access that location."})
        except FileExistsError as exc:
            json_response(self, 409, {"error": str(exc) or "A destination already exists. Nothing was moved."})
        except (ValueError, KeyError) as exc:
            json_response(self, 400, {"error": str(exc) or "The request could not be understood."})
        except (URLError, HTTPError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            json_response(self, 503, {"error": f"Local AI or file operation unavailable: {reason}. Start Ollama and make sure the selected model is installed."})
        except Exception as exc:
            json_response(self, 500, {"error": f"SlothSort hit a snag: {exc}"})

    def _scan(self, payload: dict) -> dict:
        raw = str(payload.get("path", "")).strip()
        if not raw:
            raise ValueError("Enter the full path to a folder.")
        folder = Path(raw).expanduser().resolve(strict=True)
        if not folder.is_dir():
            raise ValueError("That path is not a folder.")
        items = []
        with os.scandir(folder) as entries:
            for entry in entries:
                if entry.name.startswith(".") or entry.name.casefold() == "desktop.ini":
                    continue
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    stat = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                item_id = uuid.uuid4().hex[:12]
                items.append({"id": item_id, "original": entry.name, "bytes": stat.st_size, "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(), "mtime_ns": stat.st_mtime_ns, "category": fallback_category(entry.name)})
                if len(items) >= MAX_FILES:
                    break
        items.sort(key=lambda item: item["original"].casefold())
        scan_id = uuid.uuid4().hex
        scans[scan_id] = {"folder": folder, "items": {item["id"]: item for item in items}, "plan": {}}
        return {"scan_id": scan_id, "items": items, "limit": MAX_FILES}

    def _plan(self, payload: dict) -> dict:
        scan_id = str(payload.get("scan_id", ""))
        scan = scans.get(scan_id)
        if not scan: raise ValueError("That scan has expired. Scan the folder again.")
        model = str(payload.get("model", DEFAULT_MODEL)).strip()
        installed = model_names()
        if model not in installed:
            raise ValueError("That model is not installed in Ollama. Choose an installed model or pull Gemma 3 1B first.")
        files = list(scan["items"].values())
        input_rows = [{"id": f["id"], "filename": f["original"], "extension": Path(f["original"]).suffix} for f in files]
        example_in = [{"id": "A", "filename": "meeting-notes FINAL v3.txt", "extension": ".txt"}, {"id": "B", "filename": "IMG_2042 copy.jpg", "extension": ".jpg"}]
        example_out = {"items": [{"id": "A", "new_name": "meeting-notes.txt"}, {"id": "B", "new_name": "IMG_2042.jpg"}]}
        prompt = (
            "You clean up filenames. For each input file, remove an obvious trailing copy or version marker when present. "
            "Otherwise keep the filename unchanged. Never invent file contents, change extensions, or change the IDs. "
            "Return one item for every input ID, exactly once. Return JSON only with this shape: "
            "{\"items\":[{\"id\":\"same id\",\"new_name\":\"filename with same extension\"}]}. "
            "Example input: " + json.dumps(example_in) + " Example output: " + json.dumps(example_out) +
            "\nNow clean this list. Include every ID and no paths:\n" + json.dumps(input_rows, ensure_ascii=False)
        )
        reply = ollama_json("/api/chat", {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False, "format": "json", "options": {"temperature": 0.15}}, timeout=180)
        content = reply.get("message", {}).get("content", "")
        decoded = json.loads(content)
        suggestions = decoded.get("items", []) if isinstance(decoded, dict) else []
        by_id = {str(item.get("id")): item for item in suggestions if isinstance(item, dict)}
        plan = {}
        for record in files:
            suggestion = by_id.get(record["id"], {})
            fallback_name = conservative_filename(record["original"])
            model_name = safe_filename(suggestion.get("new_name", record["original"]), record["original"])
            new_name = fallback_name if model_name == record["original"] else model_name
            marker_removed = re.sub(r"(?:[\s._-]+(?:copy(?:[\s_-]?\d+)?|final(?:[\s_-]?\d+)?|draft|duplicate(?:[\s_-]?\d+)?|v\d+(?:\.\d+)*|\(\d+\)))+$", "", Path(record["original"]).stem, flags=re.IGNORECASE).strip(" ._-") != Path(record["original"]).stem
            if new_name != record["original"] and marker_removed and fallback_name == new_name:
                reason = "Removed a trailing copy or version marker."
            elif new_name != record["original"] and fallback_name == new_name:
                reason = "Made spacing easier to scan."
            elif new_name != record["original"]:
                reason = "Suggested a simpler name from the filename."
            else:
                reason = "No clear cleanup needed; the name stays as it is."
            plan[record["id"]] = {"id": record["id"], "original": record["original"], "bytes": record["bytes"], "category": record["category"], "new_name": new_name, "reason": reason}
        scan["plan"] = plan
        return {"model": model, "items": list(plan.values())}

    def _apply(self, payload: dict) -> dict:
        scan_id = str(payload.get("scan_id", ""))
        scan = scans.get(scan_id)
        if not scan or not scan.get("plan"): raise ValueError("No current plan was found. Scan and plan the folder again.")
        selected = payload.get("selected")
        if not isinstance(selected, list) or not selected: raise ValueError("Select at least one file.")
        selected = {str(item) for item in selected}
        if not selected.issubset(scan["plan"]): raise ValueError("The selection doesn't match this scan. Start again.")
        moves = []
        destinations = set()
        for item_id in selected:
            planned = scan["plan"][item_id]
            original = scan["items"][item_id]
            src = scan["folder"] / original["original"]
            try: stat = src.lstat()
            except FileNotFoundError: raise FileNotFoundError(f"{original['original']} is no longer in the folder. Scan again before applying.")
            if src.is_symlink() or not src.is_file(): raise ValueError(f"{original['original']} is no longer a regular file. Nothing was moved.")
            if stat.st_size != original["bytes"] or stat.st_mtime_ns != original["mtime_ns"]:
                raise ValueError(f"{original['original']} changed since the scan. Nothing was moved; scan again.")
            folder_name = planned["category"]
            dest = scan["folder"] / folder_name / safe_filename(planned["new_name"], original["original"])
            if dest == src: continue
            norm = os.path.normcase(str(dest))
            if norm in destinations or dest.exists(): raise FileExistsError(f"A file already exists at {folder_name}/{dest.name}. Rename it or scan again.")
            destinations.add(norm)
            moves.append((src, dest))
        if not moves:
            return {"message": "Everything selected is already in its suggested place. No files needed moving."}
        completed = []
        created_dirs = []
        try:
            for src, dest in moves:
                if not dest.parent.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    created_dirs.append(dest.parent)
                shutil.move(str(src), str(dest))
                completed.append({"original": str(src), "tidied": str(dest)})
        except Exception:
            for move in reversed(completed):
                try: shutil.move(move["tidied"], move["original"])
                except OSError: pass
            for directory in reversed(created_dirs):
                try: directory.rmdir()
                except OSError: pass
            raise
        op_id = uuid.uuid4().hex
        operations[op_id] = {"moves": completed}
        return {"operation_id": op_id, "message": f"Tidied {len(completed)} {('file' if len(completed) == 1 else 'files')}. You can undo this pass while SlothSort stays open."}

    def _undo(self, payload: dict) -> dict:
        op_id = str(payload.get("operation_id", ""))
        operation = operations.get(op_id)
        if not operation: raise ValueError("That undo has expired. Undo is available until you close the local app.")
        for move in operation["moves"]:
            current, original = Path(move["tidied"]), Path(move["original"])
            if not current.exists(): raise FileNotFoundError(f"{current.name} could not be found. No files were restored.")
            if original.exists(): raise FileExistsError(f"{original.name} already exists in the original folder. Nothing was restored.")
        restored = []
        try:
            for move in reversed(operation["moves"]):
                shutil.move(move["tidied"], move["original"])
                restored.append(move)
        except Exception:
            for move in reversed(restored):
                try: shutil.move(move["original"], move["tidied"])
                except OSError: pass
            raise
        del operations[op_id]
        return {"message": f"Restored {len(restored)} {('file' if len(restored) == 1 else 'files')} to the original folder."}


def main() -> None:
    host, port = "127.0.0.1", int(os.environ.get("SLOTHSORT_PORT", "8080"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"SlothSort is ready at http://{host}:{port}")
    print("Local AI only: file names and metadata are sent to Ollama on this computer. File contents are never read.")
    print("Press Ctrl+C to stop. The app binds to localhost only.")
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nSlothSort is closed.")
    finally: server.server_close()


if __name__ == "__main__":
    main()
