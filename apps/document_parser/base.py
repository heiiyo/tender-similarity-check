from typing import Union


class HFiledocument:
    def __init__(self, file_id, page, page_content):
        self.file_id = file_id
        self.page = page
        self.page_content = page_content
        self.next: HFiledocument = None

    def __iter__(self):
        # 返回一个新的迭代器对象（不是自己！）
        return HFileDocumentIterator(self)

    # ✅ 新增：支持 obj[index] 的索引操作
    def __getitem__(self, index: Union[int, slice]):
        if isinstance(index, slice):
            # 支持切片，例如 doc[1:3] -> 返回一个新列表
            return [node for i, node in enumerate(self) if index.start <= i < index.stop or index.stop is None]

        # 处理负数索引（如 doc[-1]）
        if index < 0:
            try:
                return [node for node in self][index]
            except IndexError:
                raise IndexError("Index out of range")

        # 正数索引遍历
        current = self
        count = 0
        while current:
            if count == index:
                return current
            current = current.next
            count += 1

        raise IndexError(f"Index {index} out of range")


class HFileDocumentIterator:
    def __init__(self, start_node):
        self.current = start_node  # 当前节点指针

    def __iter__(self):
        return self

    def __next__(self):
        if self.current is None:
            raise StopIteration  # ✅ 关键：结束迭代
        node = self.current      # 保存当前节点
        self.current = self.current.next  # 移动到下一个
        return node              # 返回当前节点（不是 next！）


class HDocument:
    def __init__(self, file_id, page, start_index, text, topic=""):
        self.file_id = file_id
        self.page = page
        self.start_index = start_index
        self.text: str = text
        self.topic = topic
