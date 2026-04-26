from apps import AppContext

app_context = AppContext().init_context()
minio_client = app_context.minio_client


def get_file_url(file_path: str):
    """
    获取文件网络链接url
    :param file_path: 文件在minio的路径
    :return:
    """
    url = f"https://xxxxxxx:30021/{app_context.minio_config['bucket_name']}/{file_path}"
    return url


def get_file_url_http(file_path: str):
    """
    获取文件网络链接url
    :param file_path: 文件在minio的路径
    :return:
    """
    url = f"http://xxxxxxxx:30009/{app_context.minio_config['bucket_name']}/{file_path}"
    return url


def delete_object(file_path: str):
    """
    上传路径数据
    :param file_path:
    :return:
    """
    minio_client.remove_object(app_context.minio_config['bucket_name'], file_path)
