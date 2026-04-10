"""
TCP服务器模块 - 接收稳控科技VS系列采发仪数据
支持多设备同时连接, 异步IO处理
"""

import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class VSCollectorServer:
    """VS系列采发仪TCP采集服务器"""
    
    def __init__(self, host: str, port: int, db_path: str, channel_configs: dict,
                 alarm_config: dict = None, on_data_callback=None):
        self.host = host
        self.port = port
        self.db_path = db_path
        self.channel_configs = channel_configs
        self.alarm_config = alarm_config or {}
        self.on_data_callback = on_data_callback
        self._clients = {}   # {addr: writer}
        self._server = None
        
    async def start(self):
        """启动TCP服务器"""
        self._server = await asyncio.start_server(
            self._handle_client,
            self.host, self.port,
            limit=65536,
        )
        addr = self._server.sockets[0].getsockname()
        logger.info(f"TCP服务器已启动: {addr[0]}:{addr[1]}")
        async with self._server:
            await self._server.serve_forever()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """处理单个客户端连接"""
        addr = writer.get_extra_info('peername')
        logger.info(f"新设备连接: {addr}")
        self._clients[addr] = writer
        
        buffer = b""
        try:
            while True:
                try:
                    data = await asyncio.wait_for(reader.read(4096), timeout=300)
                except asyncio.TimeoutError:
                    logger.info(f"设备 {addr} 超时，断开连接")
                    break
                
                if not data:
                    logger.info(f"设备 {addr} 断开连接")
                    break
                
                buffer += data
                
                # 处理缓冲区中的完整帧
                while buffer:
                    frame, buffer = self._extract_frame(buffer)
                    if frame is None:
                        break
                    await self._process_frame(frame, addr, writer)
                    
        except ConnectionResetError:
            logger.info(f"设备 {addr} 连接重置")
        except Exception as e:
            logger.error(f"处理设备 {addr} 数据异常: {e}", exc_info=True)
        finally:
            self._clients.pop(addr, None)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    def _extract_frame(self, buffer: bytes):
        """
        从缓冲区提取完整数据帧
        STR格式以 \r\n 结尾
        HEX格式固定91字节
        """
        # 尝试查找 \r\n 结尾的字符串帧
        crlf_pos = buffer.find(b'\r\n')
        if crlf_pos >= 0:
            frame = buffer[:crlf_pos]
            rest = buffer[crlf_pos+2:]
            return frame, rest
        
        # 尝试 \n 结尾
        lf_pos = buffer.find(b'\n')
        if lf_pos >= 0:
            frame = buffer[:lf_pos].rstrip(b'\r')
            rest = buffer[lf_pos+1:]
            return frame, rest
        
        # HEX格式: 固定91字节二进制
        if len(buffer) >= 91:
            # 检测是否为HEX格式 (第0字节为0x01或0x02)
            if buffer[0] in (0x01, 0x02):
                return buffer[:91], buffer[91:]
        
        # 数据不够, 等待更多
        if len(buffer) > 4096:
            # 防止缓冲区溢出, 丢弃
            logger.warning(f"缓冲区溢出, 丢弃 {len(buffer)} 字节")
            return b"", b""
        
        return None, buffer

    async def _process_frame(self, frame: bytes, addr, writer):
        """处理单个数据帧"""
        if not frame:
            return
        
        from src.protocol import parse_tcp_frame
        from src.database import upsert_device, save_measurement, save_alarm
        
        parsed = parse_tcp_frame(frame)
        if not parsed:
            logger.debug(f"无法解析来自 {addr} 的数据帧")
            return
        
        udid = parsed.get('udid') or f"ADDR_{addr[0]}_{addr[1]}"
        parsed['udid'] = udid
        
        logger.info(f"设备 {udid} 数据: 协议={parsed.get('protocol')}, "
                    f"通道数={len(parsed.get('channels', {}))}, "
                    f"电压={parsed.get('battery_v', 0):.2f}V")
        
        # 更新设备信息
        try:
            upsert_device(self.db_path, udid)
        except Exception as e:
            logger.error(f"更新设备信息失败: {e}")
        
        # 保存测量数据
        try:
            measurement_id = save_measurement(self.db_path, parsed, self.channel_configs)
            logger.debug(f"数据已保存, measurement_id={measurement_id}")
        except Exception as e:
            logger.error(f"保存数据失败: {e}", exc_info=True)
            return
        
        # 检查报警
        if self.alarm_config.get('enabled'):
            self._check_alarms(parsed, udid)
        
        # 回调通知
        if self.on_data_callback:
            try:
                await self.on_data_callback(parsed)
            except Exception as e:
                logger.error(f"数据回调异常: {e}")
        
        # 向设备发送ACK (可选)
        try:
            writer.write(b"OK\r\n")
            await writer.drain()
        except Exception:
            pass

    def _check_alarms(self, parsed: dict, udid: str):
        """检查各通道报警"""
        from src.protocol import calc_piezometer
        from src.database import save_alarm
        
        warn_thresh = self.alarm_config.get('water_head_warning', 10.0)
        alarm_thresh = self.alarm_config.get('water_head_alarm', 15.0)
        device_temp = parsed.get('device_temp')
        
        for ch_no, raw_val in parsed.get('channels', {}).items():
            ch_no = int(ch_no)
            cfg = self.channel_configs.get(ch_no, {})
            if not cfg:
                continue
            try:
                phys = calc_piezometer(int(raw_val), cfg, device_temp)
                h = phys['water_head_m']
                ch_name = cfg.get('name', f'CH{ch_no:02d}')
                
                if abs(h) >= alarm_thresh:
                    msg = f"{ch_name} 水头={h:.2f}m, 超过报警阈值{alarm_thresh}m"
                    logger.warning(f"【报警】{msg}")
                    save_alarm(self.db_path, udid, ch_no, 'alarm', h, alarm_thresh, msg)
                elif abs(h) >= warn_thresh:
                    msg = f"{ch_name} 水头={h:.2f}m, 超过警告阈值{warn_thresh}m"
                    logger.warning(f"【警告】{msg}")
                    save_alarm(self.db_path, udid, ch_no, 'warning', h, warn_thresh, msg)
            except Exception as e:
                logger.debug(f"通道{ch_no}报警检查失败: {e}")


def run_server(host, port, db_path, channel_configs, alarm_config=None):
    """运行TCP服务器 (阻塞)"""
    import asyncio
    server = VSCollectorServer(host, port, db_path, channel_configs, alarm_config)
    asyncio.run(server.start())
