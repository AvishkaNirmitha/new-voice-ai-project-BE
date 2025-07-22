import re
import sys
from typing import Dict
import re

# Add the scripts directory to the Python path to import find_categories
import sys
from pathlib import Path
project_root = Path(__file__).resolve().parents[1]
sys.path.append(str(project_root))

scripts_dir = Path(__file__).parent
sys.path.append(str(scripts_dir)) 

from scripts.v1.find_categories import find_main_categories, find_by_pimid, get_url_of_categoriy, get_brands_of_categories, get_brands_of_categories_with_query
from scripts.v1.filter_function import get_next_filter, get_formatted_filter, make_filter_question, get_answred_code_for_filter, get_selected_value_query, generate_url
from scripts.v1.engineering_tool_functions import get_available_engineering_tool, get_next_sizing_tool_question, validate_sizing_tool_answer, get_next_sizing_tool_filter, generate_product_urls



# Store conversation state for each room_id
conversation_states: Dict[str, Dict] = {}



tool_map_names_for_fe={
    "get_main_categories":{'display_text': "\n🔍 searching in festo inventory\n","tts_text": "searching in festo inventory"},
    "check_sub_category_available": {'display_text':"\n🔍  searching in festo inventory deeply\n","tts_text": "searching in festo inventory deeply"},
    "get_next_filter_question": {'display_text': "\n filter processing.... \n" ,"tts_text": "filter processing"},
    "validate_filter_answer": {'display_text': "\n validating your input....  \n" ,"tts_text": "i am validating your input"},
    "generate_final_url": {'display_text': "\n 🔗 finding best matching product in our store\n" ,"tts_text": "finding best matching product in our store"},
    "search_by_product_model_number": {'display_text': "\n 🔍 searching for specific product model\n" ,"tts_text": "searching for specific product model"},
    "skip_filter_question": {'display_text': "\n ⏭️ skipping current filter question\n" ,"tts_text": "skipping current filter question"},
}
# Define the tools for OpenAI API
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_main_categories",
            "description": "Get all main categories from the IoT hardware shop. Returns a list of categories with name, pimId, and description.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_sub_category_available",
            "description": "Check if any sub categories are available for a given pimId. Returns a list of subcategories with name, pimId, and description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pimId": {"type": "string", "description": "The pimId of the main category to check sub categories for."}
                },
                "required": ["pimId"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_next_filter_question",
            "description": "Get the next filtering question for a given end-level subcategory pimId. This starts the filtering process after all subcategories are explored.",
            "parameters": {
                "type": "object",
                "properties": {
                    "endSubCategoryPimId": {"type": "string", "description": "The pimId of the end-level subcategory to get filter questions for."}
                },
                "required": ["endSubCategoryPimId"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "validate_filter_answer",
            "description": "Validate user's answer to a filter question and update the query state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pimId": {"type": "string", "description": "The pimId of the end-level subcategory."},
                    "question": {"type": "string", "description": "The filter question that was asked."},
                    "userAnswer": {"type": "string", "description": "The user's answer to the filter question."},
                    "is_answer_selected_by_llm": {"type": "boolean", "description": "Set to true when the answer was automatically detected by the LLM from conversation history. Set to false when the answer is provided directly by the user. Default is false."},
                    "is_answer_selected_by_llm_text_for_user": {"type": "string", "description": "Custom text to display to the user when is_answer_selected_by_llm is true. This explains what answer was automatically detected (e.g., 'using Electric drive system for filtering'). Only used when is_answer_selected_by_llm is true."}
                },
                "required": ["pimId", "question", "userAnswer"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_final_url",
            "description": "Generate the final filtered product URL after all filter questions are answered.",
            "parameters": {
                "type": "object",
                "properties": {
                    "endSubCategoryPimId": {"type": "string", "description": "The pimId of the end-level subcategory to generate URL for."},
                    "summeise_selected_product_details": {"type": "string", "description": "Summary of the selected product details and specifications."}
                },
                "required": ["endSubCategoryPimId","summeise_selected_product_details"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reset_filter_state",
            "description": "Reset the filtering state to start a new filtering process. Use this when starting a new product search or when the user wants to change their selection.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_by_product_model_number",
            "description": "Search for a specific product by its model number. Use this when the user mentions a specific product model number like 'HGDD-50-A-G2'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "model_number": {"type": "string", "description": "The product model number to search for."}
                },
                "required": ["model_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "skip_filter_question",
            "description": "Skip the current filter question and proceed to the next one. Use this when the user wants to skip a filter question or when they indicate they don't want to specify a particular filter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "endSubCategoryPimId": {"type": "string", "description": "The pimId of the end-level subcategory to skip the filter question for."}
                },
                "required": ["endSubCategoryPimId"]
            }
        }
    }
]




