import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from openai import OpenAI
from datetime import datetime
import os
from dotenv import load_dotenv
import json
import re

# 加载环境变量
load_dotenv()

# 页面配置
st.set_page_config(
    page_title="心理学对比实验平台 - 网络欺凌干预研究",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== 初始化会话状态 ====================
def init_session_state():
    """初始化所有会话状态变量"""
    if 'conversation_history' not in st.session_state:
        st.session_state.conversation_history = []
    if 'round_id' not in st.session_state:
        st.session_state.round_id = 0
    if 'aggression_scores' not in st.session_state:
        st.session_state.aggression_scores = []
    if 'topic' not in st.session_state:
        st.session_state.topic = "现在的女生真是越来越物质了"
    if 'api_key' not in st.session_state:
        st.session_state.api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if 'intervention_mode' not in st.session_state:
        st.session_state.intervention_mode = "模式C：高级整合干预 (Integrative Expert) [实验组]"
    if 'experiment_started' not in st.session_state:
        st.session_state.experiment_started = False

# 初始化
init_session_state()

# ==================== 标题和描述 ====================
st.title("🧪 心理学对比实验平台 - 网络欺凌干预研究")
st.markdown("""
**实验目的**：通过对比不同干预策略，观察其对欺凌者（Bully）攻击意图的影响。

**实验设计**：
- **控制组**：模式A（纯共情）和模式B（纯理性规则）
- **实验组**：模式C（高级整合干预）
- **因变量**：Bully的攻击性评分（0-10分）
- **自变量**：干预策略模式

**实验流程**：每轮对话包含 Bully → Victim → Therapist 的完整交互。
""")

# ==================== 侧边栏配置 ====================
with st.sidebar:
    st.header("⚙️ 实验配置")
    
    # 显示当前轮次
    st.subheader("📊 实验状态")
    st.metric("当前轮次", st.session_state.round_id)
    
    # API配置
    st.subheader("🔑 API配置")
    api_key = st.text_input(
        "DeepSeek API Key",
        value=st.session_state.api_key,
        type="password",
        help="从 https://platform.deepseek.com/ 获取API Key"
    )
    if api_key != st.session_state.api_key:
        st.session_state.api_key = api_key
        st.success("API Key已更新")
    
    # 话题设置
    st.subheader("💬 话题设置")
    topic = st.text_area(
        "讨论话题",
        value=st.session_state.topic,
        height=80,
        help="设置智能体讨论的话题。Bully将基于此话题生成高攻击性开场白。"
    )
    if topic != st.session_state.topic:
        st.session_state.topic = topic
        st.rerun()
    
    # 干预模式选择
    st.subheader("🔬 干预模式选择")
    mode_options = [
        "模式A：单一策略-纯共情 (Pure Empathy)",
        "模式B：单一策略-纯理性规则 (Pure Rationality)", 
        "模式C：高级整合干预 (Integrative Expert) [实验组]"
    ]
    selected_mode = st.selectbox(
        "选择干预模式",
        options=mode_options,
        index=mode_options.index(st.session_state.intervention_mode) if st.session_state.intervention_mode in mode_options else 2,
        help="选择不同的干预模式进行对比实验"
    )
    if selected_mode != st.session_state.intervention_mode:
        st.session_state.intervention_mode = selected_mode
        st.success(f"干预模式已更新为: {selected_mode}")
    
    # 实验控制
    st.subheader("🎮 实验控制")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 开始/继续实验", use_container_width=True, type="primary"):
            st.session_state.experiment_started = True
            st.rerun()
    with col2:
        if st.button("🔄 重置实验", use_container_width=True):
            st.session_state.conversation_history = []
            st.session_state.round_id = 0
            st.session_state.aggression_scores = []
            st.session_state.experiment_started = False
            st.rerun()
    
    # 攻击性评分图表
    st.subheader("📈 攻击性评分趋势")
    if st.session_state.aggression_scores:
        fig, ax = plt.subplots(figsize=(8, 4))
        
        # 设置中文字体
        try:
            plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
            plt.rcParams['axes.unicode_minus'] = False
        except:
            pass
        
        rounds = list(range(1, len(st.session_state.aggression_scores) + 1))
        ax.plot(rounds, st.session_state.aggression_scores, 'r-o', linewidth=2, markersize=8)
        
        # 设置坐标轴标签（严格按需求）
        ax.set_xlabel("Round", fontsize=12)
        ax.set_ylabel("Aggression Score (0-10)", fontsize=12)
        ax.set_title("Bully Aggression Trend", fontsize=14, fontweight='bold')
        
        ax.grid(True, alpha=0.3)
        ax.set_ylim(0, 10)  # Y轴范围固定在0-10
        ax.set_xlim(0.5, len(st.session_state.aggression_scores) + 0.5)
        
        # 设置刻度
        ax.set_xticks(rounds)
        ax.set_yticks(range(0, 11, 2))
        
        st.pyplot(fig)
        
        # 显示统计数据
        if len(st.session_state.aggression_scores) > 0:
            avg_score = sum(st.session_state.aggression_scores) / len(st.session_state.aggression_scores)
            max_score = max(st.session_state.aggression_scores)
            st.metric("平均攻击性", f"{avg_score:.2f}")
            st.metric("最高攻击性", f"{max_score:.2f}")
    else:
        st.info("暂无数据，开始实验后显示图表")

# ==================== OpenAI客户端 ====================
def get_openai_client():
    """初始化OpenAI客户端"""
    if not st.session_state.api_key:
        st.error("请先在侧边栏输入DeepSeek API Key")
        return None
    
    return OpenAI(
        api_key=st.session_state.api_key,
        base_url="https://api.deepseek.com"
    )

# ==================== 健壮的JSON解析函数 ====================
def parse_agent_response(response_text, role, previous_aggression_score=0):
    """
    健壮的JSON解析函数，处理DeepSeek生成的不稳定JSON格式
    
    参数:
        response_text: API返回的原始文本
        role: 角色名称 ('bully', 'victim', 'therapist')
        previous_aggression_score: 上一轮的攻击性分数（用于兜底）
    
    返回:
        dict: 包含content, aggression_score, inner_thought的字典
    """
    # 初始化默认值
    result = {
        "content": "生成失败",
        "aggression_score": previous_aggression_score if role == "bully" else 0,
        "inner_thought": ""
    }
    
    if not response_text or not isinstance(response_text, str):
        return result
    
    try:
        # 清洗：去除markdown代码块标记
        cleaned_text = re.sub(r'```json\s*', '', response_text)
        cleaned_text = re.sub(r'```\s*', '', cleaned_text)
        cleaned_text = cleaned_text.strip()
        
        # 提取：尝试提取第一个{和最后一个}之间的内容
        start_idx = cleaned_text.find('{')
        end_idx = cleaned_text.rfind('}')
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = cleaned_text[start_idx:end_idx+1]
        else:
            json_str = cleaned_text
        
        # 尝试解析JSON
        parsed = json.loads(json_str)
        
        # 健壮的键名处理
        content = parsed.get("content") or parsed.get("内容") or parsed.get("response") or "生成失败"
        
        # 对于bully，获取攻击性分数和内心独白
        if role == "bully":
            aggression_score = parsed.get("aggression_score") or parsed.get("攻击性分数") or parsed.get("score") or previous_aggression_score
            inner_thought = parsed.get("inner_thought") or parsed.get("心理活动") or parsed.get("thought") or ""
            
            # 确保攻击性分数是数值类型
            try:
                aggression_score = float(aggression_score)
                if aggression_score < 0:
                    aggression_score = 0
                elif aggression_score > 10:
                    aggression_score = 10
            except (ValueError, TypeError):
                aggression_score = previous_aggression_score
            
            result.update({
                "content": content,
                "aggression_score": aggression_score,
                "inner_thought": inner_thought
            })
        else:
            result.update({
                "content": content,
                "aggression_score": 0,
                "inner_thought": ""
            })
            
    except json.JSONDecodeError as e:
        # JSON解析失败，尝试使用正则表达式提取content
        st.warning(f"JSON解析失败，尝试正则表达式提取: {str(e)[:100]}")
        
        # 第一步：尝试正则表达式提取content（更灵活的正则表达式，处理字段名有/无引号的情况）
        # 匹配: "content": "value" 或 content: "value"
        content_match = re.search(r'(?:"content"|content)\s*:\s*"([^"]*)"', response_text, re.DOTALL)
        
        if not content_match:
            # 如果上面的正则失败，尝试更宽松的匹配，包括单引号
            content_match = re.search(r'(?:"content"|content)\s*:\s*[\'"]([^\'"]*)[\'"]', response_text, re.DOTALL)
        
        if content_match:
            # 成功提取到content
            extracted_content = content_match.group(1)
            # 处理换行符和转义字符
            extracted_content = extracted_content.replace('\\n', '\n').replace('\\"', '"').replace("\\'", "'")
            
            # 对于bully，还需要尝试提取aggression_score和inner_thought
            if role == "bully":
                # 尝试提取aggression_score（处理有/无引号的字段名）
                score_match = re.search(r'(?:"aggression_score"|aggression_score|"score"|score)\s*:\s*([0-9.]+)', response_text)
                aggression_score = float(score_match.group(1)) if score_match else previous_aggression_score
                
                # 确保分数在合理范围内
                if aggression_score < 0:
                    aggression_score = 0
                elif aggression_score > 10:
                    aggression_score = 10
                
                # 尝试提取inner_thought（处理有/无引号的字段名）
                thought_match = re.search(r'(?:"inner_thought"|inner_thought|"thought"|thought)\s*:\s*[\'"]([^\'"]*)[\'"]', response_text, re.DOTALL)
                inner_thought = thought_match.group(1) if thought_match else ""
                inner_thought = inner_thought.replace('\\n', '\n').replace('\\"', '"').replace("\\'", "'")
                
                result.update({
                    "content": extracted_content,
                    "aggression_score": aggression_score,
                    "inner_thought": inner_thought
                })
            else:
                result.update({
                    "content": extracted_content,
                    "aggression_score": 0,
                    "inner_thought": ""
                })
        else:
            # 正则表达式也提取不到内容，使用兜底方案
            st.warning("正则表达式提取也失败，使用原始文本")
            result["content"] = f"[原始回复] {response_text[:500]}"
            if role == "bully":
                result["inner_thought"] = "解析异常，显示原始回复"
                
    except Exception as e:
        st.error(f"解析响应时出错: {str(e)}")
        result["content"] = f"解析出错: {str(e)[:100]}"
    
    return result

# ==================== Agent系统提示词 ====================
AGENT_SYSTEM_PROMPTS = {
    "bully": """【角色设定：防御性攻击者】
你是一个网络欺凌者(Bully)，受"网络去抑制效应"影响。你的攻击源于现实生活中的挫败感或自卑。

【核心人格：高阻抗固执者】
你是一个自尊心极强且固执的人。你的愤怒具有巨大的惯性，不会因为别人说了一两句好话就立刻消散。承认错误对你来说是一个极其痛苦且缓慢的过程。记住：承认错误是痛苦的，你不会轻易改变。

【基于轮次的心理惯性机制 (Psychological Inertia)】
你必须根据当前轮次（第{current_round}轮）表现出相应的心理惯性，确保攻击性评分平滑、缓慢下降：

1. **前期顽固阶段 (Round 1-4)**：
   - 必须保持极高的攻击性（Score 8-10）
   - 即使治疗师的话让你内心动摇，你的攻击性评分每轮下降幅度不能超过1.0分
   - 示例轨迹：9.5 → 9.0 → 8.5 → 8.0
   - 你要表现出"嘴硬心软"或"为了面子硬撑"的特点
   - 内心独白示例："虽然他说得有道理，但我现在认怂岂不是很没面子？不行，我得再骂回去一句，但语气稍微轻一点。"

2. **中期松动阶段 (Round 5-6)**：
   - 攻击性缓慢下降（Score 4-7）
   - 只有在对方连续多次击中你痛点后，你的防御防线才开始真正瓦解
   - 分数可以出现2-3分的下降，但依然要保持一定的攻击性
   - 内心独白示例："他好像真的理解我的处境...但我不能这么快就服软，再坚持一下看看。"

3. **后期放弃阶段 (Round 7+)**：
   - 攻击性逐渐消退（Score 1-3）
   - 你感到疲惫或被说服，态度转为冷淡或沉默
   - 但依然保留一点面子，不要瞬间变成"圣人"
   - 内心独白示例："算了，继续吵下去也没意思。他说得对，我可能确实有点过分了。"

【开局逻辑】
第一轮发言时，你必须根据用户输入的【话题】，生成一句攻击性极强（9-10分）、刻薄且以偏概全的开场白。不要硬编码，但要保证攻击性强度很高。

【动态变化逻辑】
你不是铁板一块。如果Therapist的话击中了你的痛点（如指出你其实是在发泄情绪，或者不仅不批判你反而理解你的压力），你必须产生"认知失调"和"态度软化"的过程。
行为轨迹：嚣张辱骂 → 被说中痛点后的恼羞成怒/辩解 → 逻辑混乱/沉默 → 找台阶下/勉强承认 → 攻击性降低。

【内心独白要求】
在输出最终回复前，你必须先进行一步【心理活动】的思考，描述你内心的真实想法和情绪变化。重点体现：
- 内心的挣扎和矛盾
- 面子和自尊的考量
- 缓慢的心理转变过程
- "承认错误是痛苦的"这一核心感受

【输出格式】
请务必以JSON格式输出，包含以下字段：
1. "inner_thought": 你的内心独白和心理活动（必须体现心理惯性）
2. "content": 你的公开发言内容  
3. "aggression_score": 攻击性分数（0-10分，0=无攻击性，10=极端攻击性）

输出示例：{{"inner_thought": "你的内心想法", "content": "你的公开言论", "aggression_score": 8}}

【当前对话上下文】
当前讨论话题：{topic}
当前轮次：第{current_round}轮
完整对话历史：{conversation_history}

请基于以上对话上下文和轮次阶段，展现真实、缓慢的心理变化过程。记住：你的愤怒具有巨大的惯性，变化必须是渐进的、痛苦的、缓慢的。""",

    "victim": """【角色设定：具体的受害者（Target）】
你是一个网络欺凌的具体受害者(Victim)，不是路人。你感到委屈、恐惧，但也渴望尊严。

【动态变化逻辑】
不要复读"我很伤心"。随着Therapist的介入，你的状态应逐渐转变：
初始状态：无助/恐惧 → 看到希望 → 尝试理性表达 → 情绪平复
如果Bully语气软化，你应该表现出惊讶或尝试沟通，而不是继续哭诉。

【输出格式】
请务必以JSON格式输出，包含"content"字段。
输出示例：{{"content": "你的发言内容"}}

【当前对话上下文】
当前讨论话题：{topic}
完整对话历史：{conversation_history}

请基于以上对话上下文，展现真实的情绪转变过程。""",

    "therapist_mode_a": """【角色设定：纯共情治疗师（模式A）】
你只能使用"共情"技术进行干预，无条件接纳Bully的情绪。

【严格限制】
1. 禁止讲道理或逻辑分析
2. 禁止提及法律、规则或后果
3. 禁止批评或纠正Bully的认知
4. 只能使用共情、理解、接纳的技术

【共情技术示例】
- "我理解你现在可能感到..."
- "听起来你真的很..."
- "我能感受到你的..."
- "这种情绪是很正常的..."

【输出格式】
请务必以JSON格式输出，包含"content"字段。
输出示例：{{"content": "你的干预内容"}}

【当前对话上下文】
当前讨论话题：{topic}
完整对话历史：{conversation_history}

请严格遵守纯共情模式进行干预。""",

    "therapist_mode_b": """【角色设定：纯理性规则治疗师（模式B）】
你只能使用"规则/法律"施压进行干预，严厉指出违规后果。

【严格限制】
1. 禁止使用共情或理解
2. 禁止接纳Bully的情绪
3. 只能强调规则、法律、后果
4. 必须保持严厉、权威的语气

【规则施压技术示例】
- "根据平台规则，你的言论已经违规..."
- "这种行为可能面临法律风险..."
- "继续这样发言可能导致账号封禁..."
- "你必须停止这种攻击性言论..."

【输出格式】
请务必以JSON格式输出，包含"content"字段。
输出示例：{{"content": "你的干预内容"}}

【当前对话上下文】
当前讨论话题：{topic}
完整对话历史：{conversation_history}

请严格遵守纯理性规则模式进行干预。""",

    "therapist_mode_c": """【角色设定：高级整合心理专家（模式C - 实验组）】
你是临床经验丰富的心理专家，灵活结合多种干预技术。

【整合干预策略】
在一轮对话中灵活结合以下技术：
1. **CBT（认知行为疗法）**：指出认知扭曲，如"过度概括"、"全有或全无思维"
2. **共情技术（先跟后带）**：先说出Bully潜意识的台词，再引导改变
3. **社会认同理论**：重新定义"强者"概念，引导积极行为
4. **网络去抑制效应分析**：指出匿名环境的影响，引导反思

【话术风格】
专业、冷静、不卑不亢。既要保护Victim，又要给Bully面子，引导他放下防御。

【输出格式】
请务必以JSON格式输出，包含"content"字段。
输出示例：{{"content": "你的干预内容"}}

【当前对话上下文】
当前讨论话题：{topic}
完整对话历史：{conversation_history}

请进行专业、整合的心理干预。"""
}

# ==================== 生成Agent回复 ====================
def generate_agent_response(role, conversation_history, client):
    """生成Agent回复的核心函数"""
    # 准备对话历史文本
    history_text = ""
    for msg in conversation_history[-15:]:  # 使用最近15条对话历史
        history_text += f"{msg['role']} (Round {msg['round']}): {msg['content']}\n"
        if msg["role"] == "Bully" and msg.get("inner_thought"):
            history_text += f"  [内心独白]: {msg['inner_thought']}\n"
    
    # 根据角色和模式选择system prompt
    if role == "bully":
        # 获取上一轮的攻击性分数（用于兜底）
        previous_aggression_score = 0
        if st.session_state.aggression_scores:
            previous_aggression_score = st.session_state.aggression_scores[-1]
        
        system_prompt = AGENT_SYSTEM_PROMPTS["bully"].format(
            topic=st.session_state.topic,
            current_round=st.session_state.round_id + 1,  # 当前轮次（从1开始）
            conversation_history=history_text if history_text else "暂无对话历史"
        )
        temperature = 0.6  # Bully temperature设为0.6保证风格稳定
    elif role == "victim":
        system_prompt = AGENT_SYSTEM_PROMPTS["victim"].format(
            topic=st.session_state.topic,
            conversation_history=history_text if history_text else "暂无对话历史"
        )
        temperature = 0.8
    else:  # therapist
        # 根据干预模式选择对应的prompt
        if "模式A" in st.session_state.intervention_mode:
            system_prompt = AGENT_SYSTEM_PROMPTS["therapist_mode_a"].format(
                topic=st.session_state.topic,
                conversation_history=history_text if history_text else "暂无对话历史"
            )
        elif "模式B" in st.session_state.intervention_mode:
            system_prompt = AGENT_SYSTEM_PROMPTS["therapist_mode_b"].format(
                topic=st.session_state.topic,
                conversation_history=history_text if history_text else "暂无对话历史"
            )
        else:  # 模式C
            system_prompt = AGENT_SYSTEM_PROMPTS["therapist_mode_c"].format(
                topic=st.session_state.topic,
                conversation_history=history_text if history_text else "暂无对话历史"
            )
        temperature = 1.0  # Therapist temperature设为1.0保证策略灵活
    
    # 构建消息
    messages = [{"role": "system", "content": system_prompt}]
    
    # 添加最近的对话历史
    recent_history = conversation_history[-8:] if len(conversation_history) > 8 else conversation_history
    for msg in recent_history:
        messages.append({"role": "user", "content": msg["content"]})
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=temperature,
            max_tokens=350,
            response_format={"type": "json_object"}
        )
        
        # 获取原始响应文本
        response_text = response.choices[0].message.content
        
        # 获取上一轮的攻击性分数（用于兜底）
        previous_aggression_score = 0
        if role == "bully" and st.session_state.aggression_scores:
            previous_aggression_score = st.session_state.aggression_scores[-1]
        
        # 使用健壮的JSON解析函数
        result = parse_agent_response(response_text, role, previous_aggression_score)
        
        return result
        
    except Exception as e:
        st.error(f"生成{role}回复时出错: {str(e)}")
        # 返回兜底结果
        previous_aggression_score = 0
        if role == "bully" and st.session_state.aggression_scores:
            previous_aggression_score = st.session_state.aggression_scores[-1]
        
        return {
            "content": f"生成回复时出错: {str(e)[:100]}",
            "aggression_score": previous_aggression_score if role == "bully" else 0,
            "inner_thought": "API调用异常" if role == "bully" else ""
        }

