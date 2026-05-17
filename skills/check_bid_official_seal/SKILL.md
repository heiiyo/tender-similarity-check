---
name: check_bid_official_seal
description: >-
    检测标书是否盖有公章
tools: [check_official_seal]
---
## 任务描述
检测标书bid_id={{bid_id}}, 匹规则rule_id={{rule_id}}每一页是否有盖章，并逐页输出合规判定结果。

## 任务流程
1. 调用 check_official_seal 工具获取标书所有页面的公章检测结果, 并自动保存结果
2. 调用工具后直接输出结论result_type=0，不用思考

### 正确示例：
{
    "skill_name": "check_bid_official_seal",
    "result_type": 0
    "items": [
      {"is_compliant": false, "check_basis": "存在为盖章页"}
    ]
}

