import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import cv2
from PIL import Image, ImageTk
from moviepy import VideoFileClip
from proglog import ProgressBarLogger

# MoviePy 진행률 추적 및 UI 업데이트용 로거
class TkinterLogger(ProgressBarLogger):
    def __init__(self, update_callback):
        super().__init__()
        self.update_callback = update_callback

    def callback(self, **changes):
        for bar, state in self.state['bars'].items():
            if state['total'] > 0:
                percentage = int((state['index'] / state['total']) * 100)
                self.update_callback(percentage)

class VideoGifMakerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("영상 구간 선택 GIF 변환기")
        self.root.geometry("800x850")

        self.video_path = None
        self.cap = None
        
        self.fps = 30.0
        self.total_frames = 0
        self.duration = 0.0
        self.current_sec = 0.0
        
        self.start_time = None
        self.segments = []

        self.init_ui()

    def init_ui(self):
        # 1. 상단 파일 열기
        top_frame = tk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=10, pady=5)
        
        btn_open = tk.Button(top_frame, text="영상 파일 열기", command=self.load_video)
        btn_open.pack(side=tk.LEFT)
        
        self.lbl_file = tk.Label(top_frame, text="선택된 파일 없음", anchor="w")
        self.lbl_file.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        # 2. 비디오 화면 출력 캔버스 (640x360)
        self.canvas = tk.Canvas(self.root, width=640, height=360, bg="black")
        self.canvas.pack(pady=5)

        # 3. 시간 및 슬라이더 + 미세 이동 버튼
        time_frame = tk.Frame(self.root)
        time_frame.pack(fill=tk.X, padx=15, pady=5)

        self.lbl_time = tk.Label(time_frame, text="00:00 / 00:00 (0.0초)", font=("Malgun Gothic", 11, "bold"))
        self.lbl_time.pack()

        self.slider = ttk.Scale(time_frame, from_=0, to=100, orient=tk.HORIZONTAL, command=self.on_slider_move)
        self.slider.pack(fill=tk.X, pady=5)

        # 프레임 이동 컨트롤
        ctrl_frame = tk.Frame(self.root)
        ctrl_frame.pack(pady=2)

        btn_prev = tk.Button(ctrl_frame, text="◀ -0.5초", command=lambda: self.seek_relative(-0.5))
        btn_prev.pack(side=tk.LEFT, padx=3)

        btn_prev_fine = tk.Button(ctrl_frame, text="◀ -0.1초", command=lambda: self.seek_relative(-0.1))
        btn_prev_fine.pack(side=tk.LEFT, padx=3)

        btn_next_fine = tk.Button(ctrl_frame, text="+0.1초 ▶", command=lambda: self.seek_relative(0.1))
        btn_next_fine.pack(side=tk.LEFT, padx=3)

        btn_next = tk.Button(ctrl_frame, text="+0.5초 ▶", command=lambda: self.seek_relative(0.5))
        btn_next.pack(side=tk.LEFT, padx=3)

        # 4. In/Out 구간 지정 버튼
        io_frame = tk.Frame(self.root)
        io_frame.pack(pady=8)

        self.btn_in = tk.Button(io_frame, text="[ 시작점 찍기 (In)", command=self.set_in_point, bg="#e1f5fe", font=("Malgun Gothic", 10, "bold"))
        self.btn_in.pack(side=tk.LEFT, padx=10)

        self.btn_out = tk.Button(io_frame, text="] 끝점 찍고 추가 (Out)", command=self.set_out_point, bg="#e8f5e9", font=("Malgun Gothic", 10, "bold"))
        self.btn_out.pack(side=tk.LEFT, padx=10)

        # 5. 구간 리스트
        list_frame = tk.Frame(self.root)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tk.Label(list_frame, text="추출할 구간 목록", font=("Malgun Gothic", 9, "bold")).pack(anchor="w")
        
        self.tree = ttk.Treeview(list_frame, columns=("num", "start", "end", "duration"), show="headings", height=5)
        self.tree.heading("num", text="번호")
        self.tree.heading("start", text="시작 시간(초)")
        self.tree.heading("end", text="종료 시간(초)")
        self.tree.heading("duration", text="길이(초)")
        self.tree.column("num", width=50, anchor="center")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        btn_del = tk.Button(list_frame, text="선택 삭제", command=self.delete_segment)
        btn_del.pack(side=tk.RIGHT, anchor="n", padx=5)

        # 6. GIF 변환 버튼
        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(fill=tk.X, padx=10, pady=10)

        self.btn_convert = tk.Button(bottom_frame, text="선택한 구간들 GIF로 일괄 변환", command=self.start_conversion, bg="#fff59d", font=("Malgun Gothic", 11, "bold"), height=2)
        self.btn_convert.pack(fill=tk.X)

    def load_video(self):
        file_path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4 *.mov *.avi *.mkv")])
        if not file_path:
            return
        
        self.video_path = file_path
        self.lbl_file.config(text=os.path.basename(file_path))

        if self.cap:
            self.cap.release()
        
        self.cap = cv2.VideoCapture(file_path)
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.duration = self.total_frames / self.fps

        self.slider.config(to=self.duration)
        self.segments.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.show_frame_at(0)

    def show_frame_at(self, sec):
        if not self.cap:
            return
        
        sec = max(0.0, min(sec, self.duration))
        self.current_sec = sec
        frame_no = int(sec * self.fps)
        
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ret, frame = self.cap.read()
        
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame).resize((640, 360), Image.Resampling.LANCZOS)
            self.tk_img = ImageTk.PhotoImage(image=img)
            self.canvas.create_image(0, 0, image=self.tk_img, anchor=tk.NW)
            
        self.update_time_label(sec)

    def update_time_label(self, curr):
        m1, s1 = divmod(int(curr), 60)
        m2, s2 = divmod(int(self.duration), 60)
        in_status = f" (In: {self.start_time:.2f}s)" if self.start_time is not None else ""
        self.lbl_time.config(text=f"{m1:02d}:{s1:02d} / {m2:02d}:{s2:02d} ({curr:.2f}초){in_status}")

    def on_slider_move(self, val):
        self.show_frame_at(float(val))

    def seek_relative(self, delta_sec):
        new_time = self.current_sec + delta_sec
        self.slider.set(new_time)
        self.show_frame_at(new_time)

    def set_in_point(self):
        if not self.cap:
            return
        self.start_time = round(self.current_sec, 2)
        self.btn_in.config(text=f"[ In: {self.start_time}s ]")
        self.update_time_label(self.current_sec)

    def set_out_point(self):
        if self.start_time is None:
            messagebox.showwarning("경고", "먼저 [시작점 찍기]를 클릭해 주세요.")
            return
        
        end_time = round(self.current_sec, 2)
        if end_time <= self.start_time:
            messagebox.showwarning("경고", "끝점은 시작점보다 뒤에 있어야 합니다.")
            return

        seg_len = round(end_time - self.start_time, 2)
        self.segments.append((self.start_time, end_time))
        
        idx = len(self.segments)
        self.tree.insert("", "end", values=(idx, f"{self.start_time:.2f}s", f"{end_time:.2f}s", f"{seg_len:.2f}s"))
        
        self.start_time = None
        self.btn_in.config(text="[ 시작점 찍기 (In)")
        self.update_time_label(self.current_sec)

    def delete_segment(self):
        selected = self.tree.selection()
        if not selected:
            return
        for sel in selected:
            idx = int(self.tree.item(sel)["values"][0]) - 1
            self.tree.delete(sel)
            self.segments.pop(idx)
        
        for i, item in enumerate(self.tree.get_children()):
            vals = list(self.tree.item(item)["values"])
            vals[0] = i + 1
            self.tree.item(item, values=vals)

    def start_conversion(self):
        if not self.segments:
            messagebox.showwarning("경고", "추출할 구간이 없습니다.")
            return

        output_dir = filedialog.askdirectory(title="GIF를 저장할 폴더 선택")
        if not output_dir:
            return

        self.btn_convert.config(state=tk.DISABLED, text="GIF 변환 준비 중...")
        threading.Thread(target=self.run_conversion, args=(output_dir,), daemon=True).start()

    def run_conversion(self, output_dir):
        clip = VideoFileClip(self.video_path)
        base_name = os.path.splitext(os.path.basename(self.video_path))[0]
        total_count = len(self.segments)
        
        for i, (start, end) in enumerate(self.segments, 1):
            sub = clip.subclipped(start, end)
            sub_resized = sub.resized(height=360)
            out_path = os.path.join(output_dir, f"{base_name}_part{i}_{start}s-{end}s.gif")
            
            # 진행률 업데이트 콜백 함수
            def update_progress(percent):
                text = f"GIF 변환 중... [{i}/{total_count}] ({percent}%)"
                self.root.after(0, lambda: self.btn_convert.config(text=text))

            logger = TkinterLogger(update_progress)
            sub_resized.write_gif(out_path, fps=12, logger=logger)

        clip.close()
        self.root.after(0, self.on_complete)

    def on_complete(self):
        self.btn_convert.config(state=tk.NORMAL, text="선택한 구간들 GIF로 일괄 변환")
        messagebox.showinfo("완료", "모든 GIF 변환이 완료되었습니다!")

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoGifMakerApp(root)
    root.mainloop()