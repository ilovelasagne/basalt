#!/usr/bin/env python3
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import cv2
import threading
import time
from pathlib import Path
import hashlib
import secrets
import subprocess
import shutil
import json
from PIL import Image, ImageTk
import getpass

try:
    import face_recognition
    HAVE_FACE_RECOGNITION = True
except ImportError:
    HAVE_FACE_RECOGNITION = False

class FaceUnlockSettings:
    def __init__(self, root):
        self.root = root
        self.root.title("Face Unlock Settings")
        self.root.geometry("850x650")
        self.root.minsize(800, 600)
        
        # --- MODIFICATION: Centralized Configuration ---
        self.config_dir = Path.home() / ".config" / "face-lock"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / "config.json"
        
        self.user_profiles_dir = Path.home() / ".face_lock_profiles"
        self.user_profiles_dir.mkdir(exist_ok=True)
        self.current_profile = "default"
        self.pass_file = Path.home() / ".face_lock_pass" # Simplified path
        self.known_faces_dir = self.user_profiles_dir / self.current_profile / "known_faces"
        self.known_faces_dir.mkdir(parents=True, exist_ok=True)
        self.username = os.getenv("USER") or getpass.getuser()
        
        self.config = self.load_config()
        
        # Camera variables
        self.camera_active = False
        self.camera_capture = None
        self.camera_thread = None
        
        self.setup_ui()
        self.update_face_list()
        self.check_dependencies()
        self.load_settings_to_ui()

    def load_config(self):
        """Load configuration from the central JSON file."""
        default_config = {
            "camera_index": 0, "tolerance": 0.6, "enable_animations": True,
            "anim_duration_in": 0.55, "anim_duration_out": 0.60,
            "anim_in_style": "bounce", "anim_out_style": "slide-up",
            "enable_face_recognition": True, "enable_fingerprint": True,
            "clock_font": "digital", "hint_text": "Use \u2190/\u2192 to change session. Space for password.",
            "shake_intensity": 3, "default_session": "auto"
        }
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    for key, value in default_config.items():
                        config.setdefault(key, value)
                    return config
            except (json.JSONDecodeError, TypeError): pass
        return default_config
    
    def save_config(self):
        """Save all UI settings to the central JSON file."""
        try:
            # Gather all settings from UI variables
            self.config["camera_index"] = self.camera_index_var.get()
            # The slider value is inverted: high accuracy (90) = low tolerance (0.45)
            self.config["tolerance"] = round(0.75 - (self.accuracy_var.get() / 200), 4)
            self.config["enable_animations"] = self.enable_animations_var.get()
            self.config["anim_duration_in"] = round(self.anim_in_duration_var.get(), 2)
            self.config["anim_duration_out"] = round(self.anim_out_duration_var.get(), 2)
            self.config["anim_in_style"] = self.anim_in_style_var.get()
            self.config["anim_out_style"] = self.anim_out_style_var.get()
            self.config["enable_face_recognition"] = self.enable_face_var.get()
            self.config["enable_fingerprint"] = self.enable_fingerprint_var.get()
            self.config["clock_font"] = self.clock_font_var.get()
            self.config["hint_text"] = self.hint_text_var.get()
            self.config["shake_intensity"] = self.shake_intensity_var.get()
            self.config["default_session"] = self.default_session_var.get()

            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            messagebox.showinfo("Success", "Settings saved successfully!", parent=self.root)
        except Exception as e:
            messagebox.showerror("Config Error", f"Error saving config: {e}", parent=self.root)

    def setup_ui(self):
        """Setup the main UI with a more logical layout."""
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill="both", expand=True)
        
        self.create_general_tab()
        self.create_security_tab()
        self.create_appearance_tab()
        self.create_face_mgmt_tab()
        
        # Save button at the bottom
        save_button = ttk.Button(main_frame, text="Save All Settings", command=self.save_config)
        save_button.pack(pady=10)

    def create_general_tab(self):
        frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(frame, text="General")
        
        # --- Camera Settings ---
        cam_group = ttk.LabelFrame(frame, text="Hardware", padding=10)
        cam_group.pack(fill="x", pady=5)
        
        ttk.Label(cam_group, text="Camera Device Index:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.camera_index_var = tk.IntVar()
        ttk.Spinbox(cam_group, from_=0, to=10, textvariable=self.camera_index_var, width=5).grid(row=0, column=1, sticky="w", padx=5, pady=5)
        
        # --- Session Settings ---
        session_group = ttk.LabelFrame(frame, text="Session", padding=10)
        session_group.pack(fill="x", pady=5)
        
        ttk.Label(session_group, text="Default Session:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.default_session_var = tk.StringVar()
        sessions = ["auto"] + list(self.get_available_sessions().keys())
        ttk.Combobox(session_group, textvariable=self.default_session_var, values=sessions, state="readonly").grid(row=0, column=1, sticky="w", padx=5, pady=5)

    def create_security_tab(self):
        frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(frame, text="Security")

        # --- Authentication Methods ---
        auth_group = ttk.LabelFrame(frame, text="Authentication Methods", padding=10)
        auth_group.pack(fill="x", pady=5)
        
        self.enable_face_var = tk.BooleanVar()
        ttk.Checkbutton(auth_group, text="Enable Face Recognition", variable=self.enable_face_var).pack(anchor="w")
        
        self.enable_fingerprint_var = tk.BooleanVar()
        ttk.Checkbutton(auth_group, text="Enable Fingerprint Scanning", variable=self.enable_fingerprint_var).pack(anchor="w")

        # --- Accuracy ---
        acc_group = ttk.LabelFrame(frame, text="Face Recognition Accuracy", padding=10)
        acc_group.pack(fill="x", pady=5)
        
        self.accuracy_var = tk.DoubleVar()
        ttk.Label(acc_group, text="Less Strict").pack(side="left", padx=5)
        ttk.Scale(acc_group, from_=0, to=100, orient="horizontal", variable=self.accuracy_var).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Label(acc_group, text="More Strict").pack(side="left", padx=5)
        
        # --- Password Management ---
        pw_group = ttk.LabelFrame(frame, text="Fallback Password", padding=10)
        pw_group.pack(fill="x", pady=5)
        
        ttk.Label(pw_group, text="New Password:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.new_pw = ttk.Entry(pw_group, show="*")
        self.new_pw.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(pw_group, text="Confirm:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.confirm_pw = ttk.Entry(pw_group, show="*")
        self.confirm_pw.grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Button(pw_group, text="Set Password", command=self.set_password).grid(row=2, column=0, columnspan=2, pady=10)

    def create_appearance_tab(self):
        frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(frame, text="Appearance")

        # --- Animations ---
        anim_group = ttk.LabelFrame(frame, text="Animations", padding=10)
        anim_group.pack(fill="x", pady=5)
        
        self.enable_animations_var = tk.BooleanVar()
        ttk.Checkbutton(anim_group, text="Enable Lock/Unlock Animations", variable=self.enable_animations_var).grid(row=0, column=0, columnspan=2, sticky="w")
        
        ttk.Label(anim_group, text="Entry Animation:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.anim_in_style_var = tk.StringVar()
        ttk.Combobox(anim_group, textvariable=self.anim_in_style_var, values=["bounce", "wave", "dissolve", "slide-down"], state="readonly").grid(row=1, column=1, sticky="ew")
        
        ttk.Label(anim_group, text="Entry Duration (s):").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.anim_in_duration_var = tk.DoubleVar()
        ttk.Scale(anim_group, from_=0.2, to=2.0, orient="horizontal", variable=self.anim_in_duration_var).grid(row=2, column=1, sticky="ew")
        
        ttk.Label(anim_group, text="Exit Animation:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        self.anim_out_style_var = tk.StringVar()
        ttk.Combobox(anim_group, textvariable=self.anim_out_style_var, values=["slide-up", "slide-left", "dissolve"], state="readonly").grid(row=3, column=1, sticky="ew")

        ttk.Label(anim_group, text="Exit Duration (s):").grid(row=4, column=0, sticky="w", padx=5, pady=5)
        self.anim_out_duration_var = tk.DoubleVar()
        ttk.Scale(anim_group, from_=0.2, to=2.0, orient="horizontal", variable=self.anim_out_duration_var).grid(row=4, column=1, sticky="ew")

        # --- Clock & Text ---
        text_group = ttk.LabelFrame(frame, text="Clock & Text", padding=10)
        text_group.pack(fill="x", pady=5)
        
        ttk.Label(text_group, text="Clock Font:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.clock_font_var = tk.StringVar()
        ttk.Combobox(text_group, textvariable=self.clock_font_var, values=["digital", "artistic"], state="readonly").grid(row=0, column=1, sticky="ew")
        
        ttk.Label(text_group, text="Hint Text:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.hint_text_var = tk.StringVar()
        ttk.Entry(text_group, textvariable=self.hint_text_var).grid(row=1, column=1, sticky="ew")

        # --- Effects ---
        fx_group = ttk.LabelFrame(frame, text="Effects", padding=10)
        fx_group.pack(fill="x", pady=5)
        
        ttk.Label(fx_group, text="Shake Intensity:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.shake_intensity_var = tk.IntVar()
        ttk.Scale(fx_group, from_=0, to=10, orient="horizontal", variable=self.shake_intensity_var).grid(row=0, column=1, sticky="ew")

    def create_face_mgmt_tab(self):
        """Create face recognition management tab"""
        frame = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(frame, text="Face Management")
        
        main_container = ttk.Frame(frame)
        main_container.pack(fill="both", expand=True)
        main_container.columnconfigure(1, weight=1)
        main_container.rowconfigure(0, weight=1)

        left_frame = ttk.Frame(main_container)
        left_frame.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        
        right_frame = ttk.LabelFrame(main_container, text="Camera Preview")
        right_frame.grid(row=0, column=1, sticky="nsew")

        # --- Face List ---
        list_frame = ttk.LabelFrame(left_frame, text="Registered Faces")
        list_frame.pack(fill="both", expand=True, pady=(0, 10))
        self.face_tree = ttk.Treeview(list_frame, columns=("Name",), show="headings", height=8)
        self.face_tree.heading("Name", text="Name")
        self.face_tree.pack(side="left", fill="both", expand=True)
        
        # --- Face Controls ---
        controls_frame = ttk.Frame(left_frame)
        controls_frame.pack(fill="x")
        ttk.Button(controls_frame, text="Add from Camera", command=self.add_face_from_camera).pack(fill="x", pady=2)
        ttk.Button(controls_frame, text="Add from File", command=self.add_face_from_file).pack(fill="x", pady=2)
        ttk.Button(controls_frame, text="Delete Selected", command=self.delete_selected_face).pack(fill="x", pady=2)

        # --- Camera Preview ---
        self.camera_label = ttk.Label(right_frame)
        self.camera_label.pack(pady=10, fill="both", expand=True)
        cam_btn_frame = ttk.Frame(right_frame)
        cam_btn_frame.pack(pady=5)
        self.camera_btn = ttk.Button(cam_btn_frame, text="Start Camera", command=self.toggle_camera)
        self.camera_btn.pack()

    def load_settings_to_ui(self):
        """Load config values into the UI widgets."""
        self.camera_index_var.set(self.config.get("camera_index", 0))
        # Invert tolerance to accuracy for the slider
        accuracy = (0.75 - self.config.get("tolerance", 0.6)) * 200
        self.accuracy_var.set(accuracy)
        self.enable_animations_var.set(self.config.get("enable_animations", True))
        self.anim_in_duration_var.set(self.config.get("anim_duration_in", 0.55))
        self.anim_out_duration_var.set(self.config.get("anim_duration_out", 0.60))
        self.anim_in_style_var.set(self.config.get("anim_in_style", "bounce"))
        self.anim_out_style_var.set(self.config.get("anim_out_style", "slide-up"))
        self.enable_face_var.set(self.config.get("enable_face_recognition", True))
        self.enable_fingerprint_var.set(self.config.get("enable_fingerprint", True))
        self.clock_font_var.set(self.config.get("clock_font", "digital"))
        self.hint_text_var.set(self.config.get("hint_text", ""))
        self.shake_intensity_var.set(self.config.get("shake_intensity", 3))
        self.default_session_var.set(self.config.get("default_session", "auto"))

    def get_available_sessions(self):
        """Utility to find available desktop session commands."""
        cmds = {
            "gnome-wayland": "dbus-run-session env XDG_SESSION_TYPE=wayland gnome-session",
            "gnome-x11": "dbus-run-session env XDG_SESSION_TYPE=x11 gnome-session",
            "kde": (shutil.which("startplasma-wayland") and "dbus-run-session env XDG_SESSION_TYPE=wayland startplasma-wayland")
        }
        return {k: v for k, v in cmds.items() if v and shutil.which(v.split()[0])}

    def set_password(self):
        new_pass = self.new_pw.get()
        confirm_pass = self.confirm_pw.get()
        if not new_pass or new_pass != confirm_pass:
            messagebox.showerror("Error", "Passwords do not match or are empty.", parent=self.root)
            return
        salt = secrets.token_hex(16)
        hashed = hashlib.sha256(salt.encode() + new_pass.encode()).hexdigest()
        self.pass_file.write_text(f"{salt}:{hashed}")
        messagebox.showinfo("Success", "Password has been set.", parent=self.root)
        self.new_pw.delete(0, 'end')
        self.confirm_pw.delete(0, 'end')

    def add_face_from_camera(self):
        if not self.camera_active:
            self.toggle_camera()
        
        ret, frame = self.camera_capture.read()
        if not ret:
            messagebox.showerror("Camera Error", "Could not read frame from camera.", parent=self.root)
            return
        
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if not face_recognition.face_locations(rgb_frame):
            messagebox.showwarning("No Face", "No face detected in the current frame.", parent=self.root)
            return
            
        name = simpledialog.askstring("Input", "Enter a name for this face:", parent=self.root)
        if name:
            filename = self.known_faces_dir / f"{name}.jpg"
            cv2.imwrite(str(filename), frame)
            self.update_face_list()
            messagebox.showinfo("Success", f"Face '{name}' saved.", parent=self.root)

    def add_face_from_file(self):
        filepath = filedialog.askopenfilename(title="Select an image file", filetypes=[("Image files", "*.jpg *.jpeg *.png")])
        if not filepath: return
        
        name = simpledialog.askstring("Input", "Enter a name for this face:", parent=self.root)
        if name:
            try:
                img = face_recognition.load_image_file(filepath)
                if not face_recognition.face_encodings(img):
                    messagebox.showerror("Error", "No face could be found in the selected file.", parent=self.root)
                    return
                shutil.copy(filepath, self.known_faces_dir / f"{name}.jpg")
                self.update_face_list()
            except Exception as e:
                messagebox.showerror("Error", f"Could not process file: {e}", parent=self.root)

    def delete_selected_face(self):
        selected_item = self.face_tree.selection()
        if not selected_item:
            messagebox.showwarning("Warning", "No face selected.", parent=self.root)
            return
        name = self.face_tree.item(selected_item, "values")[0]
        if messagebox.askyesno("Confirm", f"Are you sure you want to delete '{name}'?", parent=self.root):
            (self.known_faces_dir / f"{name}.jpg").unlink(missing_ok=True)
            self.update_face_list()

    def update_face_list(self):
        for i in self.face_tree.get_children(): self.face_tree.delete(i)
        for f in sorted(self.known_faces_dir.glob("*.jpg")):
            self.face_tree.insert("", "end", values=(f.stem,))

    def toggle_camera(self):
        if self.camera_active:
            self.camera_active = False
            self.camera_btn.config(text="Start Camera")
            if self.camera_thread and self.camera_thread.is_alive():
                self.camera_thread.join()
            self.camera_label.config(image=None)
            self.camera_label.image = None
        else:
            self.camera_active = True
            self.camera_btn.config(text="Stop Camera")
            self.camera_thread = threading.Thread(target=self.camera_loop, daemon=True)
            self.camera_thread.start()

    def camera_loop(self):
        self.camera_capture = cv2.VideoCapture(self.camera_index_var.get())
        if not self.camera_capture.isOpened():
            self.camera_active = False
            return

        while self.camera_active:
            ret, frame = self.camera_capture.read()
            if not ret: break
            
            # Detect faces and draw rectangles
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_frame)
            for (top, right, bottom, left) in face_locations:
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
            
            # Convert to displayable format
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            img.thumbnail((self.camera_label.winfo_width(), self.camera_label.winfo_height()))
            photo = ImageTk.PhotoImage(image=img)
            
            self.camera_label.config(image=photo)
            self.camera_label.image = photo
            time.sleep(0.03)
        
        self.camera_capture.release()

    def check_dependencies(self):
        if not HAVE_FACE_RECOGNITION:
            messagebox.showwarning("Missing Dependency",
                                 "The 'face_recognition' library is not installed.\n"
                                 "Face management features will be disabled.\n"
                                 "Please run: pip install face_recognition", parent=self.root)
            for child in self.notebook.winfo_children():
                if self.notebook.tab(child, "text") == "Face Management":
                    self.notebook.tab(child, state="disabled")

    def on_closing(self):
        if self.camera_active:
            self.camera_active = False
            if self.camera_thread: self.camera_thread.join(timeout=1.0)
        self.root.destroy()

def main():
    root = tk.Tk()
    app = FaceUnlockSettings(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()

