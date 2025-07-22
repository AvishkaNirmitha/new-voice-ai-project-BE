import requests
import json
from api_headers import get_headers
from scripts.v1.find_categories import find_sub_category_by_pimid, get_engineering_tool_by_pimid
from datetime import datetime
from groq import Groq
import os
from dotenv import load_dotenv, find_dotenv
import re

dotenv_path = find_dotenv()
load_dotenv(dotenv_path, override=True)

LLM = "llama-3.3-70b-versatile"

# Initialize Groq client
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

headers = get_headers()

# selected_engineering_tool = {}
# answered_questions = {}

def check_and_extract_code(ai_response):
    """
    Extracts the code from a formatted AI response:
    ===CODE==={"code": "<code>"}===END_CODE===
    
    Returns:
        dict with 'matched': True/False and 'code': value or None
    """
    pattern = r'===CODE===(.*?)===END_CODE==='
    match = re.search(pattern, ai_response.strip(), re.DOTALL)

    if match:
        try:
            json_str = match.group(1).strip()
            print(f"🔍 DEBUG: Found code marker with JSON: '{json_str}'")

            # Handle possible double braces
            if json_str.startswith('{{') and json_str.endswith('}}'):
                json_str = json_str[1:-1]

            json_data = json.loads(json_str)
            code = json_data.get("code", None)

            return code

        except json.JSONDecodeError as e:
            print(f"\n❌ Found code marker but invalid JSON format: {e}")
            print(f"    Raw JSON string was: '{match.group(1)}'")
            return None
    else:
        print(f"🔍 DEBUG: No code marker found in response: '{ai_response[:100]}...'")

    return None

def make_groq_request(messages, model="llama-3.3-70b-versatile", temperature=0.3):
    """
    Make a reusable request to Groq API.
    
    Args:
        messages (list): List of message objects for the conversation
        model (str): Model name to use (default: "llama-3.3-70b-versatile")
        temperature (float): Temperature for response generation (default: 0.3)
    
    Returns:
        tuple: (success: bool, response_content: str or None, error_message: str or None, token_usage: dict or None)
    """
    try:
        response = groq_client.chat.completions.create(
            messages=messages,
            model=model,
            temperature=temperature
        )

        if response and response.choices:
            bot_reply = response.choices[0].message.content
            token_usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
            print(f"DEBUG - token_usage: '{token_usage}'")
            # return True, bot_reply, None, token_usage
            return True, bot_reply, None, token_usage
        else:
            return False, None, "No response received from Groq API", None

    except Exception as e:
        return False, None, f"Groq API error: {str(e)}", None

def log_groq_response(room_id, log_type, type, system_message, question=None, user_answer=None,
                      response_content=None, error_message=None, extract_code=None):
    """
    Log the Groq API response grouped by room_id.
    """
    if type== "question_generation":
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "log_type": log_type,
            "type": type,
            "system_message": system_message.strip(),
            "question": response_content
        }
    elif type == "code_generation":
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "log_type": log_type,
            "type": type,
            "system_message": system_message.strip(),
            "question": question.strip() if question else None,
            "user_answer": user_answer.strip() if user_answer else None,
            "extract_code": extract_code.strip() if extract_code else None,
        }

    if log_type == "success":
        log_entry["response_content"] = response_content.strip() if response_content else None
    elif log_type == "error":
        log_entry["error_message"] = error_message.strip() if error_message else None

    # Determine file path
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, 'all_data', 'groq_response_log.json')

    # Create the file directory if it doesn't exist
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # Load existing logs
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                all_logs = json.load(f)
            except json.JSONDecodeError:
                all_logs = {}
    else:
        all_logs = {}

    # Append or create new room entry
    if room_id in all_logs:
        all_logs[room_id].append(log_entry)
    else:
        all_logs[room_id] = [log_entry]

    # Save the updated logs
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(all_logs, f, indent=4, ensure_ascii=False)

