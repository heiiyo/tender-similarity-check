---
frameworks:
- Pytorch
license: Apache License 2.0
tags: []
tasks:
- image-object-detection

#model-type:
##如 gpt、phi、llama、chatglm、baichuan 等
#- gpt

#domain:
##如 nlp、cv、audio、multi-modal
#- nlp

#language:
##语言代码列表 https://help.aliyun.com/document_detail/215387.html?spm=a2c4g.11186623.0.0.9f8d7467kni6Aa
#- cn 

#metrics:
##如 CIDEr、Blue、ROUGE 等
#- CIDEr

#tags:
##各种自定义，包括 pretrained、fine-tuned、instruction-tuned、RL-tuned 等训练方法和其他
#- pretrained

#tools:
##如 vllm、fastchat、llamacpp、AdaSeq 等
#- vllm
---
这里展示了一个代码片段，展示了如何使用印章检测模型：
from ultralytics import YOLO
import os
from pathlib import Path

# 1. 加载训练好的模型
model = YOLO('best.pt')

# 2. 设置输入和输出文件夹路径
input_folder = 'photo_seal'
output_folder = 'results_seal'

# 创建输出目录
Path(output_folder).mkdir(exist_ok=True)

# 3. 支持的图片格式
image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.JPG', '.JPEG', '.PNG', '.BMP', '.TIFF')

# 4. 获取所有图片文件
image_files = [f for f in os.listdir(input_folder) if f.lower().endswith(image_extensions)]

# 5. 批量推理并保存结果
for filename in image_files:
    img_path = os.path.join(input_folder, filename)
    results = model(img_path)
    output_path = os.path.join(output_folder, f"result_{filename}")
    results[0].save(filename=output_path)


SDK下载
```bash
#安装ModelScope
pip install modelscope
```
```python
#SDK模型下载
from modelscope import snapshot_download
model_dir = snapshot_download('SdtDevAi/Seal_inspection')
```
Git下载
```
#Git模型下载
git clone https://www.modelscope.cn/SdtDevAi/Seal_inspection.git
```

<p style="color: lightgrey;">如果您是本模型的贡献者，我们邀请您根据<a href="https://modelscope.cn/docs/ModelScope%E6%A8%A1%E5%9E%8B%E6%8E%A5%E5%85%A5%E6%B5%81%E7%A8%8B%E6%A6%82%E8%A7%88" style="color: lightgrey; text-decoration: underline;">模型贡献文档</a>，及时完善模型卡片内容。</p>