import json
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import cv2
import numpy as np
import pyautogui
from PIL import Image, ImageTk

CONFIG_FILE = "gacha_config.json"


class RegionSelector(tk.Toplevel):
    def __init__(self, parent, title="Select Region"):
        super().__init__(parent)
        self.title(title)
        self.attributes("-fullscreen", True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.25)
        self.configure(bg="black")
        self.overrideredirect(True)

        self.start_x = None
        self.start_y = None
        self.rect = None
        self.result = None

        self.canvas = tk.Canvas(self, cursor="cross", bg="gray")
        self.canvas.pack(fill="both", expand=True)

        self.label = tk.Label(
            self,
            text="Drag to select region. Press Enter to confirm, Esc to cancel.",
            font=("Arial", 18),
            bg="yellow",
            fg="black"
        )
        self.label.place(x=20, y=20)

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        self.bind("<Return>", self.on_confirm)
        self.bind("<Escape>", self.on_cancel)

        self.focus_force()

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect:
            self.canvas.delete(self.rect)
            self.rect = None
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="red", width=3
        )

    def on_drag(self, event):
        if self.rect is not None:
            self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        pass

    def on_confirm(self, event=None):
        if self.rect is None:
            messagebox.showwarning("Warning", "Please drag a region first.")
            return
        x1, y1, x2, y2 = self.canvas.coords(self.rect)
        x1, x2 = sorted((int(x1), int(x2)))
        y1, y2 = sorted((int(y1), int(y2)))
        if abs(x2 - x1) < 5 or abs(y2 - y1) < 5:
            messagebox.showwarning("Warning", "Selected region is too small.")
            return
        self.result = (x1, y1, x2, y2)
        self.destroy()

    def on_cancel(self, event=None):
        self.result = None
        self.destroy()


class AutoGachaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Auto Gacha Tool")
        self.root.geometry("1080x1080")

        self.running = False
        self.worker_thread = None

        self.gacha_region = None
        self.draw_button_region = None
        self.confirm_button_region = None
        self.skip_button_region = None

        self.preview_image = None

        self.build_ui()
        self.load_config()

    def build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        title = ttk.Label(main, text="Auto Gacha Tool", font=("Arial", 18, "bold"))
        title.pack(anchor="w", pady=(0, 10))

        desc = ttk.Label(
            main,
            text=(
                "1) Select gacha result area\n"
                "2) Select 'draw again' button area\n"
                "3) Select 'confirm' button area\n"
                "4) Select 'skip' button area\n"
                "5) Start auto loop"
            )
        )
        desc.pack(anchor="w", pady=(0, 12))

        control_frame = ttk.Frame(main)
        control_frame.pack(fill="x", pady=6)

        self.btn_select_gacha = ttk.Button(
            control_frame, text="Select Gacha Result Area", command=self.select_gacha_region
        )
        self.btn_select_gacha.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        self.btn_select_draw = ttk.Button(
            control_frame, text="Select Draw Button Area", command=self.select_draw_button_region
        )
        self.btn_select_draw.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.btn_select_confirm = ttk.Button(
            control_frame, text="Select Confirm Button Area", command=self.select_confirm_button_region
        )
        self.btn_select_confirm.grid(row=0, column=2, padx=5, pady=5, sticky="ew")

        self.btn_select_skip = ttk.Button(
            control_frame, text="Select Skip Button Area", command=self.select_skip_button_region
        )
        self.btn_select_skip.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

        self.btn_test = ttk.Button(
            control_frame, text="Test Detection", command=self.test_detection
        )
        self.btn_test.grid(row=1, column=0, padx=5, pady=5, sticky="ew")

        self.btn_save = ttk.Button(
            control_frame, text="Save Config", command=self.save_config
        )
        self.btn_save.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        for i in range(4):
            control_frame.columnconfigure(i, weight=1)

        settings = ttk.LabelFrame(main, text="Settings", padding=10)
        settings.pack(fill="x", pady=10)

        ttk.Label(settings, text="Target rainbow count:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.target_var = tk.IntVar(value=4)
        ttk.Spinbox(settings, from_=1, to=10, textvariable=self.target_var, width=10).grid(
            row=0, column=1, sticky="w", padx=5, pady=5
        )

        ttk.Label(settings, text="Pre-start countdown (sec):").grid(row=0, column=2, sticky="w", padx=5, pady=5)
        self.countdown_var = tk.IntVar(value=3)
        ttk.Spinbox(settings, from_=0, to=10, textvariable=self.countdown_var, width=10).grid(
            row=0, column=3, sticky="w", padx=5, pady=5
        )

        ttk.Label(settings, text="Delay after Draw click (sec):").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.delay_draw_var = tk.DoubleVar(value=0.8)
        ttk.Spinbox(settings, from_=0.0, to=10.0, increment=0.1, textvariable=self.delay_draw_var, width=10).grid(
            row=1, column=1, sticky="w", padx=5, pady=5
        )

        ttk.Label(settings, text="Delay after Confirm click (sec):").grid(row=1, column=2, sticky="w", padx=5, pady=5)
        self.delay_confirm_var = tk.DoubleVar(value=0.4)
        ttk.Spinbox(settings, from_=0.0, to=10.0, increment=0.1, textvariable=self.delay_confirm_var, width=10).grid(
            row=1, column=3, sticky="w", padx=5, pady=5
        )

        ttk.Label(settings, text="Gap between two Skip clicks (sec):").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.skip_gap_var = tk.DoubleVar(value=0.15)
        ttk.Spinbox(settings, from_=0.0, to=2.0, increment=0.05, textvariable=self.skip_gap_var, width=10).grid(
            row=2, column=1, sticky="w", padx=5, pady=5
        )

        ttk.Label(settings, text="Wait after double Skip (sec):").grid(row=2, column=2, sticky="w", padx=5, pady=5)
        self.delay_after_skip_var = tk.DoubleVar(value=1.8)
        ttk.Spinbox(settings, from_=0.0, to=10.0, increment=0.1, textvariable=self.delay_after_skip_var, width=10).grid(
            row=2, column=3, sticky="w", padx=5, pady=5
        )

        ttk.Label(settings, text="Click interval jitter (sec):").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        self.jitter_var = tk.DoubleVar(value=0.0)
        ttk.Spinbox(settings, from_=0.0, to=2.0, increment=0.1, textvariable=self.jitter_var, width=10).grid(
            row=3, column=1, sticky="w", padx=5, pady=5
        )

        settings_detect = ttk.LabelFrame(main, text="Detection Settings", padding=10)
        settings_detect.pack(fill="x", pady=10)
        
        ttk.Label(settings_detect, text="Saturation threshold:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.sat_var = tk.IntVar(value=70)
        ttk.Spinbox(settings_detect, from_=0, to=255, textvariable=self.sat_var, width=10).grid(
            row=0, column=1, sticky="w", padx=5, pady=5
        )

        ttk.Label(settings_detect, text="Value threshold:").grid(row=0, column=2, sticky="w", padx=5, pady=5)
        self.val_var = tk.IntVar(value=130)
        ttk.Spinbox(settings_detect, from_=0, to=255, textvariable=self.val_var, width=10).grid(
            row=0, column=3, sticky="w", padx=5, pady=5
        )

        info = ttk.LabelFrame(main, text="Current Selection", padding=10)
        info.pack(fill="x", pady=10)

        self.gacha_label = ttk.Label(info, text="Gacha area: Not selected")
        self.gacha_label.pack(anchor="w", pady=2)

        self.draw_label = ttk.Label(info, text="Draw button area: Not selected")
        self.draw_label.pack(anchor="w", pady=2)

        self.confirm_label = ttk.Label(info, text="Confirm button area: Not selected")
        self.confirm_label.pack(anchor="w", pady=2)

        self.skip_label = ttk.Label(info, text="Skip button area: Not selected")
        self.skip_label.pack(anchor="w", pady=2)

        action_frame = ttk.Frame(main)
        action_frame.pack(fill="x", pady=10)

        self.start_btn = ttk.Button(action_frame, text="Start Auto Gacha", command=self.start)
        self.start_btn.pack(side="left", padx=5)

        self.stop_btn = ttk.Button(action_frame, text="Stop", command=self.stop)
        self.stop_btn.pack(side="left", padx=5)

        self.log_text = tk.Text(main, height=12, wrap="word")
        self.log_text.pack(fill="both", expand=True, pady=10)

        preview_frame = ttk.LabelFrame(main, text="Preview", padding=8)
        preview_frame.pack(fill="both", expand=True)

        self.preview_panel = ttk.Label(preview_frame)
        self.preview_panel.pack(fill="both", expand=True)

    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {msg}\n")
        self.log_text.see("end")
        self.root.update_idletasks()

    def update_labels(self):
        self.gacha_label.config(text=f"Gacha area: {self.gacha_region}" if self.gacha_region else "Gacha area: Not selected")
        self.draw_label.config(text=f"Draw button area: {self.draw_button_region}" if self.draw_button_region else "Draw button area: Not selected")
        self.confirm_label.config(text=f"Confirm button area: {self.confirm_button_region}" if self.confirm_button_region else "Confirm button area: Not selected")
        self.skip_label.config(text=f"Skip button area: {self.skip_button_region}" if self.skip_button_region else "Skip button area: Not selected")

    def select_region(self, title):
        self.root.withdraw()
        time.sleep(0.2)
        selector = RegionSelector(self.root, title=title)
        self.root.wait_window(selector)
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        return selector.result

    def select_gacha_region(self):
        region = self.select_region("Select Gacha Result Area")
        if region:
            self.gacha_region = region
            self.update_labels()
            self.log(f"Gacha area selected: {region}")

    def select_draw_button_region(self):
        region = self.select_region("Select Draw Button Area")
        if region:
            self.draw_button_region = region
            self.update_labels()
            self.log(f"Draw button area selected: {region}")

    def select_confirm_button_region(self):
        region = self.select_region("Select Confirm Button Area")
        if region:
            self.confirm_button_region = region
            self.update_labels()
            self.log(f"Confirm button area selected: {region}")

    def select_skip_button_region(self):
        region = self.select_region("Select Skip Button Area")
        if region:
            self.skip_button_region = region
            self.update_labels()
            self.log(f"Skip button area selected: {region}")

    def region_to_pyautogui(self, region):
        x1, y1, x2, y2 = region
        return (x1, y1, x2 - x1, y2 - y1)

    def get_region_center(self, region):
        x1, y1, x2, y2 = region
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    def capture_region_bgr(self, region):
        left, top, width, height = self.region_to_pyautogui(region)
        img = pyautogui.screenshot(region=(left, top, width, height))
        img = np.array(img)
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    # def count_rainbow_cards(self, img_bgr, debug=False):
    #     hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

    #     lower = np.array([0, self.sat_var.get(), self.val_var.get()], dtype=np.uint8)
    #     upper = np.array([179, 255, 255], dtype=np.uint8)
    #     mask = cv2.inRange(hsv, lower, upper)

    #     kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 25))
    #     mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    #     mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8), iterations=1)

    #     contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    #     count = 0
    #     boxes = []
    #     h, w = img_bgr.shape[:2]

    #     for cnt in contours:
    #         x, y, bw, bh = cv2.boundingRect(cnt)
    #         area = bw * bh

    #         if bh < max(80, int(h * 0.30)):
    #             continue
    #         if bw < max(25, int(w * 0.03)):
    #             continue
    #         if area < 3500:
    #             continue

    #         ratio = bh / max(bw, 1)
    #         if ratio < 1.5:
    #             continue

    #         count += 1
    #         boxes.append((x, y, bw, bh))

    #     debug_img = img_bgr.copy()
    #     for x, y, bw, bh in boxes:
    #         cv2.rectangle(debug_img, (x, y), (x + bw, y + bh), (0, 255, 0), 3)

    #     return count, mask, debug_img
    
    def count_rainbow_cards(self, img_bgr, debug=False):
        """
        更稳的 rainbow 检测：
        1) 先用 HSV 找高饱和/较亮区域
        2) 只保留“高而窄”的连通区域
        3) 再检查该区域是否具有足够丰富的 hue（彩虹，而不是单色衣服）
        4) 最后按 x 方向合并相邻区域，避免同一张 rainbow 卡被算成多个
        """
        hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        H, S, V = cv2.split(hsv)

        # 先做较宽松的阈值，不要太苛刻
        sat_thr = self.sat_var.get()      # 比如 60~80
        val_thr = self.val_var.get()      # 比如 110~140

        mask = ((S >= sat_thr) & (V >= val_thr)).astype(np.uint8) * 255

        # 去掉太小的噪声
        kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 15))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_open, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close, iterations=1)

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)

        h_img, w_img = img_bgr.shape[:2]
        candidate_boxes = []

        debug_img = img_bgr.copy()

        for label_id in range(1, num_labels):
            x = stats[label_id, cv2.CC_STAT_LEFT]
            y = stats[label_id, cv2.CC_STAT_TOP]
            w = stats[label_id, cv2.CC_STAT_WIDTH]
            h = stats[label_id, cv2.CC_STAT_HEIGHT]
            area = stats[label_id, cv2.CC_STAT_AREA]

            # ---- 第一步：几何过滤 ----
            # rainbow 边框通常“高而窄”
            if h < int(h_img * 0.45):
                continue
            if w < max(12, int(w_img * 0.01)):
                continue
            if w > int(w_img * 0.12):
                continue
            if area < 1200:
                continue

            aspect = h / max(w, 1)
            if aspect < 2.2:
                continue

            # ---- 第二步：区域内部的“竖向覆盖率” ----
            # 如果只是衣服/头发的一团颜色，通常不会在很多行里持续出现
            comp_mask = (labels[y:y+h, x:x+w] == label_id).astype(np.uint8)
            row_coverage = comp_mask.sum(axis=1) / max(w, 1)

            # 有多少行在该连通块里至少覆盖了 25% 宽度
            strong_rows = np.sum(row_coverage > 0.25)
            if strong_rows < int(h * 0.55):
                continue

            # ---- 第三步：颜色多样性 ----
            # rainbow 的 hue 分布会更分散；角色衣服/头发通常 hue 比较集中
            h_patch = H[y:y+h, x:x+w]
            s_patch = S[y:y+h, x:x+w]
            v_patch = V[y:y+h, x:x+w]

            valid = (comp_mask > 0) & (s_patch >= sat_thr) & (v_patch >= val_thr)
            hue_vals = h_patch[valid]

            if len(hue_vals) < 200:
                continue

            # 统计 hue 直方图（OpenCV hue: 0~179）
            hist, _ = np.histogram(hue_vals, bins=12, range=(0, 180))

            # 至少有几个 bin 明显非零，代表颜色不止一种
            active_bins = np.sum(hist > max(20, len(hue_vals) * 0.03))
            if active_bins < 4:
                continue

            # 标准差也辅助判断
            hue_std = np.std(hue_vals.astype(np.float32))
            if hue_std < 18:
                continue

            candidate_boxes.append((x, y, w, h))

        # ---- 第四步：按 x 方向合并相近候选，避免同一张卡被拆成多个竖条 ----
        candidate_boxes = sorted(candidate_boxes, key=lambda b: b[0])

        merged = []
        for box in candidate_boxes:
            x, y, w, h = box
            if not merged:
                merged.append([x, y, x+w, y+h])
                continue

            px1, py1, px2, py2 = merged[-1]

            # 如果两个候选在 x 方向很近，就合并
            # 这可以避免同一张 rainbow 卡左右两个彩边被当两张
            if x - px2 < max(25, int(w_img * 0.03)):
                merged[-1] = [
                    min(px1, x),
                    min(py1, y),
                    max(px2, x+w),
                    max(py2, y+h),
                ]
            else:
                merged.append([x, y, x+w, y+h])

        final_boxes = []
        for x1, y1, x2, y2 in merged:
            final_boxes.append((x1, y1, x2-x1, y2-y1))
            if debug:
                cv2.rectangle(debug_img, (x1, y1), (x2, y2), (0, 255, 0), 3)

        return len(final_boxes), mask, debug_img

    def show_preview(self, img_bgr):
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        h, w = img_rgb.shape[:2]

        max_w = 840
        max_h = 260
        scale = min(max_w / w, max_h / h, 1.0)
        new_w = int(w * scale)
        new_h = int(h * scale)

        resized = cv2.resize(img_rgb, (new_w, new_h))
        pil_img = Image.fromarray(resized)
        self.preview_image = ImageTk.PhotoImage(pil_img)
        self.preview_panel.config(image=self.preview_image)

    def test_detection(self):
        if not self.gacha_region:
            messagebox.showwarning("Warning", "Please select gacha result area first.")
            return

        img = self.capture_region_bgr(self.gacha_region)
        count, mask, debug_img = self.count_rainbow_cards(img, debug=True)

        self.log(f"Test detection result: {count} rainbow card(s)")
        self.show_preview(debug_img)

        cv2.imshow("Mask", mask)
        cv2.imshow("Detected", debug_img)
        cv2.waitKey(1)

    def validate(self):
        if not self.gacha_region:
            messagebox.showwarning("Warning", "Please select gacha result area.")
            return False
        if not self.draw_button_region:
            messagebox.showwarning("Warning", "Please select draw button area.")
            return False
        if not self.confirm_button_region:
            messagebox.showwarning("Warning", "Please select confirm button area.")
            return False
        if not self.skip_button_region:
            messagebox.showwarning("Warning", "Please select skip button area.")
            return False
        return True

    def click_region_center(self, region, label="button"):
        cx, cy = self.get_region_center(region)
        pyautogui.click(cx, cy)
        self.log(f"Clicked {label} at ({cx}, {cy})")

    def sleep_with_jitter(self, base):
        jitter = self.jitter_var.get()
        total = base + (np.random.uniform(0, jitter) if jitter > 0 else 0.0)
        time.sleep(max(0.0, total))

    def auto_loop(self):
        try:
            countdown = self.countdown_var.get()
            if countdown > 0:
                for i in range(countdown, 0, -1):
                    if not self.running:
                        return
                    self.log(f"Starting in {i}...")
                    time.sleep(1)

            round_num = 0

            while self.running:
                round_num += 1

                img = self.capture_region_bgr(self.gacha_region)
                count, mask, debug_img = self.count_rainbow_cards(img, debug=False)

                self.log(f"Round {round_num}: detected {count} rainbow card(s)")
                self.root.after(0, lambda im=debug_img: self.show_preview(im))

                if count >= self.target_var.get():
                    self.log("Target reached. Stopping.")
                    self.running = False
                    break

                # Step 1: click Draw Again
                self.click_region_center(self.draw_button_region, "Draw Again")
                self.sleep_with_jitter(self.delay_draw_var.get())

                if not self.running:
                    break

                # Step 2: click Confirm
                self.click_region_center(self.confirm_button_region, "Confirm")
                self.sleep_with_jitter(self.delay_confirm_var.get())

                if not self.running:
                    break

                # Step 3: double click Skip
                self.click_region_center(self.skip_button_region, "Skip #1")
                time.sleep(max(0.0, self.skip_gap_var.get()))
                self.click_region_center(self.skip_button_region, "Skip #2")

                # Step 4: wait for animation/result page
                self.sleep_with_jitter(self.delay_after_skip_var.get())

        except Exception as e:
            self.log(f"Error: {e}")
            messagebox.showerror("Error", str(e))
        finally:
            self.running = False

    def start(self):
        if self.running:
            return
        if not self.validate():
            return

        self.running = True
        self.worker_thread = threading.Thread(target=self.auto_loop, daemon=True)
        self.worker_thread.start()
        self.log("Auto gacha started.")

    def stop(self):
        self.running = False
        self.log("Stop requested.")

    def save_config(self):
        data = {
            "gacha_region": self.gacha_region,
            "draw_button_region": self.draw_button_region,
            "confirm_button_region": self.confirm_button_region,
            "skip_button_region": self.skip_button_region,
            "target_count": self.target_var.get(),
            "countdown": self.countdown_var.get(),
            "delay_draw": self.delay_draw_var.get(),
            "delay_confirm": self.delay_confirm_var.get(),
            "skip_gap": self.skip_gap_var.get(),
            "delay_after_skip": self.delay_after_skip_var.get(),
            "jitter": self.jitter_var.get(),
            "sat_threshold": self.sat_var.get(),
            "val_threshold": self.val_var.get(),
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self.log(f"Config saved to {CONFIG_FILE}")

    def load_config(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.gacha_region = tuple(data.get("gacha_region")) if data.get("gacha_region") else None
            self.draw_button_region = tuple(data.get("draw_button_region")) if data.get("draw_button_region") else None
            self.confirm_button_region = tuple(data.get("confirm_button_region")) if data.get("confirm_button_region") else None
            self.skip_button_region = tuple(data.get("skip_button_region")) if data.get("skip_button_region") else None

            self.target_var.set(data.get("target_count", 4))
            self.countdown_var.set(data.get("countdown", 3))
            self.delay_draw_var.set(data.get("delay_draw", 0.8))
            self.delay_confirm_var.set(data.get("delay_confirm", 0.4))
            self.skip_gap_var.set(data.get("skip_gap", 0.15))
            self.delay_after_skip_var.set(data.get("delay_after_skip", 1.8))
            self.jitter_var.set(data.get("jitter", 0.0))
            self.sat_var.set(data.get("sat_threshold", 60))
            self.val_var.set(data.get("val_threshold", 120))

            self.update_labels()
            self.log(f"Config loaded from {CONFIG_FILE}")
        except FileNotFoundError:
            self.update_labels()
        except Exception as e:
            self.log(f"Failed to load config: {e}")


def main():
    pyautogui.FAILSAFE = True
    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    app = AutoGachaApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

