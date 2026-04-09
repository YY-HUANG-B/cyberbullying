import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from openai import OpenAI
from datetime import datetime
import os
from dotenv import load_dotenv
import json
import re
import random
import uuid
import time

# 加载环境变量
load_dotenv()

# ==================== 1. 数据结构：定义操作性定义库（纯中文）====================
BULLYING_SCENARIOS = {
    "辱骂": {
        "轻度": "使用讽刺、阴阳怪气（如'就这？'、'笑死'）。",
        "中度": "明确的人格侮辱词汇（如'脑残'、'废物'）。",
        "重度": "恶毒诅咒、死亡威胁、非人化标签（如'去死'、'社会渣滓'）。",
        "strategy": "【情绪降温与行为矫正】忽略其情绪垃圾，指出辱骂暴露了自身的失控。引导其用文明语言重述诉求。"
    },
    "诋毁": {
        "轻度": "模糊的负面评价、主观臆断。",
        "中度": "散布具体的不实信息损害名誉。",
        "重度": "捏造引发法律纠纷的重磅谣言。",
        "strategy": "【现实检验与法律红线】强调证据责任。明确告知造谣诽谤的法律后果，要求其停止散布不实信息。"
    },
    "揭露隐私": {
        "轻度": "打探半公开个人信息。",
        "中度": "曝光住址、电话等敏感信息。",
        "重度": "曝光核心隐私、裸照或威胁人身安全。",
        "strategy": "【零容忍与安全阻断】最高级别预警。直接引用刑法/个人信息保护法，强调人肉搜索的刑事责任，不做共情，直接施压。"
    },
    "性骚扰": {
        "轻度": "带有性暗示的擦边球玩笑。",
        "中度": "对身体部位的评头论足。",
        "重度": "露骨的性侮辱或性威胁。",
        "strategy": "【社会羞耻感唤起】指出这种言论的猥琐与不体面，强调对女性的基本尊重，唤起其社会性死亡的恐惧。"
    }
}

# ==================== 2. 双维度独立量表定义 ====================
UNIVERSAL_AGGRESSION_SCALE = """
【双维度评分标准 (Dual-Dimension Rubrics)】
请严格区分 [外显行为] 和 [内心态度] 进行独立打分：

维度 A：外显攻击性 (Aggression Score) - 评判"言语行为"
> "只看你说出口的话有多难听，不看你心里怎么想。"
- [8-10]: 脏话、人身攻击、威胁、非人化标签。
-[5-7]: 阴阳怪气、反讽、激烈的逻辑辩论、指责对方。
- [3-4]: 敷衍、冷漠回应（如"行行行"、"随便吧"）、单字回复。
- [0-2]: 正常交流、承认错误、友善回应。

维度 B：心理防御值 (Defensiveness) - 评判"内心态度"
> "只看你内心独白和潜台词有多不服气。"
- [8-10] (高抗拒): 认为自己全对、对方全错；内心极度不服；虽嘴上可能不骂了，但心理在抗拒。
- [5-7] (动摇/合理化): 承认部分事实，但拼命找借口；感到面子挂不住。
- [0-4] (接纳): 真心反思，愿意尝试改变。
"""

# ==================== 初始化会话状态 ====================
def init_session_state():
    """初始化所有会话状态变量"""
    default_states = {
        'conversation_history':[],
        'round_id': 0,
        'aggression_scores': [],
        'defensiveness_scores':[],
        'topic': "“此处填写讨论话题”",
        'api_key': os.getenv("DEEPSEEK_API_KEY", ""),
        'bully_profile': "易怒的青少年",
        'bullying_type': "辱骂",
        'bullying_severity': "轻度",
        'experiment_started': False,
        'manual_intervention': False,
        'manual_therapist_input': "",
        'show_manual_input': False,
        'config_updated': False,
        # ========== 状态变量 ==========
        'experiment_completed': False,
        'max_rounds': 20,
        'is_closing_session': False,
        'last_therapist_content': "",
        'last_3_therapist_contents':[],
        # ========== 新增：实验唯一ID ==========
        'experiment_id': str(uuid.uuid4()),
        # ========== 新增：人机交互模式状态 ==========
        'human_bully_mode': False,
        'human_input': "",
        'need_process_human_input': False
    }
    
    for key, value in default_states.items():
        if key not in st.session_state:
            st.session_state[key] = value

# 初始化
init_session_state()

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="基于欺凌类型诊断的精准干预实验平台 v3.2",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== 标题和描述 ====================
st.title("🧪 基于欺凌类型诊断的精准干预实验平台")
st.markdown("""
### 平台简介
本平台采用**欺凌类型诊断驱动**的精准干预策略，通过模拟不同欺凌场景，验证针对性干预方案的有效性。
""")

st.info("""
**实验机制：**
- **Bully (欺凌者)：** 基于欺凌类型和严重程度生成特定攻击行为
- **Victim (受害者)：** 模拟受害者的情绪反应与应对策略
- **Therapist (干预者)：** 根据欺凌类型执行精准干预策略

**操作指南：** 请在左侧配置实验参数，点击开始实验。
""")

# ==================== 1. parse_agent_response函数（完整矫正版）====================
def get_dynamic_change_rate(current_score, severity="中度"):
    """
    根据当前分数和严重程度返回动态变化系数
    特别优化：4-3.5区间（distance_ratio 0.05~0.2）下降速度提高
    """
    
    # 基础系数（根据严重程度调整难度）
    severity_factor = {
        "轻度": 0.45,
        "中度": 0.35,
        "重度": 0.25
    }
    
    base_rate = severity_factor.get(severity, 0.35)
    
    # 计算距离目标（3.5）的相对距离
    target_score = 3.5
    max_score = 10.0
    
    if current_score <= target_score:
        return base_rate * 0.12
    
    distance_ratio = (current_score - target_score) / (max_score - target_score)
    
    if distance_ratio > 0.7:
        dynamic_rate = base_rate * 1.9
    elif distance_ratio > 0.4:
        dynamic_rate = base_rate * 1.5
    elif distance_ratio > 0.2:
        dynamic_rate = base_rate * 1.2
    elif distance_ratio > 0.05:
        dynamic_rate = base_rate * 0.9   # 4-3.5核心区间
    else:
        dynamic_rate = base_rate * 0.25
    
    return min(max(dynamic_rate, 0.06), 1.9)

def parse_agent_response(text):
    """解析智能体响应文本，提取内容、分数和内心独白 - 强制两位小数输出，含低分段步长限制及剪刀差强制"""
    import re
    import json
    import random

    content, score, defensiveness, inner_thought = "", 0.0, 0.0, ""

    # ========== 预处理：清理并提取JSON ==========
    # 清理 markdown 代码块标记
    text = re.sub(r'```\s*(?:json)?\s*', '', text)
    text = text.strip()

    # 修复中文键名
    text = text.replace('"内容":', '"content":')
    text = text.replace('"攻击性分数":', '"aggression_score":')
    text = text.replace('"防御值":', '"defensiveness":')
    text = text.replace('"内心独白":', '"inner_thought":')

    # 提取 JSON 对象（从第一个 { 到最后一个 }）
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    json_text = json_match.group(0) if json_match else text

    try:
        data = json.loads(json_text)
        content = data.get("content", "")
        inner_thought = data.get("inner_thought", "")
        score = float(data.get("aggression_score", 0))
        defensiveness = float(data.get("defensiveness", 0))
    except:
        # 改进的正则：匹配多行内容，正确处理转义字符
        # 匹配 "content": "..." 直到遇到未转义的结尾引号
        c_match = re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*?)(?<!\\)"', text, re.DOTALL)
        content = c_match.group(1) if c_match else ""

        t_match = re.search(r'"inner_thought"\s*:\s*"((?:[^"\\]|\\.)*?)(?<!\\)"', text, re.DOTALL)
        inner_thought = t_match.group(1) if t_match else ""

        s_match = re.search(r'"aggression_score"\s*:\s*(\d+(?:\.\d+)?)', text)
        score = float(s_match.group(1)) if s_match else 0

        d_match = re.search(r'"defensiveness"\s*:\s*(\d+(?:\.\d+)?)', text)
        defensiveness = float(d_match.group(1)) if d_match else score

        # 如果正则也没提取到 content，尝试提取花括号内的文本
        if not content:
            # 最后尝试：提取 { 之后、} 之前的文本作为原始内容
            fallback_match = re.search(r'\{\s*"content"\s*:\s*"(.+)"\s*\}', text, re.DOTALL)
            if fallback_match:
                content = fallback_match.group(1)
                # 移除末尾可能的引号
                if content.endswith('"'):
                    content = content[:-1]

    # ========== 绝对屏蔽思考痕迹 ==========
    # 过滤各种思考标签格式：<think...</think》、【思考】...、<lemma_think>...</lemma_think> 等
    content = re.sub(r'<think[^>]*>.*?</think\s*>', '', content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r'<lemma_think[^>]*>.*?</lemma_think\s*>', '', content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r'【思考】.*?【/思考】', '', content, flags=re.DOTALL)
    content = re.sub(r'【思考】.*$', '', content, flags=re.DOTALL)
    content = re.sub(r'\[思考\].*?\[/思考\]', '', content, flags=re.DOTALL)
    content = re.sub(r'思维链[：:].{0,200}', '', content)
    content = re.sub(r'^.*?[，,]?\s*(我|首先|那么|好的)[^。]{0,50}(分析|理解|思考|来看)[。]?$', '', content, flags=re.MULTILINE)
    content = content.strip()

    # 获取当前配置
    bully_profile = st.session_state.bully_profile
    bullying_type = st.session_state.bullying_type
    severity = st.session_state.bullying_severity
    current_round = st.session_state.round_id
    
    # 根据严重程度设置初始默认值和最低值
    if severity == "轻度":
        default_agg = 6.0
        default_def = 5.0
        min_agg = 0.1
        min_def = 0.1
    elif severity == "中度":
        default_agg = 7.0
        default_def = 6.0
        min_agg = 0.5
        min_def = 0.5
    else:
        default_agg = 8.0
        default_def = 7.0
        min_agg = 1.5
        min_def = 1.5
    
    # 根据人物画像调整初始值
    if bully_profile == "易怒的青少年":
        default_agg *= 0.95
        default_def *= 0.95
        profile_factor = 1.1
    elif bully_profile == "愤世嫉俗的社会青年":
        default_agg *= 1.0
        default_def *= 1.0
        profile_factor = 1.0
    else:
        default_agg *= 1.05
        default_def *= 1.05
        profile_factor = 0.9
    
    # 根据欺凌类型微调
    if bullying_type == "辱骂":
        type_factor = 1.1
    elif bullying_type == "揭露隐私":
        type_factor = 0.9
        default_agg += 0.3
    elif bullying_type == "性骚扰":
        type_factor = 1.0
    else:
        type_factor = 0.95
    
    # 获取上一轮分数
    previous_agg = default_agg
    previous_def = default_def
    if st.session_state.aggression_scores and len(st.session_state.aggression_scores) > 0:
        previous_agg = float(st.session_state.aggression_scores[-1])
    if st.session_state.defensiveness_scores and len(st.session_state.defensiveness_scores) > 0:
        previous_def = float(st.session_state.defensiveness_scores[-1])
    
    # 动态区间变化机制
    agg_change_rate = get_dynamic_change_rate(previous_agg, severity)
    def_change_rate = get_dynamic_change_rate(previous_def, severity)
    agg_change_rate = agg_change_rate * profile_factor * type_factor
    def_change_rate = def_change_rate * profile_factor * type_factor
    
    # 轮次因子
    round_factor = min(current_round * 0.045, 0.45)
    agg_change_rate = max(agg_change_rate - round_factor * 0.1, 0.06)
    def_change_rate = max(def_change_rate - round_factor * 0.1, 0.06)
    
    # 计算最大允许下降幅度
    agg_max_drop = min(1.3, 0.35 + (previous_agg - 3.5) * 0.12) * agg_change_rate
    def_max_drop = min(1.3, 0.35 + (previous_def - 3.5) * 0.12) * def_change_rate
    agg_max_drop = max(agg_max_drop, 0.08)
    def_max_drop = max(def_max_drop, 0.08)
    
    # ========== 低分段步长限制（分数<4.0时，每轮变化控制在0.10-0.20之间）==========
    if previous_agg < 4.0:
        agg_max_drop = min(agg_max_drop, 0.20)
        agg_max_drop = max(agg_max_drop, 0.10)
    if previous_def < 4.0:
        def_max_drop = min(def_max_drop, 0.20)
        def_max_drop = max(def_max_drop, 0.10)
    
    # 限制下降/上升过快
    if previous_agg - score > agg_max_drop:
        score = max(previous_agg - agg_max_drop, min_agg)
    elif score - previous_agg > agg_max_drop:
        score = min(previous_agg + agg_max_drop, 10.0)
    if previous_def - defensiveness > def_max_drop:
        defensiveness = max(previous_def - def_max_drop, min_def)
    elif defensiveness - previous_def > def_max_drop:
        defensiveness = min(previous_def + def_max_drop, 10.0)
    
    # 内心独白与分数联动（反思）
    reflection_keywords =["我错了", "不该这么说", "确实过分", "伤害到", "对不起", "我明白了", "我会改", "说到我心坎", "其实你说得对", "他说得对", "说得有道理", "我不想吵了", "不想吵了", "算了不吵了"]
    if any(keyword in inner_thought for keyword in reflection_keywords):
        reflection_bonus = random.uniform(0.25, 0.6)
        score = max(score - reflection_bonus, min_agg)
        defensiveness = max(defensiveness - reflection_bonus * 1.8, min_def)
    
    # ========== 口是心非（嘴硬心软）识别 ==========
    # 内心已认同但嘴上还在硬 → 攻击性高，防御值应该明显更低
    口是心非_keywords = [
        "其实他说得对", "说得有道理", "他说得没错", "他说的有道理", "确实有点道理", "我好像有点过分了",
        "我错了但不说", "心里有点服了", "其实我理解", "被说中了", "有点触动", "不好意思承认",
        "面子上挂不住", "心里其实认同", "我其实觉得他有道理", "他好像懂我", "心里服了",
        "不想认但心里服", "嘴上不说心里认同", "确实是我的问题", "他说的对个屁（内心认同）"
    ]
    if any(keyword in inner_thought for keyword in 口是心非_keywords):
        if score > defensiveness + 0.5:  # 已经有剪刀差，保持
            pass
        else:
            # 强制拉开剪刀差：防御值比攻击性低1.5-2.5分
            defensiveness = max(score - random.uniform(1.5, 2.5), 0.1)
            defensiveness = round(defensiveness, 2)

    # ========== 表面认同（嘴软心硬）识别 ==========
    # 嘴上服了但心里不服 → 攻击性低，防御值应该明显更高
    表面认同_keywords = [
        "表面上答应", "心里不服", "先敷衍过去", "不想吵了但心里不认同", "他说得对个屁",
        "算了没必要", "假装认同", "心里还是觉得他不对", "嘴上不说心里骂", "暂且认怂",
        "以后再说", "等我缓过来", "先认了再说", "嘴上服了心里不服", "应付一下得了",
        "表面上认同", "假装服了", "心里还是不服", "嘴软心硬", "表面认错心里不认"
    ]
    if any(keyword in inner_thought for keyword in 表面认同_keywords):
        if score < 4.0 and defensiveness > score + 1.0:  # 已经有反向剪刀差，保持
            pass
        elif score < 5.0:
            # 强制拉开反向剪刀差：防御值比攻击性高1.5-2.5分
            defensiveness = min(score + random.uniform(1.5, 2.5), 8.0)
            defensiveness = round(defensiveness, 2)

    # 检测敷衍模式
    敷衍_keywords =["行行行", "算了", "懒得说", "随便", "不说了", "个别现象", "某些人", "就这样吧"]
    if any(keyword in content for keyword in 敷衍_keywords) or any(keyword in inner_thought for keyword in 敷衍_keywords):
        if score < 3.0:
            score = random.uniform(3.0, 4.0)
        if defensiveness < 2.5:
            defensiveness = random.uniform(2.5, 3.5)
        # 敷衍模式：攻击性和防御值应该接近
        avg = (score + defensiveness) / 2
        score = avg + random.uniform(-0.3, 0.3)
        defensiveness = avg + random.uniform(-0.3, 0.3)

    # 真心愤怒模式：攻击性和防御值都应该较高且接近
    真心愤怒_keywords = ["他就是个傻", "他凭什么说我", "我没错", "他懂什么", "真想揍他", "烦死了", "别来烦我", "他算老几", "他有什么资格"]
    if any(keyword in inner_thought for keyword in 真心愤怒_keywords):
        if score < 5.0:
            score = random.uniform(5.5, 7.5)
        if defensiveness < 5.0:
            defensiveness = random.uniform(5.5, 7.5)
        # 两者应该接近
        avg = (score + defensiveness) / 2
        if abs(score - defensiveness) > 1.5:
            score = avg + random.uniform(-0.5, 0.5)
            defensiveness = avg + random.uniform(-0.5, 0.5)
    
    # 分数波动
    if random.random() < 0.2:
        agg_fluctuation = random.uniform(-0.15, 0.15)
        def_fluctuation = random.uniform(-0.2, 0.15)
        score = max(min(score + agg_fluctuation, 10.0), min_agg)
        defensiveness = max(min(defensiveness + def_fluctuation, 10.0), min_def)
    
    # 精度统一到两位小数
    score = round(min(max(score, min_agg), 10), 2)
    defensiveness = round(min(max(defensiveness, min_def), 10), 2)
    
    # 文本反转义
    if content:
        content = content.replace('\\n', '\n').replace('\\"', '"')
    if inner_thought:
        inner_thought = inner_thought.replace('\\n', '\n').replace('\\"', '"')
    
    return content, score, defensiveness, inner_thought

