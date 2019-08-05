from goods.models import GoodsChannel


def get_categories():
    """返回商品分类数据"""

    # 定义一个大字典变量用来包装商品类别的所有数据
    categories = {}

    # 查询出所有频道数据,并且进行排序
    goods_channels_qs = GoodsChannel.objects.order_by('group_id', 'sequence')

    # 遍历商品频道查询集
    for goods_channel in goods_channels_qs:
        # 获取组号
        group_id = goods_channel.group_id
        # 判断当前组的数据最初格式是否已经准备过
        if group_id not in categories:  # 如果当前组号在字典的key中不存时,再去添加数据初始格式
            categories[group_id] = {'channels': [], 'sub_cats': []}

        cat1 = goods_channel.category  # 获取一组模型对象
        # 多给一级类型添加url属性
        cat1.url = goods_channel.url
        # 添加一级数据
        categories[group_id]['channels'].append(cat1)

        # 获取出一级下面的所有二级
        cat2_qs = cat1.subs.all()
        for cat2 in cat2_qs:
            # 把当前二级下面的所有三级拿到
            cat3_qs = cat2.subs.all()
            # 给每个二级多定义一个sub_cats属性用来保存它自己的所有三级
            cat2.sub_cats = cat3_qs
            # 添加当前组中的每一个二级
            categories[group_id]['sub_cats'].append(cat2)

    return categories
