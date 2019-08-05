from django.conf.urls import url

from . import views


urlpatterns = [
    # 首页的路径(如果路径直接实现的是根域名,不要多加 斜杠)
    url(r'^$', views.IndexView.as_view()),
]