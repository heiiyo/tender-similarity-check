---
name: check_bid_signature
description: >-
    检测标书是否法人代表或委托书签字
tools: [query_tender_keyword, query_tender_signature]
---
## 任务流程
- **查询法人代表或者委托人授权在标书哪几页**: 使用工具查询出关键字'法人代表或者委托人授权'存在标书的页码
- **根据页码检测是否有法人代表或者委托人签字**: 使用签字印章工具检测
## 输出结果
- 输出最终的结果，要求表明哪页有法人代表签字，哪页有缺失