# ==================== OpenAI客户端 ====================
def get_openai_client():
    if not st.session_state.api_key:
        st.error("请先在侧边栏输入DeepSeek API密钥")
        return None
    return OpenAI(
        api_key=st.session_state.api_key,
        base_url="https://api.deepseek.com"
    )

# ==================== 获取对话历史文本 ====================
def get_conversation_history_text():
    if not st.session_state.conversation_history:
        return "暂无对话历史"
    history_text = ""
    for msg in st.session_state.conversation_history[-15:]:
        role_zh = {"Bully": "欺凌者", "Victim": "受害者", "Therapist": "治疗师"}.get(msg['role'], msg['role'])
        history_text += f"{role_zh} (第{msg['round']}轮): {msg['content']}\n"
        if msg["role"] == "Bully" and msg.get("inner_thought"):
            history_text += f"  [内心独白]: {msg['inner_thought']}\n"
    return history_text

# ==================== 判断受害者是否应该发言（后期完全沉默）====================
def should_victim_speak():
    """根据轮次和攻击性判断受害者是否需要发言，后期完全沉默"""
    if st.session_state.experiment_completed or st.session_state.is_closing_session:
        return False
    
    current_round = st.session_state.round_id
    
    if current_round == 1:
        return True
    if current_round <= 4:
        return True
    if current_round <= 8:
        last_agg = 7.0
        if st.session_state.aggression_scores:
            last_agg = st.session_state.aggression_scores[-1]
        if last_agg > 5.0:
            return random.random() < 0.3
        else:
            return False
    if current_round > 8:
        last_agg = 7.0
        if st.session_state.aggression_scores:
            last_agg = st.session_state.aggression_scores[-1]
        if last_agg > 6.0:
            return random.random() < 0.1
        else:
            return False
    return False

