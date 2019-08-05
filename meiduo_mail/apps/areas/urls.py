from django.conf.urls import url

from . import views


urlpatterns = [
    # 获取省市区
    url(r'^areas/$', views.AreaView.as_view()),
]