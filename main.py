"""
主程序入口 - VS振弦渗压计采集软件
启动方式:
  python main.py
或后台运行:
  nohup python main.py > logs/run.log 2>&1 &
"""

import os
import sys
import logging
import threading
import asyncio

# 确保导入路径正确
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from src.database import init_db
from src.tcp_server import VSCollectorServer
from src.web_app import app as flask_app, init_app

# ===================== 日志配置 =====================
os.makedirs('data', exist_ok=True)
os.makedirs('logs', exist_ok=True)

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, 'INFO'),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.LOG_FILE, encoding='utf-8'),
    ]
)
logger = logging.getLogger('main')


def run_tcp_server():
    """在独立线程中运行TCP服务器"""
    logger.info(f"启动TCP服务器: {config.TCP_HOST}:{config.TCP_PORT}")
    
    server = VSCollectorServer(
        host=config.TCP_HOST,
        port=config.TCP_PORT,
        db_path=config.DATABASE_PATH,
        channel_configs=config.CHANNEL_CONFIG,
        alarm_config=config.ALARM_CONFIG,
    )
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(server.start())
    except Exception as e:
        logger.error(f"TCP服务器异常: {e}", exc_info=True)
    finally:
        loop.close()


def run_web_server():
    """运行Web界面服务器"""
    logger.info(f"启动Web服务器: http://{config.WEB_HOST}:{config.WEB_PORT}")
    init_app(config.DATABASE_PATH, config.CHANNEL_CONFIG)
    flask_app.run(
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


def main():
    logger.info("=" * 60)
    logger.info("VS振弦渗压计采集软件 启动")
    logger.info(f"TCP监听端口: {config.TCP_PORT}")
    logger.info(f"Web界面端口: {config.WEB_PORT}")
    logger.info(f"数据库路径: {config.DATABASE_PATH}")
    logger.info("=" * 60)
    
    # 初始化数据库
    init_db(config.DATABASE_PATH)
    
    # TCP服务器在后台线程运行
    tcp_thread = threading.Thread(target=run_tcp_server, daemon=True, name='TCPServer')
    tcp_thread.start()
    logger.info("TCP采集服务已在后台启动")
    
    # Web服务器在主线程运行 (便于 Ctrl+C 停止)
    try:
        run_web_server()
    except KeyboardInterrupt:
        logger.info("收到停止信号，程序退出")


if __name__ == '__main__':
    main()
