# =============================================================================
# Project:     HR Face Recognition Attendance System
# Author:      Subhajit Halder
# College:     Jalpaiguri Government Engineering College
# Last Updated: 12th April 2026
# 
# Description:
#   A complete desktop application for managing employee records,
#   documents, attendance, and salary.  Supports face recognition
#   for attendance marking and includes admin authentication.
#
# Revision History:
#   v1.0 (15/03/2026) – Initial release
#   v1.1 (02/04/2026) – Added dual theme (Light/Dark) support
#   v1.2 (12/04/2026) – Updated default database password,
#                       improved UI validations
# =============================================================================

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, Menu
import pymysql
import pymysql.cursors
from PIL import Image, ImageTk, ImageDraw
import os
import sys
import shutil
import datetime
import hashlib
import json
import subprocess
import platform
import time
import face_recognition
import cv2
import numpy as np
import re
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)


# ========== DATABASE CONFIG HELPER ==========
def get_db_password():
    """
    Returns the MySQL root password.
    First tries to read a custom password from 'dbpwd.txt' next to the
    executable/script; if not found or empty, returns the default.
    The default has been updated to 'Sh@#$1256'.
    """
    default_pwd = "Sh@#$1256"                # <-- CHANGED PASSWORD
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    pwd_file = os.path.join(base_dir, "dbpwd.txt")

    if os.path.exists(pwd_file):
        try:
            with open(pwd_file, 'r') as f:
                custom_pwd = f.read().strip()
                if custom_pwd:
                    return custom_pwd
        except Exception:
            pass
    return default_pwd


# ========== CONFIGURATION ==========
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": get_db_password(),
    "database": "company_db"
}
DOC_ROOT = os.path.join(os.path.expanduser("~"), "company_docs")
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

# ========== THEMES (Dual theme: light & dark) ==========
THEMES = {
    "light": {
        "bg": "#F5F7FA", "panel": "#FFFFFF", "card": "#E9EEF5",
        "border": "#CBD5E1", "accent": "#2563EB", "accent2": "#7C3AED",
        "text": "#1E293B", "subtext": "#64748B", "success": "#10B981",
        "warning": "#F59E0B", "danger": "#EF4444", "white": "#FFFFFF"
    },
    "dark": {
        "bg": "#1E1E2E", "panel": "#2B2B3C", "card": "#3A3A4A",
        "border": "#4A4A5A", "accent": "#6C63FF", "accent2": "#A78BFA",
        "text": "#E0E0E0", "subtext": "#A0A0B0", "success": "#4ADE80",
        "warning": "#FBBF24", "danger": "#F87171", "white": "#FFFFFF"
    }
}
current_theme = "light"   # will be overwritten by settings file

# ========== THEME & DATABASE HELPERS ==========
def get_colors():
    """Convenience accessor for the currently active theme colors."""
    return THEMES[current_theme]

def get_conn():
    return pymysql.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        cursorclass=pymysql.cursors.DictCursor
    )

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def load_settings():
    """Load settings from file, with fallback defaults."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {"logo_path": "", "theme": "light"}

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f)
    except Exception:
        pass

def open_file_with_default_app(filepath):
    try:
        if platform.system() == "Windows":
            os.startfile(filepath)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", filepath])
        else:
            subprocess.Popen(["xdg-open", filepath])
    except Exception as ex:
        messagebox.showerror("Error", f"Could not open file:\n{ex}")

def get_expiring_notifications():
    notes = []
    try:
        conn = get_conn()
        cur = conn.cursor()
        cutoff = datetime.date.today() + datetime.timedelta(days=14)
        cur.execute("""
            SELECT id, name, department, visa_expiry,
                   DATEDIFF(visa_expiry, CURDATE()) as days_left
            FROM employees
            WHERE visa_expiry BETWEEN CURDATE() AND %s
        """, (cutoff,))
        for r in cur.fetchall():
            notes.append({
                "emp_id": r["id"],
                "type": "VISA RENEWAL",
                "name": r["name"],
                "dept": r["department"],
                "deadline": r["visa_expiry"],
                "days_left": r["days_left"]
            })
        conn.close()
    except Exception:
        pass
    return notes

def make_avatar(path=None, size=80, fallback_text=""):
    colors = get_colors()
    img = Image.new("RGBA", (size, size), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([0,0,size-1,size-1], fill=colors["border"])
    if path and os.path.exists(path):
        try:
            pic = Image.open(path).convert("RGBA")
            pic = pic.resize((size,size), Image.LANCZOS)
            mask = Image.new("L", (size,size), 0)
            ImageDraw.Draw(mask).ellipse([0,0,size-1,size-1], fill=255)
            img.paste(pic, (0,0), mask)
        except Exception:
            _draw_default_avatar(draw, size, fallback_text, colors)
    else:
        _draw_default_avatar(draw, size, fallback_text, colors)
    return ImageTk.PhotoImage(img)

def _draw_default_avatar(draw, size, text, colors):
    cx, cy = size//2, size//2
    r = size//6
    draw.ellipse([cx-r, cy-r-size//8, cx+r, cy+r-size//8], fill=colors["accent"])
    draw.ellipse([cx-size//3, cy+size//8, cx+size//3, cy+size//2], fill=colors["accent"])
    if text:
        draw.text((cx-6, cy+size//4), text[:2].upper(), fill=colors["white"])

def styled_button(parent, text, command, color=None, fg=None, width=None, font=None):
    colors = get_colors()
    if color is None:
        color = colors["accent"]
    if fg is None:
        fg = colors["white"]
    kw = dict(text=text, command=command, bg=color, fg=fg,
              relief="flat", cursor="hand2",
              font=font or ("Segoe UI", 11), pady=8, padx=18,
              activebackground=color, activeforeground=fg, bd=0)
    if width:
        kw["width"] = width
    return tk.Button(parent, **kw)

def entry_field(parent, placeholder="", show=None):
    colors = get_colors()
    var = tk.StringVar()
    e = tk.Entry(parent, textvariable=var, bg=colors["card"], fg=colors["text"],
                 insertbackground=colors["text"], relief="flat",
                 font=("Segoe UI", 11), bd=0, highlightthickness=1,
                 highlightbackground=colors["border"], highlightcolor=colors["accent"])
    if show:
        e.config(show=show)
    if placeholder:
        e.insert(0, placeholder)
        e.config(fg=colors["subtext"])
        def on_focus_in(event):
            if e.get() == placeholder:
                e.delete(0, "end")
                e.config(fg=colors["text"])
        def on_focus_out(event):
            if not e.get():
                e.insert(0, placeholder)
                e.config(fg=colors["subtext"])
        e.bind("<FocusIn>", on_focus_in)
        e.bind("<FocusOut>", on_focus_out)
    return e, var

def separator(parent, pady=8):
    colors = get_colors()
    f = tk.Frame(parent, bg=colors["border"], height=1)
    f.pack(fill="x", pady=pady)
    return f

def scrollable_frame(parent):
    colors = get_colors()
    outer = tk.Frame(parent, bg=colors["bg"])
    canvas = tk.Canvas(outer, bg=colors["bg"], bd=0, highlightthickness=0)
    sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    inner = tk.Frame(canvas, bg=colors["bg"])

    inner_id = canvas.create_window((0,0), window=inner, anchor="nw")

    def _on_inner_configure(e):
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.itemconfig(inner_id, width=canvas.winfo_width())

    def _on_canvas_configure(e):
        canvas.itemconfig(inner_id, width=e.width)

    inner.bind("<Configure>", _on_inner_configure)
    canvas.bind("<Configure>", _on_canvas_configure)
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    def _bind_mousewheel(widget):
        widget.bind("<MouseWheel>", _on_mousewheel, add="+")
        widget.bind("<Button-4>", _on_mousewheel_linux, add="+")
        widget.bind("<Button-5>", _on_mousewheel_linux_down, add="+")
        for child in widget.winfo_children():
            _bind_mousewheel(child)

    def _on_mousewheel(e):
        canvas.yview_scroll(int(-1*(e.delta/120)), "units")

    def _on_mousewheel_linux(e):
        canvas.yview_scroll(-1, "units")

    def _on_mousewheel_linux_down(e):
        canvas.yview_scroll(1, "units")

    canvas.bind("<MouseWheel>", _on_mousewheel)
    canvas.bind("<Button-4>", _on_mousewheel_linux)
    canvas.bind("<Button-5>", _on_mousewheel_linux_down)
    inner.bind("<Enter>", lambda e: _bind_mousewheel(inner))

    return outer, inner


# ========== DATE HELPERS ==========
def parse_date_dmy(date_str):
    if not date_str:
        return None
    try:
        return datetime.datetime.strptime(date_str, "%d/%m/%Y").date()
    except ValueError:
        return None

def format_date_dmy(date_obj):
    if not date_obj:
        return ""
    return date_obj.strftime("%d/%m/%Y")

def iso_to_dmy(iso_str):
    if not iso_str:
        return ""
    try:
        d = datetime.date.fromisoformat(str(iso_str))
        return d.strftime("%d/%m/%Y")
    except:
        return str(iso_str)


# ========== CORE TIME HELPER ==========
def time_value_to_hours(t):
    if t is None:
        return None
    if isinstance(t, datetime.timedelta):
        total_seconds = t.total_seconds()
        if total_seconds < 0:
            return None
        return total_seconds / 3600.0
    if isinstance(t, datetime.time):
        return t.hour + t.minute / 60.0 + t.second / 3600.0
    if isinstance(t, str):
        s = t.strip()
        if not s or s == "—":
            return None
        parts = s.split(":")
        try:
            if len(parts) >= 2:
                h = int(parts[0])
                m = int(parts[1])
                sec = int(parts[2]) if len(parts) >= 3 else 0
                return h + m / 60.0 + sec / 3600.0
        except (ValueError, IndexError):
            return None
    return None


def time_value_to_hhmm(t):
    hours = time_value_to_hours(t)
    if hours is None:
        return ""
    total_minutes = int(round(hours * 60))
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{h:02d}:{m:02d}:00"  # add seconds


# ========== FACE RECOGNITION HELPERS ==========
def capture_face_encoding(employee_id, name, samples_needed=10):
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            messagebox.showerror("Camera Error", "Could not open webcam.\nTry reconnecting the camera or restarting the application.")
            return None

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    encodings = []
    instruction_shown = False

    try:
        while len(encodings) < samples_needed:
            ret, frame = cap.read()
            if not ret:
                continue

            display = frame.copy()
            if not instruction_shown:
                cv2.putText(display, f"Look at camera. Capturing {samples_needed} samples...",
                            (20,40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
                cv2.putText(display, f"Captured: {len(encodings)}/{samples_needed}",
                            (20,80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
            else:
                cv2.putText(display, "No face detected. Please face the camera.",
                            (20,40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)

            cv2.imshow("Enroll Face - Press ESC to skip", display)

            face_locations = face_recognition.face_locations(frame)
            if face_locations:
                encoding = face_recognition.face_encodings(frame, face_locations)
                if encoding:
                    encodings.append(encoding[0])
                    instruction_shown = False
                    cv2.putText(display, "Sample captured!", (20,120),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
                    cv2.imshow("Enroll Face - Press ESC to skip", display)
                    cv2.waitKey(200)
            else:
                instruction_shown = True

            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # ESC key
                break

    except Exception as e:
        print(f"Camera error: {e}")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        cv2.waitKey(1)

    if not encodings:
        return None
    avg_encoding = np.mean(encodings, axis=0)
    return avg_encoding.tolist()

def store_face_encoding(emp_id, encoding_list):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("UPDATE employees SET face_encoding = %s WHERE id = %s",
                    (json.dumps(encoding_list), emp_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"DB error: {e}")
        return False

def handle_attendance_by_face(emp_id, name):
    today = datetime.date.today()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, checkin, checkout FROM attendance
        WHERE emp_id = %s AND date = %s
    """, (emp_id, today))
    record = cur.fetchone()
    now = datetime.datetime.now().time()

    if not record:
        cur.execute("""
            INSERT INTO attendance (emp_id, date, checkin, status)
            VALUES (%s, %s, %s, 'P')
        """, (emp_id, today, now))
        conn.commit()
        conn.close()
        return f'"{name}" checked in at {now.strftime("%H:%M:%S")}'
    elif record['checkout'] is None:
        cur.execute("""
            UPDATE attendance SET checkout = %s WHERE id = %s
        """, (now, record['id']))
        conn.commit()
        conn.close()
        return f'"{name}" checked out at {now.strftime("%H:%M:%S")}'
    else:
        conn.close()
        return f'"{name}" already checked in and out today.'