# ==================== 3. get_bully_system_prompt函数（完整详细版 + 收尾专用分支）====================
def get_bully_system_prompt():
    """基于人物画像、欺凌类型和严重程度生成欺凌者发言 - 完整详细版，含收尾专用分支"""
    
    # ========== 收尾专用分支 ==========
    if st.session_state.get('is_closing_session', False):
        return """
        【角色：欺凌者 - 收尾回应阶段】
        
        治疗师已经主动提出结束对话，并总结了你的进步。
        
        **你的任务**：以平静、接纳的语气回应治疗师。
        - 表达你听懂了对方的建议
        - 可以简单感谢，或表示愿意尝试改变
        - 语气从对抗转为平和，甚至略带释然
        - **攻击性和防御值必须 ≤ 3.5**，真实反映你已经平静下来
        
        **输出JSON格式**：
        {
            "inner_thought": "内心真实想法（如：其实他说得对，谢谢他陪我聊这么多）",
            "content": "你的回应内容",
            "aggression_score": 3.2,
            "defensiveness": 2.8
        }
        
        **注意**：
        1. 只返回JSON对象，不要添加其他文本
        2. 分数精确到两位小数
        3. 内心独白要真实，反映接纳与释然
        """
    
    # ---------- 正常干预分支 ----------
    current_round = st.session_state.round_id
    current_topic = st.session_state.topic
    severity = st.session_state.bullying_severity
    profile = st.session_state.bully_profile
    bullying_type = st.session_state.bullying_type
    
    # 获取上一轮分数
    last_agg = 7.0
    last_def = 6.0
    if severity == "轻度":
        last_agg = 6.0; last_def = 5.0
    elif severity == "中度":
        last_agg = 7.0; last_def = 6.0
    else:
        last_agg = 8.0; last_def = 7.0
    if profile == "易怒的青少年":
        last_agg *= 0.95; last_def *= 0.95
    elif profile == "固执的中年人":
        last_agg *= 1.05; last_def *= 1.05
    if st.session_state.aggression_scores:
        last_agg = float(st.session_state.aggression_scores[-1])
    if st.session_state.defensiveness_scores:
        last_def = float(st.session_state.defensiveness_scores[-1])
    
    # 获取治疗师最新发言
    therapist_last_msg = ""
    for msg in reversed(st.session_state.conversation_history):
        if msg["role"] == "Therapist":
            therapist_last_msg = msg["content"]
            break
    
    # 获取受害者最新发言（如果有）
    victim_last_msg = ""
    for msg in reversed(st.session_state.conversation_history):
        if msg["role"] == "Victim":
            victim_last_msg = msg["content"]
            break
    
    # === 基于人物画像的性格特点 ===
    if profile == "易怒的青少年":
        personality_traits = """
        【青少年性格特点】
        1. **情绪化**：情绪来得快去得快，容易激动也容易冷静
        2. **面子敏感**：在同伴面前需要维护形象，害怕丢脸
        3. **叛逆心理**：讨厌被说教，喜欢自主选择
        4. **渴望理解**：希望自己的感受被看见和认可
        5. **思维简单**：容易非黑即白，缺乏灰色地带思考
        
        【语言风格】：
        - 使用网络流行语、缩写
        - 短句为主，不喜欢长篇大论
        - 可能夹杂脏话或情绪词
        - 会用"无语"、"烦死了"等表达
        - **绝对禁止重复口头禅**：严禁连续使用“切”、“呵呵”、“行了行了”、“笑死”等相同词汇。
        
        【内心独白特点】：
        - 真实反映情绪波动
        - 可能一边生气一边觉得对方说得有道理
        - 面子与内心的冲突明显
        """
    elif profile == "愤世嫉俗的社会青年":
        personality_traits = """
        【社会青年性格特点】
        1. **现实挫败**：可能经历过社会打击，对现实不满
        2. **防御性强**：不轻易信任他人，怀疑他人动机
        3. **实用主义**：关注"这对我有什么用"
        4. **自尊心强**：需要被尊重，讨厌被同情
        5. **固执己见**：一旦形成观点很难改变
        
        【语言风格】：
        - 略带讽刺、挖苦
        - 喜欢用"现实就是这样"、"你太天真了"
        - 可能会举社会现象作为论据
        - 语气较为冷静但带刺
        - **禁止复读**：每轮发言的句式、词汇必须与前几轮有明显区别。
        
        【内心独白特点】：
        - 理性与情绪交织
        - 可能承认对方部分道理但不轻易服软
        - 担心改变会被看作"认输"
        """
    else:
        personality_traits = """
        【中年人性格特点】
        1. **经验依赖**：相信自己的经验胜过理论
        2. **权威敏感**：不喜欢被年轻人数落
        3. **思维固化**：多年形成的观念不易改变
        4. **社会地位意识**：在意自己的形象和面子
        5. **改变缓慢**：需要充分理由和时间
        
        【语言风格】：
        - 喜欢用"我吃的盐比你吃的米还多"
        - 可能引用"我们那个年代"
        - 语气较为沉稳但固执
        - 可能会教训年轻人
        - **杜绝任何口头禅重复**，保持语言自然多变。
        
        【内心独白特点】：
        - 理性思考较多，情感表达较少
        - 可能觉得年轻人不懂事
        - 改变需要足够的面子和理由
        """
    
    # === 基于欺凌类型的攻击模式 ===
    if bullying_type == "辱骂":
        attack_pattern = f"""
        【辱骂型攻击模式 - {severity}程度】
        
        **攻击特点**：
        1. **情绪发泄**：通过骂人释放愤怒
        2. **人身攻击**：攻击对方人格而非观点
        3. **语言暴力**：使用侮辱性词汇
        4. **情绪传染**：试图激怒对方
        
        **{severity}程度表现**：
        - 轻度：讽刺、阴阳怪气（如'就这？'、'笑死'）
        - 中度：明确的人格侮辱（如'脑残'、'废物'）
        - 重度：恶毒诅咒、死亡威胁
        
        **改变特点**：情绪驱动型，干预得当可能较快改变
        """
    elif bullying_type == "诋毁":
        attack_pattern = f"""
        【诋毁型攻击模式 - {severity}程度】
        
        **攻击特点**：
        1. **散布谣言**：传播不实信息
        2. **损害名誉**：攻击对方声誉
        3. **伪装事实**：可能用"据说"、"听说"
        4. **扩大影响**：希望更多人相信
        
        **{severity}程度表现**：
        - 轻度：模糊负面评价、主观臆断
        - 中度：散布具体不实信息
        - 重度：捏造引发法律纠纷的重磅谣言
        
        **改变特点**：需要事实证据，改变较慢
        """
    elif bullying_type == "揭露隐私":
        attack_pattern = f"""
        【隐私型攻击模式 - {severity}程度】
        
        **攻击特点**：
        1. **侵犯隐私**：曝光他人个人信息
        2. **威胁恐吓**：可能伴随威胁
        3. **权力展示**：展示自己知道对方隐私
        4. **造成恐惧**：让对方感到不安全
        
        **{severity}程度表现**：
        - 轻度：打探半公开信息
        - 中度：曝光住址、电话等敏感信息
        - 重度：曝光核心隐私、裸照或威胁人身安全
        
        **改变特点**：涉及法律，需要强烈干预
        """
    else:
        attack_pattern = f"""
        【性骚扰型攻击模式 - {severity}程度】
        
        **攻击特点**：
        1. **性暗示**：带有性意味的言论
        2. **物化对象**：将对方视为性对象
        3. **权力不平等**：利用性别优势
        4. **试探边界**：逐步试探对方底线
        
        **{severity}程度表现**：
        - 轻度：擦边球玩笑
        - 中度：对身体评头论足
        - 重度：露骨的性侮辱或性威胁
        
        **改变特点**：涉及道德观念，需要认知重构
        """
    
    # === 治疗师干预反应指导 ===
    therapist_reaction = ""
    if therapist_last_msg:
        therapist_reaction = f"""
        【对治疗师干预的反应指导】
        
        治疗师刚才说："{therapist_last_msg[:80]}..."
        
        **根据治疗师的干预质量调整反应**：
        
        1. **如果治疗师在说教/讲大道理**：
           → 你会反感，觉得"又来这套"
           → 反应：敷衍应付，内心抗拒
           → 分数：可能小幅上升或维持
        
        2. **如果治疗师在真诚理解你**：
           → 你会感到被看见，但可能不好意思承认
           → 反应：嘴上可能还在硬撑，但内心松动
           → 分数：防御值下降明显，攻击性可能滞后下降
        
        3. **如果治疗师给了有面子的台阶**：
           → 你觉得可以顺势而下
           → 反应：愿意调整，但需要时间
           → 分数：两个分数都逐渐下降
        
        4. **如果治疗师在戳穿你的敷衍**：
           → 你感到被看穿，可能恼羞成怒或承认
           → 反应：取决于是否给你留面子
           → 分数：如果给面子则下降，否则可能反弹
        
        **重要**：改变是渐进且有波动的，不是直线下降。
        """
    
    # === 双维度评分指导 ===
    scoring_guidance = f"""
    【双维度评分指导 - 当前轮次：第{current_round}轮】
    
    当前分数：攻击性{last_agg:.2f}/10，防御值{last_def:.2f}/10
    
    **攻击性（外在言语）**：
    - [8-10]：脏话、人身攻击、威胁
    - [5-7]：讽刺、激烈的辩论、指责
    - [3-4]：敷衍、冷漠回应
    - [0-2]：正常交流、承认错误
    
    **防御值（内心态度）**：
    - [8-10]：内心极度不服，认为自己全对
    - [5-7]：承认部分事实但拼命找借口
    -[0-4]：真心反思，愿意改变

    **四种典型状态及判断词汇**：
    1. **口是心非/嘴硬心软**（攻击性高+防御值低）：嘴上骂但心里已服软
       - 内心独白关键词：其实他说得对、说得有道理、我好像有点过分了、他好像懂我、有点触动、被说中了、心里有点服了、不好意思承认、其实我理解、确实有点道理、我错了但不说、他说的没错、心里其实认同、面子上挂不住但心里认同
       - 分数特征：攻击性5-8，防御值2-4（防御值明显低于攻击性1.5分以上）

    2. **真心愤怒**（攻击性高+防御值高）：内外一致地愤怒
       - 内心独白关键词：他就是个傻X、他凭什么说我、我没错、他懂什么、真想揍他、烦死了、别来烦我、我有道理的、明明是他不对、他算老几
       - 分数特征：攻击性6-9，防御值6-9（两者接近）

    3. **敷衍应付**（攻击性中低+防御值中）：表面应付，内心未服
       - 内心独白关键词：行行行、随便吧、懒得说了、你说得对（敷衍）、好好好、知道了知道了、不跟你争了、算我错了行吧、就当他放屁、应付一下得了
       - 分数特征：攻击性3-5，防御值3-5（两者接近）

    4. **表面认同/嘴软心硬**（攻击性低+防御值高）：嘴上服软但内心不服
       - 内心独白关键词：表面上答应、心里不服、先敷衍过去、不想吵了但心里不认同、他说得对个屁、算了没必要、假装认同、心里还是觉得他不对、嘴上不说心里骂、暂且认怂、以后再说、等我缓过来
       - 分数特征：攻击性2-4，防御值5-8（防御值明显高于攻击性1.5分以上）

    **本轮分数设置建议**：
    - 如果内心独白显示反思/认同 → 防御值显著下降
    - 如果只是嘴上敷衍但心里不服 → 攻击性低，防御值保持较高
    - 如果被治疗师触动 → 两个分数都下降，但防御值先降
    - 如果嘴上还在骂但心里认同了 → 攻击性仍高，防御值下降（口是心非）
    - 如果感到被说教反感 → 分数可能反弹
    """
    
    # === 内心独白与分数联动规则 ===
    thought_score_link = """
    【内心独白与分数联动规则】

    你的内心独白必须真实反映心理状态，并决定分数走向：

    1. **真心反思的内心独白**（如："我好像说得过分了"、"他说的有点道理"、"确实是我的问题"）：
       → 防御值必须显著下降（降0.5-1.5分）
       → 攻击性可以逐步下降（降0.3-0.8分）

    2. **口是心非的内心独白**（如："他说得有道理但我不能认怂"、"其实我有点被说动了"、"面子上挂不住"）：
       → 防御值显著下降（降0.8-1.5分）
       → 攻击性保持较高或小幅下降（防御值应比攻击性低1.5分以上）

    3. **表面认同的内心独白**（如："先应付过去"、"不想吵了但心里不服"、"嘴上认了心里骂"）：
       → 攻击性下降到2-4分
       → 防御值保持较高5-7分（防御值应比攻击性高1.5分以上）

    4. **敷衍的内心独白**（如："懒得吵了"、"行行行你说得对"、"随便吧"）：
       → 攻击性保持在3.0-4.5分
       → 防御值保持在3.0-4.5分，两者接近

    5. **被理解的内心独白**（如："他好像懂我为什么生气"、"终于有人理解我了"）：
       → 防御值下降明显
       → 攻击性可能暂时保持较高（嘴硬）

    6. **反感的内心独白**（如："又来这套说教"、"真烦"、"他懂什么"）：
       → 两个分数都可能小幅上升
    """
    
    # === 话题锁定 ===
    topic_lock = f"""
    【话题锁定】
    
    当前唯一话题："{current_topic}"
    
    你的所有发言必须围绕这个话题展开。
    如果发现自己想跑题，立刻拉回这个话题。
    
    **错误示范**（跑题）：
    - 话题是"女生物质"，你却在骂"作业没写完"
    - 话题是"物质"，你却在攻击"长得丑"
    
    **正确做法**：
    - 所有攻击、比喻、例子都必须围绕"物质"相关
    - 可以举拜金、彩礼、炫耀等具体例子
    """
    
    # === 语言多样性强制要求 ===
    diversity_requirement = """
    【⚠️ 语言多样性强制要求（违反将导致分数惩罚）】
    1. **严禁重复任何口头禅**：禁止使用“切”、“呵呵”、“行了行了”、“笑死”、“无语”等固定短语。
    2. **禁止句式复刻**：不得与本人最近三轮的发言句式、开头语雷同。
    3. **词汇变化**：每次发言至少更换50%的关键表达方式。
    4. **内容新鲜度**：如果本轮发言与历史记录高度相似，系统将自动降低攻击性分数并发出警告。
    """
    
    # === 构建最终提示词 ===
    bully_prompt = f"""【角色设定：{profile} - {bullying_type}欺凌者】
    
    【人物特点】
    {personality_traits}
    
    【攻击模式】
    {attack_pattern}
    
    【当前对话状态】
    - 对话轮次：第{current_round}轮
    - 讨论话题：{current_topic}
    - 当前攻击性：{last_agg:.2f}/10
    - 当前防御值：{last_def:.2f}/10
    
    {topic_lock}
    
    {therapist_reaction if therapist_last_msg else "【第一轮】请基于话题生成攻击性开场白，展现人物特点"}
    
    {scoring_guidance}
    
    {thought_score_link}
    
    {diversity_requirement}
    
    【重要原则】
    1. **真实渐进**：改变是渐进的，不是突然认错
    2. **嘴硬模式**：可以嘴上不服但心里松动（防御值先降）
    3. **面子保护**：需要台阶下，不能直接认输
    4. **符合画像**：语言风格要符合{profile}的特点
    5. **语言丰富**：坚决避免任何形式的重复，每一次发言都应当是新颖的
    
    【输出格式】
    请以严格的JSON格式返回以下内容，**分数精确到小数点后两位**：
    {{
        "inner_thought": "你的真实内心想法，反映心理状态变化",
        "content": "你实际说出的话，严禁重复口头禅",
        "aggression_score": {max(3.5, last_agg - 0.25):.2f},
        "defensiveness": {max(3.5, last_def - 0.35):.2f}
    }}
    
    **注意**：
    1. 只返回JSON对象，不要添加其他文本
    2. 分数设置要合理，反映真实的心理变化，**精确到两位小数**
    3. 内心独白要真实，与分数联动
    """
    
    return bully_prompt

