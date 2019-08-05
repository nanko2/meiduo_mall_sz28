from random import randint

from django.views import View
from django_redis import get_redis_connection
from django import http

from meiduo_mail.libs.captcha.captcha import captcha
from meiduo_mail.utils.response_code import RETCODE
from celery_tasks.sms.yuntongxun.sms import CCP
from . import constants
from celery_tasks.sms.tasks import send_sms_code

import logging
logger = logging.getLogger('django')


class ImageCodeView(View):
    """图形验证码"""

    def get(self,request,uuid):

        # 使用SDK 生成图形验证码
        # name: 唯一标识
        # text： 图形验证码中的字符内容
        # image_bytes：图片bytes类型数据
        name, text, image_bytes = captcha.generate_captcha()

        # 创建redis连接对象
        redis_conn = get_redis_connection('verify_code')
        # 把图形验证码字符内容存储到redis中
        redis_conn.setex(uuid, 300, text)
        # 响应
        return http.HttpResponse(image_bytes, content_type='image/png' )


class SNSCodeView(View):
    """发送短信验证码"""
    # this.host + '/sms_codes/' + this.mobile + '/?image_code=' + this.image_code + '&uuid=' + this.uuid;
    def get(self, request, mobile):
        # 创建redis连接对象
        redis_conn = get_redis_connection('verify_code')
        # 获取此手机号是否发送过短信标记
        send_flag = redis_conn.get('send_flag_%s' % mobile)

        if send_flag:
            return http.JsonResponse({'code': RETCODE.THROTTLINGERR, 'errmsg': '频繁发送信息'})

        # 接收前端数据
        image_code_client = request.GET.get('image_code')
        uuid = request.GET.get('uuid')

        # 校验
        if all([image_code_client, uuid]) is False:
            return http.HttpResponseForbidden('缺少必传参数')

        # 创建redis连接对象ccp_send_sms_code.delay(mobile, sms_code)
        redis_conn = get_redis_connection('verify_code')
        # 获取redis中图形验证码
        image_code_server = redis_conn.get(uuid)

        # 直接将redis中用过的图形验证码删除(让每个图形验证码都是一次性)
        redis_conn.delete(uuid)

        # 判断图形验证码有没有过期
        if image_code_server is None:
            return http.JsonResponse({'code': RETCODE.IMAGECODEERR, 'errmsg': '图形验证码已过期'})

        # 判断用户输入的图形验证码和redis中之前存储的验证码是否一致
        # 从redis获取出来的数据都是bytes类型
        if image_code_client.lower() != image_code_server.decode().lower():
            return http.JsonResponse({'code': RETCODE.IMAGECODEERR, 'errmsg': '图片验证码输入有误'})

        # 利用第三方容联云发短信
        # 随机生成一个6位数字来当短信验证码
        sms_code = '%06d' % randint(0, 999999)
        logger.info(sms_code)

        # 创建管道对象(管道作用：就是将多次redis指令合并在一起,一并执行)
        pl = redis_conn.pipeline()

        # 把短信验证码存储到redis中以备后期注册时校验
        pl.setex('sms_code_%s' % mobile, constants.SNS_CODE_EXPIRE_REDIS, sms_code)
        # 发送过短信后向redis存储一个此手机号发过短信的标记
        # redis_conn.setex('send_flag_%s' % mobile, 60, 1)
        pl.setex('send_flag_%s' % mobile, 60, 1)

        # 执行管道
        pl.execute()

        # 利用第三方容联云发短信
        # CCP().send_template_sms(mobile, [sns_code, constants.SNS_CODE_EXPIRE_REDIS // 60], 1)
        send_sms_code.delay(mobile, sms_code) # 触发异步任务,将异步任务添加到仓库
        # 响应
        return http.JsonResponse({'code':RETCODE.OK, 'errmsg': 'OK'})


