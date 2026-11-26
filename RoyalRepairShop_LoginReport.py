import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import sqlite3
from pathlib import Path
from datetime import date, datetime
import hashlib
import secrets
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
import webbrowser
import html
import shutil

APP_VERSION = "1.0.4"  # نسخه‌ای که به کاربر نمایش داده می‌شود
UPDATE_VERSION = "1.3.5"  # نسخه داخلی و پیوسته برای مقایسه آپدیت‌ها
UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/asheghankoohestan-byte/RoyalRepairv4/main/version.json?v=1.3.5"
BASE_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
DB = BASE_DIR / "tamirat.db"


def gregorian_to_jalali(gy, gm, gd):
    """Convert Gregorian date to Jalali date."""
    g_days_in_month = [31, 29 if (gy % 4 == 0 and (gy % 100 != 0 or gy % 400 == 0)) else 28,
                       31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    j_days_in_month = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]
    gy2 = gy - 1600
    gm2 = gm - 1
    gd2 = gd - 1
    g_day_no = 365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
    for i in range(gm2):
        g_day_no += g_days_in_month[i]
    g_day_no += gd2
    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365
    for i, days in enumerate(j_days_in_month):
        if j_day_no < days:
            jm = i + 1
            jd = j_day_no + 1
            break
        j_day_no -= days
    return jy, jm, jd


def jalali_today():
    today = date.today()
    jy, jm, jd = gregorian_to_jalali(today.year, today.month, today.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d}"



def backup_database():
    """Create a consistent SQLite backup; return True only when verified."""
    if not DB.exists():
        messagebox.showerror("پشتیبان‌گیری", "فایل پایگاه داده پیدا نشد.")
        return False
    jy, jm, jd = gregorian_to_jalali(date.today().year, date.today().month, date.today().day)
    stamp = datetime.now().strftime("%H-%M-%S")
    suggested = f"tamirat_{jy:04d}-{jm:02d}-{jd:02d}_{stamp}.db"
    backup_dir = DB.parent / "پشتیبان‌ها"
    backup_dir.mkdir(exist_ok=True)
    target = filedialog.asksaveasfilename(
        parent=root, title="ذخیره نسخه پشتیبان",
        initialdir=str(backup_dir), initialfile=suggested,
        defaultextension=".db",
        filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")]
    )
    if not target:
        return False
    target_path = Path(target)
    if target_path.resolve() == DB.resolve():
        messagebox.showerror("پشتیبان‌گیری", "محل ذخیره نمی‌تواند خود فایل پایگاه داده اصلی باشد.")
        return False
    try:
        with sqlite3.connect(DB) as source, sqlite3.connect(target_path) as destination:
            source.backup(destination)
        # Verify that the newly written backup is a readable SQLite database.
        with sqlite3.connect(f"file:{target_path.resolve().as_posix()}?mode=ro", uri=True) as check:
            result = check.execute("PRAGMA quick_check").fetchone()
            if not result or result[0] != "ok":
                raise sqlite3.DatabaseError("بررسی سلامت فایل پشتیبان موفق نبود.")
        messagebox.showinfo("پشتیبان‌گیری موفق",
                            f"نسخه پشتیبان با تاریخ شمسی ذخیره و بررسی شد:\n{target_path}")
        return True
    except Exception as exc:
        messagebox.showerror("خطا در پشتیبان‌گیری", str(exc))
        return False


def handle_window_close():
    """Ask whether to back up before closing; never close on backup cancel/failure."""
    choice = messagebox.askyesnocancel(
        "خروج از برنامه",
        "پیش از خروج، از اطلاعات برنامه نسخه پشتیبان تهیه شود؟\n\n"
        "بله: تهیه پشتیبان و سپس خروج\n"
        "خیر: خروج بدون پشتیبان‌گیری\n"
        "لغو: بازگشت به برنامه"
    )
    if choice is None:
        return
    if choice is True and not backup_database():
        # The user cancelled the save dialog or backup failed; keep the app open.
        return
    root.destroy()

def restore_database():
    """Restore a selected SQLite backup; first preserve the current database."""
    (DB.parent / "پشتیبان‌ها").mkdir(exist_ok=True)
    selected = filedialog.askopenfilename(
        parent=root, title="انتخاب فایل پشتیبان برای بازیابی",
        initialdir=str(DB.parent / "پشتیبان‌ها"),
        filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")]
    )
    if not selected:
        return
    backup_path = Path(selected)
    if backup_path.resolve() == DB.resolve():
        messagebox.showwarning("بازیابی", "فایل انتخاب‌شده همان پایگاه داده فعلی است.")
        return
    if not messagebox.askyesno(
        "تأیید بازیابی",
        "با بازیابی، اطلاعات فعلی با اطلاعات فایل پشتیبان جایگزین می‌شود.\\n"
        "قبل از جایگزینی، یک نسخه اضطراری از اطلاعات فعلی ساخته می‌شود. ادامه می‌دهید؟"
    ):
        return
    try:
        # Validate that the selected file is a readable SQLite database.
        with sqlite3.connect(f"file:{backup_path.as_posix()}?mode=ro", uri=True) as check:
            result = check.execute("PRAGMA quick_check").fetchone()
            if not result or result[0] != "ok":
                raise sqlite3.DatabaseError("فایل پشتیبان سالم نیست.")
        # Preserve the current database with a Jalali date before restoring.
        if DB.exists():
            jy, jm, jd = gregorian_to_jalali(date.today().year, date.today().month, date.today().day)
            stamp = datetime.now().strftime("%H-%M-%S")
            safety_copy = DB.parent / f"tamirat_before_restore_{jy:04d}-{jm:02d}-{jd:02d}_{stamp}.db"
            with sqlite3.connect(DB) as current, sqlite3.connect(safety_copy) as safe:
                current.backup(safe)
        with sqlite3.connect(backup_path) as source, sqlite3.connect(DB) as destination:
            source.backup(destination)
        refresh_table()
        refresh_inventory()
        refresh_repair_part_choices()
        refresh_device_repairs()
        if "refresh_replacements" in globals():
            refresh_replacements()
        messagebox.showinfo("بازیابی موفق",
                            "اطلاعات با موفقیت بازیابی شد. نسخه قبلی نیز جداگانه نگهداری شده است.")
    except Exception as exc:
        messagebox.showerror("خطا در بازیابی", f"بازیابی انجام نشد:\\n{exc}")



def _version_parts(value):
    """Convert a dotted version string into comparable integer parts."""
    try:
        return tuple(int(part) for part in str(value).strip().split("."))
    except (TypeError, ValueError):
        raise ValueError("شماره نسخه در فایل انتشار معتبر نیست.")


def _update_state_path():
    # Keep state beside the EXE, not inside PyInstaller temporary _MEI.
    return BASE_DIR / "update_state.json"


def _record_update_check():
    try:
        _update_state_path().write_text(
            json.dumps({"last_check": datetime.now().astimezone().isoformat(timespec="minutes")},
                       ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


def _last_update_check_text():
    try:
        state = json.loads(_update_state_path().read_text(encoding="utf-8"))
        value = state.get("last_check")
        if value:
            return datetime.fromisoformat(value).astimezone().strftime("%Y/%m/%d - %H:%M")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return "هنوز بررسی نشده"



def check_for_updates(show_current=True):
    """Download and safely install a verified Windows EXE update."""
    staged_path = None
    helper_path = None
    try:
        request = urllib.request.Request(
            UPDATE_MANIFEST_URL, headers={"User-Agent": "RoyalRepairShop-Updater"}
        )
        with urllib.request.urlopen(request, timeout=25) as response:
            manifest = json.loads(response.read().decode("utf-8"))

        _record_update_check()
        if "last_update_check_var" in globals():
            last_update_check_var.set("آخرین بررسی: " + _last_update_check_text())

        # نسخه داخلی برای مقایسه آپدیت مستقل از نسخه نمایشی است.
        # فیلد version برای سازگاری با نسخه‌های قدیمی‌تر حفظ می‌شود.
        latest_update = str(
            manifest.get("update_version") or manifest.get("version", "")
        ).strip()
        latest_display = str(
            manifest.get("display_version") or manifest.get("version", "")
        ).strip()
        filename = str(manifest.get("file", "")).strip()
        expected_hash = str(manifest.get("sha256", "")).strip().lower()
        download_url = str(manifest.get("url", "")).strip()
        notes = manifest.get("changelog", [])

        if not latest_update or not latest_display or not filename or Path(filename).name != filename:
            raise ValueError("نام فایل نسخه جدید در version.json معتبر نیست.")
        if not filename.lower().endswith(".exe"):
            raise ValueError("فایل انتشار باید EXE ویندوز باشد، نه فایل PY.")
        if len(expected_hash) != 64 or any(c not in "0123456789abcdef" for c in expected_hash):
            raise ValueError("SHA256 فایل نسخه جدید معتبر نیست.")
        if not download_url.startswith("https://"):
            raise ValueError("آدرس دانلود امن فایل EXE در version.json وجود ندارد.")

        if _version_parts(latest_update) <= _version_parts(UPDATE_VERSION):
            if show_current:
                messagebox.showinfo("به‌روزرسانی", f"برنامه شما به‌روز است. نسخه فعلی: {APP_VERSION}")
            return

        if not getattr(sys, "frozen", False):
            raise RuntimeError("نصب خودکار فقط در نسخه EXE فعال است. ابتدا فایل اجرایی ویندوز را بسازید.")

        app_path = Path(sys.executable).resolve()
        if app_path.suffix.lower() != ".exe" or not app_path.is_file():
            raise RuntimeError("مسیر فایل اجرایی فعلی معتبر نیست.")

        notes_text = "\n".join("• " + str(item) for item in notes) if isinstance(notes, list) else ""
        prompt = (
            f"نسخه فعلی: {APP_VERSION}\nنسخه جدید: {latest_display}\n\n"
            + ("تغییرات این نسخه:\n" + notes_text + "\n\n" if notes_text else "")
            + "ابتدا از اطلاعات تعمیرگاه پشتیبان تهیه می‌شود؛ سپس برنامه بسته و فایل EXE جدید جایگزین خواهد شد. ادامه می‌دهید؟"
        )
        if not messagebox.askyesno("نسخه جدید موجود است", prompt):
            return

        request = urllib.request.Request(download_url, headers={"User-Agent": "RoyalRepairShop-Updater"})
        with urllib.request.urlopen(request, timeout=180) as response:
            new_exe = response.read()

        if not new_exe or new_exe[:2] != b"MZ":
            raise ValueError("فایل دانلودشده یک فایل اجرایی معتبر ویندوز نیست.")
        if hashlib.sha256(new_exe).hexdigest().lower() != expected_hash:
            raise ValueError("بررسی SHA256 ناموفق بود؛ فایل جدید نصب نشد.")

        staged_path = app_path.with_name(app_path.stem + ".update.tmp.exe")
        staged_path.write_bytes(new_exe)
        if hashlib.sha256(staged_path.read_bytes()).hexdigest().lower() != expected_hash:
            raise ValueError("بررسی فایل ذخیره‌شده ناموفق بود.")

        if DB.exists():
            backup_dir = DB.parent / "پشتیبان‌ها"
            backup_dir.mkdir(exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"tamirat_before_update_{stamp}.db"
            with sqlite3.connect(DB) as db_source, sqlite3.connect(backup_path) as db_backup:
                db_source.backup(db_backup)
            with sqlite3.connect(f"file:{backup_path.resolve().as_posix()}?mode=ro", uri=True) as check:
                result = check.execute("PRAGMA quick_check").fetchone()
                if not result or result[0] != "ok":
                    raise sqlite3.DatabaseError("بررسی سلامت نسخه پشتیبان موفق نبود.")

        helper_code = """$ErrorActionPreference = 'Stop'
$processIdToWait = [int]$args[0]
$staged = $args[1]
$target = $args[2]
$backup = "$target.previous.exe"
$log = "$target.update-error.txt"
try {
    while (Get-Process -Id $processIdToWait -ErrorAction SilentlyContinue) {
        Start-Sleep -Milliseconds 500
    }
    if (-not (Test-Path -LiteralPath $staged)) { throw "Staged update file not found: $staged" }
    if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
    if (Test-Path -LiteralPath $target) { Move-Item -LiteralPath $target -Destination $backup -Force }
    try {
        Move-Item -LiteralPath $staged -Destination $target -Force
    } catch {
        if (Test-Path -LiteralPath $backup) { Move-Item -LiteralPath $backup -Destination $target -Force }
        throw
    }
    Start-Process -FilePath $target -WorkingDirectory (Split-Path -Parent $target)
} catch {
    $_ | Out-String | Set-Content -LiteralPath $log -Encoding UTF8
}
try { Remove-Item -LiteralPath $staged -Force -ErrorAction SilentlyContinue } catch {}
try { Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue } catch {}
"""

        fd, helper_name = tempfile.mkstemp(prefix="royal_exe_updater_", suffix=".ps1")
        helper_path = Path(helper_name)
        with os.fdopen(fd, "w", encoding="utf-8-sig") as helper_file:
            helper_file.write(helper_code)

        powershell = os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"),
            "System32", "WindowsPowerShell", "v1.0", "powershell.exe"
        )
        if not Path(powershell).is_file():
            powershell = "powershell.exe"

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
             "-File", str(helper_path), str(os.getpid()), str(staged_path), str(app_path)],
            cwd=str(app_path.parent), creationflags=creation_flags
        )

        messagebox.showinfo(
            "آماده‌سازی به‌روزرسانی",
            "فایل جدید دریافت و بررسی شد و از اطلاعات تعمیرگاه پشتیبان تهیه شد. "
            "برنامه بسته می‌شود؛ پس از بسته‌شدن، نسخه جدید نصب و اجرا خواهد شد."
        )
        root.destroy()

    except Exception as exc:
        if staged_path is not None:
            try:
                staged_path.unlink(missing_ok=True)
            except OSError:
                pass
        if helper_path is not None:
            try:
                helper_path.unlink(missing_ok=True)
            except OSError:
                pass
        messagebox.showerror("خطا در به‌روزرسانی", f"به‌روزرسانی انجام نشد و برنامه فعلی حفظ شد.\n{exc}")



def connect():
    return sqlite3.connect(DB)