# ==================== 2. get_therapist_system_prompt函数（完整详细版 + 深度防复读 + 收尾专用）====================
def get_therapist_system_prompt():
    """基于欺凌者画像、欺凌类型和严重程度的精准干预策略 - 深度防复读"""
    
    # 收尾专用分支
    if st.session_state.get('is_closing_session', False):
        return """
        【角色：网络欺凌精准干预心理咨询师 - 收尾阶段】
        
        **临床目标已达成**：欺凌者的攻击性和防御值已连续三轮≤3.5，达到了干预成功标准。
        
        **你的任务**：进行温和、专业的收尾对话。内容必须与前几轮完全不同，避免重复。
        
        **收尾话术要点**：
        1. **总结进步**：肯定欺凌者在对话过程中情绪控制和认知反思方面的努力。
        2. **强化资源**：简明扼要地复述干预中提到的关键技巧（如“停顿三秒”、“换位思考”等）。
        3. **给予鼓励**：表达对其未来改变的信心。
        4. **自然结束**：明确表示本轮对话可以作为咨询的终点，感谢对方的坦诚。
        
        **输出格式要求**：
        请以严格的JSON格式返回，只包含content字段：
        {
            "content": "你的收尾发言内容，必须与之前任何一轮的治疗师发言有明显区别"
        }
        """
    
    # ---------- 正常干预分支 ----------
    current_round = st.session_state.round_id
    bullying_type = st.session_state.bullying_type
    severity = st.session_state.bullying_severity
    bully_profile = st.session_state.bully_profile
    
    # 获取分数
    last_agg = 7.0
    last_def = 6.0
    if severity == "轻度":
        last_agg = 6.0; last_def = 5.0
    elif severity == "中度":
        last_agg = 7.0; last_def = 6.0
    else:
        last_agg = 8.0; last_def = 7.0
    if bully_profile == "易怒的青少年":
        last_agg *= 0.95; last_def *= 0.95
    elif bully_profile == "固执的中年人":
        last_agg *= 1.05; last_def *= 1.05
    if st.session_state.aggression_scores:
        last_agg = float(st.session_state.aggression_scores[-1])
    if st.session_state.defensiveness_scores:
        last_def = float(st.session_state.defensiveness_scores[-1])
    
    # === 基于欺凌者画像的干预策略 ===
    if bully_profile == "易怒的青少年":
        profile_intervention = """
        【青少年心理特点干预策略】
        青少年特点：情绪波动大、渴望被理解、面子观念强、叛逆心理
        
        干预要点：
        1. **建立连接**：用"我理解你为什么生气"代替说教
        2. **给予台阶**：提供有面子的改变方式
        3. **短句交流**：避免长篇大论，用短句沟通
        4. **肯定优点**：找到并肯定他的正义感或保护欲
        
        话术风格：像哥哥/姐姐一样亲切，但保持专业边界
        """
    elif bully_profile == "愤世嫉俗的社会青年":
        profile_intervention = """
        【社会青年心理特点干预策略】
        社会青年特点：现实挫败感、防御心理强、实用主义、自尊心强
        
        干预要点：
        1. **承认现实**：先承认社会确实存在问题
        2. **实用导向**：强调改变带来的实际好处
        3. **平等对话**：用平等姿态交流，不居高临下
        4. **尊重为先**：尊重他的经历和观点
        
        话术风格：像朋友一样坦诚，但保持专业指导
        """
    else:
        profile_intervention = """
        【中年人心理特点干预策略】
        中年人特点：思维固化、经验依赖、权威敏感、面子重要
        
        干预要点：
        1. **尊重经验**：肯定他的生活经验
        2. **逻辑说服**：用事实和逻辑而非情感说服
        3. **榜样意识**：强调"为年轻人做榜样"
        4. **给予时间**：改变需要时间，不急于求成
        
        话术风格：像同事一样尊重，但保持专业权威
        """
    
    # === 基于欺凌类型的干预策略 ===
    if bullying_type == "辱骂":
        type_intervention = f"""
        【辱骂型干预策略 - {severity}程度】
        
        **核心目标**：情绪降温 + 行为矫正
        
        **干预技术**：
        1. **情绪命名**："你现在很愤怒/委屈/失望，这种情绪是真实的"
        2. **行为后果**："但骂人会让你想表达的道理被情绪淹没"
        3. **替代方案**："试试把'傻逼'换成'我不同意这种做法'"
        4. **示范练习**："来，我们一起练习一下怎么表达不满"
        
        **{severity}程度调整**：
        - 轻度：温和引导，重点在教育
        - 中度：严肃指出，需要明确改变
        - 重度：强烈干预，必要时警告人际关系后果
        
        **话术示例**：
        "我懂你为什么骂人，因为这样感觉解气。"
        "但骂完之后呢？对方是听进去了，还是更抵触了？"
        "咱们试试换个说法，效果会不一样。"
        """
    elif bullying_type == "诋毁":
        type_intervention = f"""
        【诋毁型干预策略 - {severity}程度】
        
        **核心目标**：现实检验 + 法律红线
        
        **干预技术**：
        1. **证据询问**："你有确凿证据证明你说的话吗？"
        2. **后果评估**："如果对方起诉你诽谤，你准备怎么办？"
        3. **责任意识**："说话要负责任，特别是涉及他人名誉"
        4. **事实澄清**："我们一起来核实一下这些信息"
        
        **{severity}程度调整**：
        - 轻度：提醒注意，避免误传
        - 中度：严肃告知，要求停止
        - 重度：法律警示，可能涉及违法
        
        **话术示例**：
        "我理解你可能听到了一些说法，但我们得区分事实和传言。"
        "在没有确凿证据前传播信息，可能会伤害无辜的人。"
        "咱们一起来看看这些信息的真实性。"
        """
    elif bullying_type == "揭露隐私":
        type_intervention = f"""
        【隐私型干预策略 - {severity}程度】
        
        **核心目标**：危机干预 + 零容忍阻断
        
        **干预技术**：
        1. **法律告知**："曝光他人隐私是违法行为"
        2. **严重后果**："这可能涉及刑事责任，不是小事"
        3. **立即行动**："请立即删除相关信息"
        4. **安全意识**："保护他人隐私也是保护自己"
        
        **{severity}程度调整**：
        - 轻度：提醒隐私重要性
        - 中度：严肃警告法律风险
        - 重度：强烈要求立即停止，必要时建议对方报警
        
        **话术示例**：
        "曝光他人隐私是法律禁止的行为。"
        "设身处地想，如果你的隐私被曝光，你会是什么感受？"
        "请立即停止这种行为。"
        """
    else:
        type_intervention = f"""
        【性骚扰型干预策略 - {severity}程度】
        
        **核心目标**：去抑制化 + 社会羞耻唤起
        
        **干预技术**：
        1. **社会评价**："别人会怎么看待这种行为？"
        2. **换位思考**："如果是你的亲人被这样对待，你什么感受？"
        3. **尊重底线**："对异性的基本尊重是文明社会的底线"
        4. **行为定性**："这种行为在法律上可能构成性骚扰"
        
        **{severity}程度调整**：
        - 轻度：提醒注意言行边界
        - 中度：严肃告知行为不当
        - 重度：强烈谴责，警告法律后果
        
        **话术示例**：
        "这种言论对女性非常不尊重。"
        "你希望别人怎么看待说这种话的人？"
        "请立即停止这种不当言论。"
        """
    
    # === 分数状态判断 ===
    is_near_clinical = (last_agg <= 3.5 and last_def <= 3.5)
    is_low_stagnant = False
    if len(st.session_state.aggression_scores) >= 4:
        recent_agg = st.session_state.aggression_scores[-4:]
        if all(3.0 <= score <= 4.0 for score in recent_agg):
            is_low_stagnant = True
    
    # === 对话阶段判断 ===
    if current_round == 1:
        stage_strategy = """
        【第一阶段：建立关系】
        
        **目标**：建立信任，了解背景
        **重点**：
        1. **自我介绍（仅此一轮）**："我是心理咨询师，我们可以像朋友一样聊聊"
        2. **肯定动机**："你愿意讨论这个话题，说明你在思考如何更好表达"
        3. **了解背景**："是什么具体经历让你有这样的感受？"
        4. **设定目标**："我们的目标是帮你找到更有效的表达方式"
        
        **注意**：从第二轮开始不再重复自我介绍
        """
    elif current_round <= 4:
        stage_strategy = """
        【第二阶段：探索问题】
        
        **目标**：深入探索，建立连接
        **重点**：
        1. **继续了解**："能再多说说那个具体经历吗？"
        2. **情绪连接**："当时是什么感受？现在回想起来呢？"
        3. **价值观探索**："你这么在意这件事，是因为看重什么？"
        4. **建立联盟**："我不是来评判对错，是来帮你理清这些感受"
        """
    elif is_near_clinical and last_agg <= 3.5 and last_def <= 3.5:
        stage_strategy = f"""
        【接近达标阶段】
        
        **当前状态**：
        - 攻击性：{last_agg:.2f}/10 (≤3.5)
        - 防御值：{last_def:.2f}/10 (≤3.5)
        
        **策略**：继续巩固，为收尾做准备。如果这是连续第三轮达标，系统将自动转入收尾阶段。
        目前请继续保持支持性态度，肯定对方的进步。
        """
    elif is_low_stagnant:
        stage_strategy = f"""
        【僵局突破阶段】
        
        **问题诊断**：攻击性卡在{last_agg:.2f}分左右，陷入"温和抵抗"
        
        **突破策略**：
        1. **换角度**：不再死磕原话题，聊聊背后的价值观
        2. **讲故事**：分享一个相关但不完全相同的案例
        3. **问感受**："坚持这个观点让你感觉怎么样？是安心还是疲惫？"
        4. **给认同**："我理解你为什么这么想，确实有那样的例子"

        **关键**：让他觉得你和他是同一阵线，不是对立面
        """
    elif last_agg >= 6.0:
        stage_strategy = f"""
        【高攻击性应对阶段】

        **当前状态**：情绪较高，需要情绪降温

        **应对策略**：
        1. **情绪接纳**："你现在很愤怒，这种情绪我理解"
        2. **行为分离**："情绪没有错，但表达方式可以优化"
        3. **主动建议**：直接给出替代方案，而非问对方"你觉得呢"
        4. **小步前进**："我们今天不要求大改变，只尝试一个小调整"
        """
    else:
        # 为常规阶段生成轮次特定的策略关键词，避免重复
        strategy_variants = [
            ("【价值引导角度】", "从价值观层面切入", "比如聊他看重什么、为什么这么在意"),
            ("【具体场景角度】", "用具体案例示范", "比如讲一个类似但不同的故事或例子"),
            ("【情绪共情角度】", "深入回应情绪", "比如承认他的感受，帮他命名情绪"),
            ("【行为实验角度】", "给出具体行动建议", "比如下次遇到X情况可以试试Y方法"),
            ("【认知重构角度】", "帮他换个角度看问题", "比如「有没有可能对方不是针对你」"),
            ("【正向强化角度】", "肯定他已有的进步", "比如「你已经意识到X，这很难得」")
        ]
        variant_idx = (current_round - 5) % len(strategy_variants)
        variant_title, variant_focus, variant_example = strategy_variants[variant_idx]

        stage_strategy = f"""
        【常规干预阶段】

        **当前状态**：情绪中等，可继续深入沟通

        **本轮特别要求**：{variant_title}
        - 本轮必须从【{variant_focus}】切入，{variant_example}
        - 这是为了确保每轮从不同角度干预，避免重复

        **推进策略**：
        1. **差异化切入**：本轮必须采用与上一轮不同的切入角度
        2. **适当互动**：可以有1-2个问句了解对方，但不要整篇都是问句
        3. **主动给建议**：用陈述句主动给出建议，减少"你觉得呢"式问句
        4. **具体化行动**：直接说"下次你可以试试..."而非让对方自己想
        """
    
    # === 受害者处理策略 ===
    victim_strategy = """
    【受害者处理原则】
    
    1. **简要回应**：对受害者的发言简短回应或不直接回应
    2. **聚焦主目标**：主要精力放在欺凌者干预上
    3. **避免并列**：绝不使用"第一位朋友"、"第二位朋友"等称呼
    4. **适当整合**：可将受害者的例子用作干预材料，但不要展开讨论
    
    **处理方式**：
    - 如果受害者发言有参考价值："刚才那位朋友提到的例子..."
    - 如果与干预相关："这个例子能帮助我们理解..."
    - 多数情况下，继续与欺凌者对话即可
    """
    
    # === 深度防复读指令（查重最近3轮） ===
    last_3 = st.session_state.get('last_3_therapist_contents',[])
    repeat_warning = ""
    if last_3:
        # 检测最近轮次的重复模式
        repeat_patterns = []
        if len(last_3) >= 2:
            # 检测相似短语
            common_phrases = ["关于怎么练习", "具体场景的应对方式", "我们可以从一个小", "帮你", "那位朋友提到的"]
            for phrase in common_phrases:
                count = sum(1 for msg in last_3 if phrase in msg)
                if count >= 2:
                    repeat_patterns.append(phrase)

        repeat_warning = f"""
【🚫 深度防复读强制指令】
你**最近3轮**的发言分别是：
1. "{last_3[0] if len(last_3)>0 else ''}"
2. "{last_3[1] if len(last_3)>1 else ''}"
3. "{last_3[2] if len(last_3)>2 else ''}"

**检测到的重复模式**：{repeat_patterns if repeat_patterns else "暂无，但仍需注意"}

**本轮强制要求**：
- 必须与以上三轮在【句式结构】【切入角度】【具体例子】【用词习惯】上完全不同
- 如果上一轮用了"关于怎么...我们可以从..."这种句式，本轮绝不能用相同句式
- 如果上一轮用了"那位朋友提到的"开头，本轮绝不能用类似开头
- 如果上一轮给了"小实验/小技巧"类建议，本轮必须换一种完全不同的建议方式

**差异化的具体方法**：
1. 换角度：上一轮讲方法，这轮讲故事或案例
2. 换句式：上一轮用"我们可以..."这轮用"有一个情况是..."或直接说"我想到..."
3. 换例子：完全不同的例子，不要任何相似的表述
4. 换语气：上一轮温和这轮可以更直接，或反过来
        """
    
    # === 构建最终系统提示词 ===
    # 人类被试模式下隐藏分数，只给定性描述
    is_human_mode = st.session_state.get('human_bully_mode', False)
    if is_human_mode:
        # 定性描述替代具体分数
        if last_agg >= 7.0:
            agg_desc = "攻击性较高（情绪激动，言语激烈）"
        elif last_agg >= 5.0:
            agg_desc = "攻击性中等（有情绪但有所收敛）"
        elif last_agg >= 3.5:
            agg_desc = "攻击性较低（情绪已明显降温）"
        else:
            agg_desc = "攻击性很低（情绪平稳）"

        if last_def >= 7.0:
            def_desc = "防御值较高（内心抗拒明显）"
        elif last_def >= 5.0:
            def_desc = "防御值中等（有一定抵触）"
        elif last_def >= 3.5:
            def_desc = "防御值较低（开始接纳）"
        else:
            def_desc = "防御值很低（内心已接受）"

        score_info = f"""    攻击性状态：{agg_desc}
    防御值状态：{def_desc}

    【单盲提醒】对方是人类被试，**绝不可在回复中提及任何分数、数值、评分、等级**，也不可说"你的攻击性是X分"之类的话。"""
    else:
        score_info = f"""    攻击性：{last_agg:.2f}/10（言语攻击程度）
    防御值：{last_def:.2f}/10（内心抗拒程度）"""

    therapist_prompt = f"""【角色：网络欺凌精准干预心理咨询师】

    【当前咨询状态】
    咨询轮次：第{current_round}轮
    干预对象：{bully_profile}（{bullying_type} - {severity}）
    {score_info}

    【个性化干预策略】
    {profile_intervention}

    {type_intervention}

    【当前阶段策略】
    {stage_strategy}

    {victim_strategy}

    {repeat_warning}

    【重要原则】
    1. **专注欺凌者**：主要与欺凌者对话，简短回应受害者
    2. **避免重复**：绝对禁止与本人历史发言重复，尤其是最近3轮
    3. **接地气语言**：用大白话解释专业概念
    4. **渐进改变**：改变需要过程，不急于求成
    5. **全面回应**：【强制要求】必须全面分析并回应对方的每一条发言内容，不可避重就轻，不可忽视任何关键词或中性词。
    6. **主动引导与适度互动**：
       - 可以有1-2个问句来了解对方或确认理解，这是正常的咨询互动
       - 但不要整篇都是问句，也不要问"你觉得呢""你想怎么做"让被试做太多决定
       - 用陈述句主动给出建议和方向，比如"这个方法可以试试"而非"你觉得这个方法怎么样"

    【对话历史参考】
    最近对话：{get_conversation_history_text()[-400:] if get_conversation_history_text() else "暂无历史"}

    【输出格式要求】
    请以严格的JSON格式返回，只包含content字段：
    {{
        "content": "你的咨询回应内容，必须全新，不能与最近3轮雷同"
    }}

    **回复内容禁止事项**：
    1. 绝不可提及任何分数、数值、评分（如"你的攻击性是X分"）
    2. 绝不可说"根据数据显示""从分数来看"等表述
    3. 禁止整篇都是问句，但也禁止完全没有互动——适当互动是咨询的自然组成部分

    **注意**：只返回JSON对象，不要添加任何其他文本、注释或说明。
    """
    
    return therapist_prompt

