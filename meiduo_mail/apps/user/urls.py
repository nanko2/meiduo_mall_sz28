from django.conf.urls import url

from . import views

urlpatterns = [
    # 注册
    url(r'^register/$', views.RegisterView.as_view()),
    # 用户名是否重复
    url(r'^usernames/(?P<username>[a-zA-Z0-9_-]{5,20})/count/$', views.UsernameCountView.as_view()),
    # 手机号是否重复
    url(r'^mobiles/(?P<mobile>1[3-9]\d{9})/count/$', views.MobileCountView.as_view()),
    # 用户登录
    url(r'^login/$', views.LoginView.as_view()),
    # 退出登录
    url(r'^logout/$', views.LogoutView.as_view()),
    # 用户中心
    url(r'^info/$', views.InfoView.as_view()),
    # 设置用户邮箱
    url(r'^emails/$', views.EmailView.as_view()),
    # 邮箱激活
    url(r'^emails/verification/$', views.VerifyEmailView.as_view()),
    # 用户收货地址
    url(r'^addresses/$', views.AddressView.as_view()),
    # 用户收货地址
    url(r'^addresses/create/$', views.CreateAddressView.as_view()),
    # 用户收货地址修改和删除
    url(r'^addresses/(?P<address_id>\d+)/$', views.UpdateDestroyAddressView.as_view()),
    # 设置用户默认收货地址
    url(r'^addresses/(?P<address_id>\d+)/default/$', views.DefaultAddressView.as_view()),
    # 修改用户收货地址标题
    url(r'^addresses/(?P<address_id>\d+)/title/$', views.UpdateTitleAddressView.as_view()),
    # 修改密码
    url(r'^password/$', views.ChangePasswordView.as_view()),
    # 商品浏览记录
    url(r'^browse_histories/$', views.HistoryGoodsView.as_view()),

]