# ========== MAIN APPLICATION CLASS ==========
class HRApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Face Recognized Attendance System")
        self.geometry("1100x720")
        self.resizable(True, True)
        self.minsize(900,600)

        global current_theme
        # Load settings and apply stored theme
        settings = load_settings()
        current_theme = settings.get("theme", "light")
        colors = get_colors()
        self.configure(bg=colors["bg"])

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Vertical.TScrollbar",
                        background=colors["card"], troughcolor=colors["bg"],
                        arrowcolor=colors["subtext"], bordercolor=colors["bg"])
        self.cleared_notification_ids = set()
        self._admin = None
        self._show_login()

    def _refresh_style(self):
        """Update the ttk scrollbar style according to the current theme."""
        colors = get_colors()
        self.configure(bg=colors["bg"])
        style = ttk.Style()
        style.configure("Vertical.TScrollbar",
                        background=colors["card"], troughcolor=colors["bg"],
                        arrowcolor=colors["subtext"], bordercolor=colors["bg"])

    def toggle_theme(self):
        """Switch between light and dark theme, persist choice, and refresh the UI."""
        global current_theme
        current_theme = "dark" if current_theme == "light" else "light"
        self._refresh_style()
        # Save to settings file
        settings = load_settings()
        settings["theme"] = current_theme
        save_settings(settings)
        # Rebuild the current page to apply new colours
        if self._admin:
            self._show_home()
        else:
            self._show_login()

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()

    def _show_login(self):
        self._clear()
        LoginPage(self).pack(fill="both", expand=True)

    def _show_home(self):
        self._clear()
        HomePage(self).pack(fill="both", expand=True)

    def _show_department(self, dept_label):
        self._clear()
        DepartmentPage(self, dept_label).pack(fill="both", expand=True)

    def _show_employee(self, emp_id):
        self._clear()
        EmployeePage(self, emp_id).pack(fill="both", expand=True)

    def _show_add_employee(self):
        self._clear()
        AddEmployeePage(self).pack(fill="both", expand=True)

    def _show_notifications(self):
        self._clear()
        NotificationsPage(self).pack(fill="both", expand=True)

    def _show_register(self):
        self._clear()
        RegisterPage(self).pack(fill="both", expand=True)

    def _show_forgot_password(self):
        self._clear()
        ForgotPasswordPage(self).pack(fill="both", expand=True)

    def _show_tools_attendance(self):
        self._clear()
        ToolsAttendancePage(self).pack(fill="both", expand=True)


# ========== TOP BAR ==========
class TopBar(tk.Frame):
    def __init__(self, parent, app, back_cmd=None):
        colors = get_colors()
        super().__init__(parent, bg=colors["panel"], height=58)
        self.pack_propagate(False)
        self.app = app

        logo_frame = tk.Frame(self, bg=colors["panel"])
        logo_frame.pack(side="left", padx=16)

        def resource_path(relative_path):
            """ Get absolute path to resource, works for dev and for PyInstaller """
            try:
                base_path = sys._MEIPASS
            except Exception:
                base_path = os.path.abspath(".")
            return os.path.join(base_path, relative_path)
        fixed_logo_path = resource_path("Company_logo.jpg")
        if os.path.exists(fixed_logo_path):
            try:
                logo_img = Image.open(fixed_logo_path).resize((34, 34), Image.LANCZOS)
                logo_tk = ImageTk.PhotoImage(logo_img)
                lbl_logo = tk.Label(logo_frame, image=logo_tk, bg=colors["panel"])
                lbl_logo.image = logo_tk
                lbl_logo.pack(side="left", padx=(0, 8))
            except Exception:
                self._draw_placeholder_logo(logo_frame, colors)
        else:
            self._draw_placeholder_logo(logo_frame, colors)

        tk.Label(logo_frame, text="COMPANY PLACEHOLDER", bg=colors["panel"], fg=colors["text"],
                 font=("Segoe UI", 14, "bold")).pack(side="left")

        right = tk.Frame(self, bg=colors["panel"])
        right.pack(side="right", padx=16)

        if app._admin:
            notes = get_expiring_notifications()
            cleared_ids = getattr(app, 'cleared_notification_ids', set())
            active_notes = [n for n in notes if n['emp_id'] not in cleared_ids]
            notif_count = len(active_notes)

            notif_frame = tk.Frame(right, bg=colors["panel"])
            notif_frame.pack(side="left", padx=8)
            bell = tk.Label(notif_frame, text="🔔", bg=colors["panel"], fg=colors["text"],
                            font=("Segoe UI", 14), cursor="hand2")
            bell.pack(side="left")
            if notif_count > 0:
                badge = tk.Label(notif_frame, text=str(notif_count),
                                 bg=colors["danger"], fg=colors["white"],
                                 font=("Segoe UI", 8, "bold"), width=2, height=1)
                badge.pack(side="left")
            bell.bind("<Button-1>", lambda e: app._show_notifications())

            profile_img = make_avatar(app._admin.get("profile_image"), 32, app._admin["name"])
            avatar_lbl = tk.Label(right, image=profile_img, bg=colors["panel"], cursor="hand2")
            avatar_lbl.image = profile_img
            avatar_lbl.pack(side="left", padx=8)
            tk.Label(right, text=f"  {app._admin['name']}", bg=colors["panel"], fg=colors["text"],
                     font=("Segoe UI", 10)).pack(side="left", padx=4)

            # --- Theme Toggle Button ---
            theme_icon = "☀" if current_theme == "light" else "🌙"
            theme_btn = tk.Label(right, text=theme_icon, bg=colors["panel"], fg=colors["accent"],
                                 font=("Segoe UI", 16), cursor="hand2")
            theme_btn.pack(side="left", padx=4)
            theme_btn.bind("<Button-1>", lambda e: app.toggle_theme())

            styled_button(right, "Sign Out", lambda: self._confirm_sign_out(),
                          color=colors["border"], fg=colors["subtext"],
                          font=("Segoe UI", 10)).pack(side="left", padx=4)

        if back_cmd:
            btn = tk.Label(self, text="← Back", bg=colors["panel"], fg=colors["accent"],
                           font=("Segoe UI", 11), cursor="hand2")
            btn.pack(side="left", padx=12)
            btn.bind("<Button-1>", lambda e: back_cmd())

    def _confirm_sign_out(self):
        if messagebox.askyesno("Confirm Sign Out", "Are you sure you want to sign out?", icon="question"):
            self._sign_out()

    def _sign_out(self):
        self.app._admin = None
        self.app._show_login()

    def _draw_placeholder_logo(self, parent, colors):
        try:
            img = Image.new("RGB", (34, 34), colors["accent"])
            draw = ImageDraw.Draw(img)
            draw.rectangle([2, 2, 31, 31], outline=colors["accent2"], width=2)
            draw.text((7, 8), "CO", fill=colors["white"])
            logo_tk = ImageTk.PhotoImage(img)
            lbl = tk.Label(parent, image=logo_tk, bg=colors["panel"])
            lbl.image = logo_tk
            lbl.pack(side="left", padx=(0, 8))
        except Exception:
            tk.Label(parent, text="🏢", bg=colors["panel"], fg=colors["accent"],
                     font=("Segoe UI", 20)).pack(side="left", padx=(0, 8))


# ========== LOGIN PAGE (updated to use username) ==========
class LoginPage(tk.Frame):
    def __init__(self, app):
        colors = get_colors()
        super().__init__(app, bg=colors["bg"])
        self.app = app

        center = tk.Frame(self, bg=colors["bg"])
        center.place(relx=0.5, rely=0.5, anchor="center")

        def resource_path(relative_path):
            try:
                base_path = sys._MEIPASS
            except Exception:
                base_path = os.path.abspath(".")
            return os.path.join(base_path, relative_path)

        fixed_logo_path = resource_path("Company_logo.jpg")

        if os.path.exists(fixed_logo_path):
            try:
                logo_img = Image.open(fixed_logo_path).resize((100, 100), Image.LANCZOS)
                logo_tk = ImageTk.PhotoImage(logo_img)
                lbl = tk.Label(center, image=logo_tk, bg=colors["bg"])
                lbl.image = logo_tk
                lbl.pack(pady=(0, 8))
            except Exception:
                tk.Label(center, text="◈", bg=colors["bg"], fg=colors["accent"],
                         font=("Segoe UI", 48)).pack(pady=(0, 4))
        else:
            tk.Label(center, text="◈", bg=colors["bg"], fg=colors["accent"],
                     font=("Segoe UI", 48)).pack(pady=(0, 4))

        tk.Label(center, text="COMPANY PLACEHOLDER", bg=colors["bg"], fg=colors["text"],
                 font=("Segoe UI",26,"bold")).pack()
        tk.Label(center, text="Face Recognized Attendance System",
                 bg=colors["bg"], fg=colors["subtext"], font=("Segoe UI",10)).pack(pady=(4,32))

        card = tk.Frame(center, bg=colors["panel"], padx=40, pady=36,
                        highlightbackground=colors["border"], highlightthickness=1)
        card.pack(ipadx=10)

        tk.Label(card, text="Username", bg=colors["panel"], fg=colors["subtext"],
                 font=("Segoe UI",10)).pack(anchor="w")
        self.username_e, self.username_v = entry_field(card, " ")
        self.username_e.pack(fill="x", pady=(4,16), ipady=5)

        tk.Label(card, text="Password", bg=colors["panel"], fg=colors["subtext"],
                 font=("Segoe UI",10)).pack(anchor="w")
        self.pass_e, self.pass_v = entry_field(card, show="•")
        self.pass_e.pack(fill="x", pady=(4,24), ipady=5)

        self.pass_e.bind("<Return>", lambda e: self._login())
        self.username_e.bind("<Return>", lambda e: self.pass_e.focus())

        styled_button(card, "LOG IN", self._login, width=24).pack(pady=4)

        links = tk.Frame(card, bg=colors["panel"])
        links.pack(pady=8)
        reg_link = tk.Label(links, text="Create Account", bg=colors["panel"], fg=colors["accent"],
                            cursor="hand2", font=("Segoe UI",10))
        reg_link.pack(side="left", padx=10)
        reg_link.bind("<Button-1>", lambda e: app._show_register())
        fp_link = tk.Label(links, text="Forgot Password?", bg=colors["panel"], fg=colors["accent"],
                           cursor="hand2", font=("Segoe UI",10))
        fp_link.pack(side="left", padx=10)
        fp_link.bind("<Button-1>", lambda e: app._show_forgot_password())

        self.msg = tk.Label(card, text="", bg=colors["panel"], fg=colors["danger"],
                            font=("Segoe UI",10))
        self.msg.pack(pady=6)

    def _login(self):
        username = self.username_e.get().strip()
        pwd = self.pass_e.get().strip()

        if username == "Enter username":
            username = ""

        if not username or not pwd:
            self.msg.config(text="Please enter username and password.")
            return

        if len(username) < 8:
            self.msg.config(text="Username must be at least 8 characters.")
            return

        if len(pwd) < 8:
            self.msg.config(text="Password must be at least 8 characters.")
            return

        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT id, name, username, profile_image FROM admins "
                "WHERE username=%s AND password_hash=%s",
                (username, hash_password(pwd))
            )
            admin = cur.fetchone()
            conn.close()
            if admin:
                self.app._admin = admin
                self.app._show_home()
            else:
                self.msg.config(text="Invalid username or password.")
        except Exception as ex:
            self.msg.config(text=f"DB Error: {ex}")


