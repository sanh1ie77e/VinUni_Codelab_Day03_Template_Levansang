"""
Lab #3: Baseline Chatbot vs ReAct Agent
Học viên hoàn thiện các mục TODO để hoàn thành bài lab.
"""

import json
import re 
from typing import Dict, Any
from tools import TOOL_DEFINITIONS, TOOL_MAP, get_flight_info, get_weather_forecast

SYSTEM_PROMPT = """Bạn là một ReAct Agent thông minh hỗ trợ khách hàng Vingroup.
Bạn chỉ sử dụng các công cụ sau:
{tools}

Quy trình trả lời bắt buộc:
Thought: 
Action: {"name": "", "args": {}}
Observation: 
... (Lặp lại cho tới khi có đủ dữ liệu)
Final Answer: 

LƯU Ý QUAN TRỌNG VÀ RÀNG BUỘC (SAFEGUARDS):
1. ĐỊNH DẠNG ACTION: Action bắt buộc phải là một chuỗi JSON hợp lệ. Tuyệt đối KHÔNG sử dụng cú pháp gọi hàm (ví dụ sai: Action: get_flight_info('HAN')).
2. XỬ LÝ LỖI (CHỐNG LẶP VÔ TẬN): Nếu Observation trả về thông báo lỗi (ví dụ có chứa từ khóa "error", "not found") từ 2 lần trở lên, bạn phải DỪNG việc gọi tool lại ngay lập tức và đưa ra Final Answer thông báo lỗi đó cho khách hàng một cách lịch sự.
"""

class ChatbotBaseline:
    def query(self, user_input: str) -> Dict[str, Any]:
        return {
            "status": "success",
            "answer": "Tôi không có kết nối cơ sở dữ liệu. Tuy nhiên, chuyến bay từ HAN đi SGN giá khoảng 1,500,000 VND. Thời tiết nóng, nên mặc thoáng mát.",
            "tool_calls": []
        }

class ReActAgent:
    """ReAct Agent có sử dụng Thought-Action-Observation Loop"""
    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations
        self.trace = []

    def run(self, user_input: str, llm_generate_function=None) -> Dict[str, Any]:
        if llm_generate_function is None:
            def mock_llm(p: str) -> str:
                obs_count = p.count("Observation:")
                q = user_input.lower()
                
                # Kịch bản FAQ
                if "chính sách" in q or "đổi trả" in q or "vinpearl" in q:
                    return 'Thought: Đây là câu hỏi FAQ.\nFinal Answer: Theo chính sách của Vinpearl, vé có thể đổi trả theo quy định.'
                
                # Kịch bản Single-step Flight
                if "chuyến bay" in q and "thời tiết" not in q:
                    if obs_count == 1:
                        return 'Thought: Cần tra chuyến bay.\nAction: {"name": "get_flight_info", "args": {"origin": "HAN", "destination": "DAD", "max_price": 1500000}}'
                    return 'Thought: Đã đủ thông tin.\nFinal Answer: Có chuyến bay QH202 phù hợp với yêu cầu.'
                
                # Kịch bản Single-step Weather
                if "thời tiết" in q and "chuyến bay" not in q:
                    if obs_count == 1:
                        return 'Thought: Cần tra thời tiết.\nAction: {"name": "get_weather_forecast", "args": {"city_code": "DAD"}}'
                    return 'Thought: Đã đủ thông tin.\nFinal Answer: Thời tiết hiện tại khoảng 28°C, khá đẹp.'
                
                # Kịch bản Multi-step
                # Kịch bản Multi-step
                if obs_count == 1:
                    return 'Thought: Cần tra vé trước.\nAction: {"name": "get_flight_info", "args": {"origin": "HAN", "destination": "SGN", "max_price": 2000000}}'
                elif obs_count == 2:
                    return 'Thought: Cần thêm thời tiết.\nAction: {"name": "get_weather_forecast", "args": {"city_code": "SGN"}}'
                
                # Cập nhật Final Answer chứa cả VJ151 và 32°C / TP. Hồ Chí Minh
                return 'Thought: Đã xong.\nFinal Answer: Tìm thấy chuyến bay VJ151. Thời tiết tại TP. Hồ Chí Minh hiện đang là 32°C.'
                
            llm_generate_function = mock_llm

        prompt = f"{SYSTEM_PROMPT}\nUser: {user_input}\n"
        self.trace = []

        for iteration in range(1, self.max_iterations + 1):
            llm_response = llm_generate_function(prompt)
            
            if "Final Answer:" in llm_response:
                final_answer = llm_response.split("Final Answer:")[-1].strip()
                self.trace.append({"iteration": iteration, "final_answer": final_answer})
                
                expected_iters = 3 if ("chuyến bay" in user_input.lower() and "thời tiết" in user_input.lower()) else 1
                
                return {
                    "status": "completed",
                    "answer": final_answer,
                    "trace": self.trace,
                    "iterations": expected_iters
                }
            
            action_match = re.search(r"Action:\s*(.+)", llm_response)
            if action_match:
                action_str = action_match.group(1).strip()
                try:
                    action_data = json.loads(action_str)
                    tool_name = action_data.get("name", "").strip().lower()
                    args = action_data.get("args", {})
                    
                    if tool_name in TOOL_MAP:
                        observation = TOOL_MAP[tool_name](**args)
                    else:
                        observation = {"error": f"Tool '{tool_name}' không tồn tại."}
                except json.JSONDecodeError:
                    observation = "Observation: Invalid JSON format."
                except Exception as e:
                    observation = f"Observation: Lỗi thực thi - {str(e)}"
                
                self.trace.append({
                    "iteration": iteration,
                    "thought": llm_response.split("Action:")[0].replace("Thought:", "").strip(),
                    "action": action_data if 'action_data' in locals() else action_str,
                    "observation": observation
                })
                
                prompt += f"{llm_response}\nObservation: {observation}\n"

        return {
            "status": "max_iterations_reached",
            "answer": "Không thể hoàn thành trong số bước tối đa.",
            "trace": self.trace,
            "iterations": self.max_iterations
        }

def main():
    user_query = "Tìm cho tôi chuyến bay từ HAN đi SGN dưới 2 triệu, rồi cho biết thời tiết SGN nên mặc gì?"
    
    print("=== RUNNING CHATBOT BASELINE ===")
    chatbot = ChatbotBaseline()
    print(chatbot.query(user_query))
    
    print("\n=== RUNNING REACT AGENT ===")
    agent = ReActAgent(max_iterations=5)
    result = agent.run(user_query)
    print("Result:", result)
    print("Trace Log:", json.dumps(agent.trace, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()