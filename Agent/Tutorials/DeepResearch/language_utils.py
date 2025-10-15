from langdetect import detect

def detect_language(text):
    """
    检测文本语言，支持英文和中文
    
    参数:
    text (str): 需要检测语言的文本
    
    返回:
    str: 'en'表示英文，'zh'表示中文，默认返回'en'
    """
    try:
        if detect(str(text)) == 'en':
            return 'en'
        elif detect(str(text)) == 'zh-cn':
            return 'zh'
        else:
            return 'en'
    except:
        return 'en'


if __name__ == '__main__':
    test_text1 = "hello，this a English text"
    test_text2 = "你好，这是一段中文文本"
    print(detect_language(test_text1))
    print(detect_language(test_text2))