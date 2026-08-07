from apps import AppContext


def _get_minio_client():
    """获取MinIO客户端实例（延迟加载，避免循环导入）"""
    return AppContext().minio_client


def _get_minio_config():
    """获取MinIO配置（延迟加载，避免循环导入）"""
    return AppContext().minio_config


def get_file_url(file_path: str):
    """
    获取文件网络链接url
    :param file_path: 文件在minio的路径
    :return:
    """
    app_context = AppContext()
    url = f"https://xxxxxxx:30021/{app_context.minio_config['bucket_name']}/{file_path}"
    return "http://192.168.31.141:8000/document/扫描件建筑领域知识问答场景建设技术标.pdf"
    # return url


def get_file_url_http(file_path: str):
    """
    获取文件网络链接url
    :param file_path: 文件在minio的路径
    :return:
    """
    app_context = AppContext()
    # url = f"http://xxxxxxxx:30009/{app_context.minio_config['bucket_name']}/{file_path}"
    return "http://192.168.31.141:8000/document/扫描件建筑领域知识问答场景建设技术标.pdf"


def delete_object(file_path: str):
    """
    上传路径数据
    :param file_path:
    :return:
    """
    app_context = AppContext()
    app_context.minio_client.remove_object(app_context.minio_config['bucket_name'], file_path)


def get_object_bytes(file_path: str):
    """
    获取文件字节流
    :param file_path: 文件在minio的路径
    :return: 文件的字节内容
    """
    app_context = AppContext()
    response = app_context.minio_client.get_object(app_context.minio_config['bucket_name'], file_path)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()
