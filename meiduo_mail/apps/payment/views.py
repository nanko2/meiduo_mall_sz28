from django.shortcuts import render
from alipay import AliPay
from django import http
from django.conf import settings
import os

from meiduo_mail.utils.views import LoginRequiredView
from orders.models import OrderInfo
from meiduo_mail.utils.response_code import RETCODE
from .models import Payment


class PaymentView(LoginRequiredView):
    """发起支付"""

    def get(self, request, order_id):
        # 校验
        try:
            order = OrderInfo.objects.get(order_id=order_id, user=request.user,
                                          status=OrderInfo.ORDER_STATUS_ENUM['UNPAID'])
        except OrderInfo.DoesNotExist:
            return http.HttpResponseForbidden('订单有误')

        # 支付宝
        """
        ALIPAY_APPID = '2016091900551154'
        ALIPAY_DEBUG = True  # 表示是沙箱环境还是真实支付环境
        ALIPAY_URL = 'https://openapi.alipaydev.com/gateway.do'
        ALIPAY_RETURN_URL = 'http://www.meiduo.site:8000/payment/status/'
        """
        # 创建支付宝sdk实例对象
        alipay = AliPay(
            appid=settings.ALIPAY_APPID,
            app_notify_url=None,  # 默认回调url
            # /Users/chao/Desktop/meiduo_28/meiduo_mall/meiduo_mall/apps/payment/keys/app_private_key.pem
            app_private_key_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keys/app_private_key.pem'),
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            alipay_public_key_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keys/alipay_public_key.pem'),
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=settings.ALIPAY_DEBUG  # 默认False
        )

        # 调用sdk中 api_alipay_trade_page_pay 得到支付宝登录url后面的查询参数部分
        # 电脑网站支付，需要跳转到https://openapi.alipay.com/gateway.do? + order_string
        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_id,  # 美多订单编号
            total_amount=str(order.total_amount),
            subject='美多商城:%s' % order_id,
            return_url=settings.ALIPAY_RETURN_URL  # 支付成功后的回调url

        )

        # 拼接支付宝登录url
        # 如果是沙箱环境: https://openapi.alipaydev.com/gateway.do? + order_string
        # 真实支付宝环境: https://openapi.alipay.com/gateway.do? + order_string
        alipay_url = settings.ALIPAY_URL + '?' + order_string
        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'alipay_url': alipay_url})


class PaymentStatusView(LoginRequiredView):
    """验证支付结果"""
    def get(self, request):

        # 获取查询参数
        query_dict = request.GET

        # 将查询参数QueryDict转换成字典
        data = query_dict.dict()

        # 将参数中的sign移除
        sign = data.pop('sign')

        # 创建aliapy对象
        alipay = AliPay(
            appid=settings.ALIPAY_APPID,
            app_notify_url=None,  # 默认回调url
            # /Users/chao/Desktop/meiduo_28/meiduo_mall/meiduo_mall/apps/payment/keys/app_private_key.pem
            app_private_key_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keys/app_private_key.pem'),
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            alipay_public_key_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                'keys/alipay_public_key.pem'),
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=settings.ALIPAY_DEBUG  # 默认False
        )
        # 调用verify方法进行校验支付结果
        success = alipay.verify(data, sign)
        if success:
            # 如果支付结果没有问题
            order_id = data.get('out_trade_no')  # 获取美多订单编号
            trade_id = data.get('trade_no')  # 支付宝交易号

            try:
                Payment.objects.get(trade_id=trade_id)
            except Payment.DoesNotExist:
                # 保存支付结果
                payment = Payment.objects.create(
                    order_id=order_id,
                    trade_id=trade_id
                )
            # 修改支付成功的订单状态
            OrderInfo.objects.filter(order_id=order_id, status=OrderInfo.ORDER_STATUS_ENUM['UNPAID']).update(status=OrderInfo.ORDER_STATUS_ENUM['UNCOMMENT'])
            # 响应
            return render(request, 'pay_success.html', {'trade_id': trade_id})
        else:
            # 非法请求
            return http.HttpResponseBadRequest('非法请求')


