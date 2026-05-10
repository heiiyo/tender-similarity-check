from agent.format.out_format import SkillComplianceListFormat
from agent.skill.skill_runner import invoke_with_skill_or_llm
from agent.skill.skill import SkillRegistry
from langchain_siliconflow import ChatSiliconFlow
from apps import AppContext

AppContext().init_context()

# 初始化组件
registry = SkillRegistry()
llm = ChatSiliconFlow(
    base_url="https://api.siliconflow.cn/v1",
    api_key="sk-sdbwgllpqhbnijbotgyqsikuhowhmmuzpowxraulvasfexsv",
    model="Qwen/Qwen3.6-35B-A3B",
    temperature=0,
    max_tokens=1000,
    timeout=300,
    extra_body={"enable_thinking": False},
)

if __name__ == "__main__":
    # 接收用户输入
    user_input = input("请输入你的请求: ")
    print(f"用户输入: {user_input}")

    try:
        result = invoke_with_skill_or_llm(registry, llm, user_input)
        print(f"执行模式: {result['mode']}")
        print(f"路由结果: {result['router']}")
        if result['invoke_result'].get("structured_response") is not None:
            print(f"结构化结果: {result['invoke_result']['structured_response']}")
        else:
            print(f"执行结果: {result['invoke_result']}")

        # if result['mode'] == 'general':
        #     print(f"执行结果: {result['invoke_result']}")
        # else:
        #     format:SkillComplianceListFormat = result['invoke_result']['structured_response']
        #     print(f"执行结果: {format.model_dump_json(indent=4, ensure_ascii=False)}")
    except Exception as e:
        print(f"执行出错: {e}")