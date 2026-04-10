"""
稳控科技 VS 系列采发仪协议解析模块
支持协议:
  - HEX 格式 (91字节二进制帧)
  - STR 格式 1.0 (156字符16进制字符串帧)
  - STR 格式 2.0 (BATV= 标识的可读字符串)
  - MDS 独立传感器格式 (TCP专用前缀格式)

TCP数据帧格式:
  UDID>数据帧
  例: 15B87911B123456>数据

振弦数据单位: 原始值为 频率² × 0.01 (即存储 F²×0.01)
  或 直接存储频率Hz (具体取决于设备配置)
"""

import struct
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def crc16_modbus(data: bytes) -> int:
    """CRC16 MODBUS 校验算法"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def parse_tcp_frame(raw_data: bytes) -> dict:
    """
    解析TCP数据帧，自动识别协议类型
    返回标准化的数据字典
    """
    try:
        # 尝试UTF-8解码
        try:
            text = raw_data.decode('utf-8', errors='replace').strip()
        except Exception:
            text = raw_data.decode('ascii', errors='replace').strip()

        logger.debug(f"收到原始数据: {text[:200]}")

        # TCP帧格式: UDID>数据帧
        udid = None
        data_part = text
        if '>' in text:
            parts = text.split('>', 1)
            if len(parts[0]) >= 10:  # UDID至少10位
                udid = parts[0].strip()
                data_part = parts[1].strip()

        # 识别协议类型
        if 'BATV=' in data_part:
            result = _parse_str2(data_part)
        elif 'PHYV_STR' in data_part:
            result = _parse_str3(data_part)
        elif len(data_part) == 156 and _is_hex_string(data_part):
            result = _parse_str1(data_part)
        elif len(raw_data) == 91 or (udid and len(data_part.encode()) == 91):
            result = _parse_hex(raw_data if not udid else data_part.encode())
        else:
            # 尝试MDS格式（单独传感器包）
            if '>MDS' in text:
                result = _parse_mds(text)
            else:
                # 尝试STR2.0
                result = _parse_str2(data_part)

        if result:
            result['udid'] = udid
            result['raw'] = text[:500]
        return result

    except Exception as e:
        logger.error(f"协议解析异常: {e}", exc_info=True)
        return None


def _is_hex_string(s: str) -> bool:
    """判断是否为16进制字符串"""
    try:
        int(s, 16)
        return True
    except ValueError:
        return False


def _parse_hex(data: bytes) -> dict:
    """
    解析 HEX 格式 (91字节二进制)
    偏移:
      0      : 数据类型码 (0x01手动, 0x02自动)
      1~2    : 设备ID号
      3~6    : 数据记录号
      7~12   : 时间戳 BCD(年月日时分秒)
      13     : 预留
      14     : 信号强度
      15~16  : 设备温度 (×0.1℃)
      17~18  : 供电电压 (×0.01V)
      19~20  : 充电电压 (×0.01V)
      21~24  : 脉冲传感器计数
      25~88  : 32通道数据 (每通道2字节)
      89~90  : CRC16
    """
    if len(data) < 91:
        return None
    
    data_type = data[0]
    device_id = struct.unpack('>H', data[1:3])[0]
    record_no = struct.unpack('>I', data[3:7])[0]
    
    # BCD时间解码
    bcd = data[7:13]
    year = 2000 + (bcd[0] >> 4) * 10 + (bcd[0] & 0x0F)
    month = (bcd[1] >> 4) * 10 + (bcd[1] & 0x0F)
    day = (bcd[2] >> 4) * 10 + (bcd[2] & 0x0F)
    hour = (bcd[3] >> 4) * 10 + (bcd[3] & 0x0F)
    minute = (bcd[4] >> 4) * 10 + (bcd[4] & 0x0F)
    second = (bcd[5] >> 4) * 10 + (bcd[5] & 0x0F)
    
    try:
        timestamp = datetime(year, month, day, hour, minute, second)
    except ValueError:
        timestamp = datetime.now()

    signal = data[14]
    device_temp = struct.unpack('>h', data[15:17])[0] * 0.1  # 有符号
    battery_v = struct.unpack('>H', data[17:19])[0] * 0.01
    charge_v = struct.unpack('>H', data[19:21])[0] * 0.01

    # 32通道数据 (每通道2字节, 单位: Hz 或 F²×0.01, 具体看设备配置)
    channels = {}
    for ch in range(32):
        offset = 25 + ch * 2
        val = struct.unpack('>H', data[offset:offset+2])[0]
        channels[ch + 1] = val

    # CRC验证
    crc_calc = crc16_modbus(data[:89])
    crc_recv = struct.unpack('<H', data[89:91])[0]
    crc_ok = (crc_calc == crc_recv)

    return {
        'protocol': 'HEX',
        'data_type': 'manual' if data_type == 0x01 else 'auto',
        'device_id': device_id,
        'record_no': record_no,
        'timestamp': timestamp,
        'signal': signal,
        'device_temp': device_temp,
        'battery_v': battery_v,
        'charge_v': charge_v,
        'channels': channels,
        'crc_ok': crc_ok,
    }


def _parse_str1(text: str) -> dict:
    """
    解析 STR 格式 1.0 (156字符16进制字符串)
    每2字符=1字节, 与HEX格式字段对应但无时间戳和类型码
    偏移(字符数):
      0~1   : 设备ID
      2~5   : 数据记录号
      6~7   : 预留
      8~9   : 信号强度
      10~11 : 设备温度 ℃
      12~15 : 脉冲计数
      16~19 : 供电电压 ×0.01V
      20~23 : 充电电压 ×0.01V
      24~151: 32通道数据 (128字符=64字节)
      152~155: CRC16
    """
    if len(text) < 156:
        return None
    
    try:
        device_id = int(text[0:2], 16)
        record_no = int(text[2:6], 16)
        signal = int(text[8:10], 16)
        device_temp = int(text[10:12], 16)
        battery_v = int(text[16:20], 16) * 0.01
        charge_v = int(text[20:24], 16) * 0.01

        channels = {}
        for ch in range(32):
            offset = 24 + ch * 4
            val = int(text[offset:offset+4], 16)
            channels[ch + 1] = val

        return {
            'protocol': 'STR1.0',
            'device_id': device_id,
            'record_no': record_no,
            'timestamp': datetime.now(),
            'signal': signal,
            'device_temp': device_temp,
            'battery_v': battery_v,
            'charge_v': charge_v,
            'channels': channels,
            'crc_ok': True,
        }
    except Exception as e:
        logger.warning(f"STR1.0解析失败: {e}")
        return None


def _parse_str2(text: str) -> dict:
    """
    解析 STR 格式 2.0
    格式: BATV=nnnnn CHGV=nnnnn SIGV=nnnnn TEMP=nnnnn CH01=nnnnn CH02=...
    nnnnn 为固定5字符十进制数
    BATV: 供电电压 ×0.01V
    CHGV: 充电电压 ×0.01V
    SIGV: 信号强度
    TEMP: 设备温度 ×0.1℃
    CHxx: 通道数据 (振弦频率Hz×100 或 F²×0.01, 取决于配置)
    """
    result = {
        'protocol': 'STR2.0',
        'timestamp': datetime.now(),
        'channels': {},
        'crc_ok': True,
    }
    
    # 解析各字段
    import re
    
    m = re.search(r'BATV=(\d+)', text)
    result['battery_v'] = int(m.group(1)) * 0.01 if m else 0.0
    
    m = re.search(r'CHGV=(\d+)', text)
    result['charge_v'] = int(m.group(1)) * 0.01 if m else 0.0
    
    m = re.search(r'SIGV=(\d+)', text)
    result['signal'] = int(m.group(1)) if m else 0
    
    m = re.search(r'TEMP=(-?\d+)', text)
    result['device_temp'] = int(m.group(1)) * 0.1 if m else 0.0

    # 通道数据
    for ch_match in re.finditer(r'CH(\d+)=(\d+)', text):
        ch_no = int(ch_match.group(1))
        ch_val = int(ch_match.group(2))
        result['channels'][ch_no] = ch_val
    
    if not result['channels']:
        return None
    
    return result


def _parse_str3(text: str) -> dict:
    """
    解析 STR 格式 3.0 (物理值格式)
    格式: PHYV_STR BATV=xx.xxV CHGV=xx.xxV SIGV=xx.x% TEMP=xx.x'C ZX1=xxx.xHz ...
    """
    import re
    result = {
        'protocol': 'STR3.0',
        'timestamp': datetime.now(),
        'channels': {},
        'physical_values': {},
        'crc_ok': True,
    }
    
    m = re.search(r'BATV=([\d.]+)V', text)
    result['battery_v'] = float(m.group(1)) if m else 0.0
    
    m = re.search(r'CHGV=([\d.]+)V', text)
    result['charge_v'] = float(m.group(1)) if m else 0.0
    
    m = re.search(r'SIGV=([\d.]+)%', text)
    result['signal'] = float(m.group(1)) if m else 0.0
    
    m = re.search(r"TEMP=([\d.]+)'C", text)
    result['device_temp'] = float(m.group(1)) if m else 0.0

    # 物理值通道 (ZX1, ZX2 等)
    for match in re.finditer(r'([A-Z]+\d+)=([-\d.]+)', text):
        key = match.group(1)
        val = float(match.group(2))
        result['physical_values'][key] = val

    return result


def _parse_mds(text: str) -> dict:
    """
    解析 MDS 独立传感器格式
    格式: UDID>MDSxxxx>包号/总包>数据,校验\r\n
    """
    import re
    result = {
        'protocol': 'MDS',
        'timestamp': datetime.now(),
        'channels': {},
        'crc_ok': True,
    }
    # 简单提取数据部分
    m = re.search(r'>MDS([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})>(\d+)/(\d+)>([^,\r\n]+)', text)
    if m:
        sensor_type = int(m.group(1), 16)
        sensor_no = int(m.group(2), 16)
        data_str = m.group(5)
        result['mds_sensor_type'] = sensor_type
        result['mds_sensor_no'] = sensor_no
        result['mds_raw_data'] = data_str
        result['channels'][sensor_no] = data_str

    return result


def calc_piezometer(raw_val: int, config: dict, channel_temp: float = None) -> dict:
    """
    振弦渗压计物理值换算
    
    协议中通道原始值存储规则 (VS系列设备):
      STR2.0/HEX: 存储 F²×0.01 (频率²×0.01), 单位为 Hz²×0.01
      需要先还原频率: F = sqrt(raw_val * 100) = sqrt(raw_val) * 10
      
    渗压计换算公式:
      P(kPa) = K × (F² - F0²) + B × (T - T0)
      水头 H(m) = P / 9.8066
      
    参数:
      raw_val: 通道原始值 (Hz²×0.01)
      config: 传感器标定配置 {K, F0, B, T0}
      channel_temp: 当前温度 ℃ (None则不做温度补偿)
    """
    K = config.get('K', -0.001)
    F0 = config.get('F0', 1200.0)
    B = config.get('B', 0.0)
    T0 = config.get('T0', 25.0)
    
    # 还原频率
    freq_hz = (raw_val * 100) ** 0.5  # F = sqrt(raw×100)
    
    # 计算 F² - F0²
    delta_f2 = freq_hz ** 2 - F0 ** 2
    
    # 温度补偿
    temp_comp = 0.0
    if channel_temp is not None and B != 0.0:
        temp_comp = B * (channel_temp - T0)
    
    # 渗压 (kPa)
    pressure_kpa = K * delta_f2 + temp_comp
    
    # 水头 (m)
    water_head_m = pressure_kpa / 9.8066
    
    return {
        'freq_hz': round(freq_hz, 2),
        'pressure_kpa': round(pressure_kpa, 3),
        'water_head_m': round(water_head_m, 3),
        'temp_comp': round(temp_comp, 3),
    }
