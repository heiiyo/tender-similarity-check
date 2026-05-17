---
name: check_bid_official_seal
description: >-
    检测标书是否盖有公章
tools: [check_official_seal]
---
## 任务描述
检测标书bid_id={{bid_id}}, 匹规则rule_id={{rule_id}}每一页是否有盖章，并逐页输出合规判定结果。

## 任务流程
1. 调用 check_official_seal 工具获取标书所有页面的公章检测结果
2. 工具会返回一个列表，包含每一页的检测信息（page_number, is_sign, text）
3. **重要：必须为每一页单独创建一个 SkillComplianceFormat item**
4. 根据每页的 is_sign 字段判断该页是否合规：
   - is_sign=true：该页已盖章，is_compliant=true
   - is_sign=false：该页未盖章，is_compliant=false

## 输出结果要求
- **必须逐页输出**：每一页对应一个独立的 items 条目
- 不得将多页结果合并为一个 item
- 每个 item 的 check_basis 必须明确说明是哪一页、检测结果是什么

### 正确示例：
{
  "items": [
    {"is_compliant": true, "check_basis": "第1页：检测到2个公章，内容为xxxx公司或企业"},
    {"is_compliant": true, "check_basis": "第2页：检测到1个公章"},
    {"is_compliant": false, "check_basis": "第3页：未检测到公章"},
    {"is_compliant": true, "check_basis": "第4页：检测到1个公章"},
    {"is_compliant": true, "check_basis": "第5页：检测到3个公章"}
  ]
}