def setup_database():
    with connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS repairs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer TEXT NOT NULL DEFAULT '',
                phone TEXT DEFAULT '',
                device TEXT NOT NULL DEFAULT '',
                problem TEXT DEFAULT '',
                status TEXT DEFAULT 'تحویل گرفته شد',
                asset_no TEXT DEFAULT '',
                omid_net_code TEXT DEFAULT '',
                branch TEXT DEFAULT '',
                received_date TEXT DEFAULT ''
            )
        """)
        existing = {row[1] for row in con.execute("PRAGMA table_info(repairs)")}
        new_columns = {
            "asset_no": "TEXT DEFAULT ''",
            "omid_net_code": "TEXT DEFAULT ''",
            "branch": "TEXT DEFAULT ''",
            "received_date": "TEXT DEFAULT ''",
        }
        for name, definition in new_columns.items():
            if name not in existing:
                con.execute(f"ALTER TABLE repairs ADD COLUMN {name} {definition}")
        con.execute("""
            CREATE TABLE IF NOT EXISTS device_repairs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                omid_net_code TEXT NOT NULL,
                device_name TEXT NOT NULL,
                serial_number TEXT DEFAULT '',
                repair_date TEXT DEFAULT '',
                replaced_part TEXT DEFAULT ''
            )
        """)
        repair_columns = {row[1] for row in con.execute("PRAGMA table_info(device_repairs)")}
        if "replaced_quantity" not in repair_columns:
            con.execute("ALTER TABLE device_repairs ADD COLUMN replaced_quantity INTEGER NOT NULL DEFAULT 1")
        con.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                item_code TEXT DEFAULT '',
                category TEXT DEFAULT '',
                quantity INTEGER NOT NULL DEFAULT 0,
                unit TEXT DEFAULT 'عدد',
                min_quantity INTEGER NOT NULL DEFAULT 0
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS device_replacements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                replacement_type TEXT NOT NULL DEFAULT 'موقت',
                device_name TEXT NOT NULL DEFAULT '',
                model TEXT DEFAULT '',
                asset_no TEXT DEFAULT '',
                omid_net_code TEXT DEFAULT '',
                branch_name TEXT DEFAULT '',
                replacement_date TEXT DEFAULT '',
                report TEXT DEFAULT '',
                photo_path TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        replacement_columns = {row[1] for row in con.execute("PRAGMA table_info(device_replacements)")}
        if "branch_name" not in replacement_columns:
            con.execute("ALTER TABLE device_replacements ADD COLUMN branch_name TEXT DEFAULT ''")


# -------------------- احراز هویت و مدیریت کاربران --------------------
CURRENT_USER = {"username": "", "role": "user"}

def _password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 240000
    ).hex()
    return salt, digest

def setup_user_database():
    """افزودن جدول کاربران بدون دست‌زدن به اطلاعات تعمیرات."""
    with connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS app_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # وضعیت قفل ورود جدا از جدول کاربران و به‌صورت ماندگار ذخیره می‌شود.
        con.execute("""
            CREATE TABLE IF NOT EXISTS app_login_security (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT NOT NULL DEFAULT ''
            )
        """)
        con.execute("""
            INSERT OR IGNORE INTO app_login_security(id, failed_attempts, locked_until)
            VALUES (1, 0, '')
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS app_login_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                login_time TEXT NOT NULL,
                result TEXT NOT NULL DEFAULT 'موفق'
            )
        """)
        count = con.execute("SELECT COUNT(*) FROM app_users").fetchone()[0]
        if count == 0:
            salt, digest = _password_hash("admin12345")
            con.execute(
                "INSERT INTO app_users(username,password_salt,password_hash,role) VALUES(?,?,?,?)",
                ("admin", salt, digest, "admin")
            )

def verify_user(username, password):
    with connect() as con:
        row = con.execute(
            "SELECT username,password_salt,password_hash,role FROM app_users WHERE username=?",
            (username.strip(),)
        ).fetchone()
    if not row:
        return None
    _, salt, expected, role = row
    _, actual = _password_hash(password, salt)
    return {"username": row[0], "role": role} if secrets.compare_digest(actual, expected) else None

def _login_security_state():
    with connect() as con:
        row = con.execute(
            "SELECT failed_attempts, locked_until FROM app_login_security WHERE id=1"
        ).fetchone()
    if not row:
        return 0, None
    locked_until = None
    if row[1]:
        try:
            locked_until = datetime.fromisoformat(row[1])
        except ValueError:
            locked_until = None
    return int(row[0]), locked_until

def _record_login_failure():
    with connect() as con:
        row = con.execute(
            "SELECT failed_attempts FROM app_login_security WHERE id=1"
        ).fetchone()
        attempts = (int(row[0]) if row else 0) + 1
        if attempts >= 3:
            until = datetime.now() + __import__("datetime").timedelta(minutes=15)
            con.execute(
                "UPDATE app_login_security SET failed_attempts=3, locked_until=? WHERE id=1",
                (until.isoformat(timespec="seconds"),)
            )
            return 3, until
        con.execute(
            "UPDATE app_login_security SET failed_attempts=?, locked_until='' WHERE id=1",
            (attempts,)
        )
        return attempts, None

def _clear_login_failures():
    with connect() as con:
        con.execute(
            "UPDATE app_login_security SET failed_attempts=0, locked_until='' WHERE id=1"
        )

def show_login():
    """نمایش فرم ورود؛ پس از سه تلاش ناموفق، ورود برای ۱۵ دقیقه قفل می‌شود."""
    login = tk.Toplevel(root)
    login.title("ورود به مدیریت تعمیرگاه رویال")
    login.geometry("360x285")
    login.resizable(False, False)
    login.update_idletasks()
    _lw, _lh = 360, 285
    _lx = max(0, (login.winfo_screenwidth() - _lw) // 2)
    _ly = max(0, (login.winfo_screenheight() - _lh) // 2)
    login.geometry(f"{_lw}x{_lh}+{_lx}+{_ly}")
    login.configure(bg="#eef3fa")
    login.transient(root)
    login.grab_set()
    login.protocol("WM_DELETE_WINDOW", lambda: (login.destroy(), root.destroy()))

    tk.Label(login, text="ROYAL REPAIR SHOP", bg="#eef3fa", fg="#18365c",
             font=("Segoe UI", 14, "bold")).pack(pady=(12, 2))
    tk.Label(login, text="ورود به سامانه مدیریت تعمیرگاه",
             bg="#eef3fa", fg="#53657d", font=(default_font, 9, "bold")).pack(pady=(0, 9))

    panel = tk.Frame(login, bg="white", padx=17, pady=11,
                     highlightbackground="#d5deea", highlightthickness=1)
    panel.pack(fill="x", padx=24)
    tk.Label(panel, text="نام کاربری", bg="white", font=(default_font, 9, "bold")).pack(anchor="e")
    username_var = tk.StringVar(value="admin")
    username_entry = ttk.Entry(panel, textvariable=username_var, justify="right")
    username_entry.pack(fill="x", pady=(2, 6), ipady=2)
    tk.Label(panel, text="رمز عبور", bg="white", font=(default_font, 9, "bold")).pack(anchor="e")
    password_var = tk.StringVar()
    password_entry = ttk.Entry(panel, textvariable=password_var, show="*", justify="right")
    password_entry.pack(fill="x", pady=(2, 4), ipady=2)
    error_var = tk.StringVar()
    tk.Label(panel, textvariable=error_var, bg="white", fg="#c62828",
             font=(default_font, 8)).pack(anchor="e")

    attempts_var = tk.StringVar()
    tk.Label(panel, textvariable=attempts_var, bg="white", fg="#b45309",
             font=(default_font, 8)).pack(anchor="e", pady=(2, 0))

    login_button = ttk.Button(panel, text="ورود به برنامه")
    login_button.pack(fill="x", pady=(5, 0))

    def set_login_locked(locked, remaining=0):
        state = "disabled" if locked else "normal"
        username_entry.configure(state=state)
        password_entry.configure(state=state)
        login_button.configure(state=state)
        if locked:
            minutes = (remaining + 59) // 60
            error_var.set("ورود به برنامه موقتاً قفل شده است.")
            attempts_var.set(f"پس از ۳ بار رمز اشتباه؛ زمان باقی‌مانده: {minutes} دقیقه")
        else:
            error_var.set("")
            attempts_var.set("")

    def update_lock_timer():
        _, locked_until = _login_security_state()
        if locked_until and locked_until > datetime.now():
            remaining = int((locked_until - datetime.now()).total_seconds())
            set_login_locked(True, remaining)
            login.after(1000, update_lock_timer)
        else:
            _clear_login_failures()
            set_login_locked(False)
            password_var.set("")
            password_entry.focus_set()

    def attempt_login(event=None):
        _, locked_until = _login_security_state()
        if locked_until and locked_until > datetime.now():
            remaining = int((locked_until - datetime.now()).total_seconds())
            set_login_locked(True, remaining)
            return

        user = verify_user(username_var.get(), password_var.get())
        if not user:
            attempts, locked_until = _record_login_failure()
            password_var.set("")
            if locked_until:
                set_login_locked(True, 15 * 60)
                update_lock_timer()
                messagebox.showerror(
                    "قفل امنیتی",
                    "سه بار اطلاعات ورود اشتباه وارد شد. برنامه به مدت ۱۵ دقیقه قفل شد.",
                    parent=login
                )
            else:
                left = 3 - attempts
                error_var.set("نام کاربری یا رمز عبور اشتباه است.")
                attempts_var.set(f"تعداد فرصت باقی‌مانده: {left}")
                password_entry.focus_set()
            return

        _clear_login_failures()
        CURRENT_USER.update(user)
        with connect() as con:
            con.execute(
                "INSERT INTO app_login_logs(username, role, login_time, result) VALUES (?, ?, ?, ?)",
                (user["username"], user["role"],
                 datetime.now().astimezone().strftime("%Y/%m/%d  %H:%M:%S"), "موفق")
            )
        login.grab_release()
        login.destroy()
        root.deiconify()

    login_button.configure(command=attempt_login)
    update_lock_timer()
    tk.Label(login, text="ورود اولیه: admin  |  رمز: admin12345",
             bg="#eef3fa", fg="#66758a", font=(default_font, 7)).pack(pady=6)
    password_entry.bind("<Return>", attempt_login)
    username_entry.bind("<Return>", lambda event: password_entry.focus_set())
    username_entry.focus_set()
    root.wait_window(login)
    return bool(CURRENT_USER["username"])

def open_login_report():
    """نمایش سوابق ورود موفق کاربران؛ فقط برای مدیر سیستم."""
    if CURRENT_USER.get("role") != "admin":
        messagebox.showwarning("دسترسی محدود", "فقط مدیر سیستم اجازه مشاهده گزارش ورود را دارد.")
        return

    win = tk.Toplevel(root)
    win.title("گزارش ورود کاربران")
    win.geometry("850x470")
    win.minsize(700, 350)
    win.transient(root)
    win.configure(bg="#f3f6fb")

    header = tk.Frame(win, bg="#f3f6fb")
    header.pack(fill="x", padx=12, pady=10)
    tk.Label(
        header, text="گزارش ورود کاربران",
        bg="#f3f6fb", fg="#17365d", font=(default_font, 12, "bold")
    ).pack(side="right")
    tk.Label(
        header, text="سوابق ورود موفق به برنامه",
        bg="#f3f6fb", fg="#64748b", font=(default_font, 9)
    ).pack(side="left")

    columns = ("id", "username", "role", "time", "result")
    tree = ttk.Treeview(win, columns=columns, show="headings", height=14)
    headings = {
        "id": ("ردیف", 60),
        "username": ("نام کاربری", 160),
        "role": ("سطح دسترسی", 120),
        "time": ("تاریخ و ساعت ورود", 250),
        "result": ("نتیجه", 100),
    }
    for col, (label, width) in headings.items():
        tree.heading(col, text=label, anchor="center")
        tree.column(col, width=width, minwidth=60, anchor="center")

    yscroll = ttk.Scrollbar(win, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=yscroll.set)
    tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=5)
    yscroll.pack(side="right", fill="y", padx=(0, 12), pady=5)

    footer = tk.Frame(win, bg="#f3f6fb")
    footer.pack(fill="x", padx=12, pady=8)
    count_var = tk.StringVar(value="")

    def refresh():
        tree.delete(*tree.get_children())
        with connect() as con:
            rows = con.execute(
                """SELECT id, username, role, login_time, result
                   FROM app_login_logs ORDER BY id DESC"""
            ).fetchall()
        for row in rows:
            tree.insert(
                "", "end",
                values=(row[0], row[1], "مدیر" if row[2] == "admin" else "کاربر",
                        row[3], row[4])
            )
        count_var.set(f"تعداد ورودهای ثبت‌شده: {len(rows)}")

    tk.Label(footer, textvariable=count_var, bg="#f3f6fb",
             fg="#53657d", font=(default_font, 9)).pack(side="right")
    ttk.Button(footer, text="بروزرسانی", command=refresh).pack(side="left", padx=4)
    ttk.Button(footer, text="بستن", command=win.destroy).pack(side="left", padx=4)
    refresh()


def open_user_manager():
    if CURRENT_USER.get("role") != "admin":
        messagebox.showwarning("دسترسی محدود", "فقط مدیر سیستم اجازه مدیریت کاربران را دارد.")
        return

    win = tk.Toplevel(root)
    win.title("مدیریت کاربران")
    win.geometry("590x390")
    win.resizable(False, False)
    win.update_idletasks()
    _ww, _wh = 590, 390
    _wx = max(0, (win.winfo_screenwidth() - _ww) // 2)
    _wy = max(0, (win.winfo_screenheight() - _wh) // 2)
    win.geometry(f"{_ww}x{_wh}+{_wx}+{_wy}")
    win.transient(root)
    win.grab_set()
    win.configure(bg="#f3f6fb")

    tk.Label(win, text="مدیریت کاربران و سطح دسترسی",
             bg="#f3f6fb", fg="#17365d",
             font=(default_font, 11, "bold")).pack(anchor="e", padx=10, pady=7)

    # نوار عملیات در بالای جدول قرار می‌گیرد تا با بزرگ‌شدن جدول پنهان نشود.
    buttons = tk.Frame(win, bg="#f3f6fb")
    buttons.pack(fill="x", padx=10, pady=(2, 7))

    columns = ("id", "username", "role", "created")
    tree = ttk.Treeview(win, columns=columns, show="headings", height=7)
    for col, title, width in [
        ("id", "شناسه", 48), ("username", "نام کاربری", 135),
        ("role", "سطح دسترسی", 95), ("created", "تاریخ ایجاد", 175)
    ]:
        tree.heading(col, text=title)
        tree.column(col, width=width, anchor="center")
    tree.pack(fill="both", expand=True, padx=10, pady=4)

    def refresh_users():
        tree.delete(*tree.get_children())
        with connect() as con:
            rows = con.execute(
                "SELECT id,username,role,created_at FROM app_users ORDER BY id"
            ).fetchall()
        for row in rows:
            role_label = "مدیر" if row[2] == "admin" else "کاربر"
            tree.insert("", "end", values=(row[0], row[1], role_label, row[3]))

    def add_user():
        dialog = tk.Toplevel(win)
        dialog.title("افزودن کاربر جدید")
        dialog.geometry("380x405")
        dialog.resizable(False, False)
        dialog.configure(bg="#f3f6fb")
        dialog.transient(win)
        dialog.grab_set()
        dialog.update_idletasks()
        _dw, _dh = 380, 405
        _dx = max(0, win.winfo_rootx() + (win.winfo_width() - _dw) // 2)
        _dy = max(0, win.winfo_rooty() + (win.winfo_height() - _dh) // 2)
        dialog.geometry(f"{_dw}x{_dh}+{_dx}+{_dy}")

        body = tk.Frame(dialog, bg="white", padx=18, pady=16,
                        highlightbackground="#d5deea", highlightthickness=1)
        body.pack(fill="both", expand=True, padx=12, pady=12)

        fields = {}
        for label, key, is_secret in [
            ("نام کاربری", "username", False),
            ("رمز عبور", "password", True),
            ("تکرار رمز عبور", "confirm", True)
        ]:
            tk.Label(body, text=label, bg="white", fg="#34445a",
                     font=(default_font, 9, "bold")).pack(anchor="e", pady=(7, 3))
            variable = tk.StringVar()
            entry = ttk.Entry(body, textvariable=variable,
                              show="*" if is_secret else "", justify="right")
            entry.pack(fill="x", ipady=4)
            fields[key] = variable

        tk.Label(body, text="سطح دسترسی", bg="white", fg="#34445a",
                 font=(default_font, 9, "bold")).pack(anchor="e", pady=(8, 2))
        role_var = tk.StringVar(value="کاربر")
        role_box = ttk.Combobox(
            body, textvariable=role_var, values=["کاربر", "مدیر"],
            state="readonly", justify="right"
        )
        role_box.pack(fill="x", ipady=3)

        def save():
            username = fields["username"].get().strip()
            password = fields["password"].get()
            confirm = fields["confirm"].get()

            if len(username) < 3:
                messagebox.showwarning(
                    "نام کاربری نامعتبر",
                    "نام کاربری باید حداقل ۳ نویسه داشته باشد.",
                    parent=dialog
                )
                return
            if any(ch.isspace() for ch in username):
                messagebox.showwarning(
                    "نام کاربری نامعتبر",
                    "در نام کاربری فاصله وارد نکنید.",
                    parent=dialog
                )
                return
            if len(password) < 8:
                messagebox.showwarning(
                    "رمز عبور ضعیف",
                    "رمز عبور باید حداقل ۸ نویسه داشته باشد.",
                    parent=dialog
                )
                return
            if password != confirm:
                messagebox.showwarning(
                    "عدم تطابق رمز",
                    "رمز عبور و تکرار آن یکسان نیستند.",
                    parent=dialog
                )
                return

            salt, digest = _password_hash(password)
            db_role = "admin" if role_var.get() == "مدیر" else "user"
            try:
                with connect() as con:
                    con.execute(
                        """INSERT INTO app_users
                           (username, password_salt, password_hash, role)
                           VALUES (?, ?, ?, ?)""",
                        (username, salt, digest, db_role)
                    )
                refresh_users()
                messagebox.showinfo(
                    "ثبت موفق",
                    f"کاربر «{username}» با سطح دسترسی «{role_var.get()}» ایجاد شد.",
                    parent=win
                )
                dialog.grab_release()
                dialog.destroy()
            except sqlite3.IntegrityError:
                messagebox.showerror(
                    "نام کاربری تکراری",
                    "این نام کاربری قبلاً ثبت شده است. نام دیگری انتخاب کنید.",
                    parent=dialog
                )
                fields["username"].set("")
            except (sqlite3.Error, OSError) as exc:
                messagebox.showerror(
                    "خطا در ذخیره کاربر",
                    f"اطلاعات کاربر در پایگاه داده ذخیره نشد:\n{exc}",
                    parent=dialog
                )
            except Exception as exc:
                messagebox.showerror(
                    "خطای غیرمنتظره",
                    f"ایجاد کاربر انجام نشد:\n{exc}",
                    parent=dialog
                )

        actions = tk.Frame(body, bg="white")
        actions.pack(fill="x", pady=(18, 2))
        ttk.Button(actions, text="ذخیره کاربر", command=save).pack(side="right", padx=3)
        ttk.Button(actions, text="انصراف",
                   command=lambda: (dialog.grab_release(), dialog.destroy())).pack(side="left", padx=3)
        fields["username"].set("")
        dialog.bind("<Return>", lambda event: save())
        fields_entry = [w for w in body.winfo_children() if isinstance(w, ttk.Entry)]
        if fields_entry:
            fields_entry[0].focus_set()

    def reset_password():
        selected = tree.selection()
        if not selected:
            messagebox.showinfo("انتخاب کاربر", "ابتدا یک کاربر را انتخاب کنید.", parent=win)
            return
        user_id, username = tree.item(selected[0], "values")[:2]
        new_password = simpledialog.askstring("تغییر رمز عبور", f"رمز عبور جدید برای {username}:",
                                              show="*", parent=win)
        if not new_password:
            return
        if len(new_password) < 8:
            messagebox.showwarning("رمز ضعیف", "رمز عبور باید حداقل ۸ کاراکتر باشد.", parent=win)
            return
        salt, digest = _password_hash(new_password)
        with connect() as con:
            con.execute("UPDATE app_users SET password_salt=?,password_hash=? WHERE id=?",
                        (salt, digest, user_id))
        messagebox.showinfo("انجام شد", "رمز عبور تغییر کرد.", parent=win)


    def change_role():
        selected = tree.selection()
        if not selected:
            messagebox.showinfo("انتخاب کاربر", "ابتدا یک کاربر را انتخاب کنید.", parent=win)
            return
        user_id, username = tree.item(selected[0], "values")[:2]
        if username == CURRENT_USER["username"]:
            messagebox.showwarning(
                "محدودیت امنیتی",
                "برای جلوگیری از قفل‌شدن مدیریت، سطح دسترسی حساب فعلی را از این بخش تغییر ندهید.",
                parent=win
            )
            return

        with connect() as con:
            row = con.execute("SELECT role FROM app_users WHERE id=?", (user_id,)).fetchone()
            admin_count = con.execute(
                "SELECT COUNT(*) FROM app_users WHERE role='admin'"
            ).fetchone()[0]
        if not row:
            refresh_users()
            return

        current_role = row[0]
        dialog = tk.Toplevel(win)
        dialog.title("تغییر سطح دسترسی")
        dialog.geometry("300x155")
        dialog.resizable(False, False)
        dialog.transient(win)
        dialog.grab_set()
        dialog.configure(bg="#f3f6fb")

        tk.Label(
            dialog, text=f"کاربر: {username}", bg="#f3f6fb",
            font=(default_font, 10, "bold")
        ).pack(pady=(15, 7))
        role_var = tk.StringVar(value="مدیر" if current_role == "admin" else "کاربر")
        ttk.Combobox(
            dialog, textvariable=role_var, values=["کاربر", "مدیر"],
            state="readonly", justify="right"
        ).pack(fill="x", padx=22)

        def save_role():
            new_role = "admin" if role_var.get() == "مدیر" else "user"
            if current_role == "admin" and new_role != "admin" and admin_count <= 1:
                messagebox.showwarning(
                    "محدودیت",
                    "حداقل یک مدیر باید در برنامه باقی بماند.",
                    parent=dialog
                )
                return
            try:
                with connect() as con:
                    con.execute("UPDATE app_users SET role=? WHERE id=?", (new_role, user_id))
                refresh_users()
                dialog.grab_release()
                dialog.destroy()
            except sqlite3.Error as exc:
                messagebox.showerror("خطا", f"تغییر سطح دسترسی انجام نشد:\n{exc}", parent=dialog)

        ttk.Button(dialog, text="ذخیره سطح دسترسی", command=save_role).pack(fill="x", padx=22, pady=12)

    def delete_user():
        selected = tree.selection()
        if not selected:
            messagebox.showinfo("انتخاب کاربر", "ابتدا یک کاربر را انتخاب کنید.", parent=win)
            return
        user_id, username = tree.item(selected[0], "values")[:2]
        if username == CURRENT_USER["username"]:
            messagebox.showwarning("محدودیت", "نمی‌توانید حسابی را که با آن وارد شده‌اید حذف کنید.", parent=win)
            return
        if not messagebox.askyesno("حذف کاربر", f"کاربر «{username}» حذف شود؟", parent=win):
            return
        with connect() as con:
            admins = con.execute("SELECT COUNT(*) FROM app_users WHERE role='admin'").fetchone()[0]
            role = con.execute("SELECT role FROM app_users WHERE id=?", (user_id,)).fetchone()
            if role and role[0] == "admin" and admins <= 1:
                messagebox.showwarning("محدودیت", "حداقل یک مدیر باید باقی بماند.", parent=win)
                return
            con.execute("DELETE FROM app_users WHERE id=?", (user_id,))
        refresh_users()

    ttk.Button(buttons, text="+ ایجاد کاربر", command=add_user).pack(side="right", padx=3)
    ttk.Button(buttons, text="تغییر سطح دسترسی", command=change_role).pack(side="right", padx=3)
    ttk.Button(buttons, text="تغییر رمز", command=reset_password).pack(side="right", padx=3)
    ttk.Button(buttons, text="حذف کاربر", command=delete_user).pack(side="right", padx=3)
    refresh_users()

def get_rows(query=""):
    with connect() as con:
        return con.execute("""
            SELECT id, device, asset_no, omid_net_code,
                   branch, received_date, problem, status
            FROM repairs
            WHERE device LIKE ? OR asset_no LIKE ?
               OR omid_net_code LIKE ? OR branch LIKE ? OR problem LIKE ?
            ORDER BY id DESC
        """, tuple([f"%{query}%"] * 5)).fetchall()

def refresh_table():
    for item in table.get_children():
        table.delete(item)
    for row in get_rows(search_var.get().strip()):
        table.insert("", "end", values=row)
    refresh_dashboard()

def refresh_dashboard():
    with connect() as con:
        total = con.execute("SELECT COUNT(*) FROM repairs").fetchone()[0]
        active = con.execute(
            "SELECT COUNT(*) FROM repairs WHERE status IN ('تحویل گرفته شد', 'در حال تعمیر')"
        ).fetchone()[0]
        ready = con.execute(
            "SELECT COUNT(*) FROM repairs WHERE status = 'آماده تحویل'"
        ).fetchone()[0]
        delivered = con.execute(
            "SELECT COUNT(*) FROM repairs WHERE status = 'تحویل داده شد'"
        ).fetchone()[0]
    total_value.set(str(total))
    active_value.set(str(active))
    ready_value.set(str(ready))
    delivered_value.set(str(delivered))

    # Show branches that have devices whose repair is complete or ready.
    if "branch_summary_tree" in globals() and branch_summary_tree.winfo_exists():
        for item in branch_summary_tree.get_children():
            branch_summary_tree.delete(item)
        with connect() as con:
            branch_rows = con.execute("""
                SELECT
                    TRIM(branch) AS branch_name,
                    COUNT(*) AS total_devices,
                    SUM(CASE
                        WHEN TRIM(COALESCE(status, '')) IN ('آماده تحویل', 'تحویل داده شد')
                        THEN 1 ELSE 0
                    END) AS repaired_devices
                FROM repairs
                WHERE TRIM(COALESCE(branch, '')) <> ''
                GROUP BY TRIM(branch)
                ORDER BY total_devices DESC, branch_name COLLATE NOCASE
            """).fetchall()
        for branch_name, total_devices, repaired_devices in branch_rows:
            branch_summary_tree.insert(
                "", "end",
                values=(branch_name, total_devices, repaired_devices or 0)
            )

def add_record():
    data = {
        "device": device_var.get().strip(),
        "asset_no": asset_var.get().strip(),
        "omid_net_code": omid_var.get().strip(),
        "branch": branch_var.get().strip(),
        "received_date": date_var.get().strip(),
        "problem": problem_var.get().strip(),
        "status": status_var.get().strip(),
    }
    if not data["device"]:
        messagebox.showwarning("اطلاعات ناقص", "نام دستگاه را وارد کنید.")
        return
    if data["omid_net_code"]:
        with connect() as con:
            duplicate = con.execute(
                "SELECT 1 FROM repairs WHERE TRIM(omid_net_code) COLLATE NOCASE=? LIMIT 1",
                (data["omid_net_code"],)
            ).fetchone()
        if duplicate:
            messagebox.showwarning(
                "کد تکراری",
                "این کد امید نت قبلاً برای دستگاه دیگری ثبت شده است.\nبرای جلوگیری از ثبت تکراری، کد دیگری وارد کنید."
            )
            return
    with connect() as con:
        con.execute("""
            INSERT INTO repairs
            (device, asset_no, omid_net_code, branch, received_date, problem, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, tuple(data.values()))
    for var in (device_var, problem_var, asset_var, omid_var, branch_var):
        var.set("")
    date_var.set(jalali_today())
    status_var.set("تحویل گرفته شد")
    refresh_table()
    messagebox.showinfo("ثبت شد", "دستگاه با موفقیت ثبت شد.")

