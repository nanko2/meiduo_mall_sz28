from django.shortcuts import render
from django_redis import get_redis_connection
from decimal import Decimal
import json
from django import http
from django.utils import timezone
from django.db import transaction

from meiduo_mail.utils.views import LoginRequiredView
from user.models import Address
from goods.models import SKU
from .models import OrderInfo, OrderGoods
from meiduo_mail.utils.response_code import RETCODE
import logging

logger = logging.getLogger('django')

class OrderSettlementView(LoginRequiredView):
    """去结算"""

    def get(self, request):
        user = request.user
        # 查询当前登录用户的所有未被逻辑删除的收货地址
        addresses = Address.objects.filter(user=user, is_deleted=False)
        # user.addresses.filter(is_deleted=False)
        # addresses.exists()

        # 创建redis连接对象
        redis_conn = get_redis_connection('carts')
        # 获取hash数据 {16: 1, 15: 1}
        redis_carts = redis_conn.hgetall('carts_%s' % user.id)
        # 获取set数据 {16, 15}
        selected_ids = redis_conn.smembers('selected_%s' % user.id)
        cart_dict = {}
        # 对hash数据进行过滤只要那些勾选商品的id和count
        for sku_id_bytes in selected_ids:
            cart_dict[int(sku_id_bytes)] = int(redis_carts[sku_id_bytes])

        # 通过sku_id查询到所有sku模型
        skus = SKU.objects.filter(id__in=cart_dict.keys())
        # 定义两个变量一个是商品总数量,一个总价
        total_count = 0
        total_amount = 0
        # 遍历sku查询 模型给每个sku模型多定义一个count和amount属性
        for sku in skus:
            sku.count = cart_dict[sku.id]
            sku.amount = sku.price * sku.count

            total_count += sku.count
            total_amount += sku.amount

        freight = Decimal('10.00')  # 运费
        # 包装模板要进行渲染的数据
        context = {
            'addresses': addresses,  # 收货地址
            'skus': skus,  # 所有勾选的商品
            'total_count': total_count,  # 商品总数量
            'total_amount': total_amount,  # 商品总价
            'freight': freight,  # 运费
            'payment_amount': total_amount + freight,  # 实付总金额
        }
        return render(request, 'place_order.html', context)


