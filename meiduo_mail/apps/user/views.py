from django.shortcuts import render, redirect
from django.views import View
from django import http
import re
from django.contrib.auth import login, authenticate, logout
from django_redis import get_redis_connection
from django.conf import settings
from django.contrib.auth import mixins
import json
from django.db import DatabaseError

from .models import User, Address
from meiduo_mail.utils.response_code import RETCODE
from meiduo_mail.utils.views import LoginRequiredView
from celery_tasks.email.tasks import send_verify_email
from .utils import generate_verify_email_url, check_verify_email_token
from goods.models import SKU

import logging

from carts.utils import merge_cart_cookie_to_redis

logger = logging.getLogger('django')


class RegisterView(View):
    """注册"""

    def get(self, request):
        """提供注册界面"""
        return render(request, 'register.html')

    def post(self, request):
        """注册逻辑"""

        # 接收请求体表单数据
        query_dict = request.POST
        # 获取 username password password2 mobile sms_code allow
        username = query_dict.get('username')
        password = query_dict.get('password')
        password2 = query_dict.get('password2')
        mobile = query_dict.get('mobile')
        sms_code_client = query_dict.get('sms_code')
        allow = query_dict.get('allow')  # 没有指定复选框中的value时如果勾选 'on',  没勾选None  如果前端指定了value值勾选就传递的是value中的值

        # 校验
        # if all(query_dict.dict().values()):
        # 判断里面可迭代对象中的每个元素是否有为None '', {}, [], False,如果有就返回False
        if all([username, password, password2, mobile, sms_code_client, allow]) is False:
            return http.HttpResponseForbidden('缺少必传参数')

        if not re.match(r'^[a-zA-Z0-9_-]{5,20}$', username):
            return http.HttpResponseForbidden('请输入5-20个字符的用户名')
        if not re.match(r'^[0-9A-Za-z]{8,20}$', password):
            return http.HttpResponseForbidden('请输入8-20位的密码')
        if password != password2:
            return http.HttpResponseForbidden('两次密码输入的不一致')
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return http.HttpResponseForbidden('请输入正确的手机号码')

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

        # 创建一个新用户
        # user = User.objects.create(password=password)
        # user.set_password(password)
        # user.save()
        user = User.objects.create_user(username=username, password=password, mobile=mobile)
        # 状态保持(记录用户登录状态)
        login(request, user)

        response = redirect('/') # redirect 重定向
        response.set_cookie('username', user.username, max_age=settings.SESSION_COOKIE_AGE)
        # 用户注册成功即代表登录成功
        # 响应,重定向到首页
        # return http.HttpResponse('注册成功,跳转到首页')

        return response
        # http://127.0.0.1:8000/register/login/
        # http://127.0.0.1:8000/login/


class UsernameCountView(View):
    """判断用户是否是重复注册"""

    def get(self, request, username):
        # 以username查询user模型,再取它的count, 0:代表用户名没有重复, 1代表用户名重复
        count = User.objects.filter(username=username).count()
        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'count': count})


class MobileCountView(View):
    """判断手机号是否是重复注册"""

    def get(self, request, mobile):
        # 以mobile查询user模型,再取它的count, 0:代表用户名没有重复, 1代表用户名重复
        count = User.objects.filter(mobile=mobile).count()
        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'count': count})


