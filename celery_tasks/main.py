# 客户端/生产者

from celery import Celery
import os
# 在celery自动时,指定Django项目配置文件的路径,不然后面如果celery中使用了django配置文件,就会报错
os.environ.setdefault("DJANGO_SETTINGS_MODULE","meiduo_mall.settings.dev")

# 创建celery实列对象
celery_app = Celery('meiduo')

# 加载配置(指定中间人/消息队列/仓库)
celery_app.config_from_object('celery_tasks.config')

# 指定celery可以生存的任务
celery_app.autodiscover_tasks(['celery_tasks.sms', 'celery_tasks.email'])