def make_filter_question(pimId, next_filter, answered_questions):
    end_sub_category = find_sub_category_by_pimid(pimId)
    end_sub_category_name = end_sub_category.get('name', '') if end_sub_category else ''
    end_sub_category_description = end_sub_category.get('description', '') if end_sub_category else ''

    if next_filter["key"] not in answered_questions and next_filter["resolve"] == "server":
        type = next_filter["type"]
        if type == "slider":
            print(f"  Question : {next_filter['label']}({next_filter['unit']}) ({next_filter['key']}) (ID: {next_filter['id']})")
            print(f"  Values: (min: {next_filter['value']['min']}, max: {next_filter['value']['max']}, step: {next_filter['value']['step']})")
            custom_prompt_for_each_layout_type = (
                f"You are a helpful assistant. Based on the given category and filter details, "
                f"generate a friendly and natural-sounding question that can be shown to users.\n\n"
                f"Category Name: {end_sub_category_name}\n"
                f"Category Description: {end_sub_category_description}\n"
                f"Question needed for filter: {next_filter['label']}\n"
                f"You are given a numeric range filter.\n"
                f"Filter Name: {next_filter['label']}\n"
                f"Range: {next_filter['value']['min']} to {next_filter['value']['max']} {next_filter['unit']}\n\n"
                f"Only return a user-friendly question asking for a minimum value selection in this range. "
                f"Mention the valid range is {next_filter['value']['min']} to {next_filter['value']['max']} {next_filter['unit']}\n"
            )
        elif type == "button":
            print(f"  Question : {next_filter['label']} ({next_filter['key']}) (ID: {next_filter['id']})")
            for value in next_filter["value"]:
                print(f"    Value: {value['label']} (Data: {value['data']})")
            custom_prompt_for_each_layout_type = (
                f"You are a helpful assistant. Based on the given category and filter details, "
                f"generate a friendly and natural-sounding question that can be shown to users.\n\n"
                f"Category Name: {end_sub_category_name}\n"
                f"Category Description: {end_sub_category_description}\n"
                f"Question needed for filter: {next_filter['label']}\n"
                f"You are given a button filter with multiple options.\n"
                f"Filter Name: {next_filter['label']}\n"
                f"Options:\n"
                f"{', '.join([value['label'] for value in next_filter['value']])}\n"
                f"Only return a user-friendly question asking for a selection from the available options.\n"
                f"Mention the available options are: {', '.join([value['label'] for value in next_filter['value']])}\n"
            )
        elif type == "empty":
            print(f"  Question : {next_filter['label']} ({next_filter['key']}) (ID: {next_filter['id']})")
    
    messages = [
        {
            "role": "system",
            "content": custom_prompt_for_each_layout_type
        }
    ]

    success, response_content, error_message, token_usage = make_groq_request(messages)
    
    # success =True
    # response_content = "What is the minimum value you would like to select in this range?"
    if success:
        return response_content.strip()
    else:
        print(f"Error generating question for the filter: {error_message}")
        return "Error generating question for the filter. Please try again."