class LoginView(View):
    """用户登录"""

    def get(self, request):
        return render(request, 'login.html')

    """
    多账号登录不推荐版
    def post(self, request):

        # 接收前端传入的表单数据
        query_dict = request.POST
        username = query_dict.get('username')
        password = query_dict.get('password')
        remembered = query_dict.get('remembered')

        # 校验
        # user = User.objects.get(username=username)
        # user.check_password(password)
        # return user
        # 判断用户是否用手机号登录, 如果是的,认证时就用手机号查询
        if re.match(r'^1[3-9]\d{9}$', username):
            User.USERNAME_FIELD = 'mobile'


        # authenticate 用户认证
        user = authenticate(request, username=username, password=password)

        User.USERNAME_FIELD = 'username'  # 再改回去,不然其它用户登录可能会出问题
        # 判断用户是否通过认证
        if user is None:
            return render(request, 'login.html', {'account_errmsg': '用户名或密码错误'})
        # 状态保持
        login(request, user)
        # # 如果用户没有记住登录
        if remembered != 'on':
            request.session.set_expiry(0)  # 把session的过期时间设置为0 表示会话结束后就过期
        # request.session.set_expiry((60 * 60 * 48) if remembered else 0)


        # 重定向到指定页
        return http.HttpResponse('登录成功,来到首页')
    """

    def post(self, request):
        # 接收前端传入的表单数据
        query_dict = request.POST
        username = query_dict.get('username')
        password = query_dict.get('password')
        remembered = query_dict.get('remembered')

        # 校验
        # authenticate 用户认证
        user = authenticate(request, username=username, password=password)

        # 判断用户是否通过认证
        if user is None:
            return render(request, 'login.html', {'account_errmsg': '用户名或密码错误'})
        # 状态保持

        login(request, user)
        # # 如果用户没有记住登录
        if remembered != 'on':
            request.session.set_expiry(0)  # 把session的过期时间设置为0 表示会话结束后就过期
        # /login/?next=/info/
        # /login/
        # 用户如果有来源就重定向到来源,反之就去首页
        response = redirect(request.GET.get('next') or '/')  # 创建重定向响应对象   SESSION_COOKIE_AGE
        # response.set_cookie('username', user.username, max_age=(60 * 60 * 24 * 7 * 2) if remembered else None)
        response.set_cookie('username', user.username, max_age=settings.SESSION_COOKIE_AGE if remembered else None)
        # print(settings.SESSION_COOKIE_AGE)
        # 登录时合并购物车
        merge_cart_cookie_to_redis(request, response)
        # 重定向到指定页
        # return http.HttpResponse('登录成功,来到首页')
        return response


class LogoutView(View):
    """退出登录"""

    def get(self, request):
        # 清除状态操持
        logout(request)

        # 创建响应对象
        response = redirect('/login/')
        # 删除cookie中的username
        response.delete_cookie('username')
        # 重定向到登录界面
        return response


# class InfoView(View):
#     """用户中心"""
#
#     def get(self, request):
#         # if isinstance(request.user, User):
#         if request.user.is_authenticated:  # 如果if 成立说明是登录用户
#             return render(request, 'user_center_info.html')
#         else:
#             return redirect('/login/?next=/info/')


class InfoView(mixins.LoginRequiredMixin, View):
    """用户中心"""

    def get(self, request):
        return render(request, 'user_center_info.html')


class EmailView(LoginRequiredView):
    """设置用户邮箱"""

    def put(self, request):
        # 接收数据
        json_dict = json.loads(request.body.decode())
        email = json_dict.get('email')
        if User.objects.filter(email=email):
            return http.JsonResponse({'code': RETCODE.PARAMERR, 'errmsg': '存在'})
        # 校验
        if email is None:
            return http.HttpResponseForbidden('缺少必传参数')
        if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return http.HttpResponseForbidden('邮件格式不正确')
        # 处理业务逻辑
        user = request.user
        # user.email = email  # 此写法,在当前场景会随着重新发送邮箱时,重复设置邮箱
        # user.save()
        User.objects.filter(id=user.id, email='').update(email=email)  # 邮箱只要设置成功了,此代码都是无效的修改

        # 在此顺带的发一个激活邮件出去
        # from django.core.mail import send_mail
        # send_mail(subject='主题', message='邮件普通正文', from_email='发件人', recipient_list='收件人,必须是列表',
        #       html_message='<a href='xxx'>xdfsfd<a>')
        # verify_url = 'http://www.meiduo.site:8000/emails/verification/?token=3'
        # 生成激活url
        verify_url = generate_verify_email_url(user)
        # celery异步发邮件
        send_verify_email.delay(email, verify_url)
        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})