def delete_record():
    selected = table.selection()
    if not selected:
        messagebox.showwarning("انتخاب نشده", "ابتدا یک ردیف را انتخاب کنید.")
        return
    record_id = table.item(selected[0], "values")[0]
    if messagebox.askyesno("حذف", "این دستگاه حذف شود؟"):
        with connect() as con:
            con.execute("DELETE FROM repairs WHERE id = ?", (record_id,))
        refresh_table()

def update_status():
    selected = table.selection()
    if not selected:
        messagebox.showwarning("انتخاب نشده", "ابتدا یک ردیف را انتخاب کنید.")
        return
    record_id = table.item(selected[0], "values")[0]
    with connect() as con:
        con.execute("UPDATE repairs SET status = ? WHERE id = ?",
                    (status_var.get(), record_id))
    refresh_table()
    messagebox.showinfo("انجام شد", "وضعیت دستگاه به‌روزرسانی شد.")



def refresh_device_repairs():
    for item in device_repairs_table.get_children():
        device_repairs_table.delete(item)
    code = repair_search_var.get().strip()
    with connect() as con:
        rows = con.execute("""
            SELECT id, omid_net_code, device_name, serial_number, repair_date,
                   replaced_part, replaced_quantity
            FROM device_repairs
            WHERE omid_net_code LIKE ?
            ORDER BY id DESC
        """, (f"%{code}%",)).fetchall()
    for row in rows:
        device_repairs_table.insert("", "end", values=row)


def load_registered_device(*_):
    """Show the device details already registered for the entered Omid Net code."""
    code = repair_omid_var.get().strip()
    if not code:
        registered_device_info_var.set("پس از وارد کردن کد امید نت، اطلاعات دستگاه نمایش داده می‌شود.")
        repair_device_var.set("")
        return
    with connect() as con:
        row = con.execute("""
            SELECT device, asset_no, branch, received_date, problem
            FROM repairs
            WHERE TRIM(omid_net_code) COLLATE NOCASE = ?
            ORDER BY id DESC LIMIT 1
        """, (code,)).fetchone()
    if row:
        repair_device_var.set(row[0] or "")
        registered_device_info_var.set(
            f"دستگاه: {row[0] or '—'}   |   شماره اموال: {row[1] or '—'}   |   "
            f"شعبه: {row[2] or '—'}   |   تاریخ دریافت: {row[3] or '—'}\n"
            f"شرح خرابی ثبت‌شده: {row[4] or '—'}"
        )
    else:
        registered_device_info_var.set("کدی با این مشخصات در بخش ثبت دستگاه‌ها پیدا نشد.")
        repair_device_var.set("")


def find_inventory_part(con, part_text):
    """Find a stock item by its exact displayed name or item code."""
    value = (part_text or "").strip()
    if not value:
        return None
    return con.execute("""
        SELECT id, item_name, item_code, quantity
        FROM inventory
        WHERE TRIM(item_name) COLLATE NOCASE = ?
           OR (TRIM(item_code) <> '' AND TRIM(item_code) COLLATE NOCASE = ?)
        ORDER BY CASE WHEN TRIM(item_name) COLLATE NOCASE = ? THEN 0 ELSE 1 END
        LIMIT 1
    """, (value, value, value)).fetchone()


def refresh_repair_part_choices():
    """Keep the repair part selector synchronized with inventory."""
    with connect() as con:
        rows = con.execute("""
            SELECT item_name, item_code, quantity
            FROM inventory ORDER BY item_name COLLATE NOCASE
        """).fetchall()
    labels = [
        f"{row[0]}  | کد: {row[1] or '—'} | موجودی: {row[2]}"
        for row in rows
    ]
    repair_part_display_to_name.clear()
    repair_part_display_to_name.update({label: row[0] for label, row in zip(labels, rows)})
    if "repair_part_box" in globals():
        repair_part_box.configure(values=labels)


def add_device_repair():
    code = repair_omid_var.get().strip()
    device = repair_device_var.get().strip()
    if not code or not device:
        messagebox.showwarning(
            "اطلاعات ناقص",
            "ابتدا کد امید نت معتبر را وارد کنید تا اطلاعات دستگاه از بخش ثبت دستگاه‌ها بارگذاری شود."
        )
        return
    try:
        quantity = int(repair_quantity_var.get().strip() or "1")
        if quantity < 1:
            raise ValueError
    except ValueError:
        messagebox.showwarning("تعداد نامعتبر", "تعداد قطعات تعویضی باید عدد صحیح بزرگ‌تر از صفر باشد.")
        return
    selected_part = repair_part_var.get().strip()
    part_name = repair_part_display_to_name.get(selected_part, selected_part)
    if not part_name:
        messagebox.showwarning("قطعه انتخاب نشده", "قطعه مورد استفاده را از فهرست موجودی انتخاب کنید.")
        return
    with connect() as con:
        registered = con.execute(
            "SELECT 1 FROM repairs WHERE TRIM(omid_net_code) COLLATE NOCASE=? LIMIT 1",
            (code,)
        ).fetchone()
        if not registered:
            messagebox.showwarning("کد پیدا نشد", "این کد امید نت در بخش ثبت دستگاه‌ها وجود ندارد.")
            return
        stock_item = find_inventory_part(con, part_name)
        if not stock_item:
            messagebox.showwarning("قطعه در انبار نیست", "این قطعه در موجودی انبار ثبت نشده است.")
            return
        if stock_item[3] < quantity:
            messagebox.showwarning("موجودی کافی نیست",
                                   f"موجودی «{stock_item[1]}» فقط {stock_item[3]} عدد است.")
            return
        con.execute("UPDATE inventory SET quantity = quantity - ? WHERE id = ?",
                    (quantity, stock_item[0]))
        con.execute("""
            INSERT INTO device_repairs
            (omid_net_code, device_name, serial_number, repair_date, replaced_part, replaced_quantity)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (code, device, repair_serial_var.get().strip(),
              repair_date_var.get().strip(), part_name, quantity))
    repair_omid_var.set("")
    repair_device_var.set("")
    repair_serial_var.set("")
    repair_date_var.set(jalali_today())
    repair_part_var.set("")
    repair_quantity_var.set("1")
    load_registered_device()
    refresh_device_repairs()
    refresh_inventory()
    refresh_repair_part_choices()
    messagebox.showinfo("ثبت شد", "اطلاعات تعمیر ثبت شد و موجودی قطعه از انبار کسر شد.")

def delete_device_repair():
    selected = device_repairs_table.selection()
    if not selected:
        messagebox.showwarning("انتخاب نشده", "ابتدا یک سابقه تعمیر را انتخاب کنید.")
        return
    repair_id = device_repairs_table.item(selected[0], "values")[0]
    if messagebox.askyesno("حذف سابقه", "سابقه تعمیر انتخاب‌شده حذف شود؟ موجودی قطعه به انبار برمی‌گردد."):
        with connect() as con:
            row = con.execute("SELECT replaced_part, replaced_quantity FROM device_repairs WHERE id = ?",
                              (repair_id,)).fetchone()
            if row:
                stock_item = find_inventory_part(con, row[0])
                if stock_item:
                    con.execute("UPDATE inventory SET quantity = quantity + ? WHERE id = ?",
                                (row[1], stock_item[0]))
            con.execute("DELETE FROM device_repairs WHERE id = ?", (repair_id,))
        refresh_device_repairs()
        refresh_inventory()
        refresh_repair_part_choices()


def refresh_inventory():
    for item in inventory_table.get_children():
        inventory_table.delete(item)
    with connect() as con:
        rows = con.execute("""
            SELECT id, item_name, item_code, category, quantity, unit, min_quantity
            FROM inventory
            ORDER BY CASE WHEN TRIM(COALESCE(item_code, '')) = '' THEN 1 ELSE 0 END,
                     CAST(item_code AS INTEGER) ASC,
                     item_code COLLATE NOCASE ASC
        """).fetchall()
    low_items = [row for row in rows if int(row[4]) == 0]
    # Highlight the most recently registered item (highest database ID),
    # not the numerically largest item_code.
    with connect() as con:
        latest_row = con.execute("""
            SELECT id FROM inventory
            WHERE TRIM(COALESCE(item_code, '')) <> ''
            ORDER BY id DESC LIMIT 1
        """).fetchone()
    latest_item_id = latest_row[0] if latest_row else None
    for row in rows:
        is_low = int(row[4]) <= int(row[6])
        is_latest = latest_item_id is not None and row[0] == latest_item_id
        tags = ("latest_code",) if is_latest else (("low_stock",) if is_low else ())
        inventory_table.insert("", "end", values=row, tags=tags)
    inventory_table.tag_configure("low_stock", foreground="#c00000",
                                  background="#fff0f0")
    inventory_table.tag_configure("latest_code", foreground="#111111",
                                  background="#ffeb3b")
    inventory_count_var.set(str(len(rows)))
    low_stock_var.set(str(len(low_items)))

    # The settings warning list is created with the settings tab.
    if "low_stock_listbox" in globals():
        low_stock_listbox.delete(0, tk.END)
        if low_items:
            for item in low_items:
                low_stock_listbox.insert(
                    tk.END, f"• {item[1]}   |   موجودی: صفر {item[5]}"
                )
        else:
            low_stock_listbox.insert(tk.END, "هیچ کالایی با موجودی صفر وجود ندارد.")


def add_inventory_item():
    name = stock_name_var.get().strip()
    if not name:
        messagebox.showwarning("اطلاعات ناقص", "نام کالا را وارد کنید.")
        return
    try:
        quantity = int(stock_quantity_var.get().strip() or "0")
        minimum = int(stock_min_var.get().strip() or "0")
        if quantity < 0 or minimum < 0:
            raise ValueError
    except ValueError:
        messagebox.showwarning("عدد نامعتبر", "موجودی و حداقل موجودی باید عدد صحیحِ صفر یا بیشتر باشند.")
        return
    item_code = stock_code_var.get().strip()
    if item_code:
        with connect() as con:
            duplicate = con.execute(
                "SELECT 1 FROM inventory WHERE TRIM(item_code) COLLATE NOCASE = ? LIMIT 1",
                (item_code,)
            ).fetchone()
        if duplicate:
            messagebox.showwarning("کد کالای تکراری", "این کد کالا قبلاً در موجودی انبار ثبت شده است. کد یکتایی وارد کنید.")
            return
    with connect() as con:
        con.execute("""
            INSERT INTO inventory (item_name, item_code, category, quantity, unit, min_quantity)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, item_code, stock_category_var.get().strip(),
              quantity, stock_unit_var.get().strip() or "عدد", minimum))
    for var in (stock_name_var, stock_code_var, stock_category_var,
                stock_quantity_var, stock_min_var):
        var.set("")
    stock_unit_var.set("عدد")
    refresh_inventory()
    messagebox.showinfo("ثبت شد", "کالا به موجودی انبار اضافه شد.")


