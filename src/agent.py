import logging
import json
import os
from datetime import datetime
from typing import List, Dict, Any

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RoomInputOptions,
    RoomOutputOptions,
    RunContext,
    WorkerOptions,
    cli,
    metrics,
)

from livekit.plugins import (
    groq,
    deepgram,
)


from livekit.agents.llm import function_tool
from livekit.agents.voice import MetricsCollectedEvent
from livekit.plugins import openai, silero

# # Assuming the script is in the same directory level as 'src'
# from scripts.v1.agent_recomends_with import get_next_filter_question
# get_next_filter_question("pim487", "room123")

from scripts.v1.find_categories import find_main_categories, find_by_pimid, get_url_of_categoriy, get_brands_of_categories, get_brands_of_categories_with_query
from scripts.v1.filter_function import get_next_filter, get_formatted_filter, make_filter_question, get_answred_code_for_filter, get_selected_value_query, generate_url
from scripts.v1.engineering_tool_functions import get_available_engineering_tool, get_next_sizing_tool_question, validate_sizing_tool_answer, get_next_sizing_tool_filter, generate_product_urls


import asyncio

logger = logging.getLogger("agent")
logging.basicConfig(level=logging.DEBUG)  # Set to DEBUG for detailed logging

load_dotenv()


# def validate_filter_answer(pimId, question, userAnswer, room_id,is_answer_selected_by_llm=False):

#     #check engineering tool exist for end sub category
#     selected_engineering_tool = get_available_engineering_tool(pimId)
#     if selected_engineering_tool != {} and selected_engineering_tool.get("sizing_configurations"):
#         sizing_configurations = selected_engineering_tool["sizing_configurations"]
#         current_engineering_tool = conversation_states[room_id].get("current_engineering_tool", {})
#         if current_engineering_tool != {} and current_engineering_tool.get("current_filter_data", None):
#             formatted_filter = current_engineering_tool.get("current_filter_data", {})
#             answered_questions = current_engineering_tool.get("answered_questions", {})
#             skip_filter_questions = current_engineering_tool.get("skip_filter_questions", {})

#             # Validate the answer
#             answer_code = validate_sizing_tool_answer(room_id,pimId, question, userAnswer, formatted_filter, answered_questions)
            
#             if answer_code:
#                 answered_questions[formatted_filter["payload_attribute"]] = answer_code
#                 conversation_states[room_id]["current_engineering_tool"] = {
#                     "answered_questions": answered_questions,
#                     "skip_filter_questions": skip_filter_questions,
#                     "current_filter_data": formatted_filter
#                 }
#                 return "Answer is valid and query is updated."
#             else:
#                 return f"Answer is not valid. Please provide a valid answer from {question}"
#         else:
#             return "Error: No filter data found. Please get a filter question first."
#     else:
#         current_answered_query = conversation_states[room_id].get("current_answered_query", None)
#         if current_answered_query is None:
#             conversation_states[room_id]["current_answered_query"] = "~:sortByCoreRangeAndNewProduct"
#         all_answered_query = conversation_states[room_id].get("all_answered_query", [])
        
#         formatted_filter = conversation_states[room_id].get("current_filter_data", None)

#         if not formatted_filter:
#             return "Error: No filter data found. Please get a filter question first."
        
#         # Validate the answer
#         answer_code = get_answred_code_for_filter(room_id,formatted_filter, question, userAnswer)
        
#         if answer_code:
#             selected_value_query = get_selected_value_query(formatted_filter, answer_code)
            
#             if selected_value_query:
#                 # Update the current query
#                 current_answered_query = selected_value_query
#                 all_answered_query.append(selected_value_query)
#                 conversation_states[room_id]["current_answered_query"] = current_answered_query
#                 conversation_states[room_id]["all_answered_query"] = all_answered_query
                
#                 return "Answer is valid and query is updated."
#             else:
#                 return "Answer is valid but query could not be updated. Please try again."
#         else:
#             return f"Answer is not valid. Please provide a valid answer from {question}"