class VerifyEmailView(View):
    """激活用户邮箱"""

    def get(self, request):
        # 获取查询参数中的token
        token = request.GET.get('token')
        # 校验
        if token is None:
            return http.HttpResponseForbidden('缺少token')
        # 再对token进行解密,解密后根据里面的user_id,和email查询出要激活邮箱的那个User
        user = check_verify_email_token(token)
        if user is None:
            return http.HttpResponseForbidden('token无效')
        # 修改user的email_active字段 设置为True
        user.email_active = True
        user.save()
        # 响应
        return redirect('/info/')
        # return render(request, 'user_center_info.html')


class AddressView(LoginRequiredView):
    """收货地址"""

    def get(self, request):
        user = request.user  # 获取用户
        address_qs = Address.objects.filter(user=user, is_deleted=False)
        address_list = []  # 用来装用户所有收货地址字典
        for address in address_qs:
            # 把新增的address模型对象转换成字典,并响应给前端
            address_dict = {
                'id': address.id,
                'title': address.title,
                'receiver': address.receiver,
                'province_id': address.province_id,
                'province': address.province.name,
                'city_id': address.city_id,
                'city': address.city.name,
                'district_id': address.district_id,
                'district': address.district.name,
                'place': address.place,
                'mobile': address.mobile,
                'tel': address.tel,
                'email': address.email,
            }
            # 添加收货地址字典到列表中
            address_list.append(address_dict)
        # 包装模板要进行渲染的数据
        context = {
            'addresses': address_list,  # 当前登录用户的所有收货地址 [{}, {}]
            'default_address_id': user.default_address_id  # 当前用户默认收货地址id
        }
        return render(request, 'user_center_site.html', context)  # 渲染模板必须传前面Context的里面数据


class CreateAddressView(LoginRequiredView):
    """收货地址新增"""

    def post(self, request):

        # 判断用户收货地址上限 不能多于20个
        user = request.user
        # 查询当前登录用户未逻辑删除的收货地址数量
        count = Address.objects.filter(user=user, is_deleted=False).count()
        # user.addresses.filter(is_deleted=False).count()
        if count >= 20:
            return http.JsonResponse({'code': RETCODE.MAXNUM, 'errmsg': '收货地址超限'})

        # 接收请求体数据
        json_dict = json.loads(request.body.decode())
        title = json_dict.get('title')
        receiver = json_dict.get('receiver')
        province_id = json_dict.get('province_id')
        city_id = json_dict.get('city_id')
        district_id = json_dict.get('district_id')
        place = json_dict.get('place')
        mobile = json_dict.get('mobile')
        tel = json_dict.get('tel')
        email = json_dict.get('email')

        # 校验
        if all([title, receiver, province_id, city_id, district_id, place, mobile]) is False:
            return http.HttpResponseForbidden('缺少必传参数')

        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return http.HttpResponseForbidden('参数mobile有误')
        if tel:
            if not re.match(r'^(0[0-9]{2,3}-)?([2-9][0-9]{6,7})+(-[0-9]{1,4})?$', tel):
                return http.HttpResponseForbidden('参数tel有误')
        if email:
            if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
                return http.HttpResponseForbidden('参数email有误')

        # try:
        #     Area.objects.get(id=province_id)

        # 新增
        try:
            address = Address.objects.create(
                user=user,
                title=title,
                receiver=receiver,
                province_id=province_id,
                city_id=city_id,
                district_id=district_id,
                place=place,
                mobile=mobile,
                tel=tel,
                email=email
            )
        except DatabaseError as e:
            logger.error(e)
            return http.HttpResponseForbidden('添加收货地址失败')

        # 如果用户还没有默认收货地址,把当前新增的收货地址设置为用户的默认收货地址
        if user.default_address is None:
            user.default_address = address
            user.save()
        # 把新增的address模型对象转换成字典,并响应给前端
        address_dict = {
            'id': address.id,
            'title': address.title,
            'receiver': address.receiver,
            'province_id': address.province_id,
            'province': address.province.name,
            'city_id': address.city_id,
            'city': address.city.name,
            'district_id': address.district_id,
            'district': address.district.name,
            'place': address.place,
            'mobile': address.mobile,
            'tel': address.tel,
            'email': address.email,
        }
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '添加收货地址成功', 'address': address_dict})