def change_stock(amount):
    selected = inventory_table.selection()
    if not selected:
        messagebox.showwarning("انتخاب نشده", "ابتدا یک کالا را از فهرست انتخاب کنید.")
        return
    values = inventory_table.item(selected[0], "values")
    item_id, name, code, category, current, unit, minimum = values
    count = simpledialog.askinteger(
        "تغییر موجودی",
        f"تعداد {('افزایش' if amount > 0 else 'کاهش')} برای «{name}» را وارد کنید:",
        parent=root, minvalue=1
    )
    if count is None:
        return
    new_quantity = int(current) + amount * count
    if new_quantity < 0:
        messagebox.showwarning("موجودی ناکافی", "مقدار کاهش از موجودی فعلی بیشتر است.")
        return
    with connect() as con:
        con.execute("UPDATE inventory SET quantity = ? WHERE id = ?",
                    (new_quantity, item_id))
    refresh_inventory()


def delete_inventory_item():
    selected = inventory_table.selection()
    if not selected:
        messagebox.showwarning("انتخاب نشده", "ابتدا یک کالا را انتخاب کنید.")
        return
    values = inventory_table.item(selected[0], "values")
    if messagebox.askyesno("حذف کالا", f"کالای «{values[1]}» از انبار حذف شود؟"):
        with connect() as con:
            con.execute("DELETE FROM inventory WHERE id = ?", (values[0],))
        refresh_inventory()



def open_edit_dialog(title, fields, initial_values, on_save):
    """Reusable edit window for records in each application section."""
    win = tk.Toplevel(root)
    win.title(title)
    win.transient(root)
    win.grab_set()
    win.configure(bg="#f3f6fb")
    win.resizable(False, False)
    variables = []
    for row, (label, value) in enumerate(zip(fields, initial_values)):
        tk.Label(win, text=label, bg="#f3f6fb", font=(default_font, 10)).grid(
            row=row, column=1, padx=10, pady=7, sticky="e")
        var = tk.StringVar(value="" if value is None else str(value))
        entry = ttk.Entry(win, textvariable=var, width=34, justify="right")
        entry.grid(row=row, column=0, padx=10, pady=7, sticky="ew")
        variables.append(var)

    def save():
        values = [v.get().strip() for v in variables]
        if not on_save(values):
            return
        win.destroy()

    buttons = tk.Frame(win, bg="#f3f6fb")
    buttons.grid(row=len(fields), column=0, columnspan=2, pady=12)
    ttk.Button(buttons, text="ذخیره تغییرات", style="Action.TButton",
               command=save).pack(side="right", padx=6)
    ttk.Button(buttons, text="انصراف", style="Action.TButton",
               command=win.destroy).pack(side="right", padx=6)
    win.bind("<Return>", lambda _e: save())
    win.bind("<Escape>", lambda _e: win.destroy())


def edit_repair_record():
    selected = table.selection()
    if not selected:
        messagebox.showwarning("انتخاب نشده", "ابتدا دستگاهی را از جدول انتخاب کنید.")
        return
    values = table.item(selected[0], "values")
    record_id = values[0]

    def save(data):
        if not data[0]:
            messagebox.showwarning("اطلاعات ناقص", "نام دستگاه الزامی است.", parent=root)
            return False
        if data[2]:
            with connect() as con:
                duplicate = con.execute(
                    "SELECT 1 FROM repairs WHERE TRIM(omid_net_code) COLLATE NOCASE=? AND id<>? LIMIT 1",
                    (data[2], record_id)
                ).fetchone()
            if duplicate:
                messagebox.showwarning(
                    "کد تکراری",
                    "این کد امید نت برای دستگاه دیگری ثبت شده است. کد یکتا وارد کنید.",
                    parent=root
                )
                return False
        with connect() as con:
            con.execute("""
                UPDATE repairs
                SET device=?, asset_no=?, omid_net_code=?, branch=?,
                    received_date=?, problem=?, status=?
                WHERE id=?
            """, (*data, record_id))
        refresh_table()
        refresh_dashboard()
        return True

    open_edit_dialog(
        "ویرایش اطلاعات دستگاه",
        ["نام دستگاه:", "شماره اموال:", "کد امید نت:", "شعبه:",
         "تاریخ دریافت (شمسی):", "شرح خرابی:", "وضعیت:"],
        list(values[1:]), save
    )


def edit_device_repair_record():
    selected = device_repairs_table.selection()
    if not selected:
        messagebox.showwarning("انتخاب نشده", "ابتدا سابقه‌ای را انتخاب کنید.")
        return
    values = device_repairs_table.item(selected[0], "values")
    record_id = values[0]

    def save(data):
        if not data[0] or not data[1]:
            messagebox.showwarning("اطلاعات ناقص", "کد امید نت و نام دستگاه الزامی هستند.")
            return False
        try:
            quantity = int(data[5])
            if quantity < 1:
                raise ValueError
        except (ValueError, IndexError):
            messagebox.showwarning("تعداد نامعتبر", "تعداد قطعات باید عدد صحیح بزرگ‌تر از صفر باشد.")
            return False
        with connect() as con:
            old = con.execute("SELECT replaced_part, replaced_quantity FROM device_repairs WHERE id=?",
                              (record_id,)).fetchone()
            if not old:
                messagebox.showerror("خطا", "سابقه تعمیر پیدا نشد.")
                return False
            new_stock_item = find_inventory_part(con, data[4].strip())
            if not new_stock_item:
                messagebox.showwarning("قطعه در انبار نیست",
                                       "نام قطعه باید دقیقاً با یکی از اقلام موجودی انبار مطابقت داشته باشد.")
                return False
            old_stock_item = find_inventory_part(con, old[0])
            if old_stock_item:
                con.execute("UPDATE inventory SET quantity = quantity + ? WHERE id=?",
                            (old[1], old_stock_item[0]))
            current_stock = con.execute("SELECT quantity FROM inventory WHERE id=?",
                                        (new_stock_item[0],)).fetchone()[0]
            if current_stock < quantity:
                if old_stock_item:
                    con.execute("UPDATE inventory SET quantity = quantity - ? WHERE id=?",
                                (old[1], old_stock_item[0]))
                messagebox.showwarning("موجودی کافی نیست",
                                       f"موجودی قطعه «{new_stock_item[1]}» برای این تعداد کافی نیست.")
                return False
            con.execute("UPDATE inventory SET quantity = quantity - ? WHERE id=?",
                        (quantity, new_stock_item[0]))
            con.execute("""
                UPDATE device_repairs
                SET omid_net_code=?, device_name=?, serial_number=?,
                    repair_date=?, replaced_part=?, replaced_quantity=?
                WHERE id=?
            """, (*data[:4], new_stock_item[1], quantity, record_id))
        refresh_device_repairs()
        refresh_inventory()
        refresh_repair_part_choices()
        return True

    open_edit_dialog(
        "ویرایش سابقه تعمیر",
        ["کد امید نت:", "نام دستگاه:", "شماره سریال:",
         "تاریخ تعمیر (شمسی):", "قطعه تعویضی:", "تعداد قطعات تعویضی:"],
        list(values[1:]), save
    )


def edit_inventory_record():
    selected = inventory_table.selection()
    if not selected:
        messagebox.showwarning("انتخاب نشده", "ابتدا کالایی را از انبار انتخاب کنید.")
        return
    values = inventory_table.item(selected[0], "values")
    item_id = values[0]

    def save(data):
        if not data[0]:
            messagebox.showwarning("اطلاعات ناقص", "نام کالا الزامی است.")
            return False
        try:
            quantity, minimum = int(data[3]), int(data[5])
            if quantity < 0 or minimum < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("عدد نامعتبر", "موجودی و حداقل موجودی باید عدد صحیح صفر یا بیشتر باشند.")
            return False
        item_code = data[1].strip()
        if item_code:
            with connect() as con:
                duplicate = con.execute(
                    "SELECT 1 FROM inventory WHERE TRIM(item_code) COLLATE NOCASE = ? AND id<>? LIMIT 1",
                    (item_code, item_id)
                ).fetchone()
            if duplicate:
                messagebox.showwarning("کد کالای تکراری", "این کد کالا برای کالای دیگری ثبت شده است. کد یکتایی وارد کنید.")
                return False
        with connect() as con:
            con.execute("""
                UPDATE inventory
                SET item_name=?, item_code=?, category=?, quantity=?, unit=?, min_quantity=?
                WHERE id=?
            """, (data[0], item_code, data[2], quantity, data[4] or "عدد", minimum, item_id))
        refresh_inventory()
        return True

    open_edit_dialog(
        "ویرایش کالای انبار",
        ["نام کالا:", "کد کالا:", "دسته‌بندی:", "موجودی فعلی:",
         "واحد:", "حداقل موجودی:"],
        list(values[1:]), save
    )


setup_database()
setup_user_database()

root = tk.Tk()
root.withdraw()
root.title("مدیریت تعمیرگاه رویال")
root.geometry("1280x820")
root.minsize(1000, 680)
try:
    root.state("zoomed")
except tk.TclError:
    pass
root.configure(bg="#f3f6fb")

import tkinter.font as tkfont
available_fonts = set(tkfont.families(root))
preferred_fonts = [
    "Vazirmatn", "IRANSans", "IRANSansX", "Shabnam", "Sahel",
    "Yekan Bakh", "B Nazanin", "B Mitra", "B Yekan",
    "Noto Sans Arabic", "Noto Naskh Arabic", "Tahoma",
    "Segoe UI", "Arial", "Calibri", "DejaVu Sans"
]
font_choices = [name for name in preferred_fonts if name in available_fonts]
if not font_choices:
    font_choices = ["TkDefaultFont"]
default_font = next(
    (name for name in ["Vazirmatn", "IRANSans", "Shabnam", "Tahoma",
                       "Segoe UI", "Arial", "DejaVu Sans"]
     if name in font_choices), font_choices[0]
)

if not show_login():
    raise SystemExit

style = ttk.Style()
style.theme_use("clam")
style.configure("TLabel", font=(default_font, 9), background="#f3f6fb")
style.configure("TButton", font=(default_font, 10, "bold"), padding=(9, 6),
                foreground="#ffd84d", background="#101b35")
style.map("TButton",
          background=[("active", "#243657"), ("pressed", "#243657")],
          foreground=[("disabled", "#ffd84d"), ("!disabled", "#ffd84d")])
style.configure("Action.TButton", font=(default_font, 10, "bold"),
                padding=(10, 7), foreground="#ffd84d", background="#101b35")
style.map("Action.TButton", background=[("active", "#243657"), ("pressed", "#243657")],
          foreground=[("disabled", "#ffd84d"), ("!disabled", "#ffd84d")])
style.configure("Treeview", font=(default_font, 9), rowheight=29)
style.configure("Treeview.Heading", font=(default_font, 9, "bold"), padding=(5, 5))

customer_var = tk.StringVar()
phone_var = tk.StringVar()
device_var = tk.StringVar()
problem_var = tk.StringVar()
status_var = tk.StringVar(value="تحویل گرفته شد")
asset_var = tk.StringVar()
omid_var = tk.StringVar()
branch_var = tk.StringVar()
date_var = tk.StringVar(value=jalali_today())
search_var = tk.StringVar()

total_value = tk.StringVar(value="0")
active_value = tk.StringVar(value="0")
ready_value = tk.StringVar(value="0")
delivered_value = tk.StringVar(value="0")

# Simple header with Jalali date (analog clock removed)
header = tk.Frame(root, bg="#f3f6fb")
header.pack(fill="x", padx=16, pady=(7, 6))

header_text = tk.Frame(header, bg="#f3f6fb")
header_text.pack(side="right", expand=True, fill="x")
tk.Label(header_text, text="مدیریت تعمیرگاه رویال",
         font=(default_font, 18, "bold"), bg="#f3f6fb", fg="#17365d").pack(
             anchor="e", pady=(5, 8))
jalali_header_var = tk.StringVar()
tk.Label(header_text, textvariable=jalali_header_var,
         font=(default_font, 11, "bold"), bg="#f3f6fb", fg="#16845b").pack(anchor="e")
tk.Label(header_text, text=f"نسخه برنامه: {APP_VERSION}",
         font=(default_font, 9), bg="#f3f6fb", fg="#53657d").pack(anchor="e")

def update_jalali_header():
    jalali_header_var.set("امروز: " + jalali_today())
    root.after(60000, update_jalali_header)

update_jalali_header()

# Dashboard summary panel
dash = tk.Frame(root, bg="#e6edf7", padx=6, pady=5)
dash.pack(fill="x", padx=12, pady=(0, 5))

def dashboard_card(parent, caption, variable, color):
    card = tk.Frame(parent, bg="white", padx=14, pady=8,
                    highlightbackground="#d5deea", highlightthickness=1)
    card.pack(side="right", expand=True, fill="x", padx=5)
    tk.Label(card, text=caption, font=(default_font, 9), bg="white", fg="#53657d").pack()
    tk.Label(card, textvariable=variable, font=(default_font, 18, "bold"),
             bg="white", fg=color).pack(pady=(3, 0))

dashboard_card(dash, "کل دستگاه‌ها", total_value, "#17365d")
dashboard_card(dash, "در جریان تعمیر", active_value, "#c47b13")
dashboard_card(dash, "آماده تحویل", ready_value, "#16845b")
dashboard_card(dash, "تحویل‌شده", delivered_value, "#53657d")

style.configure("TNotebook.Tab", font=(default_font, 10, "bold"), padding=(11, 6))

notebook = ttk.Notebook(root)
notebook.pack(fill="both", expand=True, padx=10, pady=(1, 8))
home_tab = tk.Frame(notebook, bg="#f3f6fb")
repairs_tab = tk.Frame(notebook, bg="#f3f6fb")
device_repairs_tab = tk.Frame(notebook, bg="#f3f6fb")
inventory_tab = tk.Frame(notebook, bg="#f3f6fb")
replacements_tab = tk.Frame(notebook, bg="#f3f6fb")
settings_tab = tk.Frame(notebook, bg="#f3f6fb")
reports_tab = tk.Frame(notebook, bg="#f3f6fb")
notebook.add(home_tab, text="پنل اصلی")
notebook.add(repairs_tab, text="ثبت دستگاه‌ها")
notebook.add(device_repairs_tab, text="تعمیرات دستگاه")
notebook.add(inventory_tab, text="موجودی انبار")
notebook.add(replacements_tab, text="جایگزینی دستگاه")
notebook.add(settings_tab, text="تنظیمات")
notebook.add(reports_tab, text="گزارش‌ها")

form = tk.LabelFrame(repairs_tab, text="ثبت دستگاه", font=(default_font, 10, "bold"),
                     bg="#f3f6fb", padx=10, pady=8)
form.pack(fill="x", padx=10, pady=4)

def add_field(parent, label, variable, row, col, width=22):
    tk.Label(parent, text=label, bg="#f3f6fb", font=(default_font, 9)).grid(
        row=row, column=col*2+1, padx=5, pady=5, sticky="e")
    entry = ttk.Entry(parent, textvariable=variable, width=width, justify="right")
    entry.grid(row=row, column=col*2, padx=5, pady=5, sticky="ew")
    return entry

add_field(form, "نام دستگاه:", device_var, 0, 0)
add_field(form, "شماره اموال:", asset_var, 0, 1)
add_field(form, "کد امید نت:", omid_var, 0, 2)
add_field(form, "شعبه:", branch_var, 1, 0)
add_field(form, "تاریخ دریافت (شمسی):", date_var, 1, 1)
add_field(form, "شرح خرابی:", problem_var, 1, 2)

tk.Label(form, text="وضعیت:", bg="#f3f6fb", font=(default_font, 9)).grid(
    row=2, column=5, padx=5, pady=5, sticky="e")
status_box = ttk.Combobox(
    form, textvariable=status_var, state="readonly", justify="right",
    values=["تحویل گرفته شد", "در حال تعمیر", "آماده تحویل", "تحویل داده شد", "جایگزین شده", "غیر قابل تعمیر"], width=19)
