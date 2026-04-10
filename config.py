"""
配置文件 - VS系列振弦采发仪渗压计采集软件
设备: 河北稳控科技 VS1XX/VS4XX 系列
"""

# TCP服务器配置
TCP_HOST = "0.0.0.0"       # 监听所有网络接口
TCP_PORT = 8866             # TCP监听端口 (可在设备端配置此端口)
TCP_BUFFER_SIZE = 4096      # 缓冲区大小

# Web界面配置
WEB_HOST = "0.0.0.0"
WEB_PORT = 5000

# 数据库配置
DATABASE_PATH = "data/vs_collector.db"

# 振弦渗压计换算配置 (每个通道可独立配置)
# 渗压 P(kPa) = K * (F1^2 - F0^2) + B * (T - T0)
# 其中 F = 频率值(Hz), K=标定系数, F0=基准频率, B=温度修正系数, T=当前温度, T0=基准温度
# 水头 H(m) = P / 9.8066
SENSOR_DEFAULT_CONFIG = {
    "K": -0.001,        # 标定系数 (典型值, 需根据传感器标定证书填写)
    "F0": 1200.0,       # 基准频率 Hz
    "B": 0.0,           # 温度修正系数 (无温度修正时为0)
    "T0": 25.0,         # 基准温度 ℃
}

# 通道传感器配置 (通道号: {名称, 标定参数, 渗压计位置描述})
# 用户可在此添加/修改各通道配置
CHANNEL_CONFIG = {
    1: {"name": "渗压计-1#", "desc": "坝体1号测点", **SENSOR_DEFAULT_CONFIG},
    2: {"name": "渗压计-2#", "desc": "坝体2号测点", **SENSOR_DEFAULT_CONFIG},
    3: {"name": "渗压计-3#", "desc": "坝体3号测点", **SENSOR_DEFAULT_CONFIG},
    4: {"name": "渗压计-4#", "desc": "坝体4号测点", **SENSOR_DEFAULT_CONFIG},
    5: {"name": "渗压计-5#", "desc": "坝体5号测点", **SENSOR_DEFAULT_CONFIG},
    6: {"name": "渗压计-6#", "desc": "坝体6号测点", **SENSOR_DEFAULT_CONFIG},
    7: {"name": "渗压计-7#", "desc": "坝体7号测点", **SENSOR_DEFAULT_CONFIG},
    8: {"name": "渗压计-8#", "desc": "坝体8号测点", **SENSOR_DEFAULT_CONFIG},
}

# 报警配置 (渗压水头单位: m)
ALARM_CONFIG = {
    "enabled": True,
    "water_head_warning": 10.0,   # 警告阈值 (m)
    "water_head_alarm": 15.0,     # 报警阈值 (m)
}

# 日志配置
LOG_LEVEL = "INFO"
LOG_FILE = "data/vs_collector.log"