class UpdateDestroyAddressView(LoginRequiredView):
    """修改和删除收货地址"""

    def put(self, request, address_id):
        """修改收货地址逻辑"""
        # 对address_id进行校验
        try:
            address = Address.objects.get(id=address_id, user=request.user, is_deleted=False)
        except Address.DoesNotExist:
            return http.HttpResponseForbidden('修改收货地址失败')

        # 接收请求体数据
        json_dict = json.loads(request.body.decode())   # json.loads()函数是将字符串转化为字典
        title = json_dict.get('title')
        receiver = json_dict.get('receiver')
        province_id = json_dict.get('province_id')
        city_id = json_dict.get('city_id')
        district_id = json_dict.get('district_id')
        place = json_dict.get('place')
        mobile = json_dict.get('mobile')
        tel = json_dict.get('tel')
        email = json_dict.get('email')

        # 校验
        if all([title, receiver, province_id, city_id, district_id, place, mobile]) is False:
            return http.HttpResponseForbidden('缺少必传参数')

        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return http.HttpResponseForbidden('参数mobile有误')
        if tel:
            if not re.match(r'^(0[0-9]{2,3}-)?([2-9][0-9]{6,7})+(-[0-9]{1,4})?$', tel):
                return http.HttpResponseForbidden('参数tel有误')
        if email:
            if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
                return http.HttpResponseForbidden('参数email有误')

        # 修改
        try:
            # Address.objects.filter(id=address_id).update(
            #     title=title,
            #     receiver=receiver,
            #     province_id=province_id,
            #     city_id=city_id,
            #     district_id=district_id,
            #     place=place,
            #     mobile=mobile,
            #     tel=tel,
            #     email=email
            # )

            address.title = title
            address.receiver = receiver
            address.province_id = province_id
            address.city_id = city_id
            address.district_id = district_id
            address.place = place
            address.mobile = mobile
            address.tel = tel
            address.email = email
            address.save()
        except DatabaseError as e:
            logger.error(e)
            return http.HttpResponseForbidden('修改收货地址失败')

        # 把新增的address模型对象转换成字典,并响应给前端
        address_dict = {
            'id': address.id,
            'title': address.title,
            'receiver': address.receiver,
            'province_id': address.province_id,
            'province': address.province.name,
            'city_id': address.city_id,
            'city': address.city.name,
            'district_id': address.district_id,
            'district': address.district.name,
            'place': address.place,
            'mobile': address.mobile,
            'tel': address.tel,
            'email': address.email,
        }

        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '修改收货地址成功', 'address': address_dict})

    def delete(self, request, address_id):
        """收货地址删除"""
        try:
            address = Address.objects.get(id=address_id, user=request.user, is_deleted=False)
        except Address.DoesNotExist:
            return http.HttpResponseForbidden('删除收货地址失败')

        address.is_deleted = True  # 逻辑删除
        address.save()

        # address.delete()  # 物理删除

        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})


class DefaultAddressView(LoginRequiredView):
    """设置用户默认收货地址"""

    def put(self, request, address_id):

        try:
            address = Address.objects.get(id=address_id, user=request.user, is_deleted=False)
        except Address.DoesNotExist:
            return http.HttpResponseForbidden('设置默认收货地址失败')

        request.user.default_address = address  # 给用户的默认收货地址字段重新赋值
        request.user.save()

        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})