status_box.grid(row=2, column=4, padx=5, pady=5, sticky="ew")

ttk.Button(form, text="ثبت دستگاه", command=add_record).grid(
    row=3, column=4, columnspan=2, padx=5, pady=7, sticky="ew")
for col in (0, 2, 4):
    form.columnconfigure(col, weight=1)

toolbar = tk.Frame(repairs_tab, bg="#f3f6fb")
toolbar.pack(fill="x", padx=10, pady=(4, 3))
ttk.Button(toolbar, text="ویرایش دستگاه انتخاب‌شده", style="Action.TButton",
           command=edit_repair_record).pack(side="left", padx=4)
ttk.Button(toolbar, text="حذف دستگاه انتخاب‌شده", style="Action.TButton",
           command=delete_record).pack(side="left", padx=4)
ttk.Button(toolbar, text="به‌روزرسانی وضعیت انتخاب‌شده", style="Action.TButton",
           command=update_status).pack(side="left", padx=4)
tk.Label(toolbar, text="جستجو:", bg="#f3f6fb", font=(default_font, 9)).pack(side="right", padx=5)
ttk.Entry(toolbar, textvariable=search_var, width=28, justify="right").pack(side="right")
search_var.trace_add("write", lambda *_: refresh_table())

columns = ("id", "device", "asset", "omid", "branch", "date", "problem", "status")
labels = {
    "id": "ردیف", "device": "نام دستگاه", "asset": "شماره اموال",
    "omid": "کد امید نت", "branch": "شعبه", "date": "تاریخ دریافت",
    "problem": "شرح خرابی", "status": "وضعیت"
}
widths = {
    "id": 55, "device": 150, "asset": 125, "omid": 125,
    "branch": 110, "date": 115, "problem": 260, "status": 130
}

table_frame = tk.Frame(repairs_tab, bg="#f3f6fb")
table_frame.pack(fill="both", expand=True, padx=10, pady=(1, 8))
table = ttk.Treeview(table_frame, columns=columns, show="headings")
for col in columns:
    table.heading(col, text=labels[col], anchor="center")
    table.column(col, width=widths[col], minwidth=55, anchor="center",
                 stretch=(col in ("device", "problem", "branch")))
yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=table.yview)
xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=table.xview)
table.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
table.grid(row=0, column=0, sticky="nsew")
yscroll.grid(row=0, column=1, sticky="ns")
xscroll.grid(row=1, column=0, sticky="ew")
table_frame.rowconfigure(0, weight=1, minsize=150)
table_frame.columnconfigure(0, weight=1)

def on_select(_event):
    selected = table.selection()
    if selected:
        values = table.item(selected[0], "values")
        status_var.set(values[7])

table.bind("<<TreeviewSelect>>", on_select)

# Device repair history tab
repair_omid_var = tk.StringVar()
repair_device_var = tk.StringVar()
repair_serial_var = tk.StringVar()
repair_date_var = tk.StringVar(value=jalali_today())
repair_part_var = tk.StringVar()
repair_part_display_to_name = {}
repair_quantity_var = tk.StringVar(value="1")
registered_device_info_var = tk.StringVar(value="پس از وارد کردن کد امید نت، اطلاعات دستگاه نمایش داده می‌شود.")
repair_search_var = tk.StringVar()

repair_form = tk.LabelFrame(
    device_repairs_tab, text="ثبت تعمیرات دستگاه",
    font=(default_font, 10, "bold"), bg="#f3f6fb", padx=12, pady=10
)
repair_form.pack(fill="x", padx=10, pady=6)

add_field(repair_form, "کد امید نت:", repair_omid_var, 0, 0)
add_field(repair_form, "نام دستگاه:", repair_device_var, 0, 1)
add_field(repair_form, "شماره سریال:", repair_serial_var, 0, 2)
add_field(repair_form, "تاریخ تعمیر (شمسی):", repair_date_var, 1, 0)
tk.Label(repair_form, text="قطعه تعویضی:", bg="#f3f6fb",
         font=(default_font, 9)).grid(row=1, column=3, padx=5, pady=5, sticky="e")
repair_part_box = ttk.Combobox(repair_form, textvariable=repair_part_var,
                               state="readonly", width=24, justify="right")
repair_part_box.grid(row=1, column=2, padx=5, pady=5, sticky="ew")
add_field(repair_form, "تعداد قطعات تعویضی:", repair_quantity_var, 1, 2, width=10)
tk.Label(
    repair_form, textvariable=registered_device_info_var, bg="#f3f6fb",
    fg="#17365d", font=(default_font, 9), justify="right", anchor="e", wraplength=1050
).grid(row=2, column=0, columnspan=6, padx=6, pady=(4, 8), sticky="ew")
repair_omid_var.trace_add("write", load_registered_device)
for col in (0, 2, 4):
    repair_form.columnconfigure(col, weight=1)

ttk.Button(
    repair_form, text="ثبت سابقه تعمیر", command=add_device_repair
).grid(row=3, column=4, columnspan=2, padx=5, pady=8, sticky="ew")

repair_search_bar = tk.Frame(device_repairs_tab, bg="#f3f6fb")
repair_search_bar.pack(fill="x", padx=10, pady=(3, 5))
tk.Label(
    repair_search_bar, text="جستجو بر اساس کد امید نت:",
    bg="#f3f6fb", font=(default_font, 9, "bold")
).pack(side="right", padx=6)
ttk.Entry(
    repair_search_bar, textvariable=repair_search_var,
    width=30, justify="right"
).pack(side="right", padx=4)
ttk.Button(
    repair_search_bar, text="پاک کردن جستجو",
    command=lambda: repair_search_var.set("")
).pack(side="right", padx=4)
ttk.Button(
    repair_search_bar, text="ویرایش سابقه انتخاب‌شده", style="Action.TButton",
    command=edit_device_repair_record
).pack(side="left", padx=4)
ttk.Button(
    repair_search_bar, text="حذف سابقه انتخاب‌شده", style="Action.TButton",
    command=delete_device_repair
).pack(side="left", padx=4)
repair_search_var.trace_add("write", lambda *_: refresh_device_repairs())

repair_table_frame = tk.Frame(device_repairs_tab, bg="#f3f6fb")
repair_table_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))
repair_columns = ("id", "omid", "device", "serial", "date", "part", "quantity")
repair_labels = {
    "id": "ردیف", "omid": "کد امید نت", "device": "نام دستگاه",
    "serial": "شماره سریال", "date": "تاریخ تعمیر", "part": "قطعه تعویضی",
    "quantity": "تعداد قطعات"
}
device_repairs_table = ttk.Treeview(
    repair_table_frame, columns=repair_columns, show="headings", height=13
)
for col in repair_columns:
    device_repairs_table.heading(col, text=repair_labels[col], anchor="center")
    device_repairs_table.column(col, width=150, minwidth=75, anchor="center",
                                 stretch=(col in ("device", "part")))
repair_y_scroll = ttk.Scrollbar(
    repair_table_frame, orient="vertical", command=device_repairs_table.yview
)
device_repairs_table.configure(yscrollcommand=repair_y_scroll.set)
device_repairs_table.grid(row=0, column=0, sticky="nsew")
repair_y_scroll.grid(row=0, column=1, sticky="ns")
repair_x_scroll = ttk.Scrollbar(
    repair_table_frame, orient="horizontal",
    command=device_repairs_table.xview
)
device_repairs_table.configure(xscrollcommand=repair_x_scroll.set)
repair_x_scroll.grid(row=1, column=0, sticky="ew")
repair_table_frame.rowconfigure(0, weight=1, minsize=150)
repair_table_frame.columnconfigure(0, weight=1)

# Inventory tab
stock_name_var = tk.StringVar()
stock_code_var = tk.StringVar()
stock_category_var = tk.StringVar()
stock_quantity_var = tk.StringVar(value="0")
stock_unit_var = tk.StringVar(value="عدد")
stock_min_var = tk.StringVar(value="0")
inventory_count_var = tk.StringVar(value="0")
low_stock_var = tk.StringVar(value="0")

# Main panel: compact, aligned layout so navigation, labels and branch table
# remain visible together on common laptop/desktop resolutions.
home_tab.grid_columnconfigure(0, weight=1)
home_tab.grid_rowconfigure(3, weight=1)

home_heading = tk.Label(
    home_tab, text="پنل اصلی مدیریت تعمیرگاه رویال",
    font=(default_font, 17, "bold"), bg="#f3f6fb", fg="#17365d"
)
home_heading.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 2))

tk.Label(
    home_tab, text="برای ورود به هر بخش، از دکمه‌های زیر استفاده کنید.",
    font=(default_font, 10), bg="#f3f6fb", fg="#53657d"
).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

home_cards = tk.Frame(home_tab, bg="#f3f6fb")
home_cards.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 8))
for card_col in range(3):
    home_cards.grid_columnconfigure(card_col, weight=1, uniform="home_cards")

def home_card(parent, title, description, button_text, command, accent, column):
    card = tk.Frame(
        parent, bg="white", padx=12, pady=10,
        highlightbackground="#d5deea", highlightthickness=1
    )
    card.grid(row=0, column=column, sticky="nsew", padx=6, pady=3)
    tk.Label(
        card, text=title, font=(default_font, 12, "bold"),
        bg="white", fg=accent, anchor="center"
    ).pack(fill="x", pady=(1, 5))
    tk.Label(
        card, text=description, font=(default_font, 9),
        bg="white", fg="#53657d", justify="center",
        anchor="center", wraplength=320, height=2
    ).pack(fill="x", pady=(0, 7))
    ttk.Button(
        card, text=button_text, command=command, style="Action.TButton"
    ).pack(fill="x", ipady=3)

home_card(
    home_cards, "ثبت و پیگیری دستگاه",
    "ثبت مشخصات، شماره اموال، کد امید نت و پیگیری وضعیت تعمیر",
    "ورود به ثبت دستگاه‌ها", lambda: notebook.select(repairs_tab),
    "#17365d", 0
)
home_card(
    home_cards, "تعمیرات دستگاه",
    "ثبت سوابق تعمیر، شماره سریال و قطعات تعویضی",
    "ورود به تعمیرات دستگاه", lambda: notebook.select(device_repairs_tab),
    "#a45b16", 1
)
home_card(
    home_cards, "مدیریت موجودی انبار",
    "ثبت کالا، مشاهده موجودی و مدیریت حداقل موجودی",
    "ورود به انبار", lambda: notebook.select(inventory_tab),
    "#16845b", 2
)

# Branch summary occupies the remaining flexible area.
branch_summary_frame = tk.LabelFrame(
    home_tab, text="آمار دستگاه‌ها به تفکیک شعبه",
    font=(default_font, 10, "bold"), bg="#f3f6fb", padx=9, pady=6
)
branch_summary_frame.grid(
    row=3, column=0, sticky="nsew", padx=24, pady=(2, 7)
)
branch_summary_frame.grid_columnconfigure(0, weight=1)
branch_summary_frame.grid_rowconfigure(1, weight=1)

tk.Label(
    branch_summary_frame,
    text="نام همه شعبه‌های ثبت‌شده، تعداد کل دستگاه‌ها و تعداد دستگاه‌های آماده تحویل یا تحویل‌شده",
    bg="#f3f6fb", fg="#53657d", font=(default_font, 9),
    anchor="e", justify="right"
).grid(row=0, column=0, sticky="ew", pady=(0, 4))

branch_table_frame = tk.Frame(branch_summary_frame, bg="#f3f6fb")
branch_table_frame.grid(row=1, column=0, sticky="nsew")
branch_table_frame.grid_columnconfigure(0, weight=1)
branch_table_frame.grid_rowconfigure(0, weight=1)

branch_summary_tree = ttk.Treeview(
    branch_table_frame,
    columns=("branch", "total", "repaired"),
    show="headings",
    height=4
)
branch_summary_tree.heading("branch", text="نام شعبه")
branch_summary_tree.heading("total", text="تعداد کل دستگاه‌ها")
branch_summary_tree.heading("repaired", text="تعمیرشده / آماده تحویل")
branch_summary_tree.column("branch", anchor="center", width=360, minwidth=160, stretch=True)
branch_summary_tree.column("total", anchor="center", width=150, minwidth=110, stretch=False)
branch_summary_tree.column("repaired", anchor="center", width=190, minwidth=140, stretch=False)
branch_y_scroll = ttk.Scrollbar(
    branch_table_frame, orient="vertical",
    command=branch_summary_tree.yview
)
branch_summary_tree.configure(yscrollcommand=branch_y_scroll.set)
branch_summary_tree.grid(row=0, column=0, sticky="nsew")
branch_y_scroll.grid(row=0, column=1, sticky="ns")
style.configure("BranchSummary.Treeview", rowheight=30)
branch_summary_tree.configure(style="BranchSummary.Treeview")

home_stats = tk.Frame(home_tab, bg="#e6edf7", padx=10, pady=7)
home_stats.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 9))
for stat_col in range(6):
    home_stats.grid_columnconfigure(stat_col, weight=1)

tk.Label(home_stats, text="دستگاه‌های ثبت‌شده:", bg="#e6edf7",
         font=(default_font, 9)).grid(row=0, column=5, padx=4, sticky="e")
tk.Label(home_stats, textvariable=total_value, bg="#e6edf7",
         fg="#17365d", font=(default_font, 11, "bold")).grid(row=0, column=4, padx=4)
tk.Label(home_stats, text="اقلام انبار:", bg="#e6edf7",
         font=(default_font, 9)).grid(row=0, column=3, padx=4, sticky="e")
tk.Label(home_stats, textvariable=inventory_count_var, bg="#e6edf7",
         fg="#16845b", font=(default_font, 11, "bold")).grid(row=0, column=2, padx=4)
tk.Label(home_stats, text="اقلام در حداقل موجودی:", bg="#e6edf7",
         font=(default_font, 9)).grid(row=0, column=1, padx=4, sticky="e")
tk.Label(home_stats, textvariable=low_stock_var, bg="#e6edf7",
         fg="#c44747", font=(default_font, 11, "bold")).grid(row=0, column=0, padx=4)

inventory_summary = tk.Frame(inventory_tab, bg="#e6edf7", padx=10, pady=8)
inventory_summary.pack(fill="x", padx=10, pady=5)
tk.Label(inventory_summary, text="تعداد اقلام انبار:", bg="#e6edf7",
         font=(default_font, 9)).pack(side="right", padx=5)
tk.Label(inventory_summary, textvariable=inventory_count_var, bg="#e6edf7",
         fg="#17365d", font=(default_font, 11, "bold")).pack(side="right", padx=4)
tk.Label(inventory_summary, text="⚠ هشدار کمبود موجودی:", bg="#e6edf7",
         fg="#d00000", font=(default_font, 9, "bold")).pack(side="right", padx=(20, 5))
tk.Label(inventory_summary, textvariable=low_stock_var, bg="#e6edf7",
         fg="#c44747", font=(default_font, 11, "bold")).pack(side="right", padx=4)

stock_form = tk.LabelFrame(inventory_tab, text="ثبت کالای جدید در انبار",
                           font=(default_font, 10, "bold"), bg="#f3f6fb",
                           padx=10, pady=8)
stock_form.pack(fill="x", padx=10, pady=4)

def stock_field(label, variable, row, col, width=18):
    tk.Label(stock_form, text=label, bg="#f3f6fb",
             font=(default_font, 9)).grid(row=row, column=col*2+1,
                                      padx=4, pady=5, sticky="e")
    entry = ttk.Entry(stock_form, textvariable=variable, width=width,
                      justify="right")
    entry.grid(row=row, column=col*2, padx=4, pady=5, sticky="ew")
    return entry

stock_field("نام کالا:", stock_name_var, 0, 0)
stock_field("کد کالا:", stock_code_var, 0, 1)
stock_field("دسته‌بندی:", stock_category_var, 0, 2)
stock_field("موجودی اولیه:", stock_quantity_var, 1, 0)
stock_field("واحد:", stock_unit_var, 1, 1)
stock_field("حداقل موجودی:", stock_min_var, 1, 2)
for col in (0, 2, 4):
    stock_form.columnconfigure(col, weight=1)

ttk.Button(stock_form, text="ثبت کالا در انبار",
           command=add_inventory_item).grid(
               row=2, column=4, columnspan=2, padx=5, pady=7, sticky="ew")

inventory_toolbar = tk.Frame(inventory_tab, bg="#f3f6fb")
inventory_toolbar.pack(fill="x", padx=10, pady=4)
ttk.Button(inventory_toolbar, text="افزایش موجودی",
           command=lambda: change_stock(1)).pack(side="right", padx=4)
ttk.Button(inventory_toolbar, text="کاهش موجودی",
           command=lambda: change_stock(-1)).pack(side="right", padx=4)
ttk.Button(inventory_toolbar, text="ویرایش کالای انتخاب‌شده",
           style="Action.TButton", command=edit_inventory_record).pack(side="left", padx=4)
ttk.Button(inventory_toolbar, text="حذف کالای انتخاب‌شده",
           style="Action.TButton", command=delete_inventory_item).pack(side="left", padx=4)
ttk.Button(inventory_toolbar, text="تازه‌سازی",
           command=refresh_inventory).pack(side="left", padx=4)