# ========== REGISTER PAGE (unchanged except theme awareness) ==========
class RegisterPage(tk.Frame):
    def __init__(self, app):
        colors = get_colors()
        super().__init__(app, bg=colors["bg"])
        self.app = app
        self.profile_image_path = ""

        outer, inner = scrollable_frame(self)
        outer.pack(fill="both", expand=True)

        wrapper = tk.Frame(inner, bg=colors["bg"])
        wrapper.pack(padx=40, pady=30)

        tk.Label(wrapper, text="Create Admin Account", bg=colors["bg"], fg=colors["text"],
                 font=("Segoe UI",22,"bold")).pack(pady=(0,20))

        card = tk.Frame(wrapper, bg=colors["panel"], padx=30, pady=20,
                        highlightbackground=colors["border"], highlightthickness=1)
        card.pack(fill="x")

        fields = [
            ("Full Name", "name", None, ""),
            ("Phone Number", "phone", None, "+971 XX XXX XXXX"),
            ("Username", "username", None, ""),
            ("Password", "pwd", "•", ""),
            ("Confirm Password", "cpwd", "•", ""),
            ("Company Key", "comp_key", None, ""),
        ]
        self.entries = {}
        for label, key, show, placeholder in fields:
            tk.Label(card, text=label, bg=colors["panel"], fg=colors["subtext"],
                     font=("Segoe UI",10)).pack(anchor="w", pady=(8,2))
            e, var = entry_field(card, placeholder=placeholder, show=show)
            e.pack(fill="x", ipady=5)
            self.entries[key] = (e, var)

        pic_row = tk.Frame(card, bg=colors["panel"])
        pic_row.pack(fill="x", pady=(10,0))
        tk.Label(pic_row, text="Profile Picture (PNG/JPEG)", bg=colors["panel"], fg=colors["subtext"],
                 font=("Segoe UI",10)).pack(anchor="w", pady=(0,4))
        self.pp_label = tk.Label(card, text="No file chosen", bg=colors["panel"],
                                 fg=colors["subtext"], font=("Segoe UI",10))
        self.pp_label.pack(anchor="w")
        styled_button(card, "Browse Image", self._browse_image,
                      color=colors["accent2"], font=("Segoe UI",10)).pack(anchor="w", pady=(4,0))

        self.msg = tk.Label(card, text="", bg=colors["panel"], fg=colors["danger"],
                            font=("Segoe UI",10))
        self.msg.pack(pady=8)

        styled_button(wrapper, "REGISTER", self._register, width=20).pack(pady=16)
        back_btn = tk.Label(wrapper, text="← Back to Login", bg=colors["bg"],
                            fg=colors["accent"], cursor="hand2", font=("Segoe UI",11))
        back_btn.pack()
        back_btn.bind("<Button-1>", lambda e: app._show_login())

    def _browse_image(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg")])
        if path:
            self.profile_image_path = path
            self.pp_label.config(text=os.path.basename(path), fg=get_colors()["success"])

    def _validate_name(self, name):
        return bool(re.match(r"^[A-Za-z\s]+$", name))

    def _validate_phone(self, phone):
        pattern = r"^\+971 \d{2} \d{3} \d{4}$"
        return bool(re.match(pattern, phone))

    def _register(self):
        name = self.entries["name"][0].get().strip()
        phone = self.entries["phone"][0].get().strip()
        username = self.entries["username"][0].get().strip()
        pwd = self.entries["pwd"][0].get()
        cpwd = self.entries["cpwd"][0].get()
        comp_key = self.entries["comp_key"][0].get().strip()

        if not all([name, phone, username, pwd, cpwd, comp_key]):
            self.msg.config(text="All fields are required")
            return

        if not self._validate_name(name):
            self.msg.config(text="Full name must contain only letters.")
            return

        if not self._validate_phone(phone):
            self.msg.config(text="Enter valid phone number (+971 XX XXX XXXX)")
            return

        if len(username) < 8:
            self.msg.config(text="Username must contain at least 8 characters.")
            return

        if pwd != cpwd:
            self.msg.config(text="Passwords do not match")
            return
        if len(pwd) < 8:
            self.msg.config(text="Password must contain at least 8 characters")
            return
        if len(pwd) > 16:
            self.msg.config(text="Password cannot contain more than 16 characters")
            return

        if comp_key != "123456":
            self.msg.config(text="Invalid Company Key")
            return

        dest_path = ""
        if self.profile_image_path:
            profile_dir = os.path.join(DOC_ROOT, "profiles")
            os.makedirs(profile_dir, exist_ok=True)
            ext = os.path.splitext(self.profile_image_path)[1]
            dest_path = os.path.join(profile_dir, f"{username}{ext}")
            shutil.copy2(self.profile_image_path, dest_path)

        try:
            conn = get_conn()
            cur = conn.cursor()
            # Check if username already exists
            cur.execute("SELECT id FROM admins WHERE username = %s", (username,))
            if cur.fetchone():
                self.msg.config(text="Username already exists. Please choose another.")
                conn.close()
                return

            cur.execute("""
                        INSERT INTO admins (name, phone, username, password_hash, company_key, profile_image)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """, (name, phone, username, hash_password(pwd), comp_key, dest_path))
            conn.commit()
            conn.close()
            messagebox.showinfo("Success", "Account created! Please login.")
            self.app._show_login()
        except pymysql.err.IntegrityError:
            self.msg.config(text="Username already exists.")
        except Exception as ex:
            self.msg.config(text=f"Error: {ex}")


# ========== FORGOT PASSWORD PAGE ==========
class ForgotPasswordPage(tk.Frame):
    def __init__(self, app):
        colors = get_colors()
        super().__init__(app, bg=colors["bg"])
        self.app = app

        center = tk.Frame(self, bg=colors["bg"])
        center.place(relx=0.5, rely=0.5, anchor="center")

        card = tk.Frame(center, bg=colors["panel"], padx=40, pady=36,
                        highlightbackground=colors["border"], highlightthickness=1)
        card.pack()

        tk.Label(card, text="Reset Password", bg=colors["panel"], fg=colors["text"],
                 font=("Segoe UI",16,"bold")).pack(pady=(0,20))

        fields = [
            ("Full Name", "name", None, ""),
            ("Phone Number", "phone", None, "+971 XX XXX XXXX"),
            ("Company Key", "comp_key", None, ""),
            ("New Password", "new_pwd", "•", ""),
            ("Confirm Password", "conf_pwd", "•", ""),
        ]
        self.entries = {}
        for label, key, show, placeholder in fields:
            tk.Label(card, text=label, bg=colors["panel"], fg=colors["subtext"],
                     font=("Segoe UI",10)).pack(anchor="w", pady=(8,2))
            e, var = entry_field(card, placeholder=placeholder, show=show)
            e.pack(fill="x", ipady=5)
            self.entries[key] = (e, var)

        self.msg = tk.Label(card, text="", bg=colors["panel"], fg=colors["danger"],
                            font=("Segoe UI",10))
        self.msg.pack(pady=8)
        styled_button(card, "RESET PASSWORD", self._reset, width=20).pack(pady=8)
        back_btn = tk.Label(card, text="← Back to Login", bg=colors["panel"],
                            fg=colors["accent"], cursor="hand2", font=("Segoe UI",11))
        back_btn.pack()
        back_btn.bind("<Button-1>", lambda e: app._show_login())

    def _validate_name(self, name):
        return bool(re.match(r"^[A-Za-z\s]+$", name))

    def _validate_phone(self, phone):
        pattern = r"^\+971 \d{2} \d{3} \d{4}$"
        return bool(re.match(pattern, phone))

    def _reset(self):
        name = self.entries["name"][0].get().strip()
        phone = self.entries["phone"][0].get().strip()
        comp_key = self.entries["comp_key"][0].get().strip()
        new_pwd = self.entries["new_pwd"][0].get()
        conf_pwd = self.entries["conf_pwd"][0].get()

        if not all([name, phone, comp_key, new_pwd, conf_pwd]):
            self.msg.config(text="All fields required")
            return

        if not self._validate_name(name):
            self.msg.config(text="Full name must contain only letters.")
            return

        if not self._validate_phone(phone):
            self.msg.config(text="Enter valid phone number (+971 XX XXX XXXX)")
            return

        if new_pwd != conf_pwd:
            self.msg.config(text="Passwords do not match")
            return
        if len(new_pwd) < 8:
            self.msg.config(text="Password must contain at least 8 characters")
            return
        if len(new_pwd) > 16:
            self.msg.config(text="Password cannot contain more than 16 characters")
            return

        if comp_key != "123456":
            self.msg.config(text="Invalid Company Key")
            return

        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM admins WHERE name=%s AND phone=%s AND company_key=%s",
                (name, phone, comp_key)
            )
            admin = cur.fetchone()
            if not admin:
                self.msg.config(text="No matching user found")
                conn.close()
                return
            cur.execute("UPDATE admins SET password_hash=%s WHERE id=%s",
                        (hash_password(new_pwd), admin['id']))
            conn.commit()
            conn.close()
            messagebox.showinfo("Success", "Password updated. Please login.")
            self.app._show_login()
        except Exception as ex:
            self.msg.config(text=f"Error: {ex}")


# ========== HOME PAGE ==========
class HomePage(tk.Frame):
    def __init__(self, app):
        colors = get_colors()
        super().__init__(app, bg=colors["bg"])
        self.app = app
        TopBar(self, app).pack(fill="x")

        outer, inner = scrollable_frame(self)
        outer.pack(fill="both", expand=True)

        hdr = tk.Frame(inner, bg=colors["bg"])
        hdr.pack(fill="x", padx=32, pady=(28,8))
        now = datetime.datetime.now()
        self._date_lbl = tk.Label(hdr, text=now.strftime("%d %B %Y"),
                                  bg=colors["bg"], fg=colors["subtext"], font=("Segoe UI",10))
        self._date_lbl.pack(side="left")
        self._time_lbl = tk.Label(hdr, text=now.strftime(" %I:%M:%S %p"),
                                  bg=colors["bg"], fg=colors["subtext"], font=("Segoe UI",10))
        self._time_lbl.pack(side="left")
        self._tick()

        tk.Label(inner, text="Departments", bg=colors["bg"], fg=colors["text"],
                 font=("Segoe UI",22,"bold")).pack(anchor="center", padx=32, pady=(8,4))

        grid = tk.Frame(inner, bg=colors["bg"])
        grid.pack(padx=32, fill="x")

        icons = ["👥", "💻", "💰", "📣", "⚙️", "📈"]
        depts = ["Human Resources (HR)", "Information Technology (IT)",
                 "Finance / Accounting", "Marketing & Communications",
                 "Operations Management", "Sales Management"]
        dept_map = {
            "Human Resources (HR)": "HR",
            "Information Technology (IT)": "IT",
            "Finance / Accounting": "Finance",
            "Marketing & Communications": "Marketing",
            "Operations Management": "Operations",
            "Sales Management": "Sales"
        }
        for i, (dept, icon) in enumerate(zip(depts, icons)):
            row, col = divmod(i,2)
            self._dept_card(grid, dept, icon, row, col, dept_map)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        tk.Label(inner, text="Tools", bg=colors["bg"], fg=colors["text"],
                 font=("Segoe UI",22,"bold")).pack(anchor="center", padx=32, pady=(24,8))
        tools_frame = tk.Frame(inner, bg=colors["bg"])
        tools_frame.pack(fill="x", padx=32, pady=10)
        tools_inner = tk.Frame(tools_frame, bg=colors["bg"])
        tools_inner.pack(anchor="center")
        scan_btn = tk.Button(tools_inner, text="📸  Face Scan",
                             command=lambda: app._show_tools_attendance(),
                             bg=colors["card"], fg=colors["accent"],
                             font=("Segoe UI",13,"bold"), padx=25, pady=12,
                             relief="flat", cursor="hand2", bd=0,
                             activebackground=colors["accent"], activeforeground=colors["white"])
        scan_btn.pack(side="left", padx=10)

        add_emp_btn = tk.Button(tools_inner, text="➕  Add Employee",
                                command=lambda: app._show_add_employee(),
                                bg=colors["card"], fg=colors["success"],
                                font=("Segoe UI",13,"bold"), padx=25, pady=12,
                                relief="flat", cursor="hand2", bd=0,
                                activebackground=colors["success"], activeforeground=colors["white"])
        add_emp_btn.pack(side="left", padx=10)

    def _tick(self):
        now = datetime.datetime.now()
        try:
            self._date_lbl.config(text=now.strftime("%d %B %Y"))
            self._time_lbl.config(text=now.strftime(" %I:%M:%S %p"))
            self.after(1000, self._tick)
        except tk.TclError:
            pass

    def _dept_card(self, parent, dept, icon, row, col, dept_map):
        colors = get_colors()
        card = tk.Frame(parent, bg=colors["card"], cursor="hand2",
                        highlightbackground=colors["border"], highlightthickness=1)
        card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew", ipadx=20, ipady=18)

        tk.Label(card, text=icon, bg=colors["card"], font=("Segoe UI",28)).pack(anchor="center", padx=16, pady=(16,4))
        tk.Label(card, text=dept, bg=colors["card"], fg=colors["text"],
                 font=("Segoe UI",13,"bold")).pack(anchor="center", padx=16)

        short = dept_map.get(dept, dept)
        count = 0
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM employees WHERE department=%s", (short,))
            row = cur.fetchone()
            count = row['COUNT(*)'] if row else 0
            conn.close()
        except Exception:
            pass

        tk.Label(card, text=f"{count} employee{'s' if count != 1 else ''}",
                 bg=colors["card"], fg=colors["subtext"], font=("Segoe UI",10)).pack(anchor="center", padx=16, pady=(2,16))

        def nav(e, d=dept):
            self.app._show_department(d)

        for w in [card] + card.winfo_children():
            w.bind("<Button-1>", nav)

        card.bind("<Enter>", lambda e, c=card: c.config(highlightbackground=colors["accent"]))
        card.bind("<Leave>", lambda e, c=card: c.config(highlightbackground=colors["border"]))


