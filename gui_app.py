"""
VS振弦渗压计采集软件 - GUI控制台 (Windows桌面版)
双击exe直接运行，无需安装Python环境

依赖:
    pip install pystray pillow
"""

import os
import sys
import logging
import threading
import asyncio
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import queue
import time
from datetime import datetime

# 确保路径正确 (兼容PyInstaller打包)
if getattr(sys, 'frozen', False):
    # PyInstaller打包后的运行目录
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

# 数据/日志目录
os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'logs'), exist_ok=True)

import config
from src.database import init_db
from src.tcp_server import VSCollectorServer
from src.web_app import app as flask_app, init_app

# ===================== 日志队列 (GUI显示用) =====================
log_queue = queue.Queue(maxsize=500)


class QueueHandler(logging.Handler):
    """把日志推送到队列，供GUI线程读取"""
    def emit(self, record):
        try:
            msg = self.format(record)
            log_queue.put_nowait(msg)
        except Exception:
            pass


# 配置日志
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, 'INFO'),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(
            os.path.join(BASE_DIR, config.LOG_FILE), encoding='utf-8'
        ),
    ]
)
root_logger = logging.getLogger()
queue_handler = QueueHandler()
queue_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%H:%M:%S'))
root_logger.addHandler(queue_handler)
logger = logging.getLogger('gui')


# ===================== 后台服务线程 =====================
class ServiceManager:
    def __init__(self):
        self.tcp_thread = None
        self.web_thread = None
        self.tcp_loop = None
        self.tcp_server = None
        self.running = False

    def start(self):
        if self.running:
            return
        self.running = True

        # 初始化数据库
        db_path = os.path.join(BASE_DIR, config.DATABASE_PATH)
        init_db(db_path)
        init_app(db_path, config.CHANNEL_CONFIG)

        # 启动TCP服务线程
        self.tcp_thread = threading.Thread(
            target=self._run_tcp, daemon=True, name='TCPServer'
        )
        self.tcp_thread.start()

        # 启动Web服务线程
        self.web_thread = threading.Thread(
            target=self._run_web, daemon=True, name='WebServer'
        )
        self.web_thread.start()
        logger.info(f"✅ 服务已启动 | TCP:{config.TCP_PORT}  Web:{config.WEB_PORT}")

    def _run_tcp(self):
        db_path = os.path.join(BASE_DIR, config.DATABASE_PATH)
        self.tcp_server = VSCollectorServer(
            host=config.TCP_HOST,
            port=config.TCP_PORT,
            db_path=db_path,
            channel_configs=config.CHANNEL_CONFIG,
            alarm_config=config.ALARM_CONFIG,
        )
        self.tcp_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.tcp_loop)
        try:
            self.tcp_loop.run_until_complete(self.tcp_server.start())
        except Exception as e:
            logger.error(f"TCP服务器异常: {e}")

    def _run_web(self):
        try:
            flask_app.run(
                host=config.WEB_HOST,
                port=config.WEB_PORT,
                debug=False,
                use_reloader=False,
                threaded=True,
            )
        except Exception as e:
            logger.error(f"Web服务器异常: {e}")

    def stop(self):
        self.running = False
        if self.tcp_loop and self.tcp_loop.is_running():
            self.tcp_loop.call_soon_threadsafe(self.tcp_loop.stop)
        logger.info("服务已停止")

    @property
    def web_url(self):
        host = 'localhost' if config.WEB_HOST == '0.0.0.0' else config.WEB_HOST
        return f"http://{host}:{config.WEB_PORT}"


