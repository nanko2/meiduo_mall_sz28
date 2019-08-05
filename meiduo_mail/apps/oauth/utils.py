from itsdangerous import TimedJSONWebSignatureSerializer as Serializer, BadData
from django.conf import settings


def generate_openid_signature(openid):
    """对openid数据进行加密"""
    # 创建加密实例对象
    serializer = Serializer(settings.SECRET_KEY, 600)
    # 包装一个字典,进它进行加密 返回bytes
    data = {'openid': openid}
    openid_sign_bytes = serializer.dumps(data)
    # 返回加密数据
    return openid_sign_bytes.decode()


def check_openid_signature(openid_sign):
    """对openid进行解密"""
    # 创建加密实例对象
    serializer = Serializer(settings.SECRET_KEY, 600)
    # 调用loads方法解密
    try:
        data = serializer.loads(openid_sign)
        return data.get('openid')  # 从字典中取出openid返回
    except BadData:
        return None
