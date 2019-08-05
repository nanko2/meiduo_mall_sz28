from django.shortcuts import render
from django.views import View
import json, pickle, base64
from django import http
from django_redis import get_redis_connection

from goods.models import SKU
from meiduo_mail.utils.response_code import RETCODE
import logging

logger = logging.getLogger('django')


class CartsView(View):
    """购物车"""

    def post(self, request):
        """购物车数据添加"""

        # 1.接收请求体中数据
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')
        count = json_dict.get('count')
        selected = json_dict.get('selected', True)

        # 2.校验
        if all([sku_id, count]) is False:
            return http.HttpResponseForbidden('缺少必传参数')
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return http.HttpResponseForbidden('sku_id不存在')

        try:
            count = int(count)
        except Exception as e:
            logger.error(e)
            return http.HttpResponseForbidden('参数类型有误')

        if isinstance(selected, bool) is False:
            return http.HttpResponseForbidden('参数类型有误')

        # 3.获取当前请求中的user
        user = request.user

        # 3.1 判断当前是否是登录用户
        """
            hash: {sku_id: count, sku_id: count}
            set: {sku_id}
        """
        if user.is_authenticated:
            # 如果是登录用户就把购物车数据添加到redis
            # 创建redis连接对象
            redis_conn = get_redis_connection('carts')

            pl = redis_conn.pipeline()
            # 使用hincrby指令添加hash数据,如果添加的key已存在,会对value做累加操作
            pl.hincrby('carts_%s' % user.id, sku_id, count)
            # 使用sadd 把勾选的商品sku_id添加到set集合中
            if selected:
                pl.sadd('selected_%s' % user.id, sku_id)
            pl.execute()
            # 响应
            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '添加购物车成功'})

        else:
            # 3.2 如果是未登录用户就把购物车数据添加到cookie中
            """
            {
                'sku_id_1': {'count': 2, 'selected': True}
            }
            """
            # 获取cookie购物车数据
            cart_str = request.COOKIES.get('carts')
            # 判断是否获取到cookie购物车数据
            if cart_str:
                # 有cookie购物车数据,就把它从字符串转换到字典
                cart_str_bytes = cart_str.encode()
                cart_bytes = base64.b64decode(cart_str_bytes)
                cart_dict = pickle.loads(cart_bytes)
                # cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
                # 判断本次添加到的商品之前是否已经添加过,如果添加过,就把count进行累加
                if sku_id in cart_dict:
                    # 获取它原有的购买数量
                    origin_count = cart_dict[sku_id]['count']
                    count += origin_count
                    # count = count + origin_count
            else:
                # 没有cookie购物车数据,准备一个空的新字典,为后面添加购物车数据准备
                cart_dict = {}

            # 添加or修改
            cart_dict[sku_id] = {
                'count': count,
                'selected': selected
            }
            # 将购物车数据设置到cookie之前需要先将字典转换成字符串
            cart_str = base64.b64encode(pickle.dumps(cart_dict)).decode()
            # 创建响应对象
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '添加购物车成功'})
            # 设置cookie
            response.set_cookie('carts', cart_str)
            # 响应
            return response

    def get(self, request):
        """购物车数据展示"""
        # 先获取请求对象中的user
        user = request.user

        # 判断用户是否登录
        if user.is_authenticated:
            # 登录用户获取redis购物车数据

            # 创建redis连接对象
            redis_conn = get_redis_connection('carts')
            # 获取hash中的数据 {b'1': b'2, b'2':b'1'}
            redis_carts = redis_conn.hgetall('carts_%s' % user.id)
            # 获取set集合中的数据 {b'1', b'2'}
            selected_ids = redis_conn.smembers('selected_%s' % user.id)
            # 把redis购物车数据格式转换成cookie购物车数据格式
            cart_dict = {}  # 准备一个空字典用来装redis购物车所有数据
            for sku_id_bytes in redis_carts:
                cart_dict[int(sku_id_bytes)] = {
                    'count': int(redis_carts[sku_id_bytes]),
                    'selected': (sku_id_bytes in selected_ids)
                }


        else:
            # 未登录用户获取cookie购物车数据
            cart_str = request.COOKIES.get('carts')
            if cart_str:
                # 有cookie购物车数据就将它从字符串转字典
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                # 没有cookie购物车数据,就显示一个空白的购物车界面
                return render(request, 'cart.html')

        # 为了sku_id查询sku模型及包装模板需要渲染的数据代码 登录和未登录共用同一个代码
        # 查询sku模型
        sku_qs = SKU.objects.filter(id__in=cart_dict.keys())
        cart_skus = []  # 此列表用来包装前端界面需要渲染的所有购物车商品数据
        for sku in sku_qs:
            # 获取指定商品要购买的数量
            count = cart_dict[sku.id]['count']
            cart_skus.append({
                'id': sku.id,
                'name': sku.name,
                'default_image_url': sku.default_image.url,
                'price': str(sku.price),  # 为了方便js进行解析数据尽量把它转换成str类型
                'count': count,
                'selected': str(cart_dict[sku.id]['selected']),  # 因为js对数据进行转换处理,js中true
                'amount': str(sku.price * count)
            })

        context = {
            'cart_skus': cart_skus
        }
        return render(request, 'cart.html', context)

    def put(self, request):
        """购物车修改"""
        # 1.接收
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')
        count = json_dict.get('count')
        selected = json_dict.get('selected', True)

        # 2.校验
        if all([sku_id, count]) is False:
            return http.HttpResponseForbidden('缺少必传参数')
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return http.HttpResponseForbidden('sku_id不存在')

        try:
            count = int(count)
        except Exception as e:
            logger.error(e)
            return http.HttpResponseForbidden('参数类型有误')

        if isinstance(selected, bool) is False:
            return http.HttpResponseForbidden('参数类型有误')

        # 判断用户是否登录
        user = request.user
        if user.is_authenticated:
            # 登录用户修改redis购物车数据
            # 创建redis连接对象
            redis_conn = get_redis_connection('carts')
            pl = redis_conn.pipeline()
            # 修改hash数据
            pl.hset('carts_%s' % user.id, sku_id, count)
            # 修改set数据
            if selected:
                # 如果要勾选,就把当前sku_id添加到set中
                pl.sadd('selected_%s' % user.id, sku_id)
            else:
                # 不勾选时,把sku_id从set中移除
                pl.srem('selected_%s' % user.id, sku_id)

            pl.execute()
            # 查询出sku_id对应的sku模型,然后包装修改后的购物车一行商品数据字典
            sku = SKU.objects.get(id=sku_id)
            sku_dict = {
                'id': sku.id,
                'name': sku.name,
                'default_image_url': sku.default_image.url,
                'price': str(sku.price),  # 为了方便js进行解析数据尽量把它转换成str类型
                'count': count,
                'selected': selected,  # 因为js对数据进行转换处理,js中true
                'amount': str(sku.price * count)
            }
            # 响应
            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '修改购物车成功', 'cart_sku': sku_dict})
        else:
            # 未登录用户修改cookie购物车数据
            # 获取cookie
            cart_str = request.COOKIES.get('carts')
            # 判断是否有cookie
            if cart_str:
                # 把cookie 字符串转换成字典
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                # 如果没有cookie提前响应
                return render(request, 'cart.html')

            # 修改cart_dict中的数据
            cart_dict[sku_id] = {
                'count': count,
                'selected': selected
            }
            # 把cookie购物车字典转换成字符串
            cart_str = base64.b64encode(pickle.dumps(cart_dict)).decode()
            sku = SKU.objects.get(id=sku_id)
            sku_dict = {
                'id': sku.id,
                'name': sku.name,
                'default_image_url': sku.default_image.url,
                'price': str(sku.price),  # 为了方便js进行解析数据尽量把它转换成str类型
                'count': count,
                'selected': selected,  # 因为js对数据进行转换处理,js中true
                'amount': str(sku.price * count)
            }
            # 创建响应对象
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '修改成功', 'cart_sku': sku_dict})
            # 设置cookie
            response.set_cookie('carts', cart_str)
            return response

    def delete(self, request):
        """删除购物车"""
        # 接收请求体中的sku_id
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')
        # 校验
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return http.HttpResponseForbidden('sku_id不存在')
        # 判断是否登录
        user = request.user
        if user.is_authenticated:
            # 登录用户操作redis
            # 创建redis连接对象
            redis_conn = get_redis_connection('carts')
            # 创建管道
            pl = redis_conn.pipeline()
            # 把指定sku_id对应的键值对从hash中移除
            pl.hdel('carts_%s' % user.id, sku_id)
            # 把对应的sku_id从set移除
            pl.srem('selected_%s' % user.id, sku_id)
            pl.execute()
            # 响应
            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '删除成功'})
        else:
            # 未登录用户操作cookie
            # 获取cookie购物车数据
            cart_str = request.COOKIES.get('carts')
            # 判断是否有cookie购物车数据
            if cart_str:
                # 把cookie字符串转字典
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                # 如果没有取到cookie提前响应
                return render(request, 'cart.html')
            # 删除cookie字典中的指定sku_id 键值对象
            if sku_id in cart_dict:  # 当sku_id在字典中存在时再去删除
                del cart_dict[sku_id]

            # 创建响应对象
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '删除成功'})
            # 如果cookie大字典已经没有商品了, 把cookie购物车数据直接删除
            if not cart_dict:
                response.delete_cookie('carts')
                return response
            # 把cookie字典转回字符串
            cart_str = base64.b64encode(pickle.dumps(cart_dict)).decode()
            # 重新设置cookie
            response.set_cookie('carts', cart_str)
            return response


