import re


def clear_md_image(text: str)->str:
    """
    处理![](images/5845b356b1c2507d8e559ae0022c8a9d06b8685e4236726e938b9b1562bbf5ea.jpg)或者![描述](url.png)格式
    :param text: 待处理文本
    :return:
    """
    # 定义正则
    pattern = r"!\[.*?\]\(.*?\)"

    # 替换为空字符串（移除）
    clean_text = re.sub(pattern, "", text)
    return clean_text


def clear_md_table(text: str)->str:
    """
    处理md格式内的table
    :param text:
    :return:
    """
    # 正则表达式
    pattern = r"<table\b[^>]*>[\s\S]*?</table>"
    clean_text = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)
    return clean_text