inventory_frame = tk.Frame(inventory_tab, bg="#f3f6fb")
inventory_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))
inventory_columns = ("id", "name", "code", "category", "quantity", "unit", "minimum")
inventory_headers = {
    "id": "ردیف", "name": "نام کالا", "code": "کد کالا",
    "category": "دسته‌بندی", "quantity": "موجودی فعلی",
    "unit": "واحد", "minimum": "حداقل موجودی"
}
inventory_table = ttk.Treeview(inventory_frame, columns=inventory_columns,
                               show="headings", height=7)
for col in inventory_columns:
    inventory_table.heading(col, text=inventory_headers[col], anchor="center")
    inventory_table.column(col, width=125, minwidth=70, anchor="center",
                            stretch=(col in ("name", "category")))
inventory_scroll = ttk.Scrollbar(inventory_frame, orient="vertical",
                                 command=inventory_table.yview)
inventory_table.configure(yscrollcommand=inventory_scroll.set)
inventory_table.grid(row=0, column=0, sticky="nsew")
inventory_scroll.grid(row=0, column=1, sticky="ns")
inventory_x_scroll = ttk.Scrollbar(
    inventory_frame, orient="horizontal", command=inventory_table.xview
)
inventory_table.configure(xscrollcommand=inventory_x_scroll.set)
inventory_x_scroll.grid(row=1, column=0, sticky="ew")
inventory_frame.rowconfigure(0, weight=1, minsize=150)
inventory_frame.columnconfigure(0, weight=1)

# Appearance settings screen - organized into compact sections
settings_title = tk.Label(
    settings_tab, text="تنظیمات برنامه",
    font=(default_font, 12, "bold"), bg="#f3f6fb", fg="#17365d"
)
settings_title.pack(anchor="e", padx=8, pady=(4, 2))

# -------------------- جایگزینی دائم و موقت دستگاه --------------------
replacement_form = tk.LabelFrame(
    replacements_tab, text="ثبت جایگزینی دستگاه",
    font=(default_font, 10, "bold"), bg="#f3f6fb", padx=8, pady=6
)
replacement_form.pack(fill="x", padx=8, pady=5)
replacement_form.columnconfigure(0, weight=1)
replacement_form.columnconfigure(2, weight=1)
replacement_form.columnconfigure(4, weight=1)

replacement_type_var = tk.StringVar(value="موقت")
replacement_name_var = tk.StringVar()
replacement_model_var = tk.StringVar()
replacement_asset_var = tk.StringVar()
replacement_code_var = tk.StringVar()
replacement_branch_var = tk.StringVar()
replacement_date_var = tk.StringVar(value=jalali_today())
replacement_photo_var = tk.StringVar()
replacement_edit_id = None

def replacement_field(label, variable, row, col, width=24):
    tk.Label(replacement_form, text=label, bg="#f3f6fb",
             font=(default_font, 9, "bold")).grid(row=row, column=col*2+1, padx=4, pady=4, sticky="e")
    entry = ttk.Entry(replacement_form, textvariable=variable, width=width, justify="right")
    entry.grid(row=row, column=col*2, padx=4, pady=4, sticky="ew")
    return entry

tk.Label(replacement_form, text="نوع جایگزینی:", bg="#f3f6fb",
         font=(default_font, 9, "bold")).grid(row=0, column=5, padx=4, pady=4, sticky="e")
ttk.Combobox(replacement_form, textvariable=replacement_type_var,
             values=["دائم", "موقت"], state="readonly", justify="right", width=20
             ).grid(row=0, column=4, padx=4, pady=4, sticky="ew")
replacement_field("نام دستگاه:", replacement_name_var, 0, 1)
replacement_field("مدل دستگاه:", replacement_model_var, 0, 0)
replacement_field("شماره اموال:", replacement_asset_var, 1, 2)
replacement_field("کد امید نت:", replacement_code_var, 1, 1)
replacement_field("تاریخ جایگزینی:", replacement_date_var, 1, 0)
replacement_field("نام شعبه:", replacement_branch_var, 2, 2)

tk.Label(replacement_form, text="گزارش / علت جایگزینی:", bg="#f3f6fb",
         font=(default_font, 9, "bold")).grid(row=3, column=5, padx=4, pady=4, sticky="ne")
replacement_report_text = tk.Text(replacement_form, height=3, wrap="word", font=(default_font, 9),
                                  relief="solid", bd=1)
replacement_report_text.grid(row=3, column=0, columnspan=5, padx=4, pady=4, sticky="ew")

replacement_photo_row = tk.Frame(replacement_form, bg="#f3f6fb")
replacement_photo_row.grid(row=4, column=0, columnspan=6, sticky="ew", padx=4, pady=3)
tk.Label(replacement_photo_row, textvariable=replacement_photo_var, bg="#f3f6fb",
         fg="#53657d", font=(default_font, 8), anchor="e").pack(side="right", fill="x", expand=True)

def choose_replacement_photo():
    selected = filedialog.askopenfilename(
        parent=root, title="انتخاب عکس دستگاه",
        filetypes=[("تصاویر", "*.png *.jpg *.jpeg *.gif *.bmp"), ("همه فایل‌ها", "*.*")]
    )
    if selected:
        replacement_photo_var.set(selected)

ttk.Button(replacement_photo_row, text="بارگذاری عکس", command=choose_replacement_photo,
           style="Action.TButton").pack(side="left", padx=3)

replacement_actions = tk.Frame(replacement_form, bg="#f3f6fb")
replacement_actions.grid(row=5, column=0, columnspan=6, sticky="ew", pady=(3, 0))

def clear_replacement_form():
    global replacement_edit_id
    replacement_edit_id = None
    for var in (replacement_name_var, replacement_model_var, replacement_asset_var, replacement_code_var, replacement_branch_var):
        var.set("")
    replacement_type_var.set("موقت")
    replacement_date_var.set(jalali_today())
    replacement_photo_var.set("")
    replacement_report_text.delete("1.0", tk.END)

def refresh_replacements():
    if "replacement_table" not in globals():
        return
    replacement_table.delete(*replacement_table.get_children())
    term = replacement_search_var.get().strip() if "replacement_search_var" in globals() else ""
    with connect() as con:
        rows = con.execute("""
            SELECT id, replacement_type, device_name, model, asset_no, omid_net_code,
                   branch_name, replacement_date, photo_path
            FROM device_replacements
            WHERE replacement_type LIKE ? OR device_name LIKE ? OR model LIKE ?
               OR asset_no LIKE ? OR omid_net_code LIKE ? OR report LIKE ? OR branch_name LIKE ?
            ORDER BY id DESC
        """, tuple([f"%{term}%"] * 7)).fetchall()
    for row in rows:
        replacement_table.insert("", "end", values=row)