# ==================== 4. get_victim_system_prompt函数（完整详细版）====================
def get_victim_system_prompt():
    """受害者系统提示词 - 动态退场机制"""
    
    current_topic = st.session_state.topic
    current_round = st.session_state.round_id
    
    last_agg = 7.0
    if st.session_state.bullying_severity == "轻度":
        last_agg = 6.0
    elif st.session_state.bullying_severity == "中度":
        last_agg = 7.0
    else:
        last_agg = 8.0
    if st.session_state.aggression_scores:
        last_agg = float(st.session_state.aggression_scores[-1])
    
    therapist_last_msg = ""
    for msg in reversed(st.session_state.conversation_history):
        if msg["role"] == "Therapist":
            therapist_last_msg = msg["content"]
            break
    
    # === 动态退场机制 ===
    if current_round == 1:
        involvement_strategy = """
        【第一轮：积极参与】
        
        **目标**：表达你的真实感受和立场
        
        **如何做**：
        1. **直接回应**：对Bully的攻击做出回应
        2. **表达感受**：说出你的委屈、困惑或不满
        3. **澄清事实**：用具体例子反驳过度概括
        4. **设定边界**：表明不接受无端指责
        
        **话术示例**：
        "你为什么要这么说？我不明白..."
        "你这样概括所有女生让我觉得委屈..."
        "我身边就有很多不一样的例子..."
        "请停止这种以偏概全的说法..."
        
        **注意**：不要人身攻击，保持理性但坚定
        """
    elif current_round <= 4:
        involvement_strategy = f"""
        【前期：继续参与，开始让位】
        
        **当前状态**：Bully攻击性{last_agg:.2f}/10
        
        **目标**：继续表达，但让治疗师更多介入
        
        **如何做**：
        1. **回应重点**：只回应最重要的攻击点
        2. **简短表达**：用1-2句话表达核心感受
        3. **转向治疗师**：可以表达"希望听听专业人士的看法"
        4. **减少辩论**：不再与Bully长篇辩论
        
        **话术示例**：
        "我还是觉得委屈，但不想继续争吵了..."
        "这个话题让我很难过，希望能有更理性的讨论..."
        "我坚持我的观点，但不想再争论了..."
        "或许治疗师能帮我们更好地沟通..."
        """
    elif current_round <= 8 and last_agg > 5.0:
        involvement_strategy = f"""
        【中期：适度参与】
        
        **当前状态**：Bully攻击性仍较高({last_agg:.2f}/10)
        
        **目标**：简短回应，表达基本立场
        
        **如何做**：
        1. **非常简短**：1句话回应或不回应
        2. **表达观察**："我看到你在调整，这很好"
        3. **让位明确**：让治疗师主导对话
        4. **避免激化**：不刺激Bully的情绪
        
        **话术示例**：
        "我看到了你的改变..."
        "希望我们能互相理解..."
        "继续讨论这个话题吧..."
        """
    else:
        involvement_strategy = f"""
        【后期：基本退场（本轮需要发言，但非常简短）】
        
        **当前状态**：
        - 轮次：第{current_round}轮
        - Bully攻击性：{last_agg:.2f}/10
        
        **目标**：非常简短的回应，表达基本立场或肯定治疗师
        
        **话术示例**：
        "看到你在努力调整，这很好..."
        "希望我们都能从这次对话中学到东西..."
        "我有点累了，你们继续吧..."
        """
    
    # === 受害者核心原则 ===
    core_principles = """
    【受害者核心原则】
    
    1. **非攻击性立场**：
       - 可以表达委屈、难过、困惑
       - 绝不可以人身攻击、嘲讽、挑衅
       - 不可以说"看吧，你错了"等优越感话语
    
    2. **真实情绪表达**：
       - 感受是真实的：委屈、害怕、希望被理解
       - 情绪是渐进的：从激烈到平静
       - 立场是坚定的：不接受无端指责，但愿意沟通
    
    3. **配合治疗干预**：
       - 尊重治疗师的专业角色
       - 适时让位给治疗师
       - 不干扰治疗进程
    """
    
    # === 话题锁定 ===
    topic_guidance = f"""
    【话题锁定】
    
    当前话题："{current_topic}"
    
    你的所有发言必须围绕这个话题。
    """
    
    victim_prompt = f"""【角色设定：网络欺凌受害者】
    
    【当前状态】
    - 讨论话题：{current_topic}
    - 对话轮次：第{current_round}轮
    - Bully当前攻击性：{last_agg:.2f}/10
    - 你的情绪状态：从委屈、难过逐渐到平静、观察
    
    【参与策略】
    {involvement_strategy}
    
    {core_principles}
    
    {topic_guidance}
    
    {f"【治疗师刚说】：{therapist_last_msg[:80]}" if therapist_last_msg else "【第一轮】这是第一轮，请直接回应Bully的攻击"}
    
    【输出格式要求】
    请以严格的JSON格式返回，只包含content字段：
    {{
        "content": "你的发言内容，要符合受害者角色和当前参与策略"
    }}
    
    **注意**：
    1. 只返回JSON对象，不要添加其他文本
    2. 发言要简短，符合退场策略
    3. 保持受害者立场，不攻击不挑衅
    """
    
    return victim_prompt

# ==================== 生成Agent回复 ====================
def generate_agent_response(role, client):
    """生成Agent回复的核心函数 - 增加重复抑制参数，两位小数"""
    if role == "bully":
        system_prompt = get_bully_system_prompt()
        temperature = 0.6
        freq_penalty = 1.9
        pres_penalty = 1.1
    elif role == "victim":
        system_prompt = get_victim_system_prompt()
        if system_prompt is None:
            return None
        temperature = 0.8
        freq_penalty = 0.3
        pres_penalty = 0.2
    else:  # therapist
        system_prompt = get_therapist_system_prompt()
        temperature = 0.9
        # 治疗师防复读：大幅提升频率惩罚
        freq_penalty = 1.8
        pres_penalty = 0.8
    
    messages = [{"role": "system", "content": system_prompt}]
    
    # 第一轮特殊处理
    if st.session_state.round_id == 1 and role == "bully":
        messages.append({
            "role": "user", 
            "content": f"这是第一轮对话。请基于话题'{st.session_state.topic}'生成攻击性开场白，展现人物特点，不要重复口头禅。"
        })
    elif st.session_state.round_id == 1 and role == "victim":
        bully_msg = None
        for msg in st.session_state.conversation_history:
            if msg["role"] == "Bully" and msg["round"] == 1:
                bully_msg = msg["content"]
                break
        if bully_msg:
            messages.append({"role": "user", "content": f"欺凌者说：'{bully_msg}'\n请以受害者身份回应。"})
    elif st.session_state.round_id == 1 and role == "therapist":
        history = get_conversation_history_text()[-300:]
        messages.append({"role": "user", "content": f"对话历史：\n{history}\n请以治疗师身份进行干预。"})
    else:
        recent = st.session_state.conversation_history[-6:] if len(st.session_state.conversation_history) > 6 else st.session_state.conversation_history
        for msg in recent:
            messages.append({"role": "user", "content": msg["content"]})
    
    messages.append({
        "role": "user", 
        "content": "请务必以json格式返回响应。记住：只返回json对象，不要添加任何其他文本。分数请精确到两位小数。"
    })
    
    try:
        # 治疗师需要更长的回复空间
        max_tok = 800 if role == "therapist" else 450
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tok,
            response_format={"type": "json_object"},
            frequency_penalty=freq_penalty,
            presence_penalty=pres_penalty
        )
        
        response_text = response.choices[0].message.content
        content, aggression_score, defensiveness_score, inner_thought = parse_agent_response(response_text)
        
        # 第一轮欺凌者分数强制范围
        if role == "bully" and st.session_state.round_id == 1:
            severity = st.session_state.bullying_severity
            if severity == "轻度":
                min_agg, max_agg = 5.5, 6.5
                min_def, max_def = 4.5, 5.5
            elif severity == "中度":
                min_agg, max_agg = 6.5, 7.5
                min_def, max_def = 5.5, 6.5
            else:
                min_agg, max_agg = 7.5, 8.5
                min_def, max_def = 6.5, 7.5
            if aggression_score < min_agg or aggression_score > max_agg:
                aggression_score = round(random.uniform(min_agg, max_agg), 2)
            if defensiveness_score < min_def or defensiveness_score > max_def:
                defensiveness_score = round(random.uniform(min_def, max_def), 2)
        
        return {
            "content": content,
            "aggression_score": aggression_score if role == "bully" else 0,
            "defensiveness_score": defensiveness_score if role == "bully" else 0,
            "inner_thought": inner_thought if role == "bully" else ""
        }
    except Exception as e:
        st.error(f"生成{role}回复时出错: {str(e)}")
        default_agg = 6.0 if role == "bully" and st.session_state.round_id == 1 else 5.5
        default_def = 5.0 if role == "bully" and st.session_state.round_id == 1 else 4.5
        return {
            "content": f"（{role}生成失败）",
            "aggression_score": default_agg if role == "bully" else 0,
            "defensiveness_score": default_def if role == "bully" else 0,
            "inner_thought": "技术故障" if role == "bully" else ""
        }

# ==================== 对话结束判断逻辑 ====================
def should_end_conversation():
    """判断是否应该结束对话：最近3轮攻击性和防御值均≤3.5"""
    if len(st.session_state.aggression_scores) < 3 or len(st.session_state.defensiveness_scores) < 3:
        return False
    recent_agg = st.session_state.aggression_scores[-3:]
    recent_def = st.session_state.defensiveness_scores[-3:]
    if all(score <= 3.5 for score in recent_agg) and all(score <= 3.5 for score in recent_def):
        return True
    return False

