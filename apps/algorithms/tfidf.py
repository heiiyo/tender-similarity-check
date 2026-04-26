import jieba
import string


def preprocess_chinese(text):
    text = text.replace(" ", "")
    # 中文分词
    words = jieba.lcut(text)
    # 去除标点和停用词
    stop_words = set([line.strip() for line in open('chinese_stopwords.txt', 'r', encoding='utf-8')])
    filtered_words = [word for word in words if word not in stop_words and word not in string.punctuation]
    return filtered_words


def find_duplicate_words(doc1, doc2):
    words1 = set(preprocess_chinese(doc1))
    words2 = set(preprocess_chinese(doc2))
    return words1.intersection(words2)


def calculate_duplicate_ratio(doc1, doc2):
    words1 = set(preprocess_chinese(doc1))
    words2 = set(preprocess_chinese(doc2))
    duplicates = words1.intersection(words2)
    total_unique = len(words1.union(words2))
    duplicate_count = len(duplicates)
    duplicate_ratio = duplicate_count / total_unique if total_unique > 0 else 0
    return duplicates, duplicate_count, duplicate_ratio




if __name__ == "__main__":
    doc1="进行系统调试的权利；在 项目实施期间，甲方有配合我公司实施的义务，我公司提出的人员配合、资源供给方面 的合理要求，甲方应根据自身条件尽可能满足。 我公司权利和义务：我公司有要求甲方配合项目实施提供必要人力、资源方面支持 "
    doc2="间内进行系统调试的 权利；在项目实施期间，甲方有配合我方实施的义务，我方提出的人员配合、资 源供给方面的合理要求，甲方应根据自身条件尽可能满足。 我方权利和义务：我方有要求甲方配合项目实施提供必要人力、资源方面支 "
    duplicates, duplicate_count,  duplicate_ratio = calculate_duplicate_ratio(doc1, doc2)
    print(f"重复词:{duplicates}; 重复词的数量：{duplicate_count}； 重复率：{duplicate_ratio}")