class UpdateTitleAddressView(LoginRequiredView):
    """修改收货地址标题"""

    def put(self, request, address_id):

        try:
            address = Address.objects.get(id=address_id, user=request.user, is_deleted=False)
        except Address.DoesNotExist:
            return http.HttpResponseForbidden('设置默认收货地址失败')

        json_dict = json.loads(request.body.decode())
        title = json_dict.get('title')

        if title is None:
            return http.HttpResponseForbidden('缺少必传参数')

        # 修改当前收货地址的标题
        address.title = title
        address.save()

        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})


class ChangePasswordView(LoginRequiredView):
    """修改用户登录密码"""

    def get(self, request):
        return render(request, 'user_center_pass.html')

    def post(self, request):
        # 接收表单数据
        query_dict = request.POST
        old_pwd = query_dict.get('old_pwd')
        new_pwd = query_dict.get('new_pwd')
        new_cpwd = query_dict.get('new_cpwd')

        user = request.user
        # 校验
        if all([old_pwd, new_cpwd, new_pwd]) is False:
            return http.HttpResponseForbidden('缺少必传参数')

        if user.check_password(old_pwd) is False:
            return render(request, 'user_center_pass.html', {'origin_pwd_errmsg': '原始密码不正确'})

        if not re.match(r'^[0-9A-Za-z]{8,20}$', new_pwd):
            return http.HttpResponseForbidden('请输入8-20位长度的密码')
        if new_pwd != new_cpwd:
            return http.HttpResponseForbidden('两次密码输入的不一致')

        # 修改用户密码
        user.set_password(new_pwd)  # 重置密码时,会自动清除状态保持
        user.save()

        # 重定向到login
        return redirect('/logout/')


class HistoryGoodsView(View):
    """商品浏览记录"""

    def post(self, request):
        """保存商品浏览记录"""
        # 判断用户是否登录
        if not request.user.is_authenticated:
            return http.JsonResponse({'code': RETCODE.SESSIONERR, 'errmsg': '用户未登录'})

        # 获取请求体中的sku_id
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')
        # 校验
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return http.HttpResponseForbidden('sku_id无效')

        # 创建redis连接对象
        redis_conn = get_redis_connection('history')
        # 创建管道
        pl = redis_conn.pipeline()

        # 存储每个用户redis的唯一key
        key = 'history_%s' % request.user.id
        # 先去重
        pl.lrem(key, 0, sku_id)

        # 添加到列表的开头
        pl.lpush(key, sku_id)

        # 保留列表中前五个元素
        pl.ltrim(key, 0, 4)
        # 执行管道
        pl.execute()
        # sku_id_list [4, 2, 6, 1]
        # SKU.objects.filter(id__in=sku_id_list)
        # [1, 2, 4, 6]

        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})

    def get(self, request):
        """获取用户商品浏览记录"""
        # 判断用户是否登录
        if not request.user.is_authenticated:
            return http.JsonResponse({'code': RETCODE.SESSIONERR, 'errmsg': '用户未登录'})

        # 创建redis连接对象
        redis_conn = get_redis_connection('history')
        # 存储每个用户redis的唯一key
        key = 'history_%s' % request.user.id
        # 获取当前用户的浏览记录数据 [b'2', 1, 3, 5]
        sku_id_list = redis_conn.lrange(key, 0, -1)
        # 定义一个列表,用来装sku字典数据
        sku_list = []  # 2, 1, 3, 5
        # 遍历sku_id列表,有顺序的一个一个去获取sku模型并转换成字典
        for sku_id in sku_id_list:
            sku = SKU.objects.get(id=sku_id)
            sku_list.append({
                'id': sku.id,
                'name': sku.name,
                'price': sku.price,
                'default_image_url': sku.default_image.url
            })

        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'skus': sku_list})