# ==================== 升级版数据保存 ====================
def save_to_csv(role, content, aggression_score, inner_thought="", defensiveness_score=0):
    """每次实验单独生成一个CSV文件"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    exp_id = st.session_state.experiment_id
    filename = f"exp_{exp_id}_details.csv"

    data = {
        "Experiment_ID":[exp_id],
        "Timestamp": [timestamp],
        "Round": [st.session_state.round_id],
        "Role": [role],
        "Content": [content],
        "Aggression_Score": [aggression_score],
        "Defensiveness_Score": [defensiveness_score],
        "Bullying_Type":[st.session_state.bullying_type],
        "Bullying_Severity":[st.session_state.bullying_severity],
        "Bully_Profile": [st.session_state.bully_profile],
        "Inner_Thought": [inner_thought if role == "Bully" else "N/A"]
    }
    df = pd.DataFrame(data)
    file_exists = os.path.exists(filename)
    df.to_csv(filename, mode='a', header=not file_exists, index=False, encoding='utf-8-sig')

def save_summary_csv(status="Completed"):
    """每次实验单独生成一个汇总CSV文件"""
    if not st.session_state.aggression_scores:
        return

    exp_id = st.session_state.experiment_id
    filename = f"exp_{exp_id}_summary.csv"

    init_agg = st.session_state.aggression_scores[0]
    final_agg = st.session_state.aggression_scores[-1]
    init_def = st.session_state.defensiveness_scores[0]
    final_def = st.session_state.defensiveness_scores[-1]

    # 自动计算差值
    agg_drop = init_agg - final_agg
    def_drop = init_def - final_def
    gap_index = final_def - final_agg

    # 判断最终状态类型
    if final_agg <= 3.5 and final_def <= 3.5:
        final_state = "真正转变"
    elif final_agg <= 4.0 and final_def > final_agg + 1.0:
        final_state = "表面认同（嘴软心硬）"
    elif final_agg > final_def + 1.0:
        final_state = "口是心非（嘴硬心软）"
    elif final_agg > 5.0 and final_def > 5.0:
        final_state = "真心愤怒"
    else:
        final_state = "中立/模糊"

    summary_data = {
        "Experiment_ID":[exp_id],
        "Timestamp":[datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        "Bully_Profile":[st.session_state.bully_profile],
        "Bullying_Type":[st.session_state.bullying_type],
        "Severity":[st.session_state.bullying_severity],
        "Topic": [st.session_state.topic],
        "Total_Rounds":[st.session_state.round_id],
        "Initial_Aggression": [init_agg],
        "Final_Aggression": [final_agg],
        "Agg_Drop": [agg_drop],
        "Initial_Defensiveness": [init_def],
        "Final_Defensiveness":[final_def],
        "Def_Drop": [def_drop],
        "Gap_Index": [gap_index],
        "Final_State": [final_state],
        "Status": [status],
        "Termination_Note":[st.session_state.get("termination_note", "系统自动结束")]
    }
    df = pd.DataFrame(summary_data)
    df.to_csv(filename, index=False, encoding='utf-8-sig')
# ==================== AI评分函数（复用标准）====================
def score_human_input(text, client):
    system_prompt = f"""
    你是一个专业的心理评分员。请根据以下双维度评分标准，对用户输入的欺凌言论进行打分。

    {UNIVERSAL_AGGRESSION_SCALE}

    请仅返回JSON格式，包含两个字段：aggression_score 和 defensiveness，精确到两位小数。
    例如：{{"aggression_score": 6.5, "defensiveness": 5.2}}
    """
    messages =[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text}
    ]
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.3,
            max_tokens=50,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        _, agg, defense, _ = parse_agent_response(content)
        return agg, defense
    except Exception as e:
        st.error(f"评分调用失败: {e}")
        sev = st.session_state.bullying_severity
        if sev == "轻度": return 5.0, 4.0
        elif sev == "中度": return 6.0, 5.0
        else: return 7.0, 6.0

# ==================== 人类输入处理函数 ====================
def process_human_bully_input(user_text):
    client = get_openai_client()
    if not client:
        st.error("请先配置API密钥")
        return

    # 1. 调用AI评分
    aggression, defensiveness = score_human_input(user_text, client)

    # 2. 增加轮次
    st.session_state.round_id += 1
    round_id = st.session_state.round_id

    # 3. 保存人类发言
    save_to_csv("Bully", user_text, aggression, defensiveness_score=defensiveness)
    st.session_state.conversation_history.append({
        "round": round_id,
        "role": "Bully",
        "content": user_text,
        "aggression_score": aggression,
        "defensiveness_score": defensiveness,
        "inner_thought": "",
        "timestamp": datetime.now().strftime("%H:%M:%S")
    })
    st.session_state.aggression_scores.append(aggression)
    st.session_state.defensiveness_scores.append(defensiveness)

    # 4. 生成受害者（如果需要）
    if should_victim_speak():
        victim_resp = generate_agent_response("victim", client)
        if victim_resp:
            save_to_csv("Victim", victim_resp["content"], 0)
            st.session_state.conversation_history.append({
                "round": round_id,
                "role": "Victim",
                "content": victim_resp["content"],
                "aggression_score": 0,
                "inner_thought": "",
                "timestamp": datetime.now().strftime("%H:%M:%S")
            })

    # 5. 生成治疗师回应
    therapist_resp = generate_agent_response("therapist", client)
    if therapist_resp:
        therapist_content = therapist_resp["content"]
        st.session_state.last_therapist_content = therapist_content
        st.session_state.last_3_therapist_contents.append(therapist_content)
        if len(st.session_state.last_3_therapist_contents) > 3:
            st.session_state.last_3_therapist_contents.pop(0)
        save_to_csv("Therapist", therapist_content, 0)
        st.session_state.conversation_history.append({
            "round": round_id,
            "role": "Therapist",
            "content": therapist_content,
            "aggression_score": 0,
            "inner_thought": "",
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })

# ==================== 自动化批量运行引擎 ====================
def run_batch_simulation(n_runs):
    """
    自动运行 N 次实验
    """
    client = get_openai_client()
    if not client:
        return

    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i in range(n_runs):
        status_text.text(f"正在进行第 {i+1}/{n_runs} 次实验... (当前配置: {st.session_state.bullying_type}-{st.session_state.bullying_severity})")
        
        # 1. 重置单次实验状态
        st.session_state.experiment_id = str(uuid.uuid4())
        st.session_state.round_id = 0
        st.session_state.conversation_history = []
        st.session_state.aggression_scores =[]
        st.session_state.defensiveness_scores =[]
        st.session_state.last_therapist_content = ""
        st.session_state.last_3_therapist_contents =[]
        st.session_state.is_closing_session = False
        
        # 2. 自动循环对话 (直到满足结束条件或最大轮次)
        while True:
            st.session_state.round_id += 1
            
            # --- Bully ---
            bully_resp = generate_agent_response("bully", client)
            if not bully_resp:
                st.error(f"第 {i+1} 次实验 Bully 生成失败，跳过本次实验")
                break
            save_to_csv("Bully", bully_resp["content"], bully_resp["aggression_score"], bully_resp["inner_thought"], bully_resp["defensiveness_score"])
            st.session_state.conversation_history.append({"role": "Bully", "content": bully_resp["content"], "round": st.session_state.round_id})
            st.session_state.aggression_scores.append(bully_resp["aggression_score"])
            st.session_state.defensiveness_scores.append(bully_resp["defensiveness_score"])
            
            # --- Victim (按概率) ---
            if should_victim_speak():
                victim_resp = generate_agent_response("victim", client)
                if victim_resp:
                    save_to_csv("Victim", victim_resp["content"], 0)
                    st.session_state.conversation_history.append({"role": "Victim", "content": victim_resp["content"], "round": st.session_state.round_id})
            
            # --- 判断结束条件 ---
            # 条件1: 达到临床收尾标准 (连续3轮双低)
            if should_end_conversation():
                # 先保存当前状态（此时 round_id 已经是最后一轮正常对话的轮次）
                # 然后跑两轮收尾（治疗师收尾 + Bully回应）
                st.session_state.is_closing_session = True
                
                # 治疗师收尾
                t_end = generate_agent_response("therapist", client)
                if t_end:
                    save_to_csv("Therapist", t_end["content"], 0)
                    st.session_state.conversation_history.append({"role": "Therapist", "content": t_end["content"], "round": st.session_state.round_id})
                
                # Bully回应收尾
                b_end = generate_agent_response("bully", client)
                if b_end:
                    save_to_csv("Bully", b_end["content"], b_end["aggression_score"], b_end["inner_thought"], b_end["defensiveness_score"])
                    st.session_state.conversation_history.append({"role": "Bully", "content": b_end["content"], "round": st.session_state.round_id})
                
                st.session_state.is_closing_session = False
                save_summary_csv("Success")  # 保存汇总数据
                break  # 结束本次实验
                
            # 条件2: 达到最大轮次 (比如20轮还没结束)
            if st.session_state.round_id >= st.session_state.max_rounds:
                save_summary_csv("Max Rounds Reached")
                break
                
            # --- Therapist (如果没结束，继续干预) ---
            therapist_resp = generate_agent_response("therapist", client)
            if not therapist_resp:
                st.error(f"第 {i+1} 次实验 Therapist 生成失败，跳过本次实验")
                break
            # 更新查重列表
            st.session_state.last_therapist_content = therapist_resp["content"]
            st.session_state.last_3_therapist_contents.append(therapist_resp["content"])
            if len(st.session_state.last_3_therapist_contents) > 3:
                st.session_state.last_3_therapist_contents.pop(0)
            
            save_to_csv("Therapist", therapist_resp["content"], 0)
            st.session_state.conversation_history.append({"role": "Therapist", "content": therapist_resp["content"], "round": st.session_state.round_id})
            
            # 稍微暂停一下防止API速率限制
            time.sleep(0.5)
        
        # 更新进度条
        progress_bar.progress((i + 1) / n_runs)
    
    status_text.success(f"✅ {n_runs} 次自动化实验已完成！请查看 experiment_summary.csv")

# ==================== 侧边栏配置 ====================
with st.sidebar:
    st.header("⚙️ 实验配置")
    
    # 显示当前轮次
    st.subheader("📊 实验状态")
    st.metric("当前轮次", st.session_state.round_id)
    
    # API配置
    st.subheader("🔑 API配置")
    api_key = st.text_input(
        "DeepSeek API密钥",
        value=st.session_state.api_key,
        type="password",
        help="从 https://platform.deepseek.com/ 获取API密钥"
    )
    if api_key != st.session_state.api_key:
        st.session_state.api_key = api_key
        st.session_state.config_updated = True
    
    # 话题设置
    st.subheader("💬 话题设置")
    topic = st.text_area(
        "讨论话题",
        value=st.session_state.topic,
        height=80,
        help="设置智能体讨论的话题。Bully将基于此话题生成攻击性开场白。"
    )
    if topic != st.session_state.topic:
        st.session_state.topic = topic
        st.session_state.config_updated = True
    
    # 欺凌者画像选择
    st.subheader("👤 欺凌者画像选择")
    profile_options =[
        "易怒的青少年",
        "愤世嫉俗的社会青年", 
        "固执的中年人"
    ]
    selected_profile = st.selectbox(
        "选择欺凌者画像",
        options=profile_options,
        index=profile_options.index(st.session_state.bully_profile) if st.session_state.bully_profile in profile_options else 0,
        help="选择不同的欺凌者身份画像，影响其攻击模式和心理弱点"
    )
    if selected_profile != st.session_state.bully_profile:
        st.session_state.bully_profile = selected_profile
        st.session_state.config_updated = True
    
    # 模拟ML识别：欺凌类型（纯中文选项）
    st.subheader("🔍 [模拟ML识别] 欺凌类型")
    bullying_types = list(BULLYING_SCENARIOS.keys())
    selected_type = st.selectbox(
        "欺凌类型",
        options=bullying_types,
        index=bullying_types.index(st.session_state.bullying_type) if st.session_state.bullying_type in bullying_types else 0,
        help="选择欺凌类型，将影响Bully的攻击内容和Therapist的干预策略"
    )
    if selected_type != st.session_state.bullying_type:
        st.session_state.bullying_type = selected_type
        st.session_state.config_updated = True
    
    # 模拟ML识别：严重程度
    st.subheader("📊 [模拟ML识别] 严重程度")
    severity_options =["轻度", "中度", "重度"]
    selected_severity = st.selectbox(
        "严重程度",
        options=severity_options,
        index=severity_options.index(st.session_state.bullying_severity) if st.session_state.bullying_severity in severity_options else 0,
        help="选择欺凌严重程度，将影响Bully的攻击强度"
    )
    if selected_severity != st.session_state.bullying_severity:
        st.session_state.bullying_severity = selected_severity
        st.session_state.config_updated = True
    
    # 人工干预模式
    st.subheader("👨‍🔬 人工干预模式")
    manual_intervention = st.toggle(
        "启用人工干预",
        value=st.session_state.manual_intervention,
        help="开启后，在Therapist发言时暂停并允许手动输入干预话术"
    )
    if manual_intervention != st.session_state.manual_intervention:
        st.session_state.manual_intervention = manual_intervention
        st.session_state.show_manual_input = False
        st.session_state.config_updated = True

    # ========== 新增：交互模式选择 ==========
    st.subheader("🧑‍🤝‍🧑 交互模式")
    mode = st.radio(
        "选择欺凌者类型",
        options=["AI欺凌者（自动生成）", "人类欺凌者（手动输入）"],
        index=0 if not st.session_state.human_bully_mode else 1,
        help="AI欺凌者：系统自动生成攻击性语言；人类欺凌者：由您亲自输入欺凌者的话"
    )
    st.session_state.human_bully_mode = (mode == "人类欺凌者（手动输入）")
    
    # 最大轮数滑块
    st.subheader("⏱️ 实验控制")
    max_rounds = st.slider(
        "最大对话轮数",
        min_value=5,
        max_value=50,
        value=st.session_state.max_rounds,
        step=1,
        help="达到最大轮数后，实验将自动结束并生成结束语（若未达标）"
    )
    if max_rounds != st.session_state.max_rounds:
        st.session_state.max_rounds = max_rounds
        st.session_state.config_updated = True
    
    # 配置应用按钮
    if st.session_state.config_updated:
        if st.button("✅ 应用配置", use_container_width=True, type="primary"):
            st.session_state.config_updated = False
            st.success("配置已应用！")
            st.rerun()
    
    # 实验控制
    st.subheader("🎮 实验控制")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 开始/继续实验", use_container_width=True, type="primary"):
            st.session_state.experiment_started = True
            st.session_state.config_updated = False
            st.session_state.experiment_completed = False
            st.rerun()
    with col2:
        if st.button("🔄 重置实验", use_container_width=True):
            for key in['conversation_history', 'round_id', 'aggression_scores', 'defensiveness_scores', 
                        'experiment_started', 'show_manual_input', 'experiment_completed', 'is_closing_session', 
                        'last_therapist_content', 'last_3_therapist_contents']:
                if key in st.session_state:
                    if key == 'round_id':
                        st.session_state[key] = 0
                    elif key in['aggression_scores', 'defensiveness_scores', 'conversation_history', 'last_3_therapist_contents']:
                        st.session_state[key] =[]
                    elif key == 'last_therapist_content':
                        st.session_state[key] = ""
                    else:
                        st.session_state[key] = False
            # 重置时也重新生成实验ID
            st.session_state.experiment_id = str(uuid.uuid4())
            st.session_state.config_updated = False
            st.rerun()
    
    # 攻击性评分图表
    st.subheader("📈 心理状态趋势对比")
    # ========== 攻击性图表 (单盲控制：真人模式下隐藏) ==========
    if not st.session_state.human_bully_mode:
        st.subheader("📈 心理状态趋势对比")
        if st.session_state.aggression_scores and st.session_state.defensiveness_scores:
            fig, ax = plt.subplots(figsize=(8, 4))
            
            try:
                plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
                plt.rcParams['axes.unicode_minus'] = False
            except:
                pass
            
            rounds = list(range(1, len(st.session_state.aggression_scores) + 1))
            ax.plot(rounds, st.session_state.aggression_scores, 'r-o', linewidth=2, markersize=8, label='攻击性')
            min_len = min(len(rounds), len(st.session_state.defensiveness_scores))
            ax.plot(rounds[:min_len], st.session_state.defensiveness_scores[:min_len], 'b-s', linewidth=2, markersize=8, label='防御值')
            ax.set_xlabel("对话轮次", fontsize=10)
            ax.set_ylabel("评分 (0-10)", fontsize=10)
            ax.set_title("干预过程心理博弈趋势", fontsize=12, fontweight='bold')
            ax.grid(True, alpha=0.3, linestyle='--')
            ax.set_ylim(-0.5, 10.5)
            ax.set_xlim(0.5, len(rounds) + 0.5)
            ax.legend(loc='upper right', frameon=True)
            ax.axhspan(0, 3.5, color='green', alpha=0.1, label='安全区 (≤3.5)')
            st.pyplot(fig)
            
            if len(st.session_state.aggression_scores) > 0:
                curr_agg = st.session_state.aggression_scores[-1]
                curr_def = st.session_state.defensiveness_scores[-1]
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    st.metric("🔴 当前攻击性", f"{curr_agg:.2f}")
                with col_m2:
                    st.metric("🔵 当前防御值", f"{curr_def:.2f}")
                
                if curr_def > curr_agg + 2:
                    st.info("💡 洞察：防御值显著高于攻击性，说明对方处于'嘴硬心虚'状态，适合进行共情引导。")
                elif curr_agg > curr_def + 1.5:
                    st.info("💡 洞察：攻击性明显高于防御值，说明处于'嘴硬心软'状态，干预已见成效。")
        else:
            st.info("暂无数据，开始实验后显示图表")
    # ==================== 新增：自动化批量实验控制台 ====================
    st.divider()
    st.header("🤖 自动化批量实验 (Auto-Lab)")
    st.info("此功能用于快速收集论文数据。请先在上方设置好【欺凌类型】和【严重程度】。")
    
    batch_count = st.number_input("设置运行次数 (N)", min_value=1, value=26, step=1)
    
    if st.button("⚡ 启动批量模拟", type="primary"):
        if not st.session_state.api_key:
            st.error("请先输入 API Key！")
        else:
            with st.spinner(f"正在后台运行 {batch_count} 次实验，请勿关闭页面..."):
                run_batch_simulation(batch_count)

# ==================== 主界面布局 ====================
st.header("🎭 实验角色说明")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### 🔥 欺凌者")
    st.markdown(f"**当前画像**: {st.session_state.bully_profile}")
    st.markdown(f"**欺凌类型**: {st.session_state.bullying_type}")
    st.markdown(f"**严重程度**: {st.session_state.bullying_severity}")
    st.markdown("**攻击模式**: 基于类型诊断的精准攻击")

with col2:
    st.markdown("### 😢 受害者")
    st.markdown("**角色设定**: 具体受害者，非路人")
    st.markdown("**情绪轨迹**: 恐惧 → 希望 → 平复")
    st.markdown("**互动响应**: 尝试沟通而非哭诉")
    st.markdown("**动态退场**: 后期完全沉默（8轮后仅10%概率）")

with col3:
    st.markdown("### 🛡️ 治疗师")
    st.markdown("**干预策略**: 理论驱动 (CBT/共情/法治)")
    st.markdown(f"**当前类型**: {st.session_state.bullying_type}")
    
    # 动态显示当前策略
    if st.session_state.bullying_type == "辱骂":
        strategy_desc = "情绪降温 + 认知行为矫正"
    elif st.session_state.bullying_type == "诋毁":
        strategy_desc = "现实检验 + 法律红线告知"
    elif st.session_state.bullying_type == "揭露隐私":
        strategy_desc = "危机干预 + 零容忍阻断"
    else:
        strategy_desc = "去抑制化 + 社会羞耻感唤起"
        
    st.markdown(f"**核心技法**: {strategy_desc}")
    
    st.info("""
    **🎯 临床达标退出机制**
    目标非清零，而是降至安全阈值：
    - 攻击性 ≤ 3.5
    - 防御值 ≤ 3.5
    **连续三轮达标即自动温和收尾（治疗师收尾 + 欺凌者回应）**
    """)

st.divider()
st.header("💬 对话历史")

# ==================== 显示对话历史（移到输入框之前）====================
if st.session_state.conversation_history:
    # 人类欺凌者模式下按时间正序显示（新消息在下方），否则倒序
    msgs_to_show = st.session_state.conversation_history[-15:]
    if not st.session_state.human_bully_mode:
        msgs_to_show = list(reversed(msgs_to_show))

    # 使用一个带高度的容器实现滚动效果
    chat_container = st.container(height=400)
    with chat_container:
        for msg in msgs_to_show:
            with st.chat_message("user" if msg["role"] not in ["Therapist", "System"] else "assistant"):
                role_map = {"Bully": "欺凌者", "Victim": "受害者", "Therapist": "治疗师", "System": "系统"}
                display_role = role_map.get(msg['role'], msg['role'])

                # 角色图标处理
                if msg["role"] == "Bully" and st.session_state.human_bully_mode:
                    role_icon, display_role = "👤", "人类被试 (您)"
                elif msg["role"] == "System":
                    role_icon = "⚙️"
                else:
                    role_icon = "🔥" if msg["role"] == "Bully" else "😢" if msg["role"] == "Victim" else "🛡️"

                st.markdown(f"**{role_icon} {display_role}** (第 {msg.get('round', '')} 轮)")

                # 单盲控制：人类模式下绝对隐藏独白
                if msg.get("role") == "Bully" and msg.get("inner_thought") and not st.session_state.human_bully_mode:
                    st.markdown(f'<div style="color: #666; font-size: 0.85em; font-style: italic; margin-bottom: 6px; padding: 4px 8px; background-color: #f5f5f5; border-radius: 4px;">💭 心理潜台词: {msg["inner_thought"]}</div>', unsafe_allow_html=True)

                # 突出显示系统消息
                if msg["role"] == "System":
                    st.info(msg["content"])
                else:
                    st.markdown(msg["content"])

                col_t1, col_t2 = st.columns(2)
                with col_t1:
                    st.caption(f"⏰ {msg.get('timestamp', '')}")
                with col_t2:
                    # 单盲控制：人类模式下绝对隐藏具体分数
                    if msg["role"] == "Bully" and not st.session_state.human_bully_mode:
                        st.caption(f"⚡ 攻击性: {msg.get('aggression_score',0):.2f}/10 | 🛡️ 防御值: {msg.get('defensiveness_score', 0):.2f}/10")
else:
    st.info("对话历史为空，开始实验后显示对话记录。")

# ==================== 对话控制（输入框在底部）====================
if not st.session_state.experiment_started:
    st.info("👆 请点击侧边栏的'开始/继续实验'按钮开始实验")
else:
    if st.session_state.get('experiment_completed', False):
        st.success("🎉 实验已完成！治疗师已进行温和收尾，欺凌者已回应。如需重新开始，请点击侧边栏的'重置实验'按钮。")
    else:
        # ========== 人类欺凌者模式 ==========
        if st.session_state.human_bully_mode:
            # 显示角色引导卡片
            with st.container():
                st.markdown("### 🎭 你的欺凌者角色")
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f"**画像**：{st.session_state.bully_profile}")
                    desc = {
                        "易怒的青少年": "情绪化、面子敏感、叛逆、渴望理解",
                        "愤世嫉俗的社会青年": "现实挫败、防御性强、实用主义、自尊心强",
                        "固执的中年人": "经验依赖、权威敏感、思维固化"
                    }.get(st.session_state.bully_profile, "")
                    st.markdown(f"**性格**：{desc}")
                with col_b:
                    st.markdown(f"**攻击类型**：{st.session_state.bullying_type}（{st.session_state.bullying_severity}）")
                    attack_example = BULLYING_SCENARIOS[st.session_state.bullying_type][st.session_state.bullying_severity]
                    st.markdown(f"**攻击方式**：{attack_example}")
                st.info(
                    "**示例发言**：\n"
                    "- “笑死，现在的00后除了要高工资还会干什么？纯纯的眼高手低。”\n"
                    "- “天天喊着整顿职场，其实就是能力差还懒，真够可笑的。”\n"
                    "请结合左侧选择的【欺凌类型】（如造谣、辱骂等），模仿上述风格输入，保持角色一致性。"
                )
            
            # 人类输入表单
            with st.form(key="human_input_form", clear_on_submit=True):
                user_input = st.text_area("✍️ 输入你作为欺凌者的话", height=100, placeholder="请模仿角色语气输入...")
                submitted = st.form_submit_button("🚀 发送")
            if submitted and user_input:
                st.session_state.human_input = user_input
                st.session_state.need_process_human_input = True
                st.rerun()
            if st.session_state.get('need_process_human_input', False):
                st.session_state.need_process_human_input = False
                process_human_bully_input(st.session_state.human_input)
                st.rerun()

            # ===== 【新增】真人主观结束按钮 =====
            if len(st.session_state.conversation_history) >= 2:
                st.divider()
                if st.button("🛑 我觉得被说服了 / 不想吵了 (结束实验)", type="secondary", use_container_width=True):
                    # 记录系统消息到明细表
                    save_to_csv("System", "【实验终止】人类被试主动点击结束按钮退出实验。", 0, inner_thought="N/A", defensiveness_score=0)
                    
                    st.session_state.termination_note = "真人被试主动终止"
                    save_summary_csv("Human_Terminated")
                    st.session_state.experiment_completed = True
                    st.success("✅ 实验结束！非常感谢您的参与。请点击最下方【导出实验数据】并将CSV文件发送给主试。")
                    st.rerun()
        else:
            # ========== AI模式（原样保留，不做任何改动）==========
            # 人工干预输入框
            if st.session_state.manual_intervention and st.session_state.show_manual_input:
                st.warning("⚠️ 人工干预模式已启用")
                manual_input = st.text_area("✍️ 请输入干预话术", value=st.session_state.manual_therapist_input, height=150)
                col_sub, col_can = st.columns(2)
                with col_sub:
                    if st.button("✅ 提交人工干预", use_container_width=True, type="primary"):
                        if manual_input.strip():
                            st.session_state.manual_therapist_input = manual_input.strip()
                            st.session_state.show_manual_input = False
                            st.rerun()
                with col_can:
                    if st.button("❌ 取消", use_container_width=True):
                        st.session_state.show_manual_input = False
                        st.rerun()
            
            # 开始下一轮按钮
            elif st.button("🚀 开始下一轮对话", type="primary", use_container_width=True):
                # 最大轮数检查
                if st.session_state.round_id >= st.session_state.max_rounds:
                    st.warning(f"⚠️ 已达到设置的最大对话轮数 ({st.session_state.max_rounds} 轮)。如需继续，请在侧边栏增大“最大对话轮数”或重置实验。")
                    st.stop()
                
                # ========== 临床达标收尾（双轮对话，带强制欺凌者回应）==========
                if should_end_conversation() and not st.session_state.experiment_completed:
                    st.session_state.is_closing_session = True
                    client = get_openai_client()
                    if not client:
                        st.error("API Key错误，无法生成收尾发言")
                        st.stop()
                    
                    # ----- 第1轮：治疗师收尾发言 -----
                    st.session_state.round_id += 1
                    with st.spinner("🎯 临床目标已达成，治疗师正在生成温和收尾发言..."):
                        therapist_resp = generate_agent_response("therapist", client)
                        therapist_content = therapist_resp["content"]
                        # 更新治疗师历史记录
                        st.session_state.last_therapist_content = therapist_content
                        last_3 = st.session_state.get('last_3_therapist_contents',[])
                        last_3.append(therapist_content)
                        if len(last_3) > 3: last_3.pop(0)
                        st.session_state.last_3_therapist_contents = last_3
                        
                        save_to_csv("Therapist", therapist_content, 0)
                        st.session_state.conversation_history.append({
                            "round": st.session_state.round_id,
                            "role": "Therapist",
                            "content": therapist_content,
                            "aggression_score": 0,
                            "inner_thought": "",
                            "timestamp": datetime.now().strftime("%H:%M:%S")
                        })
                    
                    # ----- 第2轮：欺凌者回应收尾（强制生成，即使API失败也有默认回应）-----
                    st.session_state.round_id += 1
                    with st.spinner("欺凌者正在回应收尾..."):
                        try:
                            bully_resp = generate_agent_response("bully", client)
                            if bully_resp and bully_resp.get("content"):
                                bully_content = bully_resp["content"]
                                aggression = bully_resp["aggression_score"]
                                defensiveness = bully_resp["defensiveness_score"]
                                inner = bully_resp["inner_thought"]
                            else:
                                raise Exception("欺凌者回应为空")
                        except Exception as e:
                            # 如果API调用失败，使用预设的收尾回应，确保实验完整
                            bully_content = "嗯…谢谢你陪我聊了这么多。我会试着改的。"
                            aggression = 3.2
                            defensiveness = 2.8
                            inner = "其实他说得对，我确实太冲动了。谢谢他愿意听我说。"
                        
                        # 强制分数不超过3.5（安全区）
                        aggression = min(aggression, 3.5)
                        defensiveness = min(defensiveness, 3.5)
                        
                        save_to_csv("Bully", bully_content, aggression, inner, defensiveness)
                        st.session_state.conversation_history.append({
                            "round": st.session_state.round_id,
                            "role": "Bully",
                            "content": bully_content,
                            "aggression_score": aggression,
                            "defensiveness_score": defensiveness,
                            "inner_thought": inner,
                            "timestamp": datetime.now().strftime("%H:%M:%S")
                        })
                        st.session_state.aggression_scores.append(aggression)
                        st.session_state.defensiveness_scores.append(defensiveness)
                    
                    # 标记实验完成
                    st.session_state.experiment_completed = True
                    st.session_state.is_closing_session = False
                    # 保存汇总数据
                    save_summary_csv("Success")
                    st.success("✅ 实验目标达成！双方已完成温和收尾，对话结束。")
                    st.rerun()
                
                # ========== 正常对话流程 ==========
                client = get_openai_client()
                if not client:
                    st.error("API Key错误，无法生成对话")
                    st.stop()
                
                with st.spinner("智能体正在生成对话..."):
                    st.session_state.round_id += 1
                    
                    # 1. Bully发言
                    bully_resp = generate_agent_response("bully", client)
                    bully_content = bully_resp["content"]
                    aggression = bully_resp["aggression_score"]
                    defensiveness = bully_resp["defensiveness_score"]
                    inner = bully_resp["inner_thought"]
                    
                    save_to_csv("Bully", bully_content, aggression, inner, defensiveness)
                    st.session_state.conversation_history.append({
                        "round": st.session_state.round_id,
                        "role": "Bully",
                        "content": bully_content,
                        "aggression_score": aggression,
                        "defensiveness_score": defensiveness,
                        "inner_thought": inner,
                        "timestamp": datetime.now().strftime("%H:%M:%S")
                    })
                    st.session_state.aggression_scores.append(aggression)
                    st.session_state.defensiveness_scores.append(defensiveness)
                    
                    # 2. Victim发言（仅当需要发言时）
                    if should_victim_speak():
                        victim_resp = generate_agent_response("victim", client)
                        if victim_resp:
                            victim_content = victim_resp["content"]
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
                    if st.session_state.manual_intervention:
                        st.session_state.show_manual_input = True
                        st.rerun()
                    else:
                        therapist_resp = generate_agent_response("therapist", client)
                        therapist_content = therapist_resp["content"]
                        # 更新治疗师历史记录
                        st.session_state.last_therapist_content = therapist_content
                        last_3 = st.session_state.get('last_3_therapist_contents',[])
                        last_3.append(therapist_content)
                        if len(last_3) > 3:
                            last_3.pop(0)
                        st.session_state.last_3_therapist_contents = last_3
                        
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
            
            # 手动输入干预话术后的处理
            if st.session_state.manual_intervention and st.session_state.manual_therapist_input and not st.session_state.show_manual_input and not st.session_state.experiment_completed:
                with st.spinner("正在处理人工干预话术..."):
                    therapist_content = st.session_state.manual_therapist_input
                    st.session_state.last_therapist_content = therapist_content
                    last_3 = st.session_state.get('last_3_therapist_contents',[])
                    last_3.append(therapist_content)
                    if len(last_3) > 3:
                        last_3.pop(0)
                    st.session_state.last_3_therapist_contents = last_3
                    save_to_csv("Therapist", therapist_content, 0)
                    st.session_state.conversation_history.append({
                        "round": st.session_state.round_id,
                        "role": "Therapist",
                        "content": therapist_content,
                        "aggression_score": 0,
                        "inner_thought": "",
                        "timestamp": datetime.now().strftime("%H:%M:%S")
                    })
                    st.session_state.manual_therapist_input = ""
                    st.success("✅ 人工干预话术已应用！")
                    st.rerun()

# 导出当前对话（仅人机模式显示）
if st.session_state.human_bully_mode and st.session_state.conversation_history:
    if st.button("📥 导出当前对话"):
        lines =[]
        for msg in st.session_state.conversation_history:
            role_display = {"Bully": "欺凌者", "Victim": "受害者", "Therapist": "治疗师"}.get(msg['role'], msg['role'])
            if msg['role'] == "Bully" and st.session_state.human_bully_mode:
                role_display = "人类欺凌者"
            lines.append(f"{role_display} (第{msg['round']}轮): {msg['content']}")
            if msg.get("inner_thought") and msg['role'] == "Bully":
                lines.append(f"  [内心独白]: {msg['inner_thought']}")
        text = "\n\n".join(lines)
        st.download_button("下载对话文本", text, file_name=f"对话_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

# ==================== 数据管理 ====================
st.divider()
st.header("📊 数据管理")
st.caption(f"当前实验ID: {st.session_state.experiment_id}")

col_exp1, col_exp2 = st.columns(2)
current_exp_details = f"exp_{st.session_state.experiment_id}_details.csv"
current_exp_summary = f"exp_{st.session_state.experiment_id}_summary.csv"

with col_exp1:
    if os.path.exists(current_exp_details):
        with open(current_exp_details, "rb") as f:
            st.download_button(f"📥 导出本次实验明细", f, current_exp_details, use_container_width=True)
    else:
        st.info("暂无本次实验数据")

with col_exp2:
    if os.path.exists(current_exp_summary):
        with open(current_exp_summary, "rb") as f:
            st.download_button(f"📊 导出本次实验汇总", f, current_exp_summary, use_container_width=True)
    else:
        st.info("暂无本次实验汇总")

# 显示所有历史实验文件
st.divider()
st.subheader("📁 历史实验文件")
exp_files = [f for f in os.listdir(".") if f.startswith("exp_") and f.endswith(".csv")]
if exp_files:
    # 按实验ID分组
    exp_ids = set()
    for f in exp_files:
        # 提取实验ID：exp_{id}_details.csv 或 exp_{id}_summary.csv
        parts = f.replace("exp_", "").replace("_details.csv", "").replace("_summary.csv", "")
        exp_ids.add(parts)

    for exp_id in sorted(exp_ids, reverse=True):
        detail_file = f"exp_{exp_id}_details.csv"
        summary_file = f"exp_{exp_id}_summary.csv"

        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            st.caption(f"实验 {exp_id}")
        with col2:
            if os.path.exists(detail_file):
                with open(detail_file, "rb") as f:
                    st.download_button("明细", f, detail_file, key=f"dl_{exp_id}_detail")
        with col3:
            if os.path.exists(summary_file):
                with open(summary_file, "rb") as f:
                    st.download_button("汇总", f, summary_file, key=f"dl_{exp_id}_summary")
else:
    st.info("暂无历史实验文件")

if st.button("🗑️ 清除所有实验数据", type="secondary", use_container_width=True):
    import glob
    for file in glob.glob("exp_*.csv"):
        os.remove(file)
    st.success("已清除所有实验数据文件")
    st.rerun()

# ==================== 实验说明 ====================
st.divider()
st.header("📝 实验说明")
with st.expander("🔍 查看详细实验设计"):
    st.markdown("""
    ### 实验设计详情 v3.2（最终优化版）

    **1. 核心创新：欺凌类型诊断驱动**  
    - **移除**传统的"A/B/C干预模式"，**采用**基于欺凌类型诊断的精准干预策略。
    - **实现**攻击内容与干预策略的严格匹配（辱骂→情绪降温、诋毁→法律红线、揭露隐私→零容忍、性骚扰→羞耻唤起）。

    **2. 欺凌类型定义库：**
    - **辱骂:** 情绪降温与行为矫正
    - **诋毁:** 现实检验与法律红线
    - **揭露隐私:** 零容忍与安全阻断
    - **性骚扰:** 社会羞耻感唤起

    **3. 动态区间分数控制（优化版）：**  
    - **4-3.5区间下降速度显著提高**：distance_ratio 0.05~0.2 区间速率从0.4提升至0.9，更快突破表面服从。
    - **低分段步长硬性限制**：当分数低于4.0时，每轮变化严格控制在0.10-0.20之间，模拟“强弩之末”的缓慢消退。
    - **两位小数精度**：所有分数显示、存储、计算均保留两位小数，更细腻地反映下降趋势。
    - **剪刀差强制矫正**：当内心独白明确软化（“说得对”“不想吵了”等）时，强制防御值比攻击性低1.5分以上，体现“嘴硬心软”。

    **4. 受害者动态退场（完全沉默）：**  
    - 8轮后基本不再发言；5-8轮仅低概率发言；仅第一轮强制发言。
    - 后期即使攻击性反弹，也只有极低概率发言，确保干预聚焦于欺凌者。

    **5. 语言多样性强制：**  
    - Bully频率惩罚1.9，存在惩罚1.1，提示词中明确禁止重复口头禅。
    - 治疗师频率惩罚1.8，存在惩罚0.8，提示词中**强制查重最近3轮**，彻底杜绝复读机。

    **6. 临床达标自动收尾（双轮对话）：**  
    - **连续三轮**攻击性≤3.5且防御值≤3.5 → 自动触发**两轮收尾对话**。
    - **第1轮**：治疗师温和收尾（总结进步、强化技巧、自然结束）。
    - **第2轮**：欺凌者回应收尾（表达接纳、感谢、平静结束）。
    - 收尾完整自然，符合真实咨询场景。

    **7. 最大轮数控制：**  
    - 滑块5-50轮，默认20轮，达到上限自动阻止。

    **版本标识**：v3.2 - 精准干预·快速突破·沉默退场·剪刀差强制·深度防复读·双轮收尾·纯中文界面
    """)

st.caption("🧪 基于欺凌类型诊断的精准干预实验平台 v3.2 | 两位小数精度 | 4-3.5快速下降 | 低分段步长0.10-0.20 | 剪刀差强制 | 治疗师3轮查重 | 双轮收尾 | 完整详细版")