def generate_final_url(endSubCategoryPimId, room_id, summeise_selected_product_details=None):
    """Generate the final filtered product URL after all filter questions are answered."""
    global conversation_states

    # Check if the end subcategory has an engineering tool
    selected_engineering_tool = get_available_engineering_tool(endSubCategoryPimId)
    if selected_engineering_tool != {} and selected_engineering_tool.get("sizing_configurations"):
        sizing_configurations = selected_engineering_tool["sizing_configurations"]
        current_engineering_tool = conversation_states[room_id].get("current_engineering_tool", {})
        if current_engineering_tool != {}:
            answered_questions = current_engineering_tool.get("answered_questions", {})
            url_details=generate_product_urls(endSubCategoryPimId, selected_engineering_tool, answered_questions)

            response = ""
            for url_detail in url_details:
                url = url_detail["url"]
                return f'    {url}   '
                # if isinstance(url_detail, dict) and "resultType" in url_detail:
                #     resultType = url_detail["resultType"]
                #     if resultType == "EXACT":
                #         response += f"Exact product url is {url}\n"
                #         return 
                #     elif resultType == "ECONOMIC":
                #         response += f"Economic product url is {url}\n"
                #     elif resultType == "PERFORMANCE":
                #         response += f"Performance product url is {url}\n"
            return "No products found for the current filter query. Please try different filters or check the query."
    else:
        current_answered_query = conversation_states[room_id].get("current_answered_query", None)
        if current_answered_query is None:
            conversation_states[room_id]["current_answered_query"] = "~:sortByCoreRangeAndNewProduct"
        
        final_url = generate_url(endSubCategoryPimId, current_answered_query)
        
        if final_url:
            return f'    {final_url}   '
        else:
            return "No products found for the current filter query. Please try different filters or check the query."

def reset_filter_state(room_id):
    """Reset the filtering state to start a new filtering process."""
    global conversation_states

    conversation_states[room_id]["current_answered_query"] = None
    conversation_states[room_id]["all_answered_query"] = []
    conversation_states[room_id]["current_filter_data"] = None
    conversation_states[room_id]["skip_filter_questions"] = []
    conversation_states[room_id]["current_engineering_tool"] = {
        "answered_questions": {},
        "skip_filter_questions": {},
        "current_filter_data": {}
    }
    
    return "Filter state has been reset. Ready to start a new filtering process."




class ChatHistoryManager:
    def __init__(self, room_name: str):
        self.room_name = room_name
        self.chat_history: List[Dict[str, Any]] = []
        self.filename = f"chat_history_{room_name}.json"  # Unique filename per room
        # Create chat_logs directory if it doesn't exist
        os.makedirs("chat_logs", exist_ok=True)
        self.filepath = os.path.join("chat_logs", self.filename)
        logger.debug(f"Initialized ChatHistoryManager for room: {room_name}, filepath: {self.filepath}")
        
    def add_message(self, role: str, content: str, timestamp: str = None, metadata: dict = None):
        """Add a message to chat history and save to file"""
        if timestamp is None:
            timestamp = datetime.now().isoformat()
            
        message = {
            "timestamp": timestamp,
            "role": role,  # "user" or "assistant" or "system"
            "content": content,
            "metadata": metadata or {}
        }

        print('message---------->',message)
        
        self.chat_history.append(message)
        self.save_to_file()
        logger.info(f"Added {role} message to chat history: {content[:50]}...")
        
    def save_to_file(self):
        """Save current chat history to JSON file"""
        try:
            data = {
                "room_name": self.room_name,
                "session_start": self.chat_history[0]["timestamp"] if self.chat_history else datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "message_count": len(self.chat_history),
                "messages": self.chat_history
            }
            
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved chat history to {self.filepath}")

        except Exception as e:
            logger.error(f"Failed to save chat history: {e}")