class CartsSelectedAllView(View):
    """购物车全选"""

    def put(self, request):
        # 接收请求体中selected参数
        json_dict = json.loads(request.body.decode())
        selected = json_dict.get('selected')
        # 校验
        if isinstance(selected, bool) is False:
            return http.HttpResponseForbidden('参数类型有误')

        # 获取当前请求的user
        user = request.user
        # 判断是否登录
        if user.is_authenticated:
            # 登录用户操作redis
            # 创建redis连接对象
            redis_conn = get_redis_connection('carts')
            # 判断当前是全选还是取消全选
            if selected:
                # 全选
                # 先获取hash中的所有数据,再取到里面的所有key
                redis_carts = redis_conn.hgetall('carts_%s' % user.id)
                sku_ids = redis_carts.keys()
                # 将购物车中所有sku_id添加到set中
                redis_conn.sadd('selected_%s' % user.id, *sku_ids)
            else:
                # 取消
                # 将当前用户的set集合直接删除
                redis_conn.delete('selected_%s' % user.id)

            # 响应
            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})
        else:
            # 未登录用户操作cookie
            # 获取cookie购物车数据
            cart_str = request.COOKIES.get('carts')
            # 判断是否有cookie购物车数据
            if cart_str:
                # 有就把字符串转字典
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                # 没有就响应
                return http.JsonResponse({'code': RETCODE.DBERR, 'errmsg': '没有cookie'})
            # 修改字典中每个value中的selected对应的值为True或False
            for sku_id in cart_dict:
                cart_dict[sku_id] = {
                    'count': cart_dict[sku_id]['count'],
                    'selected': selected
                }
            # 转字典转换成字符串
            cart_str = base64.b64encode(pickle.dumps(cart_dict)).decode()
            # 创建响应对象
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})
            # 设置cookie
            response.set_cookie('carts', cart_str)
            # 响应
            return response


