from django.contrib.auth.backends import ModelBackend
import re
from django.conf import settings
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer, BadData

from .models import User


def get_user_by_account(account):
    """传入用户名或手机号来查询对应的user"""
    try:
        # 判断账号是用户名还是手机号
        if re.match(r'^1[3-9]\d{9}$', account):
            # 如果是手机号就用mobile去查询用户
            user = User.objects.get(mobile=account)
        else:
            # 如果不是手机号就用username 查询用户
            user = User.objects.get(username=account)
    except User.DoesNotExist:
        return None
    else:
        return user


class UsernameMobileAuthBackend(ModelBackend):
    """自定义认证类 目的:实现多账号登录"""

    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        try:
            # 判断账号是用户名还是手机号
            if re.match(r'^1[3-9]\d{9}$', username):
                # 如果是手机号就用mobile去查询用户
                user = User.objects.get(mobile=username)
            else:
                # 如果不是手机号就用username 查询用户
                user = User.objects.get(username=username)
        except User.DoesNotExist:
            return None
        """
        user = get_user_by_account(username)

        # 判断用户的密码是否正确
        if user and user.check_password(password):
            # 把user对象返回
            return user


def generate_verify_email_url(user):
    """生成用户激活邮箱url"""
    serializer = Serializer(settings.SECRET_KEY, 3600 * 24)
    data = {'user_id': user.id, 'email': user.email}
    token = serializer.dumps(data).decode()
    # 拼接激活url   'http://www.meiduo.site:8000/emails/verification/' + '?token=' + 'xxxxdfsajadsfljdlskaj'
    verify_url = settings.EMAIL_VERIFY_URL + '?token=' + token
    return verify_url


def check_verify_email_token(token):
    """传入token解密后查询用户"""
    serializer = Serializer(settings.SECRET_KEY, 3600 * 24)
    try:
        data = serializer.loads(token)
        user_id = data.get('user_id')
        email = data.get('email')
        try:
            user = User.objects.get(id=user_id, email=email)
            return user
        except User.DoesNotExist:
            return None
    except BadData:
        return None