def extract_and_replace_link(text):
    # Find URL
    url_pattern = r'https?://[^\s\]\)]+'
    match = re.search(url_pattern, text)
    
    if match:
        url = match.group()
        # Replace the URL with placeholder or remove the markdown link
        replaced_text = re.sub(r'\[.*?\]\([^\s\)\]]+\)', '', text)
        return url, replaced_text.strip()
    else:
        return None

# Tool implementation functions
def get_main_categories():
    """Get all main categories from the IoT hardware shop."""
    return find_main_categories()

def check_sub_category_available(pimId):
    """Check if any sub categories are available for a given pimId."""
    categories = find_by_pimid(pimId)
    if len(categories) > 0:
        return categories
    else:
        return "No sub categories available for this pimId"

def get_next_filter_question(endSubCategoryPimId, room_id):
    """Get the next filter question for a given end-level subcategory pimId."""
    global conversation_states

    #check engineering tool exist for end sub category
    selected_engineering_tool = get_available_engineering_tool(endSubCategoryPimId)
    if selected_engineering_tool != {} and selected_engineering_tool.get("sizing_configurations"):
        sizing_configurations = selected_engineering_tool["sizing_configurations"]
        current_engineering_tool = conversation_states[room_id].get("current_engineering_tool", {})
        if current_engineering_tool != {}:
            answered_questions = current_engineering_tool.get("answered_questions", {})
            skip_filter_questions = current_engineering_tool.get("skip_filter_questions", {})
        else:
            answered_questions = {}
            skip_filter_questions = {}
        print(f"Current answered questions: {answered_questions}")
        next_filter = get_next_sizing_tool_filter(sizing_configurations, answered_questions, skip_filter_questions, endSubCategoryPimId)
        conversation_states[room_id]["current_engineering_tool"] = {
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
        current_answered_query = conversation_states[room_id].get("current_answered_query", None)
        if current_answered_query is None:
            conversation_states[room_id]["current_answered_query"] = "~:sortByCoreRangeAndNewProduct"
        all_answered_query = conversation_states[room_id].get("all_answered_query", [])
        
        skip_filter_questions = conversation_states[room_id].get("skip_filter_questions", [])
        # if skip_filter_questions:
        #     conversation_states[room_id]["skip_filter_questions"]=[]

        # if len(all_answered_query) > 3:
        #     return "All filter questions are answered"
        
        next_filter = get_next_filter(endSubCategoryPimId, current_answered_query,skip_filter_questions)
        
        if next_filter:
            formatted_filter = get_formatted_filter(next_filter)
            question = make_filter_question(room_id,endSubCategoryPimId,formatted_filter)
            conversation_states[room_id]["current_filter_data"] = formatted_filter
            
            if question:
                return question
            else:
                return "Error generating question for the next filter. Please try again."
        else:
            return "All filter questions are answered"

def validate_filter_answer(pimId, question, userAnswer, room_id,is_answer_selected_by_llm=False):
    """Validate user's answer to a filter question and update the query state."""
    global conversation_states

    #check engineering tool exist for end sub category
    selected_engineering_tool = get_available_engineering_tool(pimId)
    if selected_engineering_tool != {} and selected_engineering_tool.get("sizing_configurations"):
        sizing_configurations = selected_engineering_tool["sizing_configurations"]
        current_engineering_tool = conversation_states[room_id].get("current_engineering_tool", {})
        if current_engineering_tool != {} and current_engineering_tool.get("current_filter_data", None):
            formatted_filter = current_engineering_tool.get("current_filter_data", {})
            answered_questions = current_engineering_tool.get("answered_questions", {})
            skip_filter_questions = current_engineering_tool.get("skip_filter_questions", {})

            # Validate the answer
            answer_code = validate_sizing_tool_answer(room_id,pimId, question, userAnswer, formatted_filter, answered_questions)
            
            if answer_code:
                answered_questions[formatted_filter["payload_attribute"]] = answer_code
                conversation_states[room_id]["current_engineering_tool"] = {
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
        current_answered_query = conversation_states[room_id].get("current_answered_query", None)
        if current_answered_query is None:
            conversation_states[room_id]["current_answered_query"] = "~:sortByCoreRangeAndNewProduct"
        all_answered_query = conversation_states[room_id].get("all_answered_query", [])
        
        formatted_filter = conversation_states[room_id].get("current_filter_data", None)

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
                conversation_states[room_id]["current_answered_query"] = current_answered_query
                conversation_states[room_id]["all_answered_query"] = all_answered_query
                
                return "Answer is valid and query is updated."
            else:
                return "Answer is valid but query could not be updated. Please try again."
        else:
            return f"Answer is not valid. Please provide a valid answer from {question}"

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


def skip_filter_question(endSubCategoryPimId,room_id):
    """Skip the filter question and call get_next_filter_question tool to get the next filter question."""
    global conversation_states

    # Check if the end subcategory has an engineering tool
    selected_engineering_tool = get_available_engineering_tool(endSubCategoryPimId)
    if selected_engineering_tool != {} and selected_engineering_tool.get("sizing_configurations"):
        sizing_configurations = selected_engineering_tool["sizing_configurations"]
        current_engineering_tool = conversation_states[room_id].get("current_engineering_tool", {})
        if current_engineering_tool != {}:
            answered_questions = current_engineering_tool.get("answered_questions", {})
            skip_filter_questions = current_engineering_tool.get("skip_filter_questions", {})
            next_filter = get_next_sizing_tool_filter(sizing_configurations, answered_questions, skip_filter_questions, endSubCategoryPimId)
            if next_filter:
                skip_filter_code = next_filter["payload_attribute"]
                skip_filter_questions[skip_filter_code] = skip_filter_code
                conversation_states[room_id]["current_engineering_tool"] = {
                    "answered_questions": answered_questions,
                    "skip_filter_questions": skip_filter_questions,
                    "current_filter_data": next_filter
                }
                return "Filter question has been skipped. Time to get next filter question"
            else:
                return "All filter questions are answered"
    else:
        current_answered_query = conversation_states[room_id].get("current_answered_query", None)
        if current_answered_query is None:
            conversation_states[room_id]["current_answered_query"] = "~:sortByCoreRangeAndNewProduct"
        
        skip_filter_questions = conversation_states[room_id].get("skip_filter_questions", [])
        # if skip_filter_questions:
        #     conversation_states[room_id]["skip_filter_questions"]=[]

        next_filter = get_next_filter(endSubCategoryPimId, current_answered_query,skip_filter_questions)

        if next_filter:
            formatted_filter = get_formatted_filter(next_filter)
            skip_filter_code = formatted_filter['code']
            conversation_states[room_id]["skip_filter_questions"].append(skip_filter_code)
            
            return "Filter question has been skipped. Time to get next filter question"
        else:
            return "All filter questions are answered"




def search_by_product_model_number(model_number):
    """Search for a specific product by its model number."""
    return "https://www.festo.com/gr/en/search/?text=" + model_number



# System message for the chatbot
system_message = """
    You are a helpful assistant that can answer questions about the Festo IoT hardware shop. developed by Spera company AI Department.
 
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
   """


    # Run on 0.0.0.0 to make it accessible externally