from fdfs_client.client import Fdfs_client

# 创建fastdfs客户端 并指定它的配置文件
fdsf_client = Fdfs_client('./client.conf')

ret = fdsf_client.upload_by_filename('/home/python/Desktop/01.jpeg')
f = open('/home/python/Desktop/01.jpeg')
content = f.read()
fdsf_client.upload_by_buffer(content)

print(ret)



"""

getting connection
<fdfs_client.connection.Connection object at 0x7f7367f5bd30>
<fdfs_client.fdfs_protol.Tracker_header object at 0x7f7367f5bcf8>
{'Group name': 'group1',
 'Remote file_id': 'group1/M00/00/00/wKgRgF0ymPKAMZGqAAC4j90Tziw97.jpeg',
  'Status': 'Upload successed.',
   'Local file name': '/home/python/Desktop/01.jpeg',
    'Uploaded size': '46.00KB', 'Storage IP': '192.168.17.128'}

"""