class CartsSimpleView(View):
    """简单版购物车"""

    def get(self, request):
        """购物车数据展示"""
        # 先获取请求对象中的user
        user = request.user

        # 判断用户是否登录
        if user.is_authenticated:
            # 登录用户获取redis购物车数据

            # 创建redis连接对象
            redis_conn = get_redis_connection('carts')
            # 获取hash中的数据 {b'1': b'2, b'2':b'1'}
            redis_carts = redis_conn.hgetall('carts_%s' % user.id)
            # 获取set集合中的数据 {b'1', b'2'}
            selected_ids = redis_conn.smembers('selected_%s' % user.id)
            # 把redis购物车数据格式转换成cookie购物车数据格式
            cart_dict = {}  # 准备一个空字典用来装redis购物车所有数据
            for sku_id_bytes in redis_carts:
                cart_dict[int(sku_id_bytes)] = {
                    'count': int(redis_carts[sku_id_bytes]),
                    'selected': (sku_id_bytes in selected_ids)
                }


        else:
            # 未登录用户获取cookie购物车数据
            cart_str = request.COOKIES.get('carts')
            if cart_str:
                # 有cookie购物车数据就将它从字符串转字典
                cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
            else:
                # 没有cookie购物车数据,就显示一个空白的购物车界面
                return render(request, 'cart.html')

        # 为了sku_id查询sku模型及包装模板需要渲染的数据代码 登录和未登录共用同一个代码
        # 查询sku模型
        sku_qs = SKU.objects.filter(id__in=cart_dict.keys())
        cart_skus = []  # 此列表用来包装前端界面需要渲染的所有购物车商品数据
        for sku in sku_qs:
            # 获取指定商品要购买的数量
            count = cart_dict[sku.id]['count']
            cart_skus.append({
                'id': sku.id,
                'name': sku.name,
                'default_image_url': sku.default_image.url,
                'count': count,
            })

        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'cart_skus': cart_skus})