def get_answered_code_for_sizing_tool(room_id,pimId,next_filter, question, answer, answered_questions):
    end_sub_category = find_sub_category_by_pimid(pimId)
    end_sub_category_name = end_sub_category.get('name', '') if end_sub_category else ''
    end_sub_category_description = end_sub_category.get('description', '') if end_sub_category else ''

    if next_filter["key"] not in answered_questions and next_filter["resolve"] == "server":
        type = next_filter["type"]

        if type == "slider":
            formatted_filter_for_get_code = {
                "name": next_filter['label'],
                "sliderUnit": next_filter['unit'],
                "sliderMinValue": next_filter['value']['min'],
                "sliderMaxValue": next_filter['value']['max'],
                "sliderStep": next_filter['value']['step'],
            }
            custom_prompt_for_each_layout_type = f"""
                You are a strict value extractor.

                Your task is to:
                - Extract a numeric value from the user's answer.
                - The value must be between {formatted_filter_for_get_code['sliderMinValue']} and {formatted_filter_for_get_code['sliderMaxValue']} (inclusive).
                - The value must be a multiple of {formatted_filter_for_get_code['sliderStep']} relative to the minimum value.
                - If the user gives a decimal number, round it to the **nearest multiple of {formatted_filter_for_get_code['sliderStep']}**.
                - If the rounded value falls outside the valid range, return `"None"`.
                - Return the value with the same precision as the sliderStep (e.g., if sliderStep is 0.1, return one decimal place).

                Instructions:
                - Return a **numeric value** that is a multiple of {formatted_filter_for_get_code['sliderStep']} within the given range.
                - The output format must be (strictly this, no explanation):
                ===CODE==={{"code": <numeric_value>}}===END_CODE===
                - If the value is out of range or not a valid multiple of {formatted_filter_for_get_code['sliderStep']}, return:
                ===CODE==={{"code": "None"}}===END_CODE===

                Question: {question}
                User's Answer: {answer}
                Valid Range: {formatted_filter_for_get_code['sliderMinValue']} to {formatted_filter_for_get_code['sliderMaxValue']} {formatted_filter_for_get_code['sliderUnit']}
                Step: {formatted_filter_for_get_code['sliderStep']} {formatted_filter_for_get_code['sliderUnit']}
                """
        elif type == "button":
            formatted_filter_for_get_code = {
                "name": next_filter['label'],
                "values": [{"name": item['label'], "code": item['data']} for item in next_filter['value']]
            }
            custom_prompt_for_each_layout_type = f"""
                You are a matching engine. The user has answered a question using natural language.

                Your task is to:
                - Identify the best-matching value from the given list of values.
                - Match the user's answer against the `name` field in the values (case-insensitive, approximate match allowed).
                - Return the corresponding `code`.

                Instructions:
                - You are given a question and a user's answer.
                - User can only answer for one value.
                - The values are provided in a structured format.
                - Only use the `name` field to identify a match. Accept flexible formats (e.g., '10' matches '10.0').
                - Return the result strictly in this format without any additional text:
                ===CODE==={{"code": "<matched_code>"}}===END_CODE===
                - If no match is found, return:
                ===CODE==={{"code": "None"}}===END_CODE===

                Question: {question}
                User's Answer: {answer}
                Values: {formatted_filter_for_get_code['values']}
                """

        elif type == "empty":
            custom_prompt_for_each_layout_type = (
                f"You are a helpful assistant. Based on the given category and filter details, "
                f"generate a friendly and natural-sounding question that can be shown to users.\n\n"
                f"Category Name: {end_sub_category_name}\n"
                f"Category Description: {end_sub_category_description}\n"
                f"Question needed for filter: {next_filter['label']}\n"
                f"You are given an empty filter.\n"
                f"Filter Name: {next_filter['label']}\n"
                f"Only return a user-friendly question asking for a selection from the available options.\n"
            )

        success, response_content, error_message, token_usage = make_groq_request(
        messages=[
            {
                "role": "system",
                "content": custom_prompt_for_each_layout_type
            },
            {
                "role": "user",
                "content": f"Please extract the matched value from my answer."
            }
        ]
        )

        print(f"DEBUG - Response content: '{response_content}'")
        if success:
            # Extract the code using helper function
            matched_code = check_and_extract_code(response_content)

            answer_code = None
            type = next_filter["type"]
            if type == "slider":
                if matched_code is not None and matched_code != "None":
                    value = float(matched_code)
                    step = formatted_filter_for_get_code['sliderStep']
                    # Check if step is an integer (no decimal places)
                    if float(step).is_integer():
                        # Format as integer if step is an integer
                        value = int(round(value / step) * step)
                        if formatted_filter_for_get_code['sliderMinValue'] <= value <= formatted_filter_for_get_code['sliderMaxValue']:
                            answer_code = str(value)
                        else:
                            answer_code = "None"
                    else:
                        # Format as float with the same precision as step
                        step_str = str(step)
                        decimal_places = len(step_str.split('.')[-1]) if '.' in step_str else 0
                        value = round(value / step) * step
                        if formatted_filter_for_get_code['sliderMinValue'] <= value <= formatted_filter_for_get_code['sliderMaxValue']:
                            answer_code = f"{value:.{decimal_places}f}"
                        else:
                            answer_code = "None"
            elif type == "button":
                if matched_code is not None and matched_code != "None":
                    for value in next_filter['value']:
                        if value['data'] == matched_code:
                            answer_code = value['data']
                   
            # elif formatted_filter['layoutType'] == "STROKE_RANGE":
            #     for value in formatted_filter['values']:
            #         if value['code'] == matched_code:
            #             answer_code = matched_code
            # elif formatted_filter['layoutType'] == "SLIDER_MIN_VALUE":
            #     print(f"DEBUG - Matched code: '{matched_code}'")
            #     if matched_code is not None and matched_code != "None":
            #         value = int(matched_code)
            #         if formatted_filter['sliderMinValue'] <= value <= formatted_filter['sliderMaxValue']:
            #             answer_code = str(value)
                        
            log_groq_response(
                room_id=room_id,
                log_type="success",
                type="code_generation",
                system_message=custom_prompt_for_each_layout_type,
                question=question,
                user_answer=answer,
                response_content=response_content,
                extract_code=answer_code,
            )
            return answer_code
        else:
            log_groq_response(
                room_id=room_id,
                log_type="error",
                type="code_generation",
                system_message=custom_prompt_for_each_layout_type,
                question=question,
                user_answer=answer,
                error_message=error_message,
                extract_code=None,
            )
            print(f"Error generating code: {error_message}")
        
    return None
        
