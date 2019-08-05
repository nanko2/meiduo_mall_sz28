from django.shortcuts import render
from django.utils import timezone
from django.views import View
from django import http
from django.core.paginator import Paginator, EmptyPage

from contents.utils import get_categories
from .models import GoodsCategory, SKU, GoodsVisitCount
from .utils import get_breadcrumb
from meiduo_mail.utils.response_code import RETCODE



class ListView(View):
    """商品列表界面"""

    def get(self, request, category_id, page_num):
        try:
            category = GoodsCategory.objects.get(id=category_id)
        except GoodsCategory.DoesNotExist:
            return http.HttpResponseForbidden('category_id不存在')

        # 接收前端传入的sort = 'xxx'
        sort = request.GET.get('sort', 'default')

        if sort == 'price':
            sort_filed = '-price'
        elif sort == 'hot':
            sort_filed = '-sales'
        else:
            sort = 'default'
            sort_filed = 'create_time'


        # 把当前三级类型下的所有要上架的sku拿到
        sku_qs = category.sku_set.filter(is_launched=True).order_by(sort_filed)
        # 创建分页器 Paginator(要进行分页的所有数据, 指定每页显示多少条数据)
        paginator = Paginator(sku_qs, 5)
        try:
            # 获取指定页的数据  16 // 5   +  (1 if (16 % 5) else 0)
            page_skus = paginator.page(page_num)   #  (2 - 1) * 5:  5*2 - 1
        except EmptyPage:
            return http.HttpResponseForbidden('非法请求,不没指定页')
        # 获取总页数
        total_page = paginator.num_pages

        context = {
            'categories': get_categories(),  # 商品类别数据
            'breadcrumb': get_breadcrumb(category),  # 面包屑导航
            'sort': sort,  # 排序字段
            'category': category,  # 第三级分类
            'page_skus': page_skus,  # 分页后数据
            'total_page': total_page,  # 总页数
            'page_num': page_num,  # 当前页码
        }
        return render(request, 'list.html', context)


class HotGoodsView(View):
    """获取热销商品"""

    def get(self, request, category_id):
        try:
            category = GoodsCategory.objects.get(id=category_id)
        except GoodsCategory.DoesNotExist:
            return http.HttpResponseForbidden('category_id不存在')

        # 查询当前指定三级类别中销量最高的前两个商品
        sku_qs = category.sku_set.filter(is_launched=True).order_by('-sales')[:2]

        hot_skus = []
        # 模型转字典
        for sku in sku_qs:
            hot_skus.append({
                'id': sku.id,
                'name': sku.name,
                'price': sku.price,
                'default_image_url': sku.default_image.url
            })

        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'hot_skus': hot_skus})




class DetailView(View):

    def get(self, request, sku_id):

        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return render(request, '404.html')

        category = sku.category  # 获取当前sku所对应的三级分类

        # 查询当前sku所对应的spu
        spu = sku.spu

        """1.准备当前商品的规格选项列表 [8, 11]"""
        # 获取出当前正显示的sku商品的规格选项id列表
        current_sku_spec_qs = sku.specs.order_by('spec_id')
        current_sku_option_ids = []  # [8, 11]
        for current_sku_spec in current_sku_spec_qs:
            current_sku_option_ids.append(current_sku_spec.option_id)

        """2.构造规格选择仓库
        {(8, 11): 3, (8, 12): 4, (9, 11): 5, (9, 12): 6, (10, 11): 7, (10, 12): 8}
        """
        # 构造规格选择仓库
        temp_sku_qs = spu.sku_set.all()  # 获取当前spu下的所有sku
        # 选项仓库大字典
        spec_sku_map = {}  # {(8, 11): 3, (8, 12): 4, (9, 11): 5, (9, 12): 6, (10, 11): 7, (10, 12): 8}
        for temp_sku in temp_sku_qs:
            # 查询每一个sku的规格数据
            temp_spec_qs = temp_sku.specs.order_by('spec_id')
            temp_sku_option_ids = []  # 用来包装每个sku的选项值
            for temp_spec in temp_spec_qs:
                temp_sku_option_ids.append(temp_spec.option_id)
            spec_sku_map[tuple(temp_sku_option_ids)] = temp_sku.id

        """3.组合 并找到sku_id 绑定"""
        spu_spec_qs = spu.specs.order_by('id')  # 获取当前spu中的所有规格

        for index, spec in enumerate(spu_spec_qs):  # 遍历当前所有的规格
            spec_option_qs = spec.options.all()  # 获取当前规格中的所有选项
            temp_option_ids = current_sku_option_ids[:]  # 复制一个新的当前显示商品的规格选项列表
            for option in spec_option_qs:  # 遍历当前规格下的所有选项
                temp_option_ids[index] = option.id  # [8, 12]
                option.sku_id = spec_sku_map.get(tuple(temp_option_ids))  # 给每个选项对象绑定下他sku_id属性

            spec.spec_options = spec_option_qs  # 把规格下的所有选项绑定到规格对象的spec_options属性上

        context = {
            'categories': get_categories(),  # 商品分类
            'breadcrumb': get_breadcrumb(category),  # 面包屑导航
            'sku': sku,  # 当前要显示的sku模型对象
            'category': category,  # 当前的显示sku所属的三级类别
            'spu': spu,  # sku所属的spu
            'spec_qs': spu_spec_qs,  # 当前商品的所有规格数据
        }
        return render(request, 'detail.html', context)



class DetailVisitView(View):
    """商品类别每日访问类统计"""

    def post(self, request, category_id):

        try:
            category = GoodsCategory.objects.get(id=category_id)
        except GoodsCategory.DoesNotExist:
            return http.HttpResponseForbidden('category_id不存在')

        # now_date = timezone.localtime()  # 获取当前日期对象
        now_date = timezone.now() # 获取当前时间日期对象

        try:
            goods_visit = GoodsVisitCount.objects.get(category=category, date=now_date)
        except GoodsVisitCount.DoesNotExist:
            # 如果此三级类型今天是第一次访问就新增一条访问记录
            goods_visit = GoodsVisitCount(
                category=category
            )
        # 无论是新的还是旧的都做累加1
        goods_visit.count += 1
        goods_visit.save()

        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})
