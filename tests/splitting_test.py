from apps.model_action.qwen_embedding import get_embedding
from apps.splitting import overlapping_splitting


def test_overlapping_splitting():
    """
    测试文本重叠拆分效果
    """
    text = '''xxxxxxxxx'''
    print(f"text文本长度：{len(text)}")
    chunks = overlapping_splitting(text, 150)   #100个字符拆分一个片段，重叠25个字符拆分
    for chunk in chunks:
        pass
        #print(f"片段-----------------------------------：{chunk}; 字符长度-----------------------------：{len(chunk)}")
        #get_embedding(chunk)


def splitting_a():
    pass

def test_splitting_a():
    #from langchain.document_loaders import PyPDFLoader
    #from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.document_loaders import PyPDFLoader

    # Use the PyPDFLoader to load and parse the PDF
    loader = PyPDFLoader("D:/pyproject/tender-similarity-check/document/xxxxxxxxxxxxxxxxxxx.pdf")
    pages = loader.load_and_split()
    print(f'Loaded {len(pages)} pages from the PDF')

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size = 2000,
        chunk_overlap  = 100,
        length_function = len,
        add_start_index = True,
    )

    documents = text_splitter.split_documents(pages)
    print(f'Split the pages in {len(documents)} chunks')
    for index, document in enumerate(documents):
        print(f"[{index}-----------------------------------------{document.page_content}]\n")