def get_available_products(selected_engineering_tool, answered_questions):
    # Build the payload using answered_questions with sensible defaults

    payload_dict = selected_engineering_tool.get("result_payload", {})
    if selected_engineering_tool["name"] == "Gripper sizing":
        for key, payload in selected_engineering_tool["result_payload"].items():
            if key in answered_questions:
                payload_dict[key] = answered_questions[key]
            else:
                payload_dict[key] = payload

        answered_questions["additionalFunctions"]
        if 'additionalFunctions' in answered_questions:
            value = answered_questions['additionalFunctions']
            payload_dict['isDustproof'] = value == 'dustproof'
            payload_dict['isPrecise'] = value == 'precise'

    if payload_dict:
        payload = json.dumps(payload_dict)
        response = requests.post(
            url=selected_engineering_tool["result_url"],
            headers=headers,
            data=payload
        )
        if response.status_code == 200:
            print("Request was successful!")
            return response.json()
        else:
            print("Request failed with status code:", response.status_code)
            return []
    else:
        print("No payload available for the request.")
        return []    
    
def get_available_engineering_tool(pimId):
    sub_category=find_sub_category_by_pimid(pimId)
    if sub_category["engineering_tools"] and sub_category["integrated_engineering_tools"]:
        return get_engineering_tool_by_pimid(pimId)
    return {}

def get_next_sizing_tool_filter(sizing_configurations, answered_questions, skip_filter_questions, pimId):
    # Find the next filter based on the current sizing configuration and answered questions
    for conf in sizing_configurations:
        if conf["payload_attribute"] in skip_filter_questions:
            continue  # Skip filters that are already answered or skipped
        if conf["payload_attribute"] not in answered_questions and conf["resolve"] == "server":
            type = conf["type"]
            if type == "slider" or type == "button":
                return conf
    return None

#tool function
def get_next_sizing_tool_question(next_filter, answered_questions,pimId):
    question = next_filter["question"]
    # question = make_filter_question(pimId, next_filter, answered_questions)
    return question

#tool function
def validate_sizing_tool_answer(room_id,pimId, question, answer=None, next_filter=None, answered_questions=None):
    answer_code = get_answered_code_for_sizing_tool(room_id, pimId, next_filter, question, answer, answered_questions)
    return answer_code

# tool function
def generate_product_urls(pimId, selected_engineering_tool, answered_questions):
    """
    Generate product URLs based on the available products.

    Args:
        products (dict): Dictionary containing available products
    
    Returns:
        list: List of product URLs
    """
    urls_details = []
    products = get_available_products(selected_engineering_tool, answered_questions)
    for product in products["gripperSizingSolution"]:
        if isinstance(product, dict) and "resultType" in product and "gripper" in product:
            name = product["gripper"].get("orderCode")
            partNumber = product["gripper"].get("partNumber")
            resultType = product["resultType"]
            urls_details.append({
                    "resultType": resultType,
                    "name": name,
                    "partNumber": partNumber,
                    "url": f"https://www.festo.com/gr/en/a/{partNumber}/?identCode1={name}"
                })
        else:
            print(f"Unexpected product format: {product}")
    return urls_details

# tool function
def reset_tool_filter_state():
    global answered_questions
    answered_questions = {}
    return "Tool filter state has been reset."