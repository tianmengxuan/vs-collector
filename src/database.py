"""
数据库模块 - SQLite持久化存储
表结构:
  devices      - 设备信息
  measurements - 原始测量记录
  alarms       - 报警记录
"""

import sqlite3
import logging
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def init_db(db_path: str):
    """初始化数据库, 创建所有表"""
    with sqlite3.connect(db_path) as conn:
        conn.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;

        -- 设备信息表
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            udid TEXT UNIQUE NOT NULL,             -- 设备唯一识别码
            name TEXT DEFAULT '',                   -- 设备名称
            location TEXT DEFAULT '',               -- 安装位置
            protocol TEXT DEFAULT 'STR2.0',        -- 默认数据协议
            last_seen TEXT,                        -- 最后通信时间
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 原始测量记录表
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_udid TEXT NOT NULL,             -- 设备UDID
            record_time TEXT NOT NULL,             -- 采集时间 (设备上报时间)
            received_time TEXT NOT NULL,           -- 服务器收到时间
            protocol TEXT,                         -- 协议类型
            battery_v REAL,                        -- 电池电压 V
            charge_v REAL,                         -- 充电电压 V
            signal INTEGER,                        -- 信号强度
            device_temp REAL,                      -- 设备温度 ℃
            raw_json TEXT,                         -- 原始数据JSON
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        -- 通道数据表 (渗压计数据)
        CREATE TABLE IF NOT EXISTS channel_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            measurement_id INTEGER NOT NULL,       -- 关联测量记录
            device_udid TEXT NOT NULL,
            record_time TEXT NOT NULL,
            channel_no INTEGER NOT NULL,           -- 通道号 1~32
            raw_value INTEGER,                     -- 原始值 (Hz²×0.01)
            freq_hz REAL,                          -- 频率 Hz
            pressure_kpa REAL,                     -- 渗压 kPa
            water_head_m REAL,                     -- 水头 m
            channel_temp REAL,                     -- 通道温度 ℃
            FOREIGN KEY (measurement_id) REFERENCES measurements(id)
        );
        CREATE INDEX IF NOT EXISTS idx_channel_device_time 
            ON channel_data(device_udid, record_time);
        CREATE INDEX IF NOT EXISTS idx_channel_no 
            ON channel_data(channel_no, record_time);

        -- 报警记录表
        CREATE TABLE IF NOT EXISTS alarms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_udid TEXT NOT NULL,
            channel_no INTEGER NOT NULL,
            alarm_type TEXT NOT NULL,              -- 'warning' 或 'alarm'
            value REAL NOT NULL,                   -- 触发值
            threshold REAL NOT NULL,               -- 阈值
            message TEXT,
            is_cleared INTEGER DEFAULT 0,          -- 是否已消除
            alarm_time TEXT NOT NULL,
            clear_time TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        """)
        logger.info(f"数据库初始化完成: {db_path}")


@contextmanager
def get_db(db_path: str):
    """数据库连接上下文管理器"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_device(db_path: str, udid: str, **kwargs):
    """更新或插入设备信息"""
    with get_db(db_path) as conn:
        conn.execute("""
            INSERT INTO devices (udid, last_seen) VALUES (?, datetime('now','localtime'))
            ON CONFLICT(udid) DO UPDATE SET last_seen=datetime('now','localtime')
        """, (udid,))
        if kwargs:
            sets = ', '.join(f"{k}=?" for k in kwargs)
            vals = list(kwargs.values()) + [udid]
            conn.execute(f"UPDATE devices SET {sets} WHERE udid=?", vals)


