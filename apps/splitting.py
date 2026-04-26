import re
from typing import List


def overlapping_splitting(text: str, chunk_size: int = 800, overlap: int = 100) -> List[str]:
    chunks = []
    sentences = re.split(r'([。！？\!?])', text)
    # 将句号等标点符号重新附着到前面的句子上
    sentences = [sentences[i] + (sentences[i+1] if i+1 < len(sentences) else '') for i in range(0, len(sentences), 2)]

    current_chunk = ""
    for sentence in sentences:
        if len(current_chunk + sentence) <= chunk_size:
            current_chunk += sentence
        else:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            # 新块从当前句子开始，但要考虑重叠
            # 这里简化处理，直接开始新块
            # 更复杂的重叠策略可以在这里实现
            current_chunk = sentence
            # 如果当前句子本身就超过了 chunk_size，需要更精细的处理
            if len(current_chunk) > chunk_size:
                 # 按字符硬切（最后手段）
                 temp_chunks = [current_chunk[i:i+chunk_size-overlap] for i in range(0, len(current_chunk), chunk_size-overlap)]
                 if temp_chunks and len(temp_chunks[-1]) < overlap and len(chunks) > 0: # 如果最后一个块太短，合并到上一个
                     chunks[-1] += temp_chunks.pop()
                 chunks.extend(temp_chunks)
                 current_chunk = "" # 当前句子已被完全处理

    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    return chunks