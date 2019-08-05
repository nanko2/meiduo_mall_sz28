from django.db import models


class Area(models.Model):
    """省市区"""
    name = models.CharField(max_length=20, verbose_name='名称')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, related_name='subs', null=True, blank=True,
                               verbose_name='上级行政区划')

    class Meta:
        db_table = 'tb_areas'
        verbose_name = '省市区'
        verbose_name_plural = '省市区'

    def __str__(self):
        return self.name


"""
gdArea
szArea
baArea


Area.objects.filter(parent=None)


Area.objects.filter(parent_id=130100)



Area.objects.get(id=130000)


related_name  给area_set  起了个别名 
# 一查多
gdArea.subs.all()
szArea.subs.all()


# 多查一
szArea.parent   外键取出的东西绝对是一个单一模型对象
baArea.parent


hero.hbook 
# 一查多 
book.hero_set.    一查多时,模型小写_set 必须要再调用all()  filter 来获取  得到一般都是一个QuerySet



"""