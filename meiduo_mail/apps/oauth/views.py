from django.shortcuts import render, redirect
from django.views import View
from QQLoginTool.QQtool import OAuthQQ
from django.conf import settings
from django import http
import logging
from django.contrib.auth import login
import re
from django_redis import get_redis_connection

from meiduo_mail.utils.response_code import RETCODE
from .models import OAuthQQUser
from user.models import User
from .utils import generate_openid_signature, check_openid_signature
from carts.utils import merge_cart_cookie_to_redis


logger = logging.getLogger('django')


class OAuthURLView(View):

    def get(self, request):
        # 获取查询参数中的next参数'提取来源'
        next = request.GET.get('next', '/')

        # 创建OAuthQQ 对象
        # oauth = OAuthQQ(
        #     client_id='appid',
        #     client_secret='app key',
        #     redirect_uri='登录成功后的回调url',
        #     state='记录界面跳转来源'
        # )
        # QQ_CLIENT_ID = '101518219'
        # QQ_CLIENT_SECRET = '418d84ebdc7241efb79536886ae95224'
        # QQ_REDIRECT_URI = 'http://www.meiduo.site:8000/oauth_callback'
        oauth = OAuthQQ(
            client_id=settings.QQ_CLIENT_ID,
            client_secret=settings.QQ_CLIENT_SECRET,
            redirect_uri=settings.QQ_REDIRECT_URI,
            state=next
        )

        # 调用SDK中 get_qq_url方法得到拼接好的qq登录url
        login_url = oauth.get_qq_url()
        # print(login_url)
        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'login_url': login_url})

        # https://graph.qq.com/oauth2.0/authorize + ? + response_type='code'&client_id=xxxx&


class OAuthUserView(View):
    """QQ认证回调处理"""

    def get(self, request):

        # 获取查询参数中的code
        code = request.GET.get('code')

        # 判断code是否获取到了
        if code is None:
            return http.HttpResponseForbidden('缺少code')

        # 创建OAuthQQ 对象
        oauth = OAuthQQ(
            client_id=settings.QQ_CLIENT_ID,
            client_secret=settings.QQ_CLIENT_SECRET,
            redirect_uri=settings.QQ_REDIRECT_URI,
        )
        try:
            # 通过code获取access_token
            access_token = oauth.get_access_token(code)
            # 通过access_token获取openid
            openid = oauth.get_open_id(access_token)
        except Exception as er:
            logger.error(er)
            return http.HttpResponseServerError('QQ登录失败')

        try:
            # 向数据库中查询openid
            oauth_model = OAuthQQUser.objects.get(openid=openid)
        except OAuthQQUser.DoesNotExist:
            # 如果查询不到openid说明未绑定用户,把openid和美多用户绑定

            # 包装模板要进行渲染的数据
            context = {
                'openid': generate_openid_signature(openid)  # openid是敏感数据,需要加密处理
            }

            return render(request, 'oauth_callback.html', context)


        else:
            # 如果查询到了openid说明是已绑定用户, 直接代表登录成功
            user = oauth_model.user  # 利用外键获取user
            login(request, user)
            response = redirect(request.GET.get('state') or '/')
            response.set_cookie('username', user.username, max_age=settings.SESSION_COOKIE_AGE)
            # 合并
            merge_cart_cookie_to_redis(request, response)
            return response

    def post(self, request):
        # 接收请体的表单数据 POST
        query_dict = request.POST
        mobile = query_dict.get('mobile')
        password = query_dict.get('password')
        sms_code_client = query_dict.get('sms_code')
        openid = query_dict.get('openid')
        # 校验
        if all([mobile, password, sms_code_client, openid]) is False:
            return http.HttpResponseForbidden('缺少必须参数')

        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return http.HttpResponseForbidden('请输入正确的手机号码')
        if not re.match(r'^[0-9A-Za-z]{8,20}$', password):
            return http.HttpResponseForbidden('请输入8-20位的密码')

        # 短信验证码校验后期补充
        # 创建redis连接对象
        redis_conn = get_redis_connection('verify_code')
        # 获取短信验证码
        sms_code_server = redis_conn.get('sms_code_%s' % mobile)
        # 让短信验证码只能用一次
        redis_conn.delete('sms_code_%s' % mobile)
        # 判断是否过期
        if sms_code_server is None:
            return http.HttpResponseForbidden('短信验证码过期')
        # 判断用户短信验证码是否输入正确
        if sms_code_client != sms_code_server.decode():
            return http.HttpResponseForbidden('短信验证码输入错误')

        try:
            # 利用手机号查询user表,如果查询到用户,说明是老用户
            user = User.objects.get(mobile=mobile)
            # 如果是老用户,再校验一个密码是否能对上
            if user.check_password(password) is False:
                return render(request, 'oauth_callback.html', {'account_errmsg': '用户名或密码错误'})
        except User.DoesNotExist:
            # 如果使用手机号查询不到user,说明是新用户
            # 新用户就create_user 方法创建用户
            user = User.objects.create_user(username=mobile, password=password, mobile=mobile)


        # 对openid进行解密
        openid = check_openid_signature(openid)
        if openid is None:
            return http.HttpResponseForbidden('openid无效')

        # 新老用户绑定openid
        OAuthQQUser.objects.create(
            user=user,
            # user_id=user.id,
            openid=openid,
        )
        # 登录成功后要做的事情
        login(request, user)
        response = redirect(request.GET.get('state') or '/')
        response.set_cookie('username', user.username, max_age=settings.SESSION_COOKIE_AGE)
        # 合并
        merge_cart_cookie_to_redis(request, response)
        return response