class Assistant(Agent):
    def __init__(self, chat_manager: ChatHistoryManager) -> None:
        super().__init__(
            instructions="""You are a Pre-Sales Application Engineer Support assistant.your name is yobo.you can answer questions about the Festo. developed by Spera company AI Department.
 PRIORITY RULE - PRODUCT MODEL NUMBER DETECTION:
- CRITICAL: If the user mentions a specific product model number or part number (e.g., "HGDD-50-A-G2", "VZWP", "VAEM", etc.), IMMEDIATELY call the search_by_product_model_number function with that model number.
- Look for patterns like: alphanumeric codes with dashes, underscores, or mixed characters that appear to be product identifiers.
- This takes priority over the category selection workflow below.
- After providing the direct search URL, ask if they need additional information or want to explore categories.
 


WORKFLOW:
1. CATEGORY SELECTION:
   - IMPORTANT: When user starts a new product search or changes their mind about product type, ALWAYS call reset_filter_state first to clear previous filtering data.
   - First, select the most relevant main category from all main categories according to user input.
   - If the user input is not enough to select a main category, ask more questions to gather more information until you can select the most relevant category.
   - Use the get_main_categories tool to get all main categories.
   - After the main category is selected, automatically use its pimId to check for subcategories using the check_sub_category_available tool.
   - IMPORTANT: When calling check_sub_category_available, always use the exact pimId from the main categories (e.g., "pim227" for Grippers).
   - If the previous user input is not enough to select a sub categories, ask more questions to gather more information until you can select the most relevant category
   - CRITICAL RULE: This subcategory selection process should be repeated until check_sub_category_available returns'No sub categories available for this pimId'.

2. FILTERING PROCESS:
   - Once you reach an end-level subcategory (no more subcategories available), start the filtering process.
   - Use get_next_filter_question tool with the end-level subcategory pimId to get the first filter question.
   - CRITICAL SMART FILTERING RULE: First call get_next_filter_question to get the actual filter question, THEN analyze if the user already provided an answer to that specific question.
   - EXAMPLES of user-provided information that should be auto-detected:
     * If user said "electric parallel gripper" and filter asks about "Electric vs Pneumatic drive system" → automatically use "Electric"
     * If user mentioned "stroke 1.5mm" and filter asks about stroke length → automatically use "1.5mm"  
     * If user said "24V" and filter asks about voltage → automatically use "24V"
     * If user mentioned specific dimensions, materials, or specifications → use them for corresponding filter questions
   - CRITICAL: When you detect that user already provided an answer in their conversation history, immediately call validate_filter_answer tool with the detected answer instead of asking the question again.
   - IMPORTANT: Only auto-detect answers that the user EXPLICITLY mentioned. Do NOT assume or auto-select any value if the user didn't specifically mention that aspect.
   - CRITICAL: If user answer provided. Do NOT convert, interpret, or modify user input. Pass the exact user text to validate_filter_answer.
   
   ====== CRITICAL AUTO-SELECTION RULES (ZERO TOLERANCE) ======
   1. SINGLE OPTION RULE: Even if a filter question has only ONE option available, NEVER auto-select it. Always present the question to the user and wait for their explicit confirmation.
      - EXAMPLE: If question is "What drive system? • Pneumatic" (only one option), you MUST ask: "What drive system would you like? The available option is: • Pneumatic" and wait for user response.
      - NO EXCEPTIONS: Even if it seems "obvious", always ask the user.
   
   2. UNMENTIONED PARAMETER RULE: If the user never mentioned a specific parameter, NEVER auto-select any value (including minimum, maximum, or default values). Always ask the user.
      - EXAMPLE: If user never mentioned "mass moment of inertia" and question asks for range 13.92-15.07, present the question instead of auto-selecting "13.92".
      - CHECK: Before auto-selecting, ask yourself: "Did the user explicitly mention this specific parameter in their original request?"
   
   3. DOUBLE-CHECK PROCESS: Before calling validate_filter_answer with is_answer_selected_by_llm=true:
      - Step 1: Did user mention this EXACT parameter? (not just similar)
      - Step 2: Is there more than one option available?
      - Step 3: Only auto-select if BOTH answers are YES
   
   ====== WRONG vs RIGHT EXAMPLES ======
   WRONG ❌:
   - Question: "What drive system? • Pneumatic" → Auto-select "Pneumatic"
   - Question: "Mass moment of inertia 13.92-15.07?" → Auto-select "13.92"
   - User said "total gripper size should be around 50 mm" → Ask about size instead of auto-detecting "50"
   
   RIGHT ✅:
   - Question: "What drive system? • Pneumatic" → Ask user: "The available drive system is Pneumatic. Do you want to proceed with this option?"
   - Question: "Mass moment of inertia 13.92-15.07?" → Ask user: "What mass moment of inertia do you need, within the range of 13.92 to 15.07 kgcm²?"
   
   - Only present filter questions to the user if you cannot find the answer anywhere in the conversation history.
   - if user want to skip the filter question, then skip the filter question and call get_next_filter_question tool to get the next filter question.
   - if user input is answer for previously asked filter question, call validate_filter_answer tool to validate the user's answer and update the query state.
   - Continue asking filter questions until all are answered.
   - CRITICAL RULE: When validate_filter_answer returns "Answer is valid and query is updated", you MUST immediately call get_next_filter_question in the same response. Do NOT provide any conversational response. Do NOT wait for user input. Just call the tool immediately.
   - CRITICAL RULE: When get_next_filter_question returns "All filter questions are answered", you MUST immediately call generate_final_url.
   - User said "total gripper size should be around 50 mm" → Auto-detect "50" for size filter questions
 
3. IMPORTANT RULES:
    - Never ask the user for pimId - always extract it from the main categories you already retrieved.
    - Always present filter questions clearly and wait for user responses.
    - Keep track of the filtering state and guide the user through the entire process.
    - Provide the final product URL when filtering is complete.
    - CRITICAL: Always call reset_filter_state when starting a new product search to avoid conflicts with previous filtering sessions.
    - CRITICAL: Your highy specilized for IOT hardware shop, so you should not answer an other information than IOT hardware shop.
    - CRITICAL: You can only give festo.com url for the final product url. and you cant give other site links.
    - CRITICAL: If user give more than one inputs for selections (e.g., "I need both a servo motor and a stepper motor"), you should politely inform you currently i can process one option at a time. lets process one after another
        -CRITICAL: always give short and sweet answers only.
        -CRITICAL: dont give any this inside ** markdown format.
    """,

        )
        self.chat_manager = chat_manager

    conversation_states = {}
        

    # all functions annotated with @function_tool will be passed to the LLM when this
    # agent is active
    
    @function_tool
    async def get_main_categories(self, context: RunContext):
        """Use this tool to get all main categories from the IoT hardware shop."""
        logger.info(f"Getting all main categories from the IoT hardware shop.")


        """Get all main categories from the IoT hardware shop."""
        self.chat_manager.add_message(
            role="system", 
            content=f"Function call: get_main_categories",
            metadata={"function": "get_main_categories"}
        )
        result = find_main_categories()

        self.chat_manager.add_message(
            role="assistant", 
            content=f"Main categories retrieved successfully.",
            metadata={"result": result}
        )
        return result
    
    @function_tool
    async def check_sub_category_available(self, context: RunContext, pimId: str):


        # await self.session_ref.say("hello i am inside sub category selection")

        # context.session.aclose()

        


        

        """Check if any sub categories are available for a given pimId."""
        categories = find_by_pimid(pimId)

        logger.info(f"Checking sub categories for pimId: {pimId}, found: {len(categories)} categories.")
        self.chat_manager.add_message(
            role="system",
            content=f"Function call: check_sub_category_available with pimId {pimId}",
            metadata={"function": "check_sub_category_available", "pimId": pimId}
        )

        if len(categories) > 0:
            result = categories
        else:
            result = "No sub categories available for this pimId"

        self.chat_manager.add_message(
            role="assistant",
            content=f"Sub categories check completed.",
            metadata={"result": result}
        )
        return result

    @function_tool
    async def get_next_filter_question(self, context: RunContext, endSubCategoryPimId: str):

        room_id = self.chat_manager.room_name
        self.chat_manager.add_message(
            role="system",
            content=f"Function call: get_next_filter_question with pimId {endSubCategoryPimId}",
            metadata={"function": "get_next_filter_question", "pimId": endSubCategoryPimId}
        )
    # """Get the next filter question for a given end-level subcategory pimId."""

        # Initialize conversation_states for this room_id if not exists
        if room_id not in self.conversation_states:
            self.conversation_states[room_id] = {
                "current_answered_query": None,
                "all_answered_query": [],
                "current_filter_data": None,
                "skip_filter_questions": [],
                "current_engineering_tool": {
                    "answered_questions": {},
                    "skip_filter_questions": {},
                    "current_filter_data": {}
                }
            }

        #check engineering tool exist for end sub category
        selected_engineering_tool = get_available_engineering_tool(endSubCategoryPimId)
        if selected_engineering_tool != {} and selected_engineering_tool.get("sizing_configurations"):
            sizing_configurations = selected_engineering_tool["sizing_configurations"]
            current_engineering_tool = self.conversation_states[room_id].get("current_engineering_tool", {})
            if current_engineering_tool != {}:
                answered_questions = current_engineering_tool.get("answered_questions", {})
                skip_filter_questions = current_engineering_tool.get("skip_filter_questions", {})
            else:
                answered_questions = {}
                skip_filter_questions = {}
            print(f"Current answered questions: {answered_questions}")
            next_filter = get_next_sizing_tool_filter(sizing_configurations, answered_questions, skip_filter_questions, endSubCategoryPimId)
            self.conversation_states[room_id]["current_engineering_tool"] = {
                    "answered_questions": answered_questions,
                    "skip_filter_questions": skip_filter_questions,
                    "current_filter_data": next_filter
                }
            if next_filter:
                question = get_next_sizing_tool_question(next_filter, answered_questions, endSubCategoryPimId)
                if question:
                    return question
                else:
                    return "Error generating question for the next filter. Please try again."
            else:
                return "All filter questions are answered."
        else:
            current_answered_query =  self.conversation_states[room_id].get("current_answered_query", None)
            if current_answered_query is None:
                self.conversation_states[room_id]["current_answered_query"] = "~:sortByCoreRangeAndNewProduct"
            all_answered_query = self.conversation_states[room_id].get("all_answered_query", [])
            
            skip_filter_questions = self.conversation_states[room_id].get("skip_filter_questions", [])
            # if skip_filter_questions:
            #     conversation_states[room_id]["skip_filter_questions"]=[]

            # if len(all_answered_query) > 3:
            #     return "All filter questions are answered"
            
            next_filter = get_next_filter(endSubCategoryPimId, current_answered_query,skip_filter_questions)
            
            if next_filter:
                formatted_filter = get_formatted_filter(next_filter)
                question = make_filter_question(room_id,endSubCategoryPimId,formatted_filter)
                self.conversation_states[room_id]["current_filter_data"] = formatted_filter
                
                if question:
                    return question
                else:
                    return "Error generating question for the next filter. Please try again."
            else:
                return "All filter questions are answered"

    @function_tool
    async def validate_filter_answer(self, context: RunContext, pimId: str, question: str, userAnswer: str):

        room_id = 124

        # Initialize conversation_states for this room_id if not exists
        if room_id not in self.conversation_states:
            self.conversation_states[room_id] = {
                "current_answered_query": None,
                "all_answered_query": [],
                "current_filter_data": None,
                "skip_filter_questions": [],
                "current_engineering_tool": {
                    "answered_questions": {},
                    "skip_filter_questions": {},
                    "current_filter_data": {}
                }
            }

        #check engineering tool exist for end sub category
        selected_engineering_tool = get_available_engineering_tool(pimId)
        if selected_engineering_tool != {} and selected_engineering_tool.get("sizing_configurations"):
            sizing_configurations = selected_engineering_tool["sizing_configurations"]
            current_engineering_tool = self.conversation_states[room_id].get("current_engineering_tool", {})
            if current_engineering_tool != {} and current_engineering_tool.get("current_filter_data", None):
                formatted_filter = current_engineering_tool.get("current_filter_data", {})
                answered_questions = current_engineering_tool.get("answered_questions", {})
                skip_filter_questions = current_engineering_tool.get("skip_filter_questions", {})

                # Validate the answer
                answer_code = validate_sizing_tool_answer(room_id,pimId, question, userAnswer, formatted_filter, answered_questions)
                
                if answer_code:
                    answered_questions[formatted_filter["payload_attribute"]] = answer_code
                    self.conversation_states[room_id]["current_engineering_tool"] = {
                        "answered_questions": answered_questions,
                        "skip_filter_questions": skip_filter_questions,
                        "current_filter_data": formatted_filter
                    }
                    return "Answer is valid and query is updated."
                else:
                    return f"Answer is not valid. Please provide a valid answer from {question}"
            else:
                return "Error: No filter data found. Please get a filter question first."
        else:
            current_answered_query = self.conversation_states[room_id].get("current_answered_query", None)
            if current_answered_query is None:
                self.conversation_states[room_id]["current_answered_query"] = "~:sortByCoreRangeAndNewProduct"
            all_answered_query = self.conversation_states[room_id].get("all_answered_query", [])
            
            formatted_filter = self.conversation_states[room_id].get("current_filter_data", None)

            if not formatted_filter:
                return "Error: No filter data found. Please get a filter question first."
            
            # Validate the answer
            answer_code = get_answred_code_for_filter(room_id,formatted_filter, question, userAnswer)
            
            if answer_code:
                selected_value_query = get_selected_value_query(formatted_filter, answer_code)
                
                if selected_value_query:
                    # Update the current query
                    current_answered_query = selected_value_query
                    all_answered_query.append(selected_value_query)
                    self.conversation_states[room_id]["current_answered_query"] = current_answered_query
                    self.conversation_states[room_id]["all_answered_query"] = all_answered_query
                    
                    return "Answer is valid and query is updated."
                else:
                    return "Answer is valid but query could not be updated. Please try again."
            else:
                return f"Answer is not valid. Please provide a valid answer from {question}"


    @function_tool
    async def generate_final_url(self, context: RunContext, endSubCategoryPimId: str):
        """Generate the final filtered product URL after all filter questions are answered."""

        room_id = 124

        # Initialize conversation_states for this room_id if not exists
        if room_id not in self.conversation_states:
            self.conversation_states[room_id] = {
                "current_answered_query": None,
                "all_answered_query": [],
                "current_filter_data": None,
                "skip_filter_questions": [],
                "current_engineering_tool": {
                    "answered_questions": {},
                    "skip_filter_questions": {},
                    "current_filter_data": {}
                }
            }

        # Check if the end subcategory has an engineering tool
        selected_engineering_tool = get_available_engineering_tool(endSubCategoryPimId)
        if selected_engineering_tool != {} and selected_engineering_tool.get("sizing_configurations"):
            sizing_configurations = selected_engineering_tool["sizing_configurations"]
            current_engineering_tool = self.conversation_states[room_id].get("current_engineering_tool", {})
            if current_engineering_tool != {}:
                answered_questions = current_engineering_tool.get("answered_questions", {})
                url_details=generate_product_urls(endSubCategoryPimId, selected_engineering_tool, answered_questions)

                response = ""
                for url_detail in url_details:
                    url = url_detail["url"]
                    return f'    {url}   '
                    # if isinstance(url_detail, dict) and "resultType" in url_detail:
                    #     resultType = url_detail["resultType"]
                    #     if resultType == "EXACT":
                    #         response += f"Exact product url is {url}\n"
                    #         return 
                    #     elif resultType == "ECONOMIC":
                    #         response += f"Economic product url is {url}\n"
                    #     elif resultType == "PERFORMANCE":
                    #         response += f"Performance product url is {url}\n"
                return "No products found for the current filter query. Please try different filters or check the query."
        else:
            current_answered_query = self.conversation_states[room_id].get("current_answered_query", None)
            if current_answered_query is None:
                self.conversation_states[room_id]["current_answered_query"] = "~:sortByCoreRangeAndNewProduct"
            
            final_url = generate_url(endSubCategoryPimId, current_answered_query)
            
            if final_url:
                return f'    {final_url}   '
            else:
                return "No products found for the current filter query. Please try different filters or check the query."

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    # Initialize chat history manager with room name
    chat_manager = ChatHistoryManager(ctx.room.name)
    
    # each log entry will include these fields
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Set up a voice AI pipeline using OpenAI, Cartesia, Deepgram, and the LiveKit turn detector
    session = AgentSession(
        # any combination of STT, LLM, TTS, or realtime API can be used
        llm=openai.LLM(model="gpt-4o-mini",temperature=0.3,parallel_tool_calls=False),
        stt=deepgram.STT(model="nova-3", language="en"),
        # stt=groq.STT(
        #     model="whisper-large-v3-turbo",
        #     language="en",
        # ),

        # llm=groq.LLM(
        #     # model="llama3-8b-8192"
        #     model="meta-llama/llama-4-scout-17b-16e-instruct"
        # ),
        # tts=groq.TTS(
        #     model="playai-tts",
        #     voice="Arista-PlayAI",
        # ),
        # tts=cartesia.TTS(),
        tts=openai.TTS(
            model="tts-1",
            voice="alloy",
        ),
        # use LiveKit's turn detection model
        # turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],

    )

    # To use the OpenAI Realtime API, use the following session setup instead:
    # session = AgentSession(
    #     llm=openai.realtime.RealtimeModel()
    # )

        # Robust message content extraction
    def get_message_content(message) -> str:
        """Extract content from message, handling various formats"""
        if hasattr(message, 'content') and message.content:
            return str(message.content)
        elif isinstance(message, dict) and 'content' in message:
            return str(message['content'])
        elif isinstance(message, str):
            return message
        else:
            logger.warning(f"Unexpected message formatbury: {message}")
            return str(message)
        
    # Event handlers to track conversation in real-time
    @session.on("user_started_speaking")
    def on_user_started_speaking():
        logger.info("User started speaking")
        chat_manager.add_message(
            role="system",
            content="User started speaking",
            metadata={"event": "user_started_speaking"}
        )

    @session.on("user_stopped_speaking")  
    def on_user_stopped_speaking():
        logger.info("User stopped speaking")
        chat_manager.add_message(
            role="system",
            content="User stopped speaking",
            metadata={"event": "user_stopped_speaking"}
        )

    @session.on("agent_started_speaking")
    def on_agent_started_speaking(message):
        logger.info("Agent started speaking",message.content)
        chat_manager.add_message(
            role="system",
            content="Agent started speaking",
            metadata={"event": "agent_started_speaking"}
        )

    @session.on("agent_stopped_speaking")
    def on_agent_stopped_speaking():
        logger.info("Agent stopped speaking")
        chat_manager.add_message(
            role="system",
            content="Agent stopped speaking",
            metadata={"event": "agent_stopped_speaking"}
        )

    # Track user speech transcripts (if available)
    @session.on("user_speech_committed")
    def on_user_speech_committed(message):
        """Triggered when user speech is transcribed and committed"""
        content = get_message_content(message)
        logger.debug(f"Event: User speech committed - Content: {content}")
        chat_manager.add_message(
            role="user",
            content=content,
            metadata={"type": "speech_to_text", "event": "user_speech_committed"}
        )

    # Track agent responses (if available)
    @session.on("agent_speech_committed")
    def on_agent_speech_committed(message):
        """Triggered when agent speech is committed"""
        content = get_message_content(message)
        logger.debug(f"Event: Agent speech committed - Content: {content}")
        chat_manager.add_message(
            role="assistant", 
            content=content,
            metadata={"type": "text_to_speech", "event": "agent_speech_committed"}
        )

    # Alternative event handlers (different versions might use different event names)
    @session.on("user_message")
    def on_user_message(message):
        content = get_message_content(message)
        logger.debug(f"Event: User message - Content: {content}")
        chat_manager.add_message(
            role="user",
            content=content,
            metadata={"type": "user_message", "event": "user_message"}
        )

    @session.on("agent_message")
    def on_agent_message(message):
        content = get_message_content(message)
        logger.debug(f"Event: Agent message - Content: {content}")
        chat_manager.add_message(
            role="assistant",
            content=content,
            metadata={"type": "agent_message", "event": "agent_message"}
        )

    # Track room events
    @session.on("participant_connected")
    def on_participant_connected(participant):
        logger.debug(f"Event: Participant connected - ID: {participant.identity}")
        chat_manager.add_message(
            role="system",
            content=f"Participant connected: {participant.identity}",
            metadata={"event": "participant_connected", "participant_id": participant.identity}
        )

    @session.on("participant_disconnected")
    def on_participant_disconnected(participant):
        logger.debug(f"Event: Participant disconnected - ID: {participant.identity}")
        chat_manager.add_message(
            role="system",
            content=f"Participant disconnected: {participant.identity}",
            metadata={"event": "participant_disconnected", "participant_id": participant.identity}
        )

    # log metrics as they are emitted, and total usage after session is over
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        logger.debug(f"Event: Metrics collected - {ev.metrics}")
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.debug(f"Usage summary: {summary}")
        # Log session end
        chat_manager.add_message(
            role="system",
            content="Session ended",
            metadata={"event": "session_end", "usage_summary": str(summary)}
        )

    # shutdown callbacks are triggered when the session is over
    ctx.add_shutdown_callback(log_usage)
    
    # Chat history tracking - Add session start message
    chat_manager.add_message(
        role="system", 
        content="Session started",
        metadata={"event": "session_start", "room": ctx.room.name}
    )

   
    await session.start(
        agent=Assistant(chat_manager),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            # LiveKit Cloud enhanced noise cancellation
            # - If self-hosting, omit this parameter
            # - For telephony applications, use `BVCTelephony` for best results

            # noise_cancellation=noise_cancellation.BVC(),
            # noise_cancellation=noise_cancellation.BVC(),
            
        ),
        room_output_options=RoomOutputOptions(transcription_enabled=True),
    )

    await asyncio.sleep(1)
    await session.say("Hi, I am yobo. your pre-sales application engineering assistant in Festo, how can I help you today?",allow_interruptions=True) # initial message


    # join the room when agent is ready
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