# ========== DEPARTMENT PAGE ==========
class DepartmentPage(tk.Frame):
    def __init__(self, app, dept_label):
        colors = get_colors()
        super().__init__(app, bg=colors["bg"])
        self.app = app
        self.dept_label = dept_label
        dept_map = {
            "Human Resources (HR)": "HR",
            "Information Technology (IT)": "IT",
            "Finance / Accounting": "Finance",
            "Marketing & Communications": "Marketing",
            "Operations Management": "Operations",
            "Sales Management": "Sales"
        }
        self.dept_short = dept_map.get(dept_label, dept_label)

        TopBar(self, app, back_cmd=lambda: app._show_home()).pack(fill="x")

        hdr = tk.Frame(self, bg=colors["bg"])
        hdr.pack(fill="x", padx=32, pady=(24,0))
        tk.Label(hdr, text=dept_label, bg=colors["bg"], fg=colors["text"],
                 font=("Segoe UI",22,"bold")).pack(anchor="center")

        separator(self, pady=12)

        outer, inner = scrollable_frame(self)
        outer.pack(fill="both", expand=True, padx=32, pady=8)
        self._load_employees(inner)

    def _load_employees(self, parent):
        colors = get_colors()
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT * FROM employees WHERE department=%s ORDER BY name",
                        (self.dept_short,))
            employees = cur.fetchall()
            conn.close()
        except Exception as ex:
            tk.Label(parent, text=f"DB Error: {ex}", bg=colors["bg"], fg=colors["danger"]).pack()
            return

        if not employees:
            tk.Label(parent, text="No employees in this department.",
                     bg=colors["bg"], fg=colors["subtext"], font=("Segoe UI",11)).pack(pady=40)
            return

        for emp in employees:
            self._emp_row(parent, emp)

    def _emp_row(self, parent, emp):
        colors = get_colors()
        row = tk.Frame(parent, bg=colors["card"],
                       highlightbackground=colors["border"], highlightthickness=1)
        row.pack(fill="x", pady=6, padx=2, ipady=10)

        photo_path = self._get_employee_photo(emp["id"])
        av_img = make_avatar(photo_path, 48, emp["name"])
        av_lbl = tk.Label(row, image=av_img, bg=colors["card"], cursor="hand2")
        av_lbl.image = av_img
        av_lbl.pack(side="left", padx=16)

        info = tk.Frame(row, bg=colors["card"], cursor="hand2")
        info.pack(side="left", fill="x", expand=True)
        tk.Label(info, text=emp["name"], bg=colors["card"], fg=colors["text"],
                 font=("Segoe UI",13,"bold"), cursor="hand2").pack(anchor="w")
        tk.Label(info, text=f"{emp['position']}  •  ID: {emp['company_id']}",
                 bg=colors["card"], fg=colors["subtext"], font=("Segoe UI",10),
                 cursor="hand2").pack(anchor="w")

        right_side = tk.Frame(row, bg=colors["card"])
        right_side.pack(side="right", padx=8)

        # Replace recycle bin icon with "Remove" button
        remove_btn = styled_button(right_side, "Remove",
                                   command=lambda eid=emp["id"], ename=emp["name"]: self._quick_delete(eid, ename),
                                   color=colors["danger"], font=("Segoe UI", 9))
        remove_btn.pack(side="right", padx=(4,0))

        def nav(e, eid=emp["id"]):
            self.app._show_employee(eid)

        for w in [row, av_lbl, info] + info.winfo_children():
            w.bind("<Button-1>", nav)

        row.bind("<Enter>", lambda e, r=row: r.config(highlightbackground=colors["accent"]))
        row.bind("<Leave>", lambda e, r=row: r.config(highlightbackground=colors["border"]))

    def _quick_delete(self, emp_id, emp_name):
        if not messagebox.askyesno("Confirm Delete",
                                   f"Delete {emp_name}? This cannot be undone.",
                                   icon="warning"):
            return
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT department FROM employees WHERE id=%s", (emp_id,))
            row = cur.fetchone()
            dept = row['department'] if row else ""
            cur.execute("DELETE FROM employees WHERE id=%s", (emp_id,))
            cur.execute("DELETE FROM documents WHERE emp_id=%s", (emp_id,))
            conn.commit()
            conn.close()
            folder = os.path.join(DOC_ROOT, dept, str(emp_id))
            if os.path.exists(folder):
                shutil.rmtree(folder)
            self.app._show_department(self.dept_label)
        except Exception as ex:
            messagebox.showerror("Error", str(ex))

    def _get_employee_photo(self, emp_id):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT file_path FROM documents WHERE emp_id=%s AND doc_type='photo' LIMIT 1",
                (emp_id,)
            )
            row = cur.fetchone()
            conn.close()
            if row and os.path.exists(row['file_path']):
                return row['file_path']
        except Exception:
            pass
        return None


