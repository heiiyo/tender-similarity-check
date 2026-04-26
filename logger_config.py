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


def get_logger(level="INFO", name=__package__):
    # 应用配置
    LOGGING_CONFIG["root"]["level"] = level
    logging.config.dictConfig(LOGGING_CONFIG)
    logger = logging.getLogger(name)
    return logger