def save_measurement(db_path: str, parsed: dict, channel_configs: dict) -> int:
    """
    保存一次完整的测量记录
    返回 measurement_id
    """
    import json
    from src.protocol import calc_piezometer

    udid = parsed.get('udid', 'UNKNOWN')
    record_time = parsed.get('timestamp', datetime.now())
    if isinstance(record_time, datetime):
        record_time_str = record_time.strftime('%Y-%m-%d %H:%M:%S')
    else:
        record_time_str = str(record_time)
    
    received_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    with get_db(db_path) as conn:
        # 插入测量记录
        cur = conn.execute("""
            INSERT INTO measurements 
            (device_udid, record_time, received_time, protocol, battery_v, charge_v, signal, device_temp, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            udid,
            record_time_str,
            received_time,
            parsed.get('protocol', ''),
            parsed.get('battery_v', 0),
            parsed.get('charge_v', 0),
            parsed.get('signal', 0),
            parsed.get('device_temp', 0),
            json.dumps(parsed.get('channels', {})),
        ))
        measurement_id = cur.lastrowid
        
        # 插入各通道数据
        channels = parsed.get('channels', {})
        device_temp = parsed.get('device_temp', None)
        
        for ch_no, raw_val in channels.items():
            ch_no = int(ch_no)
            if not isinstance(raw_val, (int, float)):
                continue
            
            # 获取通道配置
            cfg = channel_configs.get(ch_no, {})
            
            # 计算物理值
            try:
                phys = calc_piezometer(int(raw_val), cfg, device_temp)
                freq_hz = phys['freq_hz']
                pressure_kpa = phys['pressure_kpa']
                water_head_m = phys['water_head_m']
            except Exception:
                freq_hz = pressure_kpa = water_head_m = None

            conn.execute("""
                INSERT INTO channel_data 
                (measurement_id, device_udid, record_time, channel_no, raw_value, freq_hz, pressure_kpa, water_head_m, channel_temp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                measurement_id, udid, record_time_str,
                ch_no, int(raw_val) if raw_val is not None else None,
                freq_hz, pressure_kpa, water_head_m,
                device_temp,
            ))
        
        return measurement_id


def get_latest_data(db_path: str, device_udid: str = None, limit: int = 100) -> list:
    """获取最新测量数据 (含通道数据)"""
    with get_db(db_path) as conn:
        if device_udid:
            rows = conn.execute("""
                SELECT m.*, GROUP_CONCAT(
                    cd.channel_no || ':' || COALESCE(cd.water_head_m,'') || ':' || COALESCE(cd.freq_hz,'') || ':' || COALESCE(cd.pressure_kpa,'')
                ) as channel_str
                FROM measurements m
                LEFT JOIN channel_data cd ON cd.measurement_id = m.id
                WHERE m.device_udid = ?
                GROUP BY m.id
                ORDER BY m.record_time DESC
                LIMIT ?
            """, (device_udid, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT m.*, GROUP_CONCAT(
                    cd.channel_no || ':' || COALESCE(cd.water_head_m,'') || ':' || COALESCE(cd.freq_hz,'') || ':' || COALESCE(cd.pressure_kpa,'')
                ) as channel_str
                FROM measurements m
                LEFT JOIN channel_data cd ON cd.measurement_id = m.id
                GROUP BY m.id
                ORDER BY m.record_time DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_channel_history(db_path: str, device_udid: str, channel_no: int, 
                        start_time: str = None, end_time: str = None, limit: int = 500) -> list:
    """获取某通道历史数据"""
    with get_db(db_path) as conn:
        query = """
            SELECT record_time, raw_value, freq_hz, pressure_kpa, water_head_m, channel_temp
            FROM channel_data
            WHERE device_udid=? AND channel_no=?
        """
        params = [device_udid, channel_no]
        if start_time:
            query += " AND record_time >= ?"
            params.append(start_time)
        if end_time:
            query += " AND record_time <= ?"
            params.append(end_time)
        query += " ORDER BY record_time DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_devices(db_path: str) -> list:
    """获取所有设备列表"""
    with get_db(db_path) as conn:
        rows = conn.execute("SELECT * FROM devices ORDER BY last_seen DESC").fetchall()
        return [dict(r) for r in rows]


def save_alarm(db_path: str, device_udid: str, channel_no: int, 
               alarm_type: str, value: float, threshold: float, message: str):
    """保存报警记录"""
    with get_db(db_path) as conn:
        conn.execute("""
            INSERT INTO alarms (device_udid, channel_no, alarm_type, value, threshold, message, alarm_time)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now','localtime'))
        """, (device_udid, channel_no, alarm_type, value, threshold, message))


def get_alarms(db_path: str, limit: int = 50, only_active: bool = False) -> list:
    """获取报警记录"""
    with get_db(db_path) as conn:
        query = "SELECT * FROM alarms"
        if only_active:
            query += " WHERE is_cleared=0"
        query += " ORDER BY alarm_time DESC LIMIT ?"
        rows = conn.execute(query, (limit,)).fetchall()
        return [dict(r) for r in rows]