def save_replacement():
    global replacement_edit_id
    name = replacement_name_var.get().strip()
    if not name:
        messagebox.showwarning("اطلاعات ناقص", "نام دستگاه را وارد کنید.", parent=root)
        return
    photo = replacement_photo_var.get().strip()
    stored_photo = photo
    if photo and Path(photo).is_file():
        try:
            photo_dir = BASE_DIR / "تصاویر_جایگزینی"
            photo_dir.mkdir(exist_ok=True)
            source = Path(photo)
            target = photo_dir / f"replacement_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{source.suffix.lower()}"
            shutil.copy2(source, target)
            stored_photo = str(target)
        except OSError as exc:
            messagebox.showerror("خطا در عکس", f"کپی عکس انجام نشد:\n{exc}", parent=root)
            return
    values = (replacement_type_var.get(), name, replacement_model_var.get().strip(),
              replacement_asset_var.get().strip(), replacement_code_var.get().strip(),
              replacement_branch_var.get().strip(), replacement_date_var.get().strip(), replacement_report_text.get("1.0", "end-1c").strip(),
              stored_photo)
    try:
        with connect() as con:
            if replacement_edit_id is None:
                con.execute("""INSERT INTO device_replacements
                    (replacement_type, device_name, model, asset_no, omid_net_code, branch_name, replacement_date, report, photo_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", values)
                message = "سابقه جایگزینی با موفقیت ثبت شد."
            else:
                con.execute("""UPDATE device_replacements SET replacement_type=?, device_name=?, model=?,
                    asset_no=?, omid_net_code=?, branch_name=?, replacement_date=?, report=?, photo_path=? WHERE id=?""",
                    values + (replacement_edit_id,))
                message = "سابقه جایگزینی ویرایش شد."
        clear_replacement_form()
        refresh_replacements()
        messagebox.showinfo("ثبت موفق", message, parent=root)
    except sqlite3.Error as exc:
        messagebox.showerror("خطای پایگاه داده", str(exc), parent=root)

def load_replacement_for_edit(_event=None):
    global replacement_edit_id
    selected = replacement_table.selection()
    if not selected:
        return
    row = replacement_table.item(selected[0], "values")
    with connect() as con:
        data = con.execute("SELECT replacement_type, device_name, model, asset_no, omid_net_code, branch_name, replacement_date, report, photo_path FROM device_replacements WHERE id=?", (row[0],)).fetchone()
    if not data:
        return
    replacement_edit_id = int(row[0])
    replacement_type_var.set(data[0] or "موقت")
    replacement_name_var.set(data[1] or "")
    replacement_model_var.set(data[2] or "")
    replacement_asset_var.set(data[3] or "")
    replacement_code_var.set(data[4] or "")
    replacement_branch_var.set(data[5] or "")
    replacement_date_var.set(data[6] or "")
    replacement_report_text.delete("1.0", tk.END)
    replacement_report_text.insert("1.0", data[7] or "")
    replacement_photo_var.set(data[8] or "")

def delete_replacement():
    selected = replacement_table.selection()
    if not selected:
        messagebox.showwarning("انتخاب سابقه", "ابتدا یک سابقه را انتخاب کنید.", parent=root)
        return
    record_id = replacement_table.item(selected[0], "values")[0]
    if messagebox.askyesno("حذف سابقه", "سابقه جایگزینی انتخاب‌شده حذف شود؟", parent=root):
        with connect() as con:
            con.execute("DELETE FROM device_replacements WHERE id=?", (record_id,))
        clear_replacement_form()
        refresh_replacements()

def open_replacement_photo():
    selected = replacement_table.selection()
    if not selected:
        messagebox.showinfo("عکس دستگاه", "ابتدا یک سابقه را انتخاب کنید.", parent=root)
        return
    path = replacement_table.item(selected[0], "values")[8]
    if not path or not Path(path).is_file():
        messagebox.showwarning("عکس موجود نیست", "برای این سابقه عکس ذخیره نشده یا فایل آن پیدا نشد.", parent=root)
        return
    try:
        if os.name == "nt": os.startfile(path)
        else: webbrowser.open(Path(path).resolve().as_uri())
    except Exception as exc:
        messagebox.showerror("خطا در بازکردن عکس", str(exc), parent=root)

def print_replacement_report():
    with connect() as con:
        rows = con.execute("""SELECT replacement_type, replacement_date, device_name, model,
            asset_no, omid_net_code, branch_name, report FROM device_replacements ORDER BY id DESC""").fetchall()
    headers = ["نوع", "تاریخ", "نام دستگاه", "مدل", "شماره اموال", "کد امید نت", "نام شعبه", "گزارش"]
    _html_report("گزارش جایگزینی دائم و موقت دستگاه", f"تعداد سوابق: {len(rows)}", headers, rows)

ttk.Button(replacement_actions, text="ویرایش", command=load_replacement_for_edit, style="Action.TButton").pack(side="right", padx=3)
ttk.Button(replacement_actions, text="ثبت / ذخیره", command=save_replacement, style="Action.TButton").pack(side="right", padx=3)
ttk.Button(replacement_actions, text="فرم جدید", command=clear_replacement_form).pack(side="right", padx=3)
ttk.Button(replacement_actions, text="حذف سابقه", command=delete_replacement).pack(side="right", padx=3)
ttk.Button(replacement_actions, text="بازکردن عکس", command=open_replacement_photo).pack(side="right", padx=3)
ttk.Button(replacement_actions, text="چاپ گزارش", command=print_replacement_report).pack(side="left", padx=3)

replacement_list_frame = tk.LabelFrame(replacements_tab, text="سوابق جایگزینی",
    font=(default_font, 10, "bold"), bg="#f3f6fb", padx=5, pady=4)
replacement_list_frame.pack(fill="both", expand=True, padx=8, pady=(2, 7))
replacement_search_var = tk.StringVar()
replacement_search_row = tk.Frame(replacement_list_frame, bg="#f3f6fb")
replacement_search_row.pack(fill="x", pady=(0, 4))
tk.Label(replacement_search_row, text="جستجو (نام، مدل، اموال یا کد امید نت):",
         bg="#f3f6fb", font=(default_font, 8)).pack(side="right", padx=4)
replacement_search_entry = ttk.Entry(replacement_search_row, textvariable=replacement_search_var, justify="right", width=30)
replacement_search_entry.pack(side="right", padx=3)
replacement_search_var.trace_add("write", lambda *_: refresh_replacements())
replacement_columns = ("id", "type", "name", "model", "asset", "code", "branch", "date", "photo")
replacement_headers = {"id":"ردیف", "type":"نوع", "name":"نام دستگاه", "model":"مدل",
                      "asset":"شماره اموال", "code":"کد امید نت", "branch":"نام شعبه", "date":"تاریخ", "photo":"مسیر عکس"}
replacement_table = ttk.Treeview(replacement_list_frame, columns=replacement_columns, show="headings", height=8)
for col in replacement_columns:
    replacement_table.heading(col, text=replacement_headers[col], anchor="center")
    replacement_table.column(col, width=105 if col != "photo" else 170, minwidth=65, anchor="center")
replacement_scroll = ttk.Scrollbar(replacement_list_frame, orient="vertical", command=replacement_table.yview)
replacement_table.configure(yscrollcommand=replacement_scroll.set)
replacement_table.pack(side="left", fill="both", expand=True)
replacement_scroll.pack(side="right", fill="y")
replacement_table.bind("<Double-1>", load_replacement_for_edit)
tk.Label(replacement_list_frame, text="برای ویرایش، ردیف را انتخاب کنید، دکمه «ویرایش» را بزنید و پس از تغییر اطلاعات، «ثبت / ذخیره» را انتخاب کنید.",
         bg="#f3f6fb", fg="#53657d", font=(default_font, 8)).pack(anchor="e", pady=(3, 0))

settings_panel = tk.LabelFrame(
    settings_tab, text="شخصی‌سازی ظاهر برنامه",
    font=(default_font, 10, "bold"), bg="#f3f6fb", padx=14, pady=10
)
settings_panel.pack(fill="x", padx=6, pady=2)

if CURRENT_USER.get("role") == "admin":
    users_panel = tk.LabelFrame(
        settings_tab, text="امنیت و کاربران",
        font=(default_font, 10, "bold"), bg="#f3f6fb", padx=10, pady=7
    )
    users_panel.pack(fill="x", padx=6, pady=3)
    tk.Label(
        users_panel, text=f"کاربر واردشده: {CURRENT_USER['username']}  |  سطح دسترسی: مدیر",
        bg="#f3f6fb", fg="#53657d", font=(default_font, 9)
    ).pack(side="right", padx=8)
    ttk.Button(users_panel, text="مدیریت کاربران", command=open_user_manager).pack(side="left", padx=6)
    ttk.Button(users_panel, text="گزارش ورود کاربران", command=open_login_report).pack(side="left", padx=6)

font_family_var = tk.StringVar(value=default_font)
font_size_var = tk.StringVar(value="10")
button_size_var = tk.StringVar(value="متوسط")
theme_var = tk.StringVar(value="سبز دودی")
windows_theme_var = tk.StringVar(value="ویندوز مدرن")

settings_panel.columnconfigure(0, weight=1)
settings_panel.columnconfigure(1, weight=1)
settings_panel.columnconfigure(2, weight=1)
settings_panel.columnconfigure(3, weight=1)

def add_setting_field(row, column, label_text, variable, values, width=18):
    cell = tk.Frame(settings_panel, bg="#f3f6fb")
    cell.grid(row=row, column=column, padx=3, pady=2, sticky="ew")
    tk.Label(cell, text=label_text, bg="#f3f6fb",
             font=(default_font, 8, "bold")).pack(anchor="e", pady=(0, 1))
    widget = ttk.Combobox(
        cell, textvariable=variable, state="readonly",
        values=values, width=width, justify="right"
    )
    widget.pack(fill="x", ipady=0)
    return widget

font_family_box = add_setting_field(0, 2, "نوع فونت", font_family_var, font_choices, 22)
font_size_box = add_setting_field(0, 1, "اندازه فونت", font_size_var,
                                  ["9", "10", "11", "12", "13", "14", "16"], 10)
button_size_box = add_setting_field(0, 0, "اندازه دکمه‌ها", button_size_var,
                                    ["کوچک", "متوسط", "بزرگ"], 14)
theme_box = add_setting_field(1, 2, "پوسته رنگی", theme_var,
                              ["سبز دودی", "فیروزه‌ای کدر", "نیلی متالیک", "بنفش آبی", "گرافیتی مدرن", "زمردی تیره", "آبی اقیانوسی", "سورمه‌ای", "آبی روشن", "تیره", "مشکی", "سبز", "بنفش", "ویندوز ۷", "آفیس ۲۰۱۰", "آفیس ۲۰۱۳", "آفیس ۲۰۱۶", "آفیس ۲۰۲۱", "فیروزه‌ای", "قرمز", "طلایی", "خاکستری"], 18)
windows_theme_box = add_setting_field(
    1, 1, "سبک کنترل‌های ویندوز", windows_theme_var,
    ["ویندوز مدرن", "ویندوز کلاسیک", "ویندوز XP", "سازگار با همه سیستم‌ها"], 22
)

settings_note = tk.Label(
    settings_panel,
    text="گزینه‌ها را انتخاب کنید و سپس «اعمال تنظیمات» را بزنید.",
    bg="#f3f6fb", fg="#53657d", font=(default_font, 8), anchor="e"
)
settings_note.grid(row=2, column=0, columnspan=4, sticky="ew", padx=4, pady=(1, 3))

low_stock_panel = tk.LabelFrame(
    settings_tab, text="هشدار کالاهای کم‌موجودی",
    font=(default_font, 10, "bold"), bg="#fff5f5", fg="#b00000",
    padx=10, pady=7
)
low_stock_panel.pack(fill="x", padx=6, pady=2)

tk.Label(
    low_stock_panel, text="نام کالاهایی که موجودی آن‌ها صفر شده است:",
    bg="#fff5f5", fg="#b00000", font=(default_font, 8, "bold")
).pack(anchor="e", pady=(0, 2))

low_stock_list_frame = tk.Frame(low_stock_panel, bg="#fff5f5")
low_stock_list_frame.pack(fill="x")
low_stock_scroll = ttk.Scrollbar(low_stock_list_frame, orient="vertical")
low_stock_listbox = tk.Listbox(
    low_stock_list_frame, height=2, font=(default_font, 8),
    fg="#b00000", bg="#fffafa", relief="solid", bd=1,
    justify="right", yscrollcommand=low_stock_scroll.set
)
low_stock_scroll.configure(command=low_stock_listbox.yview)
low_stock_listbox.pack(side="right", fill="x", expand=True)
low_stock_scroll.pack(side="left", fill="y")

backup_panel = tk.LabelFrame(
    settings_tab, text="پشتیبان‌گیری و بازیابی اطلاعات",
    font=(default_font, 10, "bold"), bg="#f3f6fb", padx=8, pady=4
)
backup_panel.pack(fill="x", padx=6, pady=2)
backup_panel.columnconfigure(0, weight=1)
backup_panel.columnconfigure(1, weight=0)
backup_info = tk.Frame(backup_panel, bg="#f3f6fb")
backup_info.grid(row=0, column=0, sticky="ew", padx=5, pady=2)
tk.Label(backup_info, text="برای حفظ اطلاعات، مرتب نسخه پشتیبان تهیه کنید.",
         bg="#f3f6fb", fg="#53657d", font=(default_font, 8)).pack(anchor="e")
last_update_check_var = tk.StringVar(value="آخرین بررسی: " + _last_update_check_text())
tk.Label(backup_info, textvariable=last_update_check_var,
         bg="#f3f6fb", fg="#53657d", font=(default_font, 8)).pack(anchor="e")
backup_buttons = tk.Frame(backup_panel, bg="#f3f6fb")
backup_buttons.grid(row=0, column=1, sticky="e", padx=2, pady=1)
ttk.Button(backup_buttons, text="تهیه پشتیبان", style="Action.TButton",
           command=backup_database).pack(side="right", padx=1)
ttk.Button(backup_buttons, text="بازیابی اطلاعات", style="Action.TButton",
           command=restore_database).pack(side="right", padx=1)
ttk.Button(backup_buttons, text="بررسی به‌روزرسانی", style="Action.TButton",
           command=check_for_updates).pack(side="right", padx=1)

def apply_appearance_settings(show_message=True):
    family = font_family_var.get()
    size = int(font_size_var.get())
    button_padding = {"کوچک": (8, 6), "متوسط": (12, 9), "بزرگ": (18, 13)}[
        button_size_var.get()
    ]
    native_theme_map = {
        "ویندوز مدرن": "vista",
        "ویندوز کلاسیک": "winnative",
        "ویندوز XP": "xpnative",
        "سازگار با همه سیستم‌ها": "clam",
    }
    requested_theme = native_theme_map[windows_theme_var.get()]
    available_themes = style.theme_names()
    if requested_theme not in available_themes:
        requested_theme = "clam" if "clam" in available_themes else available_themes[0]
    style.theme_use(requested_theme)
    style.configure("TButton", font=(family, size, "bold"), padding=button_padding)
    style.configure("Action.TButton", font=(family, size, "bold"),
                    padding=button_padding, foreground="#ffd84d",
                    background="#101b35")
    style.configure("TLabel", font=(family, size), background="#f3f6fb")
    style.configure("TEntry", font=(family, size), padding=5)
    style.configure("TCombobox", font=(family, size), padding=5)
    style.configure("Treeview", font=(family, size), rowheight=size * 3 + 8)
    style.configure("Treeview.Heading", font=(family, size, "bold"))
    style.configure("TLabelframe.Label", font=(family, size, "bold"))

    def update_widgets(widget):
        try:
            if isinstance(widget, (tk.Label, tk.Button, tk.LabelFrame)):
                current = widget.cget("font")
                if isinstance(current, tuple):
                    weight = current[2] if len(current) > 2 else "normal"
                else:
                    weight = "normal"
                widget.configure(font=(family, size, weight))
            elif isinstance(widget, tk.Entry):
                widget.configure(font=(family, size))
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            update_widgets(child)

    update_widgets(root)

    palettes = {
        "سورمه‌ای": {
            "bg": "#101b35", "surface": "#1a2948", "panel": "#243657",
            "fg": "#f2f5fb", "muted": "#c3cde0", "accent": "#f2c94c",
            "button": "#101b35", "button_active": "#405b83",
            "button_fg": "#ffd84d",
            "tree": "#1a2948", "select": "#526b91"
        },
        "آبی روشن": {
            "bg": "#f3f6fb", "surface": "#ffffff", "panel": "#e6edf7",
            "fg": "#17365d", "muted": "#53657d", "accent": "#245a9b",
            "button": "#dce8f6", "button_active": "#c7dbf2",
            "tree": "#ffffff", "select": "#b8d2ef"
        },
        "تیره": {
            "bg": "#202833", "surface": "#293442", "panel": "#344253",
            "fg": "#f0f4f8", "muted": "#c1ccd8", "accent": "#82b7f4",
            "button": "#40536a", "button_active": "#526b86",
            "tree": "#293442", "select": "#45698f"
        },
        "فیروزه‌ای کدر": {
            "bg": "#e3eeee", "surface": "#f4f8f7", "panel": "#c8d9d8",
            "fg": "#294748", "muted": "#607879", "accent": "#4f8586",
            "button": "#668f90", "button_active": "#507778",
            "button_fg": "#ffffff", "tree": "#f4f8f7", "select": "#b4d0cf"
        },
        "نیلی متالیک": {
            "bg": "#e7e9f1", "surface": "#f7f8fc", "panel": "#cbd0df",
            "fg": "#303957", "muted": "#68718d", "accent": "#58658f",
            "button": "#65739d", "button_active": "#4f5d85",
            "button_fg": "#ffffff", "tree": "#f7f8fc", "select": "#bdc6df"
        },
        "بنفش آبی": {
            "bg": "#eeebf4", "surface": "#faf9fc", "panel": "#d9d2e5",
            "fg": "#443b60", "muted": "#756b91", "accent": "#76669f",
            "button": "#8173a6", "button_active": "#685987",
            "button_fg": "#ffffff", "tree": "#faf9fc", "select": "#d0c5e4"
        },
        "گرافیتی مدرن": {
            "bg": "#e5e8eb", "surface": "#f6f7f8", "panel": "#cbd1d6",
            "fg": "#303941", "muted": "#68747d", "accent": "#526675",
            "button": "#5e7180", "button_active": "#465966",
            "button_fg": "#ffffff", "tree": "#f6f7f8", "select": "#bdc9d1"
        },
        "زمردی تیره": {
            "bg": "#dfe9e4", "surface": "#f4f8f5", "panel": "#bfd2c8",
            "fg": "#203d32", "muted": "#587467", "accent": "#34765b",
            "button": "#3f795f", "button_active": "#2d624a",
            "button_fg": "#ffffff", "tree": "#f4f8f5", "select": "#b2d0bf"
        },
        "آبی اقیانوسی": {
            "bg": "#e2ebf0", "surface": "#f6f9fb", "panel": "#c6d7e0",
            "fg": "#294354", "muted": "#607b8b", "accent": "#477d98",
            "button": "#56839a", "button_active": "#3e687e",
            "button_fg": "#ffffff", "tree": "#f6f9fb", "select": "#b6d1df"
        },
        "سبز دودی": {
            "bg": "#e6ece8", "surface": "#f7faf7", "panel": "#cbd6cf",
            "fg": "#26372e", "muted": "#65736a", "accent": "#60796a",
            "button": "#657d6e", "button_active": "#4f6658",
            "button_fg": "#ffffff", "tree": "#f7faf7", "select": "#b9cbbf"
        },
        "سبز": {
            "bg": "#edf5ef", "surface": "#ffffff", "panel": "#dcebe0",
            "fg": "#214b32", "muted": "#526b5a", "accent": "#28784a",
            "button": "#d3e8d9", "button_active": "#bddbc7",
            "tree": "#ffffff", "select": "#b9d9c3"
        },
        "بنفش": {
            "bg": "#f3eff8", "surface": "#ffffff", "panel": "#e6def0",
            "fg": "#49345f", "muted": "#6c5b7d", "accent": "#7652a3",
            "button": "#e2d8ef", "button_active": "#d2c2e5",
            "tree": "#ffffff", "select": "#d0bee5"
        },
        "مشکی": {"bg":"#111111","surface":"#1b1b1b","panel":"#292929","fg":"#f5f5f5","muted":"#cccccc","accent":"#ffffff","button":"#292929","button_active":"#454545","tree":"#1b1b1b","select":"#555555"},
        "ویندوز ۷": {"bg":"#eaf3fb","surface":"#f8fcff","panel":"#d5e7f5","fg":"#183b59","muted":"#536d82","accent":"#2878b8","button":"#d5e7f5","button_active":"#b7d8ef","tree":"#f8fcff","select":"#9fc9e8"},
        "آفیس ۲۰۱۰": {"bg":"#e8f1fa","surface":"#ffffff","panel":"#d2e2f2","fg":"#17365d","muted":"#53657d","accent":"#1f5f9d","button":"#d2e2f2","button_active":"#a9c8e5","tree":"#ffffff","select":"#a9c8e5"},
        "آفیس ۲۰۱۳": {"bg":"#f4f4f4","surface":"#ffffff","panel":"#e5e5e5","fg":"#333333","muted":"#666666","accent":"#217346","button":"#e5e5e5","button_active":"#d2e8dc","tree":"#ffffff","select":"#b7d9c5"},
        "آفیس ۲۰۱۶": {"bg":"#f5f5f5","surface":"#ffffff","panel":"#e7e7e7","fg":"#242424","muted":"#666666","accent":"#0078d4","button":"#e7e7e7","button_active":"#cce4f7","tree":"#ffffff","select":"#a9d3f2"},
        "آفیس ۲۰۲۱": {"bg":"#f2f2f2","surface":"#ffffff","panel":"#e3e3e3","fg":"#202020","muted":"#666666","accent":"#6264a7","button":"#e3e3e3","button_active":"#d8d8f0","tree":"#ffffff","select":"#c5c5e4"},
        "فیروزه‌ای": {"bg":"#e9f7f7","surface":"#ffffff","panel":"#d1eeee","fg":"#164b50","muted":"#527477","accent":"#008c95","button":"#d1eeee","button_active":"#b4e2e4","tree":"#ffffff","select":"#a9dfe1"},
        "قرمز": {"bg":"#fbefef","surface":"#ffffff","panel":"#f2dada","fg":"#572323","muted":"#805858","accent":"#b83232","button":"#f2dada","button_active":"#e9bcbc","tree":"#ffffff","select":"#e8b4b4"},
        "طلایی": {"bg":"#f8f3e7","surface":"#fffdf7","panel":"#eee3c8","fg":"#514326","muted":"#786b4c","accent":"#a77b22","button":"#eee3c8","button_active":"#e4d3a6","tree":"#fffdf7","select":"#e4d3a6"},
        "خاکستری": {"bg":"#eeeeee","surface":"#ffffff","panel":"#dcdcdc","fg":"#333333","muted":"#666666","accent":"#666666","button":"#dcdcdc","button_active":"#c7c7c7","tree":"#ffffff","select":"#bcbcbc"}
    }
    palette = palettes[theme_var.get()]
    style.theme_use("clam")  # ثابت نگه داشتن رنگ پس‌زمینه دکمه‌ها در همه سیستم‌ها

    # رنگ‌آمیزی سراسری ویجت‌های کلاسیک Tk؛ رنگ‌های قدیمی برنامه
    # به نقش‌های پس‌زمینه، پنل و سطح در پوسته جدید نگاشت می‌شوند.
    old_background_roles = {
        "#f3f6fb": "bg", "#202833": "bg", "#edf5ef": "bg",
        "#f3eff8": "bg", "#101b35": "bg", "#111111": "bg",
        "#e6edf7": "panel", "#344253": "panel", "#dcebe0": "panel",
        "#e6def0": "panel", "#243657": "panel", "#fff5f5": "panel",
        "#d5deea": "panel", "#d5e7f5": "panel", "#d2e2f2": "panel",
        "#e5e5e5": "panel", "#e7e7e7": "panel", "#e3e3e3": "panel",
        "#f4f4f4": "bg", "#f5f5f5": "bg", "#eeeeee": "bg",
        "#ffffff": "surface", "white": "surface", "#fffafa": "surface",
        "#1a2948": "surface", "#293442": "surface", "#1b1b1b": "surface",
        "#f4f8f7": "surface", "#f7f8fc": "surface", "#faf9fc": "surface",
        "#f6f7f8": "surface", "#f4f8f5": "surface", "#f6f9fb": "surface",
        "#f7faf7": "surface", "#fffdf7": "surface"
    }
    semantic_foregrounds = {
        "#16845b", "#c44747", "#b00000", "#d00000",
        "#b83232", "#28784a"
    }

    def recolor(widget):
        try:
            cls = widget.winfo_class()
            options = set(widget.configure().keys())
            if "background" in options or "bg" in options:
                option = "background" if "background" in options else "bg"
                old_bg = str(widget.cget(option)).lower()
                role = old_background_roles.get(old_bg)
                if role:
                    widget.configure(**{option: palette[role]})

            # متن‌ها و کنترل‌های ورودی
            if cls in ("Label", "Message", "Button", "Checkbutton",
                       "Radiobutton", "Menubutton", "Labelframe"):
                if "foreground" in options or "fg" in options:
                    fg_option = "foreground" if "foreground" in options else "fg"
                    old_fg = str(widget.cget(fg_option)).lower()
                    if old_fg not in semantic_foregrounds:
                        widget.configure(**{fg_option: palette["fg"]})
            if cls in ("Entry", "Text", "Listbox", "Spinbox"):
                cfg = {}
                if "foreground" in options:
                    cfg["foreground"] = palette["fg"]
                elif "fg" in options:
                    cfg["fg"] = palette["fg"]
                if "background" in options:
                    cfg["background"] = palette["surface"]
                elif "bg" in options:
                    cfg["bg"] = palette["surface"]
                if "insertbackground" in options:
                    cfg["insertbackground"] = palette["fg"]
                if cfg:
                    widget.configure(**cfg)
            if cls == "Canvas":
                widget.configure(background=palette["surface"])
            if cls == "Menu":
                widget.configure(background=palette["panel"],
                                 foreground=palette["fg"],
                                 activebackground=palette["select"],
                                 activeforeground=palette["fg"])
        except (tk.TclError, KeyError, TypeError):
            pass

        try:
            for child in widget.winfo_children():
                recolor(child)
        except tk.TclError:
            pass

    root.configure(bg=palette["bg"])
    recolor(root)
    style.configure("TFrame", background=palette["bg"])
    style.configure("TNotebook", background=palette["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", background=palette["panel"],
                    foreground=palette["fg"], padding=(10, 5))
    style.map("TNotebook.Tab",
              background=[("selected", palette["surface"]), ("active", palette["select"])],
              foreground=[("selected", palette["fg"])])
    style.configure("TScrollbar", background=palette["panel"],
                    troughcolor=palette["bg"], arrowcolor=palette["fg"])
    style.configure("Horizontal.TProgressbar", background=palette["accent"],
                    troughcolor=palette["panel"])
    style.configure("Vertical.TProgressbar", background=palette["accent"],
                    troughcolor=palette["panel"])
    style.configure("TCheckbutton", background=palette["bg"],
                    foreground=palette["fg"])
    style.configure("TRadiobutton", background=palette["bg"],
                    foreground=palette["fg"])
    style.configure("TLabel", background=palette["bg"], foreground=palette["fg"],
                    font=(family, size))
    style.configure("TLabelframe", background=palette["bg"],
                    foreground=palette["fg"])
    style.configure("TLabelframe.Label", background=palette["bg"],
                    foreground=palette["fg"], font=(family, size, "bold"))
    button_fg = palette.get("button_fg", palette["fg"])
    style.configure("TButton", font=(family, size, "bold"),
                    padding=button_padding, foreground=button_fg,
                    background=palette["button"])
    style.map("TButton", background=[("active", palette["button_active"])],
              foreground=[("!disabled", button_fg), ("disabled", "#9aa5b8")])
    style.configure("Action.TButton", font=(family, size, "bold"),
                    padding=button_padding, foreground=button_fg,
                    background=palette["button"])
    style.map("Action.TButton",
              background=[("active", palette["button_active"])],
              foreground=[("!disabled", button_fg), ("disabled", "#9aa5b8")])
    style.configure("TEntry", fieldbackground=palette["surface"],
                    foreground=palette["fg"], padding=5)
    style.configure("TCombobox", fieldbackground=palette["surface"],
                    foreground=palette["fg"], padding=5)
    style.configure("Treeview", background=palette["tree"],
                    fieldbackground=palette["tree"], foreground=palette["fg"],
                    rowheight=size * 3 + 8)
    style.configure("Treeview.Heading", background=palette["panel"],
                    foreground=palette["fg"], font=(family, size, "bold"))
    style.map("Treeview", background=[("selected", palette["select"])],
              foreground=[("selected", palette["fg"])])

    if show_message:
        messagebox.showinfo("تنظیمات اعمال شد",
                            "فونت، اندازه دکمه‌ها و پوسته ظاهری برنامه تغییر کرد.")

# با انتخاب پوسته، تغییر رنگ‌ها فوراً در تمام پنجره اعمال شود.
theme_box.bind(
    "<<ComboboxSelected>>",
    lambda event: apply_appearance_settings(show_message=False)
)

ttk.Button(
    settings_panel, text="اعمال تنظیمات", style="Action.TButton",
    command=apply_appearance_settings
).grid(row=3, column=0, columnspan=4, pady=(3, 2), ipadx=10)

# A clear hint that records can be edited by selecting a row and using Edit.
tk.Label(
    settings_tab,
    text="برای ویرایش اطلاعات، ابتدا ردیف موردنظر را در جدول انتخاب کنید و سپس دکمه «ویرایش» همان بخش را بزنید.",
    bg="#f3f6fb", fg="#53657d", font=(default_font, 8)
).pack(anchor="e", padx=8, pady=3)


# Reports page - compact dashboard and balanced detail panels
report_header = tk.Frame(reports_tab, bg="#e6edf7", padx=8, pady=5)
report_header.pack(fill="x", padx=8, pady=(5, 3))
tk.Label(
    report_header, text="گزارش عملکرد تعمیرگاه و انبار",
    bg="#e6edf7", fg="#17365d", font=(default_font, 11, "bold")
).pack(side="right")
ttk.Button(
    report_header, text="تازه‌سازی",
    command=lambda: refresh_reports()
).pack(side="left", padx=2)
ttk.Button(
    report_header, text="چاپ انبار",
    command=lambda: print_inventory_report(), style="Action.TButton"
).pack(side="left", padx=2)
ttk.Button(
    report_header, text="چاپ تعمیرات و جایگزینی",
    command=lambda: print_repair_report(), style="Action.TButton"
).pack(side="left", padx=2, pady=1)

report_cards_frame = tk.Frame(reports_tab, bg="#f3f6fb")
report_cards_frame.pack(fill="x", padx=6, pady=2)
for col in range(6):
    report_cards_frame.columnconfigure(col, weight=1, uniform="reportcard")

report_values = {}
report_card_specs = [
    ("دستگاه‌های وارده", "incoming", "#17365d"),
    ("دستگاه‌های خارج‌شده", "outgoing", "#53657d"),
    ("تعمیرشده / آماده تحویل", "repaired", "#16845b"),
    ("جایگزین‌شده", "replaced", "#2878a8"),
    ("غیر قابل تعمیر", "unrepairable", "#b04b42"),
    ("اقلام انبار", "stock_items", "#8a641d"),
]
for index, (caption, key, color) in enumerate(report_card_specs):
    row, col = divmod(index, 6)
    card = tk.Frame(
        report_cards_frame, bg="white", padx=4, pady=3,
        highlightbackground="#d5deea", highlightthickness=1
    )
    card.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)
    tk.Label(
        card, text=caption, bg="white", fg="#53657d",
        font=(default_font, 8), wraplength=120
    ).pack()
    var = tk.StringVar(value="0")
    report_values[key] = var
    tk.Label(
        card, textvariable=var, bg="white", fg=color,
        font=(default_font, 12, "bold")
    ).pack(pady=(0, 0))

report_details = tk.Frame(reports_tab, bg="#f3f6fb")
report_details.pack(fill="both", expand=True, padx=6, pady=(1, 5))
report_details.columnconfigure(0, weight=1, uniform="reportdetail")
report_details.columnconfigure(1, weight=1, uniform="reportdetail")
report_details.rowconfigure(0, weight=2)
report_details.rowconfigure(1, weight=1)

report_devices_frame = tk.LabelFrame(
    report_details, text="دستگاه‌های وارده و وضعیت آن‌ها",
    bg="#f3f6fb", fg="#17365d", font=(default_font, 10, "bold"),
    padx=4, pady=3
)
report_devices_frame.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
report_stock_frame = tk.LabelFrame(
    report_details, text="موجودی فعلی انبار",
    bg="#f3f6fb", fg="#17365d", font=(default_font, 10, "bold"),
    padx=4, pady=3
)
report_stock_frame.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

report_device_cols = ("id", "device", "code", "branch", "date", "status")
report_device_headers = {
    "id": "ردیف", "device": "نام دستگاه", "code": "کد امید نت",
    "branch": "شعبه", "date": "تاریخ ورود", "status": "وضعیت"
}
report_device_table = ttk.Treeview(
    report_devices_frame, columns=report_device_cols, show="headings", height=7
)
for col in report_device_cols:
    report_device_table.heading(col, text=report_device_headers[col], anchor="center")
    report_device_table.column(col, width=88, minwidth=60, anchor="center")
report_device_y = ttk.Scrollbar(
    report_devices_frame, orient="vertical", command=report_device_table.yview
)
report_device_x = ttk.Scrollbar(
    report_devices_frame, orient="horizontal", command=report_device_table.xview
)
report_device_table.configure(
    yscrollcommand=report_device_y.set, xscrollcommand=report_device_x.set
)
report_devices_frame.rowconfigure(0, weight=1)
report_devices_frame.columnconfigure(0, weight=1)
report_device_table.grid(row=0, column=0, sticky="nsew")
report_device_y.grid(row=0, column=1, sticky="ns")
report_device_x.grid(row=1, column=0, sticky="ew")

report_stock_cols = ("name", "code", "category", "quantity", "unit", "minimum")
report_stock_headers = {
    "name": "نام کالا", "code": "کد کالا", "category": "دسته‌بندی",
    "quantity": "موجودی", "unit": "واحد", "minimum": "حداقل موجودی"
}
report_stock_table = ttk.Treeview(
    report_stock_frame, columns=report_stock_cols, show="headings", height=7
)
for col in report_stock_cols:
    report_stock_table.heading(col, text=report_stock_headers[col], anchor="center")
    report_stock_table.column(col, width=88, minwidth=60, anchor="center")
report_stock_y = ttk.Scrollbar(
    report_stock_frame, orient="vertical", command=report_stock_table.yview
)
report_stock_x = ttk.Scrollbar(
    report_stock_frame, orient="horizontal", command=report_stock_table.xview
)
report_stock_table.configure(
    yscrollcommand=report_stock_y.set, xscrollcommand=report_stock_x.set
)
report_stock_frame.rowconfigure(0, weight=1)
report_stock_frame.columnconfigure(0, weight=1)
report_stock_table.grid(row=0, column=0, sticky="nsew")
report_stock_y.grid(row=0, column=1, sticky="ns")
report_stock_x.grid(row=1, column=0, sticky="ew")

report_parts_frame = tk.LabelFrame(
    report_details, text="گزارش دستگاه‌های تعمیرشده و قطعات تعویضی / جایگزین‌شده",
    bg="#f3f6fb", fg="#17365d", font=(default_font, 9, "bold"), padx=4, pady=3
)
report_parts_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=2, pady=2)
report_parts_frame.rowconfigure(0, weight=1)
report_parts_frame.columnconfigure(0, weight=1)
report_parts_cols = ("date", "code", "device", "serial", "part", "quantity", "status")
report_parts_headers = {
    "date": "تاریخ", "code": "کد امید نت", "device": "نام دستگاه",
    "serial": "شماره سریال / اموال", "part": "قطعه تعویضی",
    "quantity": "تعداد", "status": "وضعیت دستگاه"
}
report_parts_table = ttk.Treeview(
    report_parts_frame, columns=report_parts_cols, show="headings", height=4
)
for col in report_parts_cols:
    report_parts_table.heading(col, text=report_parts_headers[col], anchor="center")
    report_parts_table.column(col, width=130, minwidth=75, anchor="center",
                              stretch=(col in ("device", "part", "status")))
report_parts_y = ttk.Scrollbar(report_parts_frame, orient="vertical", command=report_parts_table.yview)
report_parts_x = ttk.Scrollbar(report_parts_frame, orient="horizontal", command=report_parts_table.xview)
report_parts_table.configure(yscrollcommand=report_parts_y.set, xscrollcommand=report_parts_x.set)
report_parts_table.grid(row=0, column=0, sticky="nsew")
report_parts_y.grid(row=0, column=1, sticky="ns")
report_parts_x.grid(row=1, column=0, sticky="ew")
style.configure("CompactReport.Treeview", font=(default_font, 8), rowheight=22)
style.configure("CompactReport.Treeview.Heading", font=(default_font, 8, "bold"), padding=(3, 3))
report_device_table.configure(style="CompactReport.Treeview")
report_stock_table.configure(style="CompactReport.Treeview")
report_parts_table.configure(style="CompactReport.Treeview")



def _html_report(title, subtitle, headers, rows, highlight_column=None, low_stock=False):
    """Create a printable Persian RTL HTML report and open it in the browser."""
    def cell(value):
        return html.escape("" if value is None else str(value))
    body_rows = []
    for row in rows:
        is_low = False
        if low_stock and len(row) >= 6:
            try:
                is_low = int(row[3]) <= int(row[5])
            except (TypeError, ValueError):
                pass
        css = ' class="low"' if is_low else ''
        body_rows.append("<tr" + css + ">" + "".join(f"<td>{cell(v)}</td>" for v in row) + "</tr>")
    table = "<table><thead><tr>" + "".join(f"<th>{cell(h)}</th>" for h in headers) + "</tr></thead><tbody>" + "".join(body_rows) + "</tbody></table>"
    note_html = '<p class="note">ردیف‌های زردرنگ نشان‌دهنده کالاهای کم‌موجود یا رسیده به حداقل موجودی هستند.</p>' if low_stock else ''
    document = f"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><title>{cell(title)}</title>
<style>body{{font-family:Tahoma,Arial,sans-serif;margin:28px;color:#172033}}h1{{font-size:22px}}.sub{{color:#555;margin-bottom:20px}}table{{width:100%;border-collapse:collapse;font-size:12px}}th,td{{border:1px solid #777;padding:7px;text-align:center}}th{{background:#e7edf5}}tr.low{{background:#fff0b3}}.note{{margin-top:12px;color:#9b1c1c;font-size:12px}}@media print{{body{{margin:10mm}}button{{display:none}}}}</style></head>
<body><h1>{cell(title)}</h1><div class="sub">{cell(subtitle)} | تاریخ تهیه: {cell(jalali_today())}</div>{table}
{note_html}<button onclick="window.print()">چاپ گزارش</button></body></html>"""

    try:
        fd, filename = tempfile.mkstemp(prefix="royal_report_", suffix=".html")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(document)
        webbrowser.open(Path(filename).resolve().as_uri())
        messagebox.showinfo("گزارش آماده چاپ", "گزارش در مرورگر باز شد. برای چاپ، دکمه «چاپ گزارش» یا کلیدهای Ctrl+P را بزنید.")
    except Exception as exc:
        messagebox.showerror("خطا در تهیه گزارش", str(exc))


def print_inventory_report():
    with connect() as con:
        rows = con.execute("""SELECT item_name, item_code, category, quantity, unit, min_quantity
            FROM inventory ORDER BY item_name COLLATE NOCASE""").fetchall()
    headers = ["نام کالا", "کد کالا", "دسته‌بندی", "موجودی", "واحد", "حداقل موجودی"]
    _html_report("گزارش موجودی انبار و کمبود قطعات", "فهرست همه کالاها؛ موارد کمبود با رنگ زرد مشخص شده‌اند", headers, rows, low_stock=True)


def print_repair_report():
    """Print repair actions and all repaired/replaced device records."""
    with connect() as con:
        part_rows = con.execute("""SELECT repair_date, omid_net_code, device_name,
            serial_number, replaced_part, replaced_quantity
            FROM device_repairs ORDER BY id DESC""").fetchall()
        device_rows = con.execute("""SELECT received_date, omid_net_code, device,
            asset_no, branch, status FROM repairs
            WHERE TRIM(COALESCE(status,'')) IN
            ('آماده تحویل','تحویل داده شد','جایگزین شده','جایگزین‌شده')
            ORDER BY id DESC""").fetchall()

    rows = []
    for row in part_rows:
        rows.append(("قطعه مصرف‌شده در تعمیر", row[0], row[1], row[2], row[3], row[4], "—", row[5]))
    for row in device_rows:
        status = str(row[5] or "").strip()
        kind = "دستگاه جایگزین‌شده" if status in ("جایگزین شده", "جایگزین‌شده") else "دستگاه تعمیرشده"
        rows.append((kind, row[0], row[1], row[2], row[3], status, row[4], "—"))
    headers = [
        "نوع سابقه", "تاریخ", "کد امید نت", "نام دستگاه",
        "سریال / شماره اموال", "قطعه / وضعیت", "شعبه", "تعداد"
    ]
    _html_report(
        "گزارش دستگاه‌های تعمیرشده و جایگزین‌شده",
        f"سوابق قطعات مصرف‌شده: {len(part_rows)} | دستگاه‌های تعمیرشده یا جایگزین‌شده: {len(device_rows)}",
        headers, rows
    )


def refresh_reports():
    """Refresh report totals and the device/stock detail tables."""
    with connect() as con:
        total = con.execute("SELECT COUNT(*) FROM repairs").fetchone()[0]
        outgoing = con.execute(
            "SELECT COUNT(*) FROM repairs WHERE TRIM(COALESCE(status,''))='تحویل داده شد'"
        ).fetchone()[0]
        repaired = con.execute(
            "SELECT COUNT(*) FROM repairs WHERE TRIM(COALESCE(status,'')) IN ('آماده تحویل','تحویل داده شد')"
        ).fetchone()[0]
        replaced = con.execute(
            "SELECT COUNT(*) FROM repairs WHERE TRIM(COALESCE(status,''))='جایگزین شده'"
        ).fetchone()[0]
        unrepairable = con.execute(
            "SELECT COUNT(*) FROM repairs WHERE TRIM(COALESCE(status,''))='غیر قابل تعمیر'"
        ).fetchone()[0]
        stock_items = con.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]
        device_rows = con.execute("""
            SELECT id, device, omid_net_code, branch, received_date, status
            FROM repairs ORDER BY id DESC
        """).fetchall()
        stock_rows = con.execute("""
            SELECT item_name, item_code, category, quantity, unit, min_quantity
            FROM inventory ORDER BY item_name COLLATE NOCASE
        """).fetchall()
        part_rows = con.execute("""SELECT repair_date, omid_net_code, device_name,
            serial_number, replaced_part, replaced_quantity, ''
            FROM device_repairs ORDER BY id DESC""").fetchall()
        device_status_rows = con.execute("""SELECT received_date, omid_net_code, device,
            asset_no, '', 0, status FROM repairs
            WHERE TRIM(COALESCE(status,'')) IN
            ('آماده تحویل','تحویل داده شد','جایگزین شده','جایگزین‌شده')
            ORDER BY id DESC""").fetchall()
        part_rows = part_rows + device_status_rows

    report_values["incoming"].set(str(total))
    report_values["outgoing"].set(str(outgoing))
    report_values["repaired"].set(str(repaired))
    report_values["replaced"].set(str(replaced))
    report_values["unrepairable"].set(str(unrepairable))
    report_values["stock_items"].set(str(stock_items))

    for item in report_device_table.get_children():
        report_device_table.delete(item)
    for row in device_rows:
        report_device_table.insert("", "end", values=row)

    for item in report_stock_table.get_children():
        report_stock_table.delete(item)
    for row in stock_rows:
        is_low = int(row[3]) <= int(row[5])
        report_stock_table.insert("", "end", values=row, tags=(("low",) if is_low else ()))
    report_stock_table.tag_configure("low", background="#fff0b3", foreground="#8a4b00")

    for item in report_parts_table.get_children():
        report_parts_table.delete(item)
    for row in part_rows:
        report_parts_table.insert("", "end", values=row)


apply_appearance_settings(show_message=False)
refresh_table()
refresh_inventory()
refresh_dashboard()
refresh_repair_part_choices()
refresh_device_repairs()
refresh_replacements()
refresh_reports()
notebook.select(home_tab)
root.protocol("WM_DELETE_WINDOW", handle_window_close)
root.after(2500, lambda: check_for_updates(show_current=False))
root.mainloop()
