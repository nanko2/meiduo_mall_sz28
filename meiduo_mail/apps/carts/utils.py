import pickle, base64
from django_redis import get_redis_connection


def merge_cart_cookie_to_redis(request, response):
    """登录时合并购物车数据"""
    # 获取cookie中的购物车数据
    cart_str = request.COOKIES.get('carts')
    # 判断是否有cookie购物车数据
    if cart_str is None:
        # 如果没有,提前结构函数运行
        return

    # 将字符串转字典
    cart_dict = pickle.loads(base64.b64decode(cart_str.encode()))
    # 创建redis连接对象
    redis_conn = get_redis_connection('carts')
    pl = redis_conn.pipeline()
    user = request.user  # 注意: 如果要这样拿user 此函数必须在login之后去调用
    # 遍历cookie购物车数据字典
    for sku_id in cart_dict:
        # 将sku_id 和count向redis的hash添加 hset
        pl.hset('carts_%s' % user.id, sku_id, cart_dict[sku_id]['count'])
        # 判断cookie中当前商品是勾选还是不勾选
        if cart_dict[sku_id]['selected']:
            # 勾选就将sku_id向redis的set中添加
            pl.sadd('selected_%s' % user.id, sku_id)
        else:
            # 不勾选就将sku_id 从redis的set中删除
            pl.srem('selected_%s' % user.id, sku_id)
    pl.execute()

    # 将cookie购物车数据删除
    response.delete_cookie('carts')

