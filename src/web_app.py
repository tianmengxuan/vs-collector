"""
Web应用模块 - Flask实现可视化界面
功能:
  - 实时数据看板
  - 历史曲线查看 (ECharts)
  - 设备管理
  - 报警记录
  - 数据导出CSV
"""

import json
import csv
import io
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, Response, redirect, url_for

logger = logging.getLogger(__name__)

app = Flask(__name__, 
            template_folder='../templates',
            static_folder='../static')

# 全局配置 (由main.py注入)
_db_path = None
_channel_configs = None


def init_app(db_path: str, channel_configs: dict):
    global _db_path, _channel_configs
    _db_path = db_path
    _channel_configs = channel_configs


# ===================== 页面路由 =====================

@app.route('/')
def index():
    """首页 - 实时数据看板"""
    return render_template('index.html', channel_configs=_channel_configs)


@app.route('/history')
def history():
    """历史曲线页"""
    return render_template('history.html', channel_configs=_channel_configs)


@app.route('/devices')
def devices():
    """设备管理页"""
    return render_template('devices.html')


@app.route('/alarms')
def alarms_page():
    """报警记录页"""
    return render_template('alarms.html')


# ===================== API接口 =====================

@app.route('/api/devices')
def api_devices():
    """获取设备列表"""
    from src.database import get_devices
    devs = get_devices(_db_path)
    return jsonify({'ok': True, 'data': devs})


@app.route('/api/devices/<udid>', methods=['POST'])
def api_update_device(udid):
    """更新设备信息"""
    from src.database import upsert_device
    data = request.json or {}
    upsert_device(_db_path, udid, 
                  name=data.get('name', ''),
                  location=data.get('location', ''))
    return jsonify({'ok': True})


@app.route('/api/latest')
def api_latest():
    """获取最新数据 (按设备分组)"""
    from src.database import get_latest_data, get_devices
    from src.protocol import calc_piezometer
    
    devices = get_devices(_db_path)
    result = []
    
    for dev in devices:
        udid = dev['udid']
        rows = get_latest_data(_db_path, device_udid=udid, limit=1)
        if not rows:
            continue
        row = rows[0]
        
        # 解析通道数据
        channels_out = []
        try:
            ch_raw = json.loads(row.get('raw_json') or '{}')
        except Exception:
            ch_raw = {}
        
        device_temp = row.get('device_temp', 0)
        for ch_no_str, raw_val in ch_raw.items():
            ch_no = int(ch_no_str)
            cfg = _channel_configs.get(ch_no, {})
            ch_name = cfg.get('name', f'CH{ch_no:02d}')
            ch_desc = cfg.get('desc', '')
            
            try:
                phys = calc_piezometer(int(raw_val), cfg or {'K': -0.001, 'F0': 1200, 'B': 0, 'T0': 25},
                                       device_temp)
            except Exception:
                phys = {'freq_hz': 0, 'pressure_kpa': 0, 'water_head_m': 0}
            
            channels_out.append({
                'ch_no': ch_no,
                'name': ch_name,
                'desc': ch_desc,
                'raw_value': raw_val,
                **phys,
            })
        
        channels_out.sort(key=lambda x: x['ch_no'])
        
        result.append({
            'udid': udid,
            'name': dev.get('name') or udid,
            'location': dev.get('location', ''),
            'last_seen': dev.get('last_seen', ''),
            'record_time': row.get('record_time', ''),
            'battery_v': row.get('battery_v', 0),
            'charge_v': row.get('charge_v', 0),
            'signal': row.get('signal', 0),
            'device_temp': device_temp,
            'channels': channels_out,
        })
    
    return jsonify({'ok': True, 'data': result, 'server_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})


@app.route('/api/history')
def api_history():
    """获取通道历史数据"""
    from src.database import get_channel_history
    
    device_udid = request.args.get('udid', '')
    channel_no = int(request.args.get('ch', 1))
    days = int(request.args.get('days', 7))
    limit = int(request.args.get('limit', 500))
    
    start_time = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    
    rows = get_channel_history(_db_path, device_udid, channel_no, 
                                start_time=start_time, limit=limit)
    rows.reverse()  # 时间正序
    
    # 格式化为ECharts数据
    times = [r['record_time'] for r in rows]
    water_heads = [r.get('water_head_m') for r in rows]
    freq_hzs = [r.get('freq_hz') for r in rows]
    pressures = [r.get('pressure_kpa') for r in rows]
    
    cfg = _channel_configs.get(channel_no, {})
    
    return jsonify({
        'ok': True,
        'channel_name': cfg.get('name', f'CH{channel_no:02d}'),
        'channel_desc': cfg.get('desc', ''),
        'times': times,
        'water_heads': water_heads,
        'freq_hzs': freq_hzs,
        'pressures': pressures,
    })


@app.route('/api/alarms')
def api_alarms():
    """获取报警记录"""
    from src.database import get_alarms
    only_active = request.args.get('active', '0') == '1'
    alarms = get_alarms(_db_path, limit=100, only_active=only_active)
    return jsonify({'ok': True, 'data': alarms})


@app.route('/api/export/csv')
def api_export_csv():
    """导出CSV数据"""
    from src.database import get_channel_history, get_devices
    
    device_udid = request.args.get('udid', '')
    channel_no = int(request.args.get('ch', 1))
    days = int(request.args.get('days', 30))
    
    start_time = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    rows = get_channel_history(_db_path, device_udid, channel_no, 
                                start_time=start_time, limit=10000)
    rows.reverse()
    
    cfg = _channel_configs.get(channel_no, {})
    ch_name = cfg.get('name', f'CH{channel_no:02d}')
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['采集时间', '频率(Hz)', '渗压(kPa)', '水头(m)', '温度(℃)'])
    for r in rows:
        writer.writerow([
            r.get('record_time', ''),
            r.get('freq_hz', ''),
            r.get('pressure_kpa', ''),
            r.get('water_head_m', ''),
            r.get('channel_temp', ''),
        ])
    
    output.seek(0)
    filename = f"{ch_name}_{datetime.now().strftime('%Y%m%d')}.csv"
    
    return Response(
        '\ufeff' + output.getvalue(),  # BOM for Excel中文兼容
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@app.route('/api/stats')
def api_stats():
    """获取统计信息"""
    from src.database import get_db
    with get_db(_db_path) as conn:
        total_records = conn.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
        total_devices = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
        active_alarms = conn.execute("SELECT COUNT(*) FROM alarms WHERE is_cleared=0").fetchone()[0]
        last_data = conn.execute(
            "SELECT MAX(received_time) FROM measurements"
        ).fetchone()[0]
    
    return jsonify({
        'ok': True,
        'total_records': total_records,
        'total_devices': total_devices,
        'active_alarms': active_alarms,
        'last_data_time': last_data or '',
    })