class OrderCommitView(LoginRequiredView):
    """提交订单"""

    def post(self, request):

        # 1.接收请求体数据
        json_dict = json.loads(request.body.decode())
        address_id = json_dict.get('address_id')
        pay_method = json_dict.get('pay_method')
        user = request.user
        # 2.校验
        if all([address_id, pay_method]) is False:
            return http.HttpResponseForbidden('缺少必传参数')
        try:
            address = Address.objects.get(id=address_id, user=user, is_deleted=False)
        except Address.DoesNotExist:
            return http.HttpResponseForbidden('address_id无效')

        if pay_method not in [OrderInfo.PAY_METHODS_ENUM['CASH'], OrderInfo.PAY_METHODS_ENUM['ALIPAY']]:
            return http.HttpResponseForbidden('参数有误')

        # 生成订单编号:  2019071912212   + 000000001
        order_id = timezone.now().strftime('%Y%m%d%H%M%S') + '%09d' % user.id

        # 判断订单状态
        status = (OrderInfo.ORDER_STATUS_ENUM['UNPAID']
                  if (pay_method == OrderInfo.PAY_METHODS_ENUM['ALIPAY'])
                  else OrderInfo.ORDER_STATUS_ENUM['UNSEND'])

        # 手动开启事务
        with transaction.atomic():

            # 创建事务保存点
            save_point1 = transaction.savepoint()
            try:
                # 一. 新增订单基本信息记录
                order = OrderInfo.objects.create(
                    order_id=order_id,
                    user=user,
                    address=address,
                    total_count=0,
                    total_amount=Decimal('0.00'),
                    freight=Decimal('10.00'),
                    pay_method=pay_method,
                    status=status
                )
                # 创建redis连接
                redis_conn = get_redis_connection('carts')
                # 获取hash数据
                redis_carts = redis_conn.hgetall('carts_%s' % user.id)
                # 获取set数据
                selected_ids = redis_conn.smembers('selected_%s' % user.id)
                # 定义字典用来装所有要购买商品id和count
                cart_dict = {}  # {1: 1, 2: 1, }
                # 对redis 中hash购物车数据进行过滤,只要勾选的数据
                for sku_id_bytes in selected_ids:
                    cart_dict[int(sku_id_bytes)] = int(redis_carts[sku_id_bytes])
                # 遍历要购买商品数据字典
                for sku_id in cart_dict:

                    while True:
                        sku = SKU.objects.get(id=sku_id)
                        # 查询sku模型
                        # 获取当前商品要购买的数量
                        buy_count = cart_dict[sku_id]
                        # 获取当前sku原本的库存
                        origin_stock = sku.stock
                        # 获取当前sku原本销量
                        origin_sales = sku.sales

                        # import time
                        # time.sleep(5)

                        # 判断库存
                        if buy_count > origin_stock:
                            # 如果库存不足对事务中的操作进行回滚
                            transaction.savepoint_rollback(save_point1)
                            return http.JsonResponse({'code': RETCODE.STOCKERR, 'errmsg': '库存不足'})

                        # 二. 修改sku的库存和销量
                        # 计算新的库存
                        new_stock = origin_stock - buy_count
                        # 计算新的销量
                        new_sales = origin_sales + buy_count
                        # 给sku的库存和销量属性重新赋值
                        # sku.stock = new_stock
                        # sku.sales = new_sales
                        # sku.save()
                        result = SKU.objects.filter(id=sku_id, stock=origin_stock).update(stock=new_stock, sales=new_sales)
                        if result == 0:  # 说明本次修改失败
                            continue


                        # 三. 修改spu销量
                        spu = sku.spu
                        spu.sales += buy_count
                        spu.save()

                        # 四. 新增订单中N个商品记录
                        OrderGoods.objects.create(
                            order=order,
                            sku=sku,
                            count=buy_count,
                            price=sku.price
                        )
                        # 累加订单中商品总数量
                        order.total_count += buy_count
                        order.total_amount += (sku.price * buy_count)
                        break  # 当前商品下单成功结束死循环,继续对下一个商品下单
                # 累加运费一定要写在for的外面
                order.total_amount += order.freight
                order.save()
            except Exception as e:
                # try里面出现任务问题,进行暴力回滚
                logger.error(e)
                transaction.savepoint_rollback(save_point1)
                return http.JsonResponse({'code': RETCODE.STOCKERR, 'errmsg': '提交订单失败'})
            else:
                # 提交事务
                transaction.savepoint_commit(save_point1)
        # 清除购物车中已购买过的商品
        pl = redis_conn.pipeline()
        pl.hdel('carts_%s' % user.id, *cart_dict.keys())
        pl.delete('selected_%s' % user.id)
        pl.execute()
        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'order_id': order_id})


class OrderSuccessView(LoginRequiredView):
    """展示订单成功后界面"""

    def get(self, request):
        # 获取查询参数
        query_dict = request.GET
        payment_amount = query_dict.get('payment_amount')
        order_id = query_dict.get('order_id')
        pay_method = query_dict.get('pay_method')

        # 校验
        try:
            OrderInfo.objects.get(order_id=order_id, total_amount=payment_amount, pay_method=pay_method, user=request.user)
        except OrderInfo.DoesNotExist:
            return http.HttpResponseForbidden('订单有误')

        # 包装要进行渲染的数据
        context = {
            'payment_amount': payment_amount,
            'order_id': order_id,
            'pay_method': pay_method
        }

        return render(request, 'order_success.html', context)