# ========== EMPLOYEE DETAIL PAGE (with editable attendance + unsaved changes warning) ==========
class EmployeePage(tk.Frame):
    def __init__(self, app, emp_id):
        colors = get_colors()
        super().__init__(app, bg=colors["bg"])
        self.app = app
        self.emp_id = emp_id
        self.emp = self._fetch_emp()
        self.unsaved_changes = False

        if not self.emp:
            tk.Label(self, text="Employee not found.", bg=colors["bg"], fg=colors["danger"]).pack(pady=40)
            return

        dept_map = {
            "HR": "Human Resources (HR)",
            "IT": "Information Technology (IT)",
            "Finance": "Finance / Accounting",
            "Marketing": "Marketing & Communications",
            "Operations": "Operations Management",
            "Sales": "Sales Management"
        }
        dept_label = dept_map.get(self.emp.get("department", ""), self.emp.get("department", ""))

        back_cmd = self._safe_navigate(lambda: app._show_department(dept_label))
        TopBar(self, app, back_cmd=back_cmd).pack(fill="x")

        main = tk.Frame(self, bg=colors["bg"])
        main.pack(fill="both", expand=True, padx=24, pady=16)

        left = tk.Frame(main, bg=colors["panel"], width=300,
                        highlightbackground=colors["border"], highlightthickness=1)
        left.pack(side="left", fill="y", padx=(0,16))
        left.pack_propagate(False)
        self._build_left(left)

        self.right_panel = tk.Frame(main, bg=colors["bg"])
        self.right_panel.pack(side="left", fill="both", expand=True)
        self._build_right(self.right_panel)

    def _safe_navigate(self, action):
        def wrapper():
            if self.unsaved_changes:
                answer = messagebox.askyesnocancel(
                    "Unsaved Changes",
                    "You have unsaved changes in Attendance.\n\n"
                    "• Yes = Save and continue\n"
                    "• No = Discard and continue\n"
                    "• Cancel = Stay here"
                )
                if answer is None:
                    return
                elif answer:
                    self._save_attendance_changes(silent=True)
            action()
        return wrapper

    def _check_unsaved_before_action(self, action):
        if self.unsaved_changes:
            answer = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes in Attendance.\n\n"
                "• Yes = Save and continue\n"
                "• No = Discard and continue\n"
                "• Cancel = Stay here"
            )
            if answer is None:
                return False
            elif answer:
                self._save_attendance_changes(silent=True)
        return True

    def _fetch_emp(self):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT * FROM employees WHERE id=%s", (self.emp_id,))
            e = cur.fetchone()
            conn.close()
            return e
        except Exception:
            return None

    def _get_photo_path(self):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT file_path FROM documents WHERE emp_id=%s AND doc_type='photo' LIMIT 1",
                (self.emp_id,)
            )
            row = cur.fetchone()
            conn.close()
            if row and os.path.exists(row['file_path']):
                return row['file_path']
        except Exception:
            pass
        return None

    def _build_left(self, parent):
        colors = get_colors()
        tk.Frame(parent, bg=colors["panel"], height=16).pack()
        photo_path = self._get_photo_path()
        av_img = make_avatar(photo_path, 90, self.emp["name"])
        av_lbl = tk.Label(parent, image=av_img, bg=colors["panel"])
        av_lbl.image = av_img
        av_lbl.pack(pady=(16,8))

        tk.Label(parent, text=self.emp["name"], bg=colors["panel"], fg=colors["text"],
                 font=("Segoe UI",13,"bold"), wraplength=260, justify="center").pack()
        tk.Label(parent, text=self.emp.get("position","—"), bg=colors["panel"],
                 fg=colors["accent"], font=("Segoe UI",10)).pack(pady=(2,16))
        separator(parent, pady=4)

        fields = [
            ("Department", self.emp.get("department","—")),
            ("Company ID", self.emp.get("company_id","—")),
            ("National ID", self.emp.get("emirates_id","—")),
            ("Labour Card", self.emp.get("labour_card","—")),
            ("Date of Birth", iso_to_dmy(self.emp.get("dob","—"))),
            ("Daily Earnings (AED)", f"{float(self.emp.get('salary') or 0):,.2f}"),
        ]
        for label, val in fields:
            row = tk.Frame(parent, bg=colors["panel"])
            row.pack(fill="x", padx=20, pady=3)
            tk.Label(row, text=label, bg=colors["panel"], fg=colors["subtext"],
                     font=("Segoe UI",9)).pack(anchor="w")
            tk.Label(row, text=str(val), bg=colors["panel"], fg=colors["text"],
                     font=("Segoe UI",10)).pack(anchor="w")

        separator(parent, pady=4)
        today = datetime.date.today()
        visa = self.emp.get("visa_expiry")
        if visa:
            days = (visa - today).days
            vc = colors["danger"] if days <= 14 else (colors["warning"] if days <= 30 else colors["success"])
            row = tk.Frame(parent, bg=colors["panel"])
            row.pack(fill="x", padx=20, pady=3)
            tk.Label(row, text="Visa Expiry", bg=colors["panel"], fg=colors["subtext"],
                     font=("Segoe UI",9)).pack(anchor="w")
            tk.Label(row, text=f"{iso_to_dmy(visa)}  ({days} days left)",
                     bg=colors["panel"], fg=vc, font=("Segoe UI",10)).pack(anchor="w")

        separator(parent, pady=8)
        tk.Label(parent, text="Contact", bg=colors["panel"], fg=colors["subtext"],
                 font=("Segoe UI",9,"bold")).pack(anchor="w", padx=20)
        phone = self.emp.get("phone") or "—"
        email = self.emp.get("email") or "—"
        tk.Label(parent, text=f"📞 {phone}", bg=colors["panel"], fg=colors["text"],
                 font=("Segoe UI",10)).pack(anchor="w", padx=20, pady=2)
        tk.Label(parent, text=f"✉  {email}", bg=colors["panel"], fg=colors["text"],
                 font=("Segoe UI",10)).pack(anchor="w", padx=20, pady=2)
        tk.Frame(parent, bg=colors["panel"], height=16).pack()

    def _build_right(self, parent):
        colors = get_colors()
        tab_frame = tk.Frame(parent, bg=colors["bg"])
        tab_frame.pack(fill="x", pady=(0,12))
        tab_inner = tk.Frame(tab_frame, bg=colors["bg"])
        tab_inner.pack(anchor="center")
        self.active_tab = tk.StringVar(value="attendance")
        self.tab_btns = {}
        for label, key in [("Attendance","attendance"), ("Salary","salary"), ("Documents","documents")]:
            btn = tk.Button(tab_inner, text=label,
                            command=lambda k=key: self._safe_switch_tab(k),
                            relief="flat", font=("Segoe UI",11), cursor="hand2",
                            bg=colors["accent"] if key=="attendance" else colors["card"],
                            fg=colors["white"] if key=="attendance" else colors["subtext"],
                            padx=20, pady=8, bd=0,
                            activebackground=colors["accent"], activeforeground=colors["white"])
            btn.pack(side="left", padx=5)
            self.tab_btns[key] = btn

        self.content_frame = tk.Frame(parent, bg=colors["bg"])
        self.content_frame.pack(fill="both", expand=True)
        self._switch_tab("attendance")

    def _safe_switch_tab(self, key):
        if not self._check_unsaved_before_action(lambda: None):
            return
        self._switch_tab(key)

    def _switch_tab(self, key):
        colors = get_colors()
        self.active_tab.set(key)
        for k, btn in self.tab_btns.items():
            btn.config(bg=colors["accent"] if k==key else colors["card"],
                       fg=colors["white"] if k==key else colors["subtext"])
        for w in self.content_frame.winfo_children():
            w.destroy()
        if key == "attendance":
            self._build_attendance(self.content_frame)
        elif key == "salary":
            self._build_salary(self.content_frame)
        else:
            self._build_documents(self.content_frame)

    # ========== ATTENDANCE WITH EDIT MODE & UNSAVED TRACKING ==========
    def _get_attendance_data(self, year=None, month=None):
        today = datetime.date.today()
        if year is None:
            year = today.year
        if month is None:
            month = today.month

        month_start = datetime.date(year, month, 1)
        if month == 12:
            month_end = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
        else:
            month_end = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)

        raw_join = self.emp.get("join_date")
        if raw_join:
            try:
                join_date = raw_join if isinstance(raw_join, datetime.date) \
                    else datetime.date.fromisoformat(str(raw_join))
            except Exception:
                join_date = month_start
        else:
            join_date = month_start

        db_records = {}
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                SELECT id, date, checkin, checkout, status
                FROM attendance
                WHERE emp_id = %s AND date BETWEEN %s AND %s
                ORDER BY date
            """, (self.emp_id, month_start, month_end))
            for row in cur.fetchall():
                row["checkin"]  = time_value_to_hhmm(row["checkin"])
                row["checkout"] = time_value_to_hhmm(row["checkout"])
                db_records[row["date"]] = row
            conn.close()
        except Exception as e:
            print(f"DB error in _get_attendance_data: {e}")

        records = []
        d = max(join_date, month_start)
        while d <= month_end:
            if d.weekday() == 5:
                records.append({"date": d, "checkin": "", "checkout": "", "status": "H", "id": None})
            else:
                if d in db_records:
                    r = db_records[d]
                    status = (r.get("status") or "A").strip().upper()
                    if status not in ("P", "A", "E"):
                        status = "P" if r["checkin"] else "A"
                    records.append({
                        "date": d,
                        "checkin": r["checkin"],
                        "checkout": r["checkout"],
                        "status": status,
                        "id": r["id"]
                    })
                else:
                    status = "A" if d <= today else ""
                    records.append({"date": d, "checkin": "", "checkout": "", "status": status, "id": None})
            d += datetime.timedelta(days=1)

        return records, max(join_date, month_start), join_date

    def _build_attendance(self, parent, year=None, month=None):
        colors = get_colors()
        today = datetime.date.today()
        if year is None:
            year = today.year
        if month is None:
            month = today.month

        self.att_year = year
        self.att_month = month
        self.unsaved_changes = False
        records, start_date, join_date = self._get_attendance_data(year, month)
        month_start = datetime.date(year, month, 1)

        if month == 12:
            next_month_start = datetime.date(year + 1, 1, 1)
        else:
            next_month_start = datetime.date(year, month + 1, 1)
        last_day_of_month = next_month_start - datetime.timedelta(days=1)

        total_working_days = sum(
            1 for d_off in range((last_day_of_month - month_start).days + 1)
            if (month_start + datetime.timedelta(days=d_off)).weekday() != 5
        )

        nav_frame = tk.Frame(parent, bg=colors["bg"])
        nav_frame.pack(fill="x", pady=(0, 10))
        nav_inner = tk.Frame(nav_frame, bg=colors["bg"])
        nav_inner.pack(anchor="center")

        def go_prev():
            if not self._check_unsaved_before_action(lambda: None):
                return
            m, y = (month - 1, year) if month > 1 else (12, year - 1)
            for w in parent.winfo_children(): w.destroy()
            self._build_attendance(parent, y, m)

        def go_next():
            if not self._check_unsaved_before_action(lambda: None):
                return
            m, y = (month + 1, year) if month < 12 else (1, year + 1)
            if datetime.date(y, m, 1) > today.replace(day=1):
                return
            for w in parent.winfo_children(): w.destroy()
            self._build_attendance(parent, y, m)

        tk.Button(nav_inner, text="◀", command=go_prev,
                  bg=colors["card"], fg=colors["accent"], font=("Segoe UI", 16, "bold"),
                  relief="flat", cursor="hand2", bd=0, padx=15, pady=6).pack(side="left")
        month_label = tk.Label(nav_inner, text=datetime.date(year, month, 1).strftime("%B  %Y"),
                               bg=colors["bg"], fg=colors["text"],
                               font=("Segoe UI", 14, "bold"), width=18, anchor="center")
        month_label.pack(side="left", padx=15)
        next_btn = tk.Button(nav_inner, text="▶", command=go_next,
                             bg=colors["card"], fg=colors["accent"], font=("Segoe UI", 16, "bold"),
                             relief="flat", cursor="hand2", bd=0, padx=15, pady=6)
        next_btn.pack(side="left")
        if datetime.date(year, month, 1) >= today.replace(day=1):
            next_btn.config(fg=colors["border"], state="disabled")

        month_status = "Completed" if (year < today.year or (year == today.year and month < today.month)) else "Ongoing"
        status_color = colors["success"] if month_status == "Completed" else colors["warning"]
        tk.Label(parent, text=month_status, bg=colors["bg"], fg=status_color,
                 font=("Segoe UI", 11, "bold")).pack(pady=(0, 8))

        if join_date > month_start:
            banner = tk.Frame(parent, bg=colors["card"],
                              highlightbackground=colors["success"], highlightthickness=1)
            banner.pack(fill="x", pady=(0, 10))
            tk.Label(banner, text=f"ℹ  Joined on {join_date}  —  records start from that date.",
                     bg=colors["card"], fg=colors["success"],
                     font=("Segoe UI", 10)).pack(anchor="center", padx=16, pady=8)

        p = sum(1 for x in records if x["status"] == "P")
        a = sum(1 for x in records if x["status"] == "A")
        e = sum(1 for x in records if x["status"] == "E")
        h = sum(1 for x in records if x["status"] == "H")

        stats_container = tk.Frame(parent, bg=colors["bg"])
        stats_container.pack(fill="x", pady=(0, 12))
        stats_inner = tk.Frame(stats_container, bg=colors["bg"])
        stats_inner.pack(anchor="center")
        for label, val, color in [("Present", p, colors["success"]),
                                  ("Absent", a, colors["danger"]),
                                  ("Excused", e, colors["warning"]),
                                  ("Holiday", h, colors["accent2"]),
                                  ("Working Days", total_working_days, colors["accent"])]:
            card = tk.Frame(stats_inner, bg=colors["card"], padx=20, pady=12,
                            highlightbackground=colors["border"], highlightthickness=1)
            card.pack(side="left", padx=5)
            tk.Label(card, text=str(val), bg=colors["card"], fg=color,
                     font=("Segoe UI", 22, "bold")).pack()
            tk.Label(card, text=label, bg=colors["card"], fg=colors["subtext"],
                     font=("Segoe UI", 10)).pack()

        self.edit_mode = tk.BooleanVar(value=False)
        edit_frame = tk.Frame(parent, bg=colors["bg"])
        edit_frame.pack(fill="x", pady=5)
        edit_inner = tk.Frame(edit_frame, bg=colors["bg"])
        edit_inner.pack(anchor="e")

        self.edit_btn = styled_button(edit_inner, "✎ Edit Mode", self._toggle_edit_mode,
                                      color=colors["accent2"], font=("Segoe UI", 10))
        self.edit_btn.pack(side="left", padx=5)
        self.save_btn = styled_button(edit_inner, "💾 Save Changes", self._save_attendance_changes,
                                      color=colors["success"], font=("Segoe UI", 10))
        self.save_btn.pack(side="left", padx=5)
        self.save_btn.config(state="disabled")

        if not records:
            tk.Label(parent, text="No records for this month.",
                     bg=colors["bg"], fg=colors["subtext"], font=("Segoe UI", 11)).pack(pady=30)
            return

        head = tk.Frame(parent, bg=colors["border"])
        head.pack(fill="x")
        for col_name in ["Date", "Check In", "Check Out", "Status"]:
            lbl = tk.Label(head, text=col_name, bg=colors["border"], fg=colors["subtext"],
                           font=("Segoe UI", 10, "bold"), width=15, anchor="center")
            lbl.pack(side="left", padx=5, pady=6, expand=True)

        self.att_outer, self.att_inner = scrollable_frame(parent)
        self.att_outer.pack(fill="both", expand=True)

        self.att_widgets = []
        self._populate_attendance_rows(records)

    def _toggle_edit_mode(self):
        if self.edit_mode.get() and self.unsaved_changes:
            answer = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes.\n\n"
                "• Yes = Save and exit Edit Mode\n"
                "• No = Discard and exit Edit Mode\n"
                "• Cancel = Stay in Edit Mode"
            )
            if answer is None:
                return
            elif answer:
                self._save_attendance_changes(silent=True)

        self.edit_mode.set(not self.edit_mode.get())
        if self.edit_mode.get():
            self.edit_btn.config(text="👁 View Mode", bg=get_colors()["warning"])
            self.save_btn.config(state="normal")
        else:
            self.edit_btn.config(text="✎ Edit Mode", bg=get_colors()["accent2"])
            self.save_btn.config(state="disabled")
            self.unsaved_changes = False

        for w in self.att_inner.winfo_children():
            w.destroy()
        records, _, _ = self._get_attendance_data(self.att_year, self.att_month)
        self._populate_attendance_rows(records)

    def _populate_attendance_rows(self, records):
        colors = get_colors()
        self.att_widgets.clear()
        for rec in records:
            row = tk.Frame(self.att_inner, bg=colors["card"],
                           highlightbackground=colors["border"], highlightthickness=1)
            row.pack(fill="x", pady=2)

            date_lbl = tk.Label(row, text=format_date_dmy(rec["date"]), bg=colors["card"],
                                fg=colors["text"], font=("Segoe UI", 10), width=15, anchor="center")
            date_lbl.pack(side="left", padx=5, pady=7, expand=True)

            if rec["status"] == "H":
                tk.Label(row, text="—", bg=colors["card"], fg=colors["subtext"],
                         width=15, anchor="center").pack(side="left", padx=5, expand=True)
                tk.Label(row, text="—", bg=colors["card"], fg=colors["subtext"],
                         width=15, anchor="center").pack(side="left", padx=5, expand=True)
                tk.Label(row, text="Holiday", bg=colors["card"], fg=colors["accent2"],
                         font=("Segoe UI", 10, "bold"), width=15, anchor="center").pack(side="left", padx=5, expand=True)
                continue

            if self.edit_mode.get():
                ci_var = tk.StringVar(value=rec["checkin"])
                ci_var.trace_add("write", lambda *args: self._mark_unsaved())
                ci_entry = tk.Entry(row, textvariable=ci_var, bg=colors["white"], fg=colors["text"],
                                    font=("Segoe UI", 10), width=15, justify="center",
                                    relief="solid", bd=1)
                ci_entry.pack(side="left", padx=5, expand=True)
            else:
                ci_var = None
                tk.Label(row, text=rec["checkin"] or "—", bg=colors["card"],
                         fg=colors["text"], font=("Segoe UI", 10), width=15, anchor="center").pack(side="left", padx=5, expand=True)

            if self.edit_mode.get():
                co_var = tk.StringVar(value=rec["checkout"])
                co_var.trace_add("write", lambda *args: self._mark_unsaved())
                co_entry = tk.Entry(row, textvariable=co_var, bg=colors["white"], fg=colors["text"],
                                    font=("Segoe UI", 10), width=15, justify="center",
                                    relief="solid", bd=1)
                co_entry.pack(side="left", padx=5, expand=True)
            else:
                co_var = None
                tk.Label(row, text=rec["checkout"] or "—", bg=colors["card"],
                         fg=colors["text"], font=("Segoe UI", 10), width=15, anchor="center").pack(side="left", padx=5, expand=True)

            status_frame = tk.Frame(row, bg=colors["card"])
            status_frame.pack(side="left", padx=5, expand=True)

            status_var = tk.StringVar(value=rec["status"])
            original_status = rec["status"]

            def make_radio_callback(var, original_val):
                def callback(*args):
                    if self.edit_mode.get():
                        self._mark_unsaved()
                    else:
                        var.set(original_val)
                return callback

            status_var.trace_add("write", make_radio_callback(status_var, original_status))

            for rb_text, rb_val, rb_fg in [("P", "P", colors["success"]),
                                           ("A", "A", colors["danger"]),
                                           ("E", "E", colors["warning"])]:
                rb = tk.Radiobutton(status_frame, text=rb_text, variable=status_var, value=rb_val,
                                    bg=colors["card"], fg=rb_fg,
                                    selectcolor=colors["card"],
                                    font=("Segoe UI", 10, "bold"))
                rb.pack(side="left", padx=2)

            widget_data = {
                "row": row,
                "date": rec["date"],
                "id": rec["id"],
                "ci_var": ci_var,
                "co_var": co_var,
                "status_var": status_var,
            }
            self.att_widgets.append(widget_data)

    def _mark_unsaved(self):
        if self.edit_mode.get():
            self.unsaved_changes = True

    def _save_attendance_changes(self, silent=False):
        if not self.edit_mode.get():
            return

        conn = get_conn()
        cur = conn.cursor()
        try:
            for wdata in self.att_widgets:
                date_obj = wdata["date"]
                rec_id = wdata["id"]
                ci_str = wdata["ci_var"].get().strip() if wdata["ci_var"] else ""
                co_str = wdata["co_var"].get().strip() if wdata["co_var"] else ""
                status = wdata["status_var"].get().strip()
                if not status:
                    status = "A"

                ci_val = ci_str if ci_str else None
                co_val = co_str if co_str else None

                if rec_id is None:
                    cur.execute("""
                        INSERT INTO attendance (emp_id, date, checkin, checkout, status)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (self.emp_id, date_obj, ci_val, co_val, status))
                else:
                    cur.execute("""
                        UPDATE attendance
                        SET checkin = %s, checkout = %s, status = %s
                        WHERE id = %s
                    """, (ci_val, co_val, status, rec_id))
            conn.commit()
            self.unsaved_changes = False
            if not silent:
                messagebox.showinfo("Success", "Attendance records updated.")
        except Exception as e:
            conn.rollback()
            if not silent:
                messagebox.showerror("Error", f"Failed to save changes: {e}")
        finally:
            conn.close()
            if not silent:
                self._switch_tab("attendance")

    # ========== SALARY TAB ==========
    def _build_salary(self, parent, year=None, month=None):
        colors = get_colors()
        today = datetime.date.today()
        if year is None:
            year = today.year
        if month is None:
            month = today.month

        daily_rate  = float(self.emp.get("salary") or 0)
        hourly_rate = daily_rate / 8.0

        month_start = datetime.date(year, month, 1)
        if month == 12:
            month_end = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
        else:
            month_end = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)

        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT date, checkin, checkout, status
            FROM attendance
            WHERE emp_id = %s AND date BETWEEN %s AND %s
            ORDER BY date
        """, (self.emp_id, month_start, month_end))
        db_rows = cur.fetchall()
        conn.close()

        attendance_by_date = {}
        for row in db_rows:
            date_obj = row["date"]
            ci_hours = time_value_to_hours(row["checkin"])
            co_hours = time_value_to_hours(row["checkout"])
            status   = (row["status"] or "A").strip().upper()
            attendance_by_date[date_obj] = {
                "checkin_hours":  ci_hours,
                "checkout_hours": co_hours,
                "status": status,
            }

        full_month_working_days = sum(
            1 for d_off in range((month_end - month_start).days + 1)
            if (month_start + datetime.timedelta(days=d_off)).weekday() != 5
        )

        last_working_day = month_end
        while last_working_day.weekday() == 5:
            last_working_day -= datetime.timedelta(days=1)

        if year < today.year or (year == today.year and month < today.month):
            month_completed = True
        elif year == today.year and month == today.month:
            month_completed = (today >= last_working_day)
        else:
            month_completed = False

        cutoff_date = last_working_day if month_completed else min(today, last_working_day)

        to_date_working_days = sum(
            1 for d_off in range((cutoff_date - month_start).days + 1)
            if (month_start + datetime.timedelta(days=d_off)).weekday() != 5
        )

        projected_full_month = daily_rate * full_month_working_days
        projected_to_date    = daily_rate * to_date_working_days

        working_records = []
        actual_earned   = 0.0

        d = month_start
        while d <= cutoff_date:
            if d.weekday() == 5:
                d += datetime.timedelta(days=1)
                continue

            rec = attendance_by_date.get(d)
            if rec is None:
                working_records.append({
                    "date": d, "status": "Absent",
                    "hours": None, "earned": 0.0
                })
            else:
                status = rec["status"]
                if status == "P":
                    ci = rec["checkin_hours"]
                    co = rec["checkout_hours"]
                    if ci is not None and co is not None and co > ci:
                        hrs = min(co - ci, 8.0)
                    else:
                        hrs = 0.0
                    earned = hrs * hourly_rate
                    working_records.append({
                        "date": d, "status": "Present",
                        "hours": hrs, "earned": earned
                    })
                    actual_earned += earned

                elif status == "E":
                    earned = daily_rate * 0.80
                    working_records.append({
                        "date": d, "status": "Excused",
                        "hours": None, "earned": earned
                    })
                    actual_earned += earned

                else:
                    working_records.append({
                        "date": d, "status": "Absent",
                        "hours": None, "earned": 0.0
                    })

            d += datetime.timedelta(days=1)

        deductions = projected_to_date - actual_earned

        nav_frame = tk.Frame(parent, bg=colors["bg"])
        nav_frame.pack(fill="x", pady=(0, 10))
        nav_inner = tk.Frame(nav_frame, bg=colors["bg"])
        nav_inner.pack(anchor="center")

        def go_prev():
            m, y = (month - 1, year) if month > 1 else (12, year - 1)
            for w in parent.winfo_children(): w.destroy()
            self._build_salary(parent, y, m)

        def go_next():
            m, y = (month + 1, year) if month < 12 else (1, year + 1)
            if datetime.date(y, m, 1) > today.replace(day=1):
                return
            for w in parent.winfo_children(): w.destroy()
            self._build_salary(parent, y, m)

        tk.Button(nav_inner, text="◀", command=go_prev,
                  bg=colors["card"], fg=colors["accent"], font=("Segoe UI", 16, "bold"),
                  relief="flat", cursor="hand2", bd=0, padx=15, pady=6).pack(side="left")
        month_label = tk.Label(nav_inner, text=datetime.date(year, month, 1).strftime("%B  %Y"),
                               bg=colors["bg"], fg=colors["text"],
                               font=("Segoe UI", 14, "bold"), width=18, anchor="center")
        month_label.pack(side="left", padx=15)
        next_btn = tk.Button(nav_inner, text="▶", command=go_next,
                             bg=colors["card"], fg=colors["accent"], font=("Segoe UI", 16, "bold"),
                             relief="flat", cursor="hand2", bd=0, padx=15, pady=6)
        next_btn.pack(side="left")
        if datetime.date(year, month, 1) >= today.replace(day=1):
            next_btn.config(fg=colors["border"], state="disabled")

        month_status = "Completed" if month_completed else "Ongoing"
        status_color = colors["success"] if month_status == "Completed" else colors["warning"]
        tk.Label(parent, text=month_status, bg=colors["bg"], fg=status_color,
                 font=("Segoe UI", 11, "bold")).pack(pady=(0,8))

        summary = tk.Frame(parent, bg=colors["bg"])
        summary.pack(fill="x", pady=(0, 16))
        summary_inner = tk.Frame(summary, bg=colors["bg"])
        summary_inner.pack(anchor="center")
        for label, val, color in [
            ("Daily Earnings (AED)",          f"{daily_rate:,.2f}",          colors["text"]),
            ("Working Days (Full Month)",     str(full_month_working_days),  colors["subtext"]),
            ("AED Projected (Full Month)",    f"{projected_full_month:,.2f}",colors["accent2"]),
            ("Actual Earned (To Date)",       f"{actual_earned:,.2f}",       colors["success"]),
            ("Deductions (To Date)",          f"{deductions:,.2f}",
             colors["danger"] if deductions > 0 else colors["subtext"]),
        ]:
            card = tk.Frame(summary_inner, bg=colors["card"], padx=18, pady=12,
                            highlightbackground=colors["border"], highlightthickness=1)
            card.pack(side="left", padx=5)
            tk.Label(card, text=val, bg=colors["card"], fg=color,
                     font=("Segoe UI", 16, "bold")).pack()
            tk.Label(card, text=label, bg=colors["card"], fg=colors["subtext"],
                     font=("Segoe UI", 10)).pack()

        legend = tk.Frame(parent, bg=colors["panel"], padx=16, pady=10,
                          highlightbackground=colors["border"], highlightthickness=1)
        legend.pack(fill="x", pady=(0, 12))

        if not working_records:
            tk.Label(parent, text="No salary records found for this month.",
                     bg=colors["bg"], fg=colors["subtext"], font=("Segoe UI", 11)).pack(pady=30)
            return

        head = tk.Frame(parent, bg=colors["border"])
        head.pack(fill="x")
        for col_name in ["Date", "Status", "Hours Worked", "Earned (AED)"]:
            lbl = tk.Label(head, text=col_name, bg=colors["border"], fg=colors["subtext"],
                           font=("Segoe UI", 10, "bold"), width=20, anchor="center")
            lbl.pack(side="left", padx=5, pady=6, expand=True)

        outer, inner = scrollable_frame(parent)
        outer.pack(fill="both", expand=True)

        for rec in working_records:
            row = tk.Frame(inner, bg=colors["card"],
                           highlightbackground=colors["border"], highlightthickness=1)
            row.pack(fill="x", pady=2)

            date_lbl = tk.Label(row, text=format_date_dmy(rec["date"]), bg=colors["card"],
                                fg=colors["text"], font=("Segoe UI", 10), width=20, anchor="center")
            date_lbl.pack(side="left", padx=5, pady=7, expand=True)

            if rec["status"] == "Present":
                sc = colors["success"]
            elif rec["status"] == "Excused":
                sc = colors["warning"]
            else:
                sc = colors["danger"]

            tk.Label(row, text=rec["status"], bg=colors["card"], fg=sc,
                     font=("Segoe UI", 10, "bold"), width=20, anchor="center").pack(side="left", padx=5, expand=True)

            hours_text = f"{rec['hours']:.2f} h" if rec["hours"] is not None else "—"
            tk.Label(row, text=hours_text, bg=colors["card"], fg=colors["subtext"],
                     font=("Segoe UI", 10), width=20, anchor="center").pack(side="left", padx=5, expand=True)

            tk.Label(row, text=f"{rec['earned']:,.2f}",
                     bg=colors["card"],
                     fg=colors["success"] if rec["earned"] > 0 else colors["danger"],
                     font=("Segoe UI", 10, "bold"), width=20, anchor="center").pack(side="left", padx=5, expand=True)

    # ========== DOCUMENTS TAB ==========
    def _build_documents(self, parent):
        colors = get_colors()
        for w in parent.winfo_children():
            w.destroy()

        doc_types = [
            ("Visa", "visa"),
            ("National ID", "emirates_id"),
            ("Labour Card", "labour_card"),
            ("Profile Picture", "photo"),
        ]

        title = tk.Label(parent, text="Employee Documents",
                         bg=colors["bg"], fg=colors["text"],
                         font=("Segoe UI", 13, "bold"))
        title.pack(side="top", anchor="n", pady=(10, 0))

        doc_container = tk.Frame(parent, bg=colors["bg"])
        doc_container.pack(side="top", fill="x", expand=False, pady=(5, 0))

        for label, doc_type in doc_types:
            row = tk.Frame(doc_container, bg=colors["card"],
                           highlightbackground=colors["border"], highlightthickness=1)
            row.pack(fill="x", pady=2, ipady=8, padx=50)

            lbl = tk.Label(row, text=label, bg=colors["card"], fg=colors["text"],
                           font=("Segoe UI", 11), width=20, anchor="center")
            lbl.pack(side="left", padx=16)

            file_path = self._get_document_path(doc_type)
            has_file = file_path is not None

            if has_file:
                status_lbl = tk.Label(row, text=f"✓ {os.path.basename(file_path)}", bg=colors["card"],
                                      fg=colors["success"], font=("Segoe UI", 10), anchor="center")
                status_lbl.pack(side="left", padx=8)
                view_btn = styled_button(row, "View",
                                         lambda fp=file_path: open_file_with_default_app(fp),
                                         color=colors["accent2"],
                                         font=("Segoe UI", 10))
                view_btn.pack(side="right", padx=8)
            else:
                status_lbl = tk.Label(row, text="No file", bg=colors["card"],
                                      fg=colors["subtext"], font=("Segoe UI", 10), anchor="center")
                status_lbl.pack(side="left", padx=8)

            upload_btn = styled_button(row, "Upload",
                                       lambda dt=doc_type, lbl=label: self._upload_doc(dt, lbl),
                                       color=colors["accent"] if not has_file else colors["border"],
                                       fg=colors["white"] if not has_file else colors["subtext"],
                                       font=("Segoe UI", 10))
            upload_btn.pack(side="right", padx=(0 if has_file else 8))

        recapture_frame = tk.Frame(parent, bg=colors["bg"])
        recapture_frame.pack(side="top", fill="x", pady=20)
        styled_button(recapture_frame, "📷 Re-capture Face",
                      command=self._recapture_face,
                      color=colors["accent2"], font=("Segoe UI", 11)).pack()

    def _get_document_path(self, doc_type):
        try:
            conn = get_conn()
            cur  = conn.cursor()
            cur.execute(
                "SELECT file_path FROM documents WHERE emp_id=%s AND doc_type=%s LIMIT 1",
                (self.emp_id, doc_type)
            )
            row = cur.fetchone()
            conn.close()
            if row and os.path.exists(row['file_path']):
                return row['file_path']
        except Exception:
            pass
        return None

    def _upload_doc(self, doc_type, label):
        is_photo  = (doc_type == "photo")
        filetypes = [("Image files", "*.jpg *.jpeg *.png")] if is_photo \
                    else [("PDF files", "*.pdf")]
        path = filedialog.askopenfilename(title=f"Upload {label}", filetypes=filetypes)
        if not path:
            return

        dept        = self.emp.get("department", "")
        dest_folder = os.path.join(DOC_ROOT, dept, str(self.emp_id), doc_type)
        os.makedirs(dest_folder, exist_ok=True)
        ext       = os.path.splitext(path)[1].lower()
        dest_file = os.path.join(dest_folder, f"{doc_type}{ext}")
        shutil.copy2(path, dest_file)

        try:
            conn = get_conn()
            cur  = conn.cursor()
            cur.execute("DELETE FROM documents WHERE emp_id=%s AND doc_type=%s",
                        (self.emp_id, doc_type))
            cur.execute(
                "INSERT INTO documents (emp_id, doc_type, file_path) VALUES (%s, %s, %s)",
                (self.emp_id, doc_type, dest_file)
            )
            conn.commit()
            conn.close()
            messagebox.showinfo("Uploaded", f"{label} uploaded successfully!")
            self._switch_tab("documents")
        except Exception as ex:
            messagebox.showerror("Error", f"Failed to save to database: {ex}")

    def _recapture_face(self):
        if not messagebox.askyesno("Recapture Face",
                                   "This will replace the existing face data.\nProceed?"):
            return
        encoding = capture_face_encoding(self.emp_id, self.emp["name"])
        if encoding:
            if store_face_encoding(self.emp_id, encoding):
                messagebox.showinfo("Success", "Face data updated!")
            else:
                messagebox.showerror("Error", "Failed to save face data.")
        else:
            messagebox.showwarning("Cancelled", "No face captured.")


# ========== ADD EMPLOYEE PAGE ==========
class AddEmployeePage(tk.Frame):
    def __init__(self, app):
        colors = get_colors()
        super().__init__(app, bg=colors["bg"])
        self.app = app
        self._emp_data = {}
        self._doc_paths = {}
        self._auto_company_id = None

        TopBar(self, app, back_cmd=lambda: app._show_home()).pack(fill="x")

        self.content = tk.Frame(self, bg=colors["bg"])
        self.content.pack(fill="both", expand=True)
        self._build_step1()

    def _clear_content(self):
        for w in self.content.winfo_children():
            w.destroy()

    def _validate_name(self, name):
        return bool(re.match(r"^[A-Za-z\s]+$", name))

    def _validate_position(self, pos):
        return bool(re.match(r"^[A-Za-z\s]+$", pos))

    def _validate_emirates_id(self, eid):
        return bool(re.match(r"^\d{3}-\d{4}-\d{7}-\d{1}$", eid))

    def _validate_labour_card(self, lc):
        return bool(re.match(r"^\d{8}$", lc))

    def _validate_phone(self, phone):
        return bool(re.match(r"^\+971 \d{2} \d{3} \d{4}$", phone))

    def _validate_email(self, email):
        if not email:
            return False
        if "@" not in email or "." not in email.split("@")[-1]:
            return False
        email_lower = email.lower()
        return email_lower.endswith("@gmail.com") or email_lower.endswith("@hotmail.com")

    def _validate_salary(self, salary):
        try:
            val = float(salary)
            return val > 0
        except ValueError:
            return False

    def _generate_company_id(self):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT company_id FROM employees ORDER BY id DESC LIMIT 1")
            last = cur.fetchone()
            conn.close()
            if last and last['company_id'] and last['company_id'].startswith("C-"):
                num = int(last['company_id'][2:]) + 1
            else:
                num = 1
            new_id = f"C-{num:04d}"
            return new_id
        except Exception as e:
            print(f"Error generating company ID: {e}")
            return "C-0001"

    def _build_step1(self):
        colors = get_colors()
        self._clear_content()

        if self._auto_company_id is None:
            self._auto_company_id = self._generate_company_id()

        outer, inner = scrollable_frame(self.content)
        outer.pack(fill="both", expand=True)
        wrapper = tk.Frame(inner, bg=colors["bg"])
        wrapper.pack(padx=60, pady=16, fill="x")

        tk.Label(wrapper, text="ENTER EMPLOYEE DETAILS",
                 bg=colors["bg"], fg=colors["text"],
                 font=("Segoe UI", 18, "bold")).pack(anchor="center", pady=(0, 10))
        tk.Label(wrapper, text="Step 1/3",
                 bg=colors["bg"], fg=colors["subtext"],
                 font=("Segoe UI", 11)).pack(anchor="center", pady=(0, 20))

        form = tk.Frame(wrapper, bg=colors["panel"], padx=32, pady=24,
                        highlightbackground=colors["border"], highlightthickness=1)
        form.pack(fill="x")

        self._entries = {}
        fields = [
            ("Full Name", "name", "", ""),
            ("Position", "position", "", ""),
            ("Department", "department", "dropdown", ""),
            ("National ID", "emirates_id", "784-XXXX-XXXXXXX-X", ""),
            ("Labour Card", "labour_card", "XXXXXXXX", ""),
            ("Visa Expiry", "visa_expiry", "DD/MM/YYYY", ""),
            ("Date of Birth", "dob", "DD/MM/YYYY", ""),
            ("Join Date", "join_date", "DD/MM/YYYY", ""),
            ("Daily Earnings (AED)", "salary", "", ""),
            ("Phone", "phone", "+971 XX XXX XXXX", ""),
            ("Email Address", "email", "user@domain.com", ""),
            ("Company ID", "company_id", "", ""),
        ]

        left_col = tk.Frame(form, bg=colors["panel"])
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 16))
        right_col = tk.Frame(form, bg=colors["panel"])
        right_col.pack(side="left", fill="both", expand=True)

        self.department_var = tk.StringVar()
        dept_options = ["HR", "IT", "Finance", "Marketing", "Operations", "Sales"]

        for i, (label, key, placeholder, hint) in enumerate(fields):
            col = left_col if i < 6 else right_col
            frame = tk.Frame(col, bg=colors["panel"])
            frame.pack(fill="x", pady=(8, 2))

            tk.Label(frame, text=label, bg=colors["panel"], fg=colors["subtext"],
                     font=("Segoe UI", 10)).pack(anchor="w")

            if key == "department":
                dropdown = ttk.Combobox(frame, textvariable=self.department_var,
                                        values=dept_options, state="readonly",
                                        font=("Segoe UI", 11))
                dropdown.pack(fill="x", ipady=5, pady=(2, 0))
                if self._emp_data.get("department"):
                    self.department_var.set(self._emp_data["department"])
                self._entries[key] = (dropdown, self.department_var)
            elif key == "company_id":
                entry = tk.Entry(frame, bg=colors["white"], fg=colors["text"],
                                 font=("Segoe UI", 11), relief="solid", bd=1)
                entry.pack(fill="x", ipady=5, pady=(2, 0))
                entry.insert(0, self._auto_company_id)
                entry.config(state="readonly", readonlybackground=colors["white"])
                self._entries[key] = (entry, None)
            else:
                e, v = entry_field(frame, placeholder=placeholder if placeholder else "")
                e.pack(fill="x", ipady=5, pady=(2, 0))
                if key in self._emp_data:
                    val = self._emp_data[key]
                    if isinstance(val, datetime.date):
                        val = val.strftime("%d/%m/%Y")
                    e.delete(0, tk.END)
                    e.insert(0, str(val))
                    e.config(fg=colors["text"])
                self._entries[key] = (e, v)

            if hint:
                tk.Label(frame, text=hint, bg=colors["panel"],
                         fg=colors["subtext"], font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))

        self.msg = tk.Label(wrapper, text="", bg=colors["bg"], fg=colors["danger"],
                            font=("Segoe UI", 10))
        self.msg.pack(anchor="center", pady=8)
        styled_button(wrapper, "NEXT →", self._step1_next, width=20).pack(anchor="center", pady=8)

    def _step1_next(self):
        data = {}
        for key, (widget, var) in self._entries.items():
            if key == "department":
                data[key] = var.get().strip()
            elif key == "company_id":
                data[key] = widget.get().strip() if widget else self._auto_company_id
            else:
                data[key] = widget.get().strip()

        required = ["name", "position", "department", "emirates_id", "labour_card",
                    "visa_expiry", "dob", "join_date", "salary", "phone", "email"]
        for field in required:
            if not data.get(field):
                self.msg.config(text=f"{field.replace('_',' ').title()} is required.")
                return

        if not self._validate_name(data["name"]):
            self.msg.config(text="Full name must contain letters only.")
            return
        if not self._validate_position(data["position"]):
            self.msg.config(text="Position must contain letters only.")
            return
        if not self._validate_emirates_id(data["emirates_id"]):
            self.msg.config(text="National ID must follow the format (784-XXXX-XXXXXXX-X)")
            return
        if not self._validate_labour_card(data["labour_card"]):
            self.msg.config(text="Labour Card ID must contain 8 digits only.")
            return
        if not self._validate_salary(data["salary"]):
            self.msg.config(text="Daily earnings must be a positive number (integer or decimal).")
            return
        if not self._validate_phone(data["phone"]):
            self.msg.config(text="Phone Number must follow the format: +971 XX XXX XXXX")
            return
        if not self._validate_email(data["email"]):
            self.msg.config(text="Email must be @gmail.com or @hotmail.com")
            return

        visa_date = parse_date_dmy(data["visa_expiry"])
        dob_date = parse_date_dmy(data["dob"])
        join_date = parse_date_dmy(data["join_date"])

        if visa_date is None:
            self.msg.config(text="Visa Expiry must follow the format (DD/MM/YYYY).")
            return
        if visa_date <= datetime.date.today():
            self.msg.config(text="Visa expiry must be in the future")
            return

        if dob_date is None:
            self.msg.config(text="Date of Birth must follow the format (DD/MM/YYYY).")
            return
        if dob_date >= datetime.date.today():
            self.msg.config(text="Date of birth must be in the past.")
            return

        if join_date is None:
            self.msg.config(text="Join Date must follow the format (DD/MM/YYYY).")
            return
        if join_date > datetime.date.today():
            self.msg.config(text="Join date cannot be in the future.")
            return

        data["visa_expiry"] = visa_date
        data["dob"] = dob_date
        data["join_date"] = join_date
        data["salary"] = float(data["salary"])
        data["company_id"] = self._auto_company_id

        self._emp_data = data
        self._build_step2()

    def _build_step2(self):
        colors = get_colors()
        self._clear_content()
        outer, inner = scrollable_frame(self.content)
        outer.pack(fill="both", expand=True)
        wrapper = tk.Frame(inner, bg=colors["bg"])
        wrapper.pack(padx=60, pady=16, fill="x")

        tk.Label(wrapper, text="UPLOAD DOCUMENTS",
                 bg=colors["bg"], fg=colors["text"],
                 font=("Segoe UI",18,"bold")).pack(anchor="center", pady=(0,10))
        tk.Label(wrapper, text="Step 2/3",
                 bg=colors["bg"], fg=colors["subtext"],
                 font=("Segoe UI",11)).pack(anchor="center", pady=(0,20))

        form = tk.Frame(wrapper, bg=colors["panel"], padx=32, pady=24,
                        highlightbackground=colors["border"], highlightthickness=1)
        form.pack(fill="x")

        doc_fields = [
            ("VISA (PDF)", "visa", False),
            ("National ID (PDF)", "emirates_id", False),
            ("Labour Card (PDF)", "labour_card", False),
            ("Employee Photo (JPEG/PNG)", "photo", True),
        ]
        self._doc_labels = {}
        for label, key, is_img in doc_fields:
            row = tk.Frame(form, bg=colors["panel"])
            row.pack(fill="x", pady=8)
            tk.Label(row, text=label, bg=colors["panel"], fg=colors["text"],
                     font=("Segoe UI",11), width=30, anchor="center").pack(side="left")
            status_text = "No file chosen"
            if key in self._doc_paths:
                status_text = os.path.basename(self._doc_paths[key])
            status = tk.Label(row, text=status_text, bg=colors["panel"],
                              fg=colors["subtext"], font=("Segoe UI",10))
            status.pack(side="left", padx=12)
            self._doc_labels[key] = status
            styled_button(row, "Browse",
                          lambda k=key, lbl=status, img=is_img: self._pick_file(k, lbl, img),
                          color=colors["accent2"], font=("Segoe UI",10)).pack(side="right")

        self.msg2 = tk.Label(wrapper, text="", bg=colors["bg"], fg=colors["danger"],
                             font=("Segoe UI",10))
        self.msg2.pack(anchor="center", pady=8)

        btn_row = tk.Frame(wrapper, bg=colors["bg"])
        btn_row.pack(fill="x")
        btn_inner = tk.Frame(btn_row, bg=colors["bg"])
        btn_inner.pack(anchor="center")
        styled_button(btn_inner, "← Back", self._build_step1,
                      color=colors["border"], fg=colors["subtext"]).pack(side="left", padx=10)
        styled_button(btn_inner, "NEXT →", self._step2_next,
                      color=colors["accent"]).pack(side="left", padx=10)

    def _pick_file(self, key, label_widget, is_image):
        ft = [("Image files","*.jpg *.jpeg *.png")] if is_image else [("PDF files","*.pdf")]
        path = filedialog.askopenfilename(filetypes=ft)
        if path:
            self._doc_paths[key] = path
            label_widget.config(text=os.path.basename(path), fg=get_colors()["success"])

    def _step2_next(self):
        self._build_step3()

    def _build_step3(self):
        colors = get_colors()
        self._clear_content()
        wrapper = tk.Frame(self.content, bg=colors["bg"])
        wrapper.pack(padx=60, pady=40, fill="both", expand=True)

        tk.Label(wrapper, text="FACE REGISTRATION",
                 bg=colors["bg"], fg=colors["text"],
                 font=("Segoe UI",18,"bold")).pack(anchor="center", pady=(0,10))
        tk.Label(wrapper, text="Step 3/3",
                 bg=colors["bg"], fg=colors["subtext"],
                 font=("Segoe UI",11)).pack(anchor="center", pady=(0,20))

        tk.Label(wrapper, text="Would you like to start face scanning?",
                 bg=colors["bg"], fg=colors["subtext"],
                 font=("Segoe UI",12)).pack(anchor="center", pady=(0,30))

        btn_frame = tk.Frame(wrapper, bg=colors["bg"])
        btn_frame.pack(anchor="center")

        def on_yes():
            emp_id = self._save_employee_to_db()
            if not emp_id:
                return
            encoding = capture_face_encoding(emp_id, self._emp_data["name"])
            if encoding:
                store_face_encoding(emp_id, encoding)
                messagebox.showinfo("Success", "Employee added and face registered!")
            else:
                messagebox.showwarning("Partial", "Employee added but face not captured.")
            self.app._show_home()

        def on_no():
            emp_id = self._save_employee_to_db()
            if emp_id:
                messagebox.showinfo("Success", "Employee added successfully.")
                self.app._show_home()

        styled_button(btn_frame, "Yes", on_yes,
                      color=colors["success"], font=("Segoe UI",12,"bold")).pack(side="left", padx=20)
        styled_button(btn_frame, "No", on_no,
                      color=colors["danger"], font=("Segoe UI",12,"bold")).pack(side="left", padx=20)

        back_btn = tk.Label(wrapper, text="← Back", bg=colors["bg"],
                            fg=colors["accent"], cursor="hand2", font=("Segoe UI",11))
        back_btn.pack(pady=20)
        back_btn.bind("<Button-1>", lambda e: self._build_step2())

    def _save_employee_to_db(self):
        d = self._emp_data
        company_id = self._auto_company_id
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO employees
                (name, position, department, company_id, emirates_id, labour_card,
                 visa_expiry, dob, join_date, phone, email, salary)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                d["name"], d["position"], d["department"],
                company_id, d["emirates_id"], d["labour_card"],
                d["visa_expiry"], d["dob"], d["join_date"],
                d["phone"], d["email"], d["salary"]
            ))
            emp_id = cur.lastrowid
            conn.commit()
            conn.close()
        except Exception as ex:
            messagebox.showerror("DB Error", f"Failed to save employee: {ex}")
            return None

        dept = d["department"]
        for doc_type, src_path in self._doc_paths.items():
            dest_folder = os.path.join(DOC_ROOT, dept, str(emp_id), doc_type)
            os.makedirs(dest_folder, exist_ok=True)
            ext = os.path.splitext(src_path)[1].lower()
            dest_file = os.path.join(dest_folder, f"{doc_type}{ext}")
            shutil.copy2(src_path, dest_file)
            try:
                conn2 = get_conn()
                cur2 = conn2.cursor()
                cur2.execute(
                    "INSERT INTO documents (emp_id, doc_type, file_path) VALUES (%s, %s, %s)",
                    (emp_id, doc_type, dest_file)
                )
                conn2.commit()
                conn2.close()
            except Exception as ex:
                messagebox.showwarning("Warning", f"Document {doc_type} saved but DB record failed: {ex}")

        return emp_id


# ========== NOTIFICATIONS PAGE ==========
class NotificationsPage(tk.Frame):
    def __init__(self, app):
        self.app = app
        self.colors = get_colors()
        super().__init__(app, bg=self.colors["bg"])
        TopBar(self, app, back_cmd=lambda: app._show_home()).pack(fill="x")

        tk.Label(self, text="Notifications", bg=self.colors["bg"], fg=self.colors["text"],
                 font=("Segoe UI", 22, "bold")).pack(anchor="center", padx=32, pady=(24, 4))
        separator(self, pady=0)

        self.outer, self.inner = scrollable_frame(self)
        self.outer.pack(fill="both", expand=True, padx=32, pady=16)
        self._load_notifications()

    def _load_notifications(self):
        for w in self.inner.winfo_children():
            w.destroy()

        notes = get_expiring_notifications()
        cleared_ids = getattr(self.app, 'cleared_notification_ids', set())
        active_notes = [n for n in notes if n['emp_id'] not in cleared_ids]

        if not active_notes:
            tk.Label(self.inner, text="✓  No New Notifications", bg=self.colors["bg"],
                     fg=self.colors["success"], font=("Segoe UI", 13, "bold")).pack(pady=40)
            return

        for note in active_notes:
            card = tk.Frame(self.inner, bg=self.colors["card"],
                            highlightbackground=self.colors["danger"], highlightthickness=1)
            card.pack(fill="x", pady=6, ipady=12)

            left = tk.Frame(card, bg=self.colors["card"])
            left.pack(side="left", padx=20, fill="x", expand=True)
            tk.Label(left, text=f"⚠  {note['type']}", bg=self.colors["card"],
                     fg=self.colors["danger"], font=("Segoe UI", 13, "bold")).pack(anchor="w")
            tk.Label(left, text=f"{note['name']}  •  {note['dept']}",
                     bg=self.colors["card"], fg=self.colors["text"], font=("Segoe UI", 11)).pack(anchor="w", pady=(4, 0))

            right = tk.Frame(card, bg=self.colors["card"])
            right.pack(side="right", padx=20)
            tk.Label(right, text=f"Deadline: {iso_to_dmy(note['deadline'])}",
                     bg=self.colors["card"], fg=self.colors["subtext"], font=("Segoe UI", 10)).pack(anchor="e")
            tk.Label(right, text=f"{note['days_left']} days remaining",
                     bg=self.colors["card"], fg=self.colors["danger"],
                     font=("Segoe UI", 12, "bold")).pack(anchor="e")

            clear_btn = styled_button(card, "Clear",
                                      command=lambda n=note: self._clear_single(n),
                                      color=self.colors["border"], fg=self.colors["subtext"],
                                      font=("Segoe UI", 9))
            clear_btn.pack(side="right", padx=10)

    def _clear_single(self, note):
        if not hasattr(self.app, 'cleared_notification_ids'):
            self.app.cleared_notification_ids = set()
        self.app.cleared_notification_ids.add(note['emp_id'])
        self._load_notifications()
        self.app._show_notifications()


# ========== TOOLS ATTENDANCE PAGE ==========
class ToolsAttendancePage(tk.Frame):
    def __init__(self, app):
        colors = get_colors()
        super().__init__(app, bg=colors["bg"])
        self.app = app
        TopBar(self, app, back_cmd=lambda: app._show_home()).pack(fill="x")

        center = tk.Frame(self, bg=colors["bg"])
        center.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(center, text="📸 Face Scan",
                 bg=colors["bg"], fg=colors["text"],
                 font=("Segoe UI",22,"bold")).pack()
        tk.Label(center, text="Click below to start scanning",
                 bg=colors["bg"], fg=colors["subtext"],
                 font=("Segoe UI",12)).pack(pady=10)

        styled_button(center, "START FACE SCAN",
                      command=self._start_scan,
                      color=colors["accent"],
                      font=("Segoe UI",13,"bold")).pack(pady=20)

    def _start_scan(self):
        self.app._clear()
        FaceAttendancePage(self.app).pack(fill="both", expand=True)


# ========== FACE ATTENDANCE SCANNER PAGE ==========
class FaceAttendancePage(tk.Frame):
    def __init__(self, app):
        colors = get_colors()
        super().__init__(app, bg=colors["bg"])
        self.app = app
        self.running = True
        self.cap = None
        self.start_time = None
        self.timeout_seconds = 5

        TopBar(self, app, back_cmd=self._close_and_return).pack(fill="x")

        tk.Label(self, text="📸 Face Recognition Attendance",
                 bg=colors["bg"], fg=colors["text"],
                 font=("Segoe UI", 18, "bold")).pack(pady=20)

        self.video_label = tk.Label(self, bg=colors["bg"])
        self.video_label.pack(pady=10)

        self.status_label = tk.Label(self, text="Initializing camera...",
                                     bg=colors["bg"], fg=colors["accent"],
                                     font=("Segoe UI", 12))
        self.status_label.pack(pady=10)

        self.after(100, self._init_camera)

    def _init_camera(self):
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                self.status_label.config(
                    text="❌ Could not open webcam.",
                    fg=get_colors()["danger"],
                    font=("Segoe UI", 12, "bold")
                )
                self.after(2000, self._close_and_return)
                return
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.start_time = time.time()
        self._update_frame()

    def _update_frame(self):
        if not self.running or self.cap is None:
            return

        if self.start_time and (time.time() - self.start_time) > self.timeout_seconds:
            self.status_label.config(
                text="❌ Face not recognised.\nPlease try after 5 seconds.",
                fg=get_colors()["danger"],
                font=("Segoe UI", 12, "bold"),
                justify="center"
            )
            self.running = False
            self.after(2000, self._close_and_return)
            return

        ret, frame = self.cap.read()
        if not ret:
            self.after(100, self._update_frame)
            return

        small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
        rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame)
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

        for (top, right, bottom, left) in face_locations:
            top *= 2; right *= 2; bottom *= 2; left *= 2
            cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        imgtk = ImageTk.PhotoImage(image=img)
        self.video_label.imgtk = imgtk
        self.video_label.config(image=imgtk)

        if face_encodings:
            live_encoding = face_encodings[0]
            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("SELECT id, name, face_encoding FROM employees WHERE face_encoding IS NOT NULL")
                employees = cur.fetchall()
                conn.close()
                for emp in employees:
                    if emp['face_encoding'] is None:
                        continue
                    db_encoding = np.array(json.loads(emp['face_encoding']))
                    matches = face_recognition.compare_faces([db_encoding], live_encoding, tolerance=0.6)
                    if matches[0]:
                        result = handle_attendance_by_face(emp['id'], emp['name'])
                        self.status_label.config(
                            text=result,
                            fg=get_colors()["success"],
                            font=("Segoe UI", 12)
                        )
                        self.running = False
                        self.after(2000, self._close_and_return)
                        return
            except Exception as e:
                self.status_label.config(
                    text=f"DB error: {e}",
                    fg=get_colors()["danger"],
                    font=("Segoe UI", 12, "bold")
                )
                self.after(2000, self._close_and_return)
                return

        self.after(30, self._update_frame)

    def _close_and_return(self):
        self.running = False
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()
        cv2.waitKey(1)
        self.app._show_home()


# ========== MAIN ENTRY POINT ==========
if __name__ == "__main__":
    os.makedirs(DOC_ROOT, exist_ok=True)
    app = HRApp()
    app.mainloop()
