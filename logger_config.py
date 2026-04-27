import logging
import logging.config

from pathlib import Path

# 获取当前文件的绝对路径
current_file_path = Path(__file__).resolve()

# 获取当前文件所在的目录路径 (通常最常用)
current_dir = current_file_path.parent

logging_dir = f"{current_dir}/logs"

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
        'error': {
            'format': '%(asctime)s [ERROR] %(pathname)s:%(lineno)d - %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'formatter': 'default',
        },
        'file_info': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'INFO',
            'formatter': 'default',
            'filename': f'{logging_dir}/info.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'encoding': 'utf-8',
        },
        'file_error': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'ERROR',
            'formatter': 'error',
            'filename': f'{logging_dir}/error.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'encoding': 'utf-8',
        }
    },
    'root': {
        'level': 'DEBUG',
        'handlers': ['console', 'file_info', 'file_error']
    }
}

# --- 3. 初始化函数 (全局只调用一次) ---
def setup_logging(level="INFO"):
    """
    在项目启动入口（如 main.py）调用此函数，仅执行一次。
    """
    # 获取 SQLAlchemy 的核心引擎 Logger
    sqla_logger = logging.getLogger("sqlalchemy.engine")

    # 关键设置：禁止冒泡
    # 这样 SQLAlchemy 的日志就不会传递给根 Logger，从而避免被你的全局配置再次处理
    sqla_logger.propagate = False
    LOGGING_CONFIG['root']['level'] = level
    logging.config.dictConfig(LOGGING_CONFIG)
    print(f"✅ 日志系统已初始化，级别: {level}")


def get_logger(name=__package__):
    logger = logging.getLogger(name)
    return logger