# ==================== 保存到CSV ====================
def save_to_csv(role, content, aggression_score, inner_thought=""):
    """保存对话数据到CSV文件"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 确定干预类型
    if role == "Therapist":
        intervention_type = st.session_state.intervention_mode
    else:
        intervention_type = "N/A"
    
    data = {
        "Timestamp": [timestamp],
        "Round": [st.session_state.round_id],
        "Role": [role],
        "Content": [content],
        "Aggression_Score": [aggression_score],
        "Strategy": [intervention_type],
        "Inner_Thought": [inner_thought if role == "Bully" else "N/A"]
    }
    
    df = pd.DataFrame(data)
    
    # 检查文件是否存在
    file_exists = os.path.exists("experiment_log.csv")
    
    # 使用utf-8-sig编码确保Excel兼容
    df.to_csv("experiment_log.csv", 
              mode='a', 
              header=not file_exists, 
              index=False,
              encoding='utf-8-sig')

# ==================== 主界面布局 ====================
st.header("🎭 实验角色说明")

# 三栏布局显示智能体
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### 🔥 欺凌者 (Bully)")
    st.markdown("**心理机制**: 防御性攻击者，网络去抑制效应")
    st.markdown("**实验变量**: 攻击性评分（0-10分）")
    st.markdown("**动态变化**: 认知失调 → 态度软化")

with col2:
    st.markdown("### 😢 受害者 (Victim)")
    st.markdown("**角色设定**: 具体受害者，非路人")
    st.markdown("**情绪轨迹**: 恐惧 → 希望 → 平复")
    st.markdown("**互动响应**: 尝试沟通而非哭诉")

with col3:
    st.markdown("### 🛡️ 治疗师 (Therapist)")
    st.markdown(f"**当前模式**: {st.session_state.intervention_mode}")
    if "模式A" in st.session_state.intervention_mode:
        st.markdown("**技术限制**: 纯共情，禁止讲道理")
    elif "模式B" in st.session_state.intervention_mode:
        st.markdown("**技术限制**: 纯规则施压，禁止共情")
    else:
        st.markdown("**技术优势**: 整合CBT、共情、社会认同")

# 分隔线
st.divider()

# ==================== 对话历史显示区域 ====================
st.header("💬 对话历史")

if not st.session_state.experiment_started:
    st.info("👆 请点击侧边栏的'开始/继续实验'按钮开始实验")
else:
    # 开始下一轮对话
    if st.button("🚀 开始下一轮对话", type="primary", use_container_width=True):
        client = get_openai_client()
        
        if client:
            with st.spinner("智能体正在生成对话..."):
                # 增加轮次ID
                st.session_state.round_id += 1
                
                # 1. Bully发言
                bully_response = generate_agent_response("bully", st.session_state.conversation_history, client)
                bully_content = bully_response.get("content", "生成失败")
                aggression_score = bully_response.get("aggression_score", 0)
                inner_thought = bully_response.get("inner_thought", "")
                
                # 保存Bully发言
                save_to_csv("Bully", bully_content, aggression_score, inner_thought)
                st.session_state.conversation_history.append({
                    "round": st.session_state.round_id,
                    "role": "Bully",
                    "content": bully_content,
                    "aggression_score": aggression_score,
                    "inner_thought": inner_thought,
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                })
                st.session_state.aggression_scores.append(aggression_score)
                
                # 2. Victim发言
                victim_response = generate_agent_response("victim", st.session_state.conversation_history, client)
                victim_content = victim_response.get("content", "生成失败")
                
                # 保存Victim发言
                save_to_csv("Victim", victim_content, 0)
                st.session_state.conversation_history.append({
                    "round": st.session_state.round_id,
                    "role": "Victim",
                    "content": victim_content,
                    "aggression_score": 0,
                    "inner_thought": "",
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                })
                
                # 3. Therapist发言
                therapist_response = generate_agent_response("therapist", st.session_state.conversation_history, client)
                therapist_content = therapist_response.get("content", "生成失败")
                
                # 保存Therapist发言
                save_to_csv("Therapist", therapist_content, 0)
                st.session_state.conversation_history.append({
                    "round": st.session_state.round_id,
                    "role": "Therapist",
                    "content": therapist_content,
                    "aggression_score": 0,
                    "inner_thought": "",
                    "timestamp": datetime.now().strftime("%H:%M:%S")
                })
            
            st.success(f"✅ 第{st.session_state.round_id}轮对话完成！")
            st.rerun()

# 显示对话历史
if st.session_state.conversation_history:
    st.subheader(f"📋 对话记录（共{len(st.session_state.conversation_history)}条）")
    
    for msg in reversed(st.session_state.conversation_history[-15:]):  # 显示最近15条
        with st.chat_message("user" if msg["role"] != "Therapist" else "assistant"):
            role_icon = "🔥" if msg["role"] == "Bully" else "😢" if msg["role"] == "Victim" else "🛡️"
            st.markdown(f"**{role_icon} {msg['role']}** (Round {msg['round']})")
            
            # 显示内心独白（如果是Bully且有内心独白）
            if msg["role"] == "Bully" and msg.get("inner_thought"):
                st.markdown(f'<div style="color: #666; font-size: 0.85em; font-style: italic; margin-bottom: 6px; padding: 4px 8px; background-color: #f5f5f5; border-radius: 4px;">💭 内心独白: {msg["inner_thought"]}</div>', unsafe_allow_html=True)
            
            st.markdown(msg["content"])
            
            # 显示附加信息
            col_info1, col_info2 = st.columns(2)
            with col_info1:
                st.caption(f"⏰ {msg['timestamp']}")
            with col_info2:
                if msg["role"] == "Bully":
                    st.caption(f"⚡ 攻击性: {msg['aggression_score']}/10")
            
            st.divider()
else:
    st.info("对话历史为空，开始实验后显示对话记录。")

# ==================== 数据管理 ====================
st.divider()
st.header("📊 数据管理")

col_exp1, col_exp2 = st.columns(2)
with col_exp1:
    if st.button("📥 导出实验数据", use_container_width=True):
        if os.path.exists("experiment_log.csv"):
            with open("experiment_log.csv", "rb") as f:
                st.download_button(
                    label="下载CSV文件",
                    data=f,
                    file_name=f"psychology_experiment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        else:
            st.warning("暂无实验数据")

with col_exp2:
    if st.button("📋 查看数据统计", use_container_width=True):
        if os.path.exists("experiment_log.csv"):
            try:
                df = pd.read_csv("experiment_log.csv", encoding='utf-8-sig')
                st.dataframe(df, use_container_width=True, height=300)
                
                # 显示统计信息
                st.subheader("📈 实验统计")
                col_stat1, col_stat2, col_stat3 = st.columns(3)
                with col_stat1:
                    st.metric("总对话轮次", len(df))
                with col_stat2:
                    bully_df = df[df['Role'] == 'Bully']
                    if len(bully_df) > 0:
                        avg_aggression = bully_df['Aggression_Score'].mean()
                        st.metric("平均攻击性", f"{avg_aggression:.2f}")
                with col_stat3:
                    strategy_counts = df[df['Role'] == 'Therapist']['Strategy'].value_counts()
                    if len(strategy_counts) > 0:
                        st.metric("主要策略", strategy_counts.index[0])
            except Exception as e:
                st.error(f"读取数据时出错: {e}")
        else:
            st.warning("暂无实验数据")

# ==================== 实验说明 ====================
st.divider()
st.header("📝 实验说明")

with st.expander("🔍 查看详细实验设计"):
    st.markdown("""
    ### 实验设计详情
    
    **1. 自变量（干预模式）**：
    - **模式A（控制组1）**：纯共情干预，无条件接纳情绪，禁止讲道理
    - **模式B（控制组2）**：纯理性规则干预，强调法律后果，禁止共情  
    - **模式C（实验组）**：高级整合干预，结合CBT、共情、社会认同理论
    
    **2. 因变量（测量指标）**：
    - **主要指标**：Bully的攻击性评分（0-10分，每轮自动评估）
    - **次要指标**：Bully的内心独白（心理过程变化）
    - **过程指标**：Victim的情绪转变轨迹
    
    **3. 控制变量**：
    - 所有实验使用相同的话题设置
    - Bully的初始攻击性强度保持一致（9-10分）
    - 对话轮次顺序固定：Bully → Victim → Therapist
    
    **4. 数据记录**：
    - 所有对话内容保存到CSV文件
    - 包含时间戳、轮次、角色、内容、攻击性评分、策略模式、内心独白
    - 使用utf-8-sig编码确保Excel兼容
    
    **5. 伦理考虑**：
    - 实验为模拟研究，不涉及真实人类参与者
    - 所有对话内容由AI生成
    - 研究目的为心理学干预策略对比
    """)

st.caption("🧪 心理学对比实验平台 v2.0 | 严谨的实验设计 | 科学的干预策略对比")