# ===================== 主GUI窗口 =====================
class VSCollectorGUI:
    def __init__(self):
        self.service = ServiceManager()
        self.root = tk.Tk()
        self._setup_window()
        self._build_ui()
        self._start_log_poll()

    def _setup_window(self):
        self.root.title("VS振弦渗压计采集软件")
        self.root.geometry("700x520")
        self.root.minsize(600, 450)
        self.root.resizable(True, True)

        # 尝试设置图标 (打包时带入图标文件)
        icon_path = os.path.join(BASE_DIR, 'icon.ico')
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

        # 关闭窗口时最小化到托盘（或直接退出）
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 配色
        self.colors = {
            'bg': '#1e2433',
            'panel': '#262d40',
            'accent': '#4a9eff',
            'green': '#2ecc71',
            'red': '#e74c3c',
            'yellow': '#f39c12',
            'text': '#e0e6f0',
            'subtext': '#8a99b8',
        }
        self.root.configure(bg=self.colors['bg'])

    def _build_ui(self):
        c = self.colors

        # ---- 顶部标题栏 ----
        header = tk.Frame(self.root, bg=c['accent'], height=50)
        header.pack(fill='x')
        header.pack_propagate(False)
        tk.Label(
            header, text="🔬  VS振弦渗压计采集软件",
            font=('Microsoft YaHei', 14, 'bold'),
            bg=c['accent'], fg='white'
        ).pack(side='left', padx=16, pady=10)
        tk.Label(
            header, text="河北稳控科技 VS1XX/VS4XX",
            font=('Microsoft YaHei', 9),
            bg=c['accent'], fg='#d0e8ff'
        ).pack(side='right', padx=16)

        # ---- 主体区域 ----
        body = tk.Frame(self.root, bg=c['bg'])
        body.pack(fill='both', expand=True, padx=12, pady=10)

        # 左侧控制面板
        left = tk.Frame(body, bg=c['panel'], width=200, bd=0,
                        highlightbackground='#3a4460', highlightthickness=1)
        left.pack(side='left', fill='y', padx=(0, 8))
        left.pack_propagate(False)
        self._build_control_panel(left)

        # 右侧日志区
        right = tk.Frame(body, bg=c['panel'],
                         highlightbackground='#3a4460', highlightthickness=1)
        right.pack(side='left', fill='both', expand=True)
        self._build_log_panel(right)

    def _build_control_panel(self, parent):
        c = self.colors
        tk.Label(parent, text="服务状态", bg=c['panel'], fg=c['subtext'],
                 font=('Microsoft YaHei', 9)).pack(pady=(14, 4))

        # 状态指示灯
        status_frame = tk.Frame(parent, bg=c['panel'])
        status_frame.pack(fill='x', padx=12)

        # TCP状态
        self._tcp_status_label = self._status_row(status_frame, "TCP采集服务", "待启动", c['yellow'])
        # Web状态
        self._web_status_label = self._status_row(status_frame, "Web界面服务", "待启动", c['yellow'])

        tk.Frame(parent, bg='#3a4460', height=1).pack(fill='x', padx=10, pady=12)

        # 端口信息
        tk.Label(parent, text="端口配置", bg=c['panel'], fg=c['subtext'],
                 font=('Microsoft YaHei', 9)).pack(pady=(0, 6))
        self._port_info(parent, "TCP接入端口", str(config.TCP_PORT))
        self._port_info(parent, "Web管理端口", str(config.WEB_PORT))

        tk.Frame(parent, bg='#3a4460', height=1).pack(fill='x', padx=10, pady=12)

        # 操作按钮
        self.btn_start = tk.Button(
            parent, text="▶  启动服务",
            command=self._start_service,
            bg=c['green'], fg='white',
            font=('Microsoft YaHei', 10, 'bold'),
            relief='flat', cursor='hand2',
            padx=8, pady=6
        )
        self.btn_start.pack(fill='x', padx=12, pady=3)

        self.btn_stop = tk.Button(
            parent, text="■  停止服务",
            command=self._stop_service,
            bg='#3a4460', fg=c['subtext'],
            font=('Microsoft YaHei', 10),
            relief='flat', cursor='hand2',
            padx=8, pady=6, state='disabled'
        )
        self.btn_stop.pack(fill='x', padx=12, pady=3)

        self.btn_web = tk.Button(
            parent, text="🌐  打开Web界面",
            command=self._open_browser,
            bg=c['accent'], fg='white',
            font=('Microsoft YaHei', 10),
            relief='flat', cursor='hand2',
            padx=8, pady=6, state='disabled'
        )
        self.btn_web.pack(fill='x', padx=12, pady=3)

        tk.Frame(parent, bg='#3a4460', height=1).pack(fill='x', padx=10, pady=12)

        # 配置按钮
        tk.Button(
            parent, text="⚙  修改配置",
            command=self._open_config_editor,
            bg='#3a4460', fg=c['text'],
            font=('Microsoft YaHei', 9),
            relief='flat', cursor='hand2',
            padx=8, pady=5
        ).pack(fill='x', padx=12, pady=2)

        tk.Button(
            parent, text="📁  打开数据目录",
            command=self._open_data_dir,
            bg='#3a4460', fg=c['text'],
            font=('Microsoft YaHei', 9),
            relief='flat', cursor='hand2',
            padx=8, pady=5
        ).pack(fill='x', padx=12, pady=2)

        # 底部版本信息
        tk.Label(parent, text="v1.0  稳控科技协议兼容",
                 bg=c['panel'], fg=c['subtext'],
                 font=('Microsoft YaHei', 7)).pack(side='bottom', pady=8)

    def _status_row(self, parent, label, text, color):
        c = self.colors
        row = tk.Frame(parent, bg=c['panel'])
        row.pack(fill='x', pady=2)
        tk.Label(row, text=label, bg=c['panel'], fg=c['subtext'],
                 font=('Microsoft YaHei', 8), width=10, anchor='w').pack(side='left')
        lbl = tk.Label(row, text=f"● {text}", bg=c['panel'], fg=color,
                       font=('Microsoft YaHei', 8))
        lbl.pack(side='left')
        return lbl

    def _port_info(self, parent, label, value):
        c = self.colors
        row = tk.Frame(parent, bg=c['panel'])
        row.pack(fill='x', padx=8, pady=1)
        tk.Label(row, text=label + ":", bg=c['panel'], fg=c['subtext'],
                 font=('Microsoft YaHei', 8)).pack(side='left')
        tk.Label(row, text=value, bg=c['panel'], fg=c['accent'],
                 font=('Microsoft YaHei', 8, 'bold')).pack(side='right')

    def _build_log_panel(self, parent):
        c = self.colors
        header = tk.Frame(parent, bg='#2e3650')
        header.pack(fill='x')
        tk.Label(header, text="运行日志", bg='#2e3650', fg=c['text'],
                 font=('Microsoft YaHei', 9, 'bold')).pack(side='left', padx=10, pady=6)
        tk.Button(
            header, text="清空",
            command=self._clear_log,
            bg='#3a4460', fg=c['subtext'],
            font=('Microsoft YaHei', 8),
            relief='flat', cursor='hand2',
            padx=6, pady=2
        ).pack(side='right', padx=8, pady=4)

        self.log_text = scrolledtext.ScrolledText(
            parent,
            bg='#131824', fg='#a8c4e0',
            font=('Consolas', 9),
            relief='flat', bd=0,
            state='disabled',
            wrap='word',
        )
        self.log_text.pack(fill='both', expand=True, padx=6, pady=6)

        # 日志颜色标签
        self.log_text.tag_config('ERROR', foreground='#ff6b6b')
        self.log_text.tag_config('WARNING', foreground='#f0a500')
        self.log_text.tag_config('INFO', foreground='#a8c4e0')
        self.log_text.tag_config('OK', foreground='#2ecc71')

    # ===================== 事件处理 =====================

    def _start_service(self):
        self.btn_start.config(state='disabled', text="启动中...")
        self.service.start()

        # 稍等后更新状态
        self.root.after(1500, self._update_running_state)

    def _update_running_state(self):
        c = self.colors
        self._tcp_status_label.config(text="● 运行中", fg=c['green'])
        self._web_status_label.config(text="● 运行中", fg=c['green'])
        self.btn_start.config(state='disabled', text="▶  已启动")
        self.btn_stop.config(state='normal', bg=c['red'])
        self.btn_web.config(state='normal')

    def _stop_service(self):
        if messagebox.askyesno("确认停止", "停止服务后设备数据将无法接收，确定停止吗？"):
            self.service.stop()
            c = self.colors
            self._tcp_status_label.config(text="● 已停止", fg=c['red'])
            self._web_status_label.config(text="● 已停止", fg=c['red'])
            self.btn_start.config(state='normal', text="▶  启动服务")
            self.btn_stop.config(state='disabled', bg='#3a4460')
            self.btn_web.config(state='disabled')

    def _open_browser(self):
        url = self.service.web_url
        webbrowser.open(url)
        logger.info(f"已打开浏览器: {url}")

    def _clear_log(self):
        self.log_text.config(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.config(state='disabled')

    def _open_data_dir(self):
        data_dir = os.path.join(BASE_DIR, 'data')
        os.makedirs(data_dir, exist_ok=True)
        if sys.platform == 'win32':
            os.startfile(data_dir)
        else:
            import subprocess
            subprocess.Popen(['open', data_dir])

    def _open_config_editor(self):
        """打开配置编辑对话框"""
        ConfigEditorDialog(self.root, self.colors)

    def _on_close(self):
        if self.service.running:
            if messagebox.askyesno(
                "退出确认",
                "服务正在运行，退出后设备数据将停止采集。\n\n确定退出程序吗？"
            ):
                self.service.stop()
                self.root.destroy()
        else:
            self.root.destroy()

    # ===================== 日志轮询 =====================

    def _start_log_poll(self):
        self._poll_log()

    def _poll_log(self):
        try:
            while True:
                msg = log_queue.get_nowait()
                self._append_log(msg)
        except queue.Empty:
            pass
        self.root.after(200, self._poll_log)

    def _append_log(self, msg: str):
        self.log_text.config(state='normal')
        # 根据级别着色
        if '[ERROR]' in msg:
            tag = 'ERROR'
        elif '[WARNING]' in msg:
            tag = 'WARNING'
        elif '✅' in msg or '启动' in msg or '运行' in msg:
            tag = 'OK'
        else:
            tag = 'INFO'
        self.log_text.insert('end', msg + '\n', tag)
        self.log_text.see('end')
        # 保留最后500行
        lines = int(self.log_text.index('end-1c').split('.')[0])
        if lines > 500:
            self.log_text.delete('1.0', f'{lines-500}.0')
        self.log_text.config(state='disabled')

    # ===================== 自动启动 =====================

    def auto_start(self):
        """程序启动后自动开始采集服务"""
        self.root.after(800, self._start_service)

    def run(self):
        # 写入启动日志
        logger.info("=" * 50)
        logger.info("VS振弦渗压计采集软件 启动")
        logger.info(f"程序目录: {BASE_DIR}")
        logger.info(f"TCP端口: {config.TCP_PORT} | Web端口: {config.WEB_PORT}")
        logger.info("=" * 50)

        # 自动启动服务
        self.auto_start()
        self.root.mainloop()


# ===================== 配置编辑对话框 =====================
class ConfigEditorDialog:
    def __init__(self, parent, colors):
        self.colors = colors
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("修改配置")
        self.dialog.geometry("480x420")
        self.dialog.resizable(False, False)
        self.dialog.configure(bg=colors['bg'])
        self.dialog.grab_set()  # 模态

        self._build()

    def _build(self):
        c = self.colors
        tk.Label(self.dialog, text="服务端口配置",
                 bg=c['bg'], fg=c['text'],
                 font=('Microsoft YaHei', 11, 'bold')).pack(pady=(16, 4))
        tk.Label(self.dialog, text="修改后需重启软件生效",
                 bg=c['bg'], fg=c['subtext'],
                 font=('Microsoft YaHei', 8)).pack()

        frame = tk.Frame(self.dialog, bg=c['panel'],
                         highlightbackground='#3a4460', highlightthickness=1)
        frame.pack(fill='x', padx=20, pady=12)

        fields = [
            ("TCP采集端口（设备端填入此端口）:", "TCP_PORT", str(config.TCP_PORT)),
            ("Web管理端口（浏览器访问端口）:", "WEB_PORT", str(config.WEB_PORT)),
        ]
        self.vars = {}
        for label, key, default in fields:
            row = tk.Frame(frame, bg=c['panel'])
            row.pack(fill='x', padx=12, pady=6)
            tk.Label(row, text=label, bg=c['panel'], fg=c['text'],
                     font=('Microsoft YaHei', 9)).pack(anchor='w')
            var = tk.StringVar(value=default)
            self.vars[key] = var
            tk.Entry(row, textvariable=var, bg='#1e2433', fg=c['accent'],
                     font=('Consolas', 11), relief='flat',
                     insertbackground=c['accent']).pack(fill='x', pady=2, ipady=4)

        # 报警阈值
        tk.Label(self.dialog, text="报警阈值配置（水头 m）",
                 bg=c['bg'], fg=c['text'],
                 font=('Microsoft YaHei', 11, 'bold')).pack(pady=(4, 2))
        frame2 = tk.Frame(self.dialog, bg=c['panel'],
                          highlightbackground='#3a4460', highlightthickness=1)
        frame2.pack(fill='x', padx=20, pady=6)
        alarm_fields = [
            ("警告阈值 (m):", "WARNING", str(config.ALARM_CONFIG.get('water_head_warning', 10.0))),
            ("报警阈值 (m):", "ALARM", str(config.ALARM_CONFIG.get('water_head_alarm', 15.0))),
        ]
        for label, key, default in alarm_fields:
            row = tk.Frame(frame2, bg=c['panel'])
            row.pack(fill='x', padx=12, pady=6)
            tk.Label(row, text=label, bg=c['panel'], fg=c['text'],
                     font=('Microsoft YaHei', 9)).pack(anchor='w')
            var = tk.StringVar(value=default)
            self.vars[key] = var
            tk.Entry(row, textvariable=var, bg='#1e2433', fg=c['accent'],
                     font=('Consolas', 11), relief='flat',
                     insertbackground=c['accent']).pack(fill='x', pady=2, ipady=4)

        # 按钮
        btn_frame = tk.Frame(self.dialog, bg=c['bg'])
        btn_frame.pack(pady=12)
        tk.Button(
            btn_frame, text="保存配置", command=self._save,
            bg=c['green'], fg='white',
            font=('Microsoft YaHei', 10, 'bold'),
            relief='flat', cursor='hand2', padx=20, pady=6
        ).pack(side='left', padx=8)
        tk.Button(
            btn_frame, text="取消",
            command=self.dialog.destroy,
            bg='#3a4460', fg=c['text'],
            font=('Microsoft YaHei', 10),
            relief='flat', cursor='hand2', padx=20, pady=6
        ).pack(side='left', padx=8)

    def _save(self):
        try:
            tcp_port = int(self.vars['TCP_PORT'].get())
            web_port = int(self.vars['WEB_PORT'].get())
            warning = float(self.vars['WARNING'].get())
            alarm_val = float(self.vars['ALARM'].get())
        except ValueError:
            messagebox.showerror("错误", "请输入合法的数值！")
            return

        # 写入config.py
        config_path = os.path.join(BASE_DIR, 'config.py')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()

            import re
            content = re.sub(r'TCP_PORT\s*=\s*\d+', f'TCP_PORT = {tcp_port}', content)
            content = re.sub(r'WEB_PORT\s*=\s*\d+', f'WEB_PORT = {web_port}', content)
            content = re.sub(r'"water_head_warning"\s*:\s*[\d.]+', f'"water_head_warning": {warning}', content)
            content = re.sub(r'"water_head_alarm"\s*:\s*[\d.]+', f'"water_head_alarm": {alarm_val}', content)

            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(content)

            messagebox.showinfo("保存成功", "配置已保存，重启软件后生效。")
            self.dialog.destroy()
        except Exception as e:
            messagebox.showerror("保存失败", str(e))


# ===================== 程序入口 =====================
if __name__ == '__main__':
    app = VSCollectorGUI()
    app.run()
