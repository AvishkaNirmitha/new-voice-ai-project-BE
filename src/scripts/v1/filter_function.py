import re
from scripts.v1.find_categories import get_brands_of_categories_with_query,get_url_of_categoriy, find_sub_category_by_pimid
import os
from dotenv import load_dotenv, find_dotenv
import json
from groq import Groq
import urllib.parse
from datetime import datetime

dotenv_path = find_dotenv()
load_dotenv(dotenv_path, override=True)

LLM = "llama-3.3-70b-versatile"

# Initialize Groq client
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

current_answered_query=None


def next_filter_quation_generator(pim_id):
    global current_answered_query
    next_filter=get_next_filter(pim_id,current_answered_query)

    if next_filter:
        formatted_filter=get_formatted_filter(next_filter)

        question=make_filter_question(pim_id,formatted_filter)
        if question:
            return question
        else:
            return "Error generating question for the next filter. Please try again."
    else:
        return "Next quation not found all quation are processed"

def check_answer_validation(pim_id,question,answer):
    global current_answered_query
    next_filter=get_next_filter(pim_id, current_answered_query)
    if next_filter:
        formatted_filter=get_formatted_filter(next_filter)
        answer_code=get_answred_code_for_filter(123,formatted_filter,question,answer)
        if answer_code:
            selected_value_query = get_selected_value_query(formatted_filter, answer_code)
            if selected_value_query :
                current_answered_query=selected_value_query
                return "Answer is valid and query is updated."
            else:
                return "Answer is valid but query could not be updated. Please try again."
        else:
            return F"Answer is not valid. Please provide a valid answer from {question}"
    else:
        return "No more filters available. All questions have been answered."

def final_filtered_url_generator(pim_id):
    global current_answered_query
    final_url=generate_url(pim_id,current_answered_query)
    if final_url:
        return final_url
    else:
        return "No products found for the current filter query. Please try different filters or check the query."

    
def clear_filter_ralated_states():
    global current_answered_query
    current_answered_query = None
    return "Filter related states cleared successfully."


#other functions

pattern = re.compile(r"^CC_.+")
def get_next_filter(pim_id, current_answered_query=None,skip_filter_questions=[]):
    if current_answered_query:
        query = current_answered_query
    else:
        query = "~:sortByCoreRangeAndNewProduct"

    final_query = f"?q={query}"
    filters_data = get_brands_of_categories_with_query(pim_id, final_query)

    # Check if the productList is present and has only one article
    # If it does, return None to indicate no further filters are needed
    if "productList" in filters_data:
        if len(filters_data["productList"]) ==1:
                isArticle=filters_data["productList"][0]["isArticle"]
                if isArticle == True or isArticle == 'true' or isArticle == 'True':
                    return None
                
    filters = filters_data['facets']
    if filters:
        for filter in filters:
            layout_type = filter.get('layoutType')
            code=filter.get('code')
            if code in skip_filter_questions:
                continue
            if pattern.match(code):
                if check_filter_is_not_selected_other_senarios(layout_type, filter):
                    return filter
    return None

def check_filter_is_not_selected_other_senarios(layout_type, filter):
    """
    Check if the filter is not selected based on its layout type.
    Returns True if the filter is not selected, False otherwise.
    """
    if layout_type == "DROPDOWN":
        values = filter.get('values')
        for value in values:
            if value.get('selected') == True  or value.get('selected') == 'true'  or value.get('selected') == 'True' or value.get('visible') == False or value.get('visible') == 'false' or value.get('visible') == 'False':
                #already selected. skip this filter
                return False
        #if no value is selected, then this is next filter
        return True
    elif layout_type == "STROKE_RANGE":
        if filter.get('sliderReadonly') == 'true' or filter.get('sliderReadonly') == 'True' or filter.get('sliderReadonly') == True:
            return False
        
        if filter.get('sliderSelectedValue') is None:
            return True
    elif layout_type == "SLIDER_MIN_VALUE":
        if filter.get('sliderReadonly') == 'true' or filter.get('sliderReadonly') == 'True' or filter.get('sliderReadonly') == True:
            return False
        
        sliderMinValue = filter["sliderRange"][0]
        sliderMaxValue = filter["sliderRange"][1]

        if (sliderMaxValue - sliderMinValue) < 1:
            return False
        if filter.get('sliderSelectedValue') is None:
            return True
    # elif layout_type == "SLIDER_EXACT_VALUE":
    #     return not filter.get('selected', False)

    return False
    

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

def get_formatted_filter(next_filter):
    """
    Convert the next filter to a formatted dictionary.
    """

    if next_filter['layoutType']== "DROPDOWN":
        formatted_filter = {
            "code": next_filter['code'],
            "name": next_filter['name'],
            "layoutType": next_filter['layoutType'],
            "values": [
                {
                    "code": value['code'],
                    "name": value['name'],
                    "query": value['query']['query']['value']
                } for value in next_filter.get('values', [])
            ]
        }
        return formatted_filter
    elif next_filter['layoutType'] == "STROKE_RANGE":
        formatted_filter = {
            "code": next_filter['code'],
            "name": next_filter['name'],
            "layoutType": next_filter['layoutType'],
            "sliderUnit": next_filter["sliderUnit"],
            "values": [
                {
                    "code": value['code'],
                    "name": value['name'],
                    "query": value['query']['query']['value']
                } for value in next_filter.get('values', [])
            ]
        }
        return formatted_filter
    elif next_filter['layoutType'] == "SLIDER_MIN_VALUE":
        formatted_filter = {
            "code": next_filter['code'],
            "name": next_filter['name'],
            "layoutType": next_filter['layoutType'],
            "sliderUnit": next_filter["sliderUnit"],
            "sliderMinValue": next_filter["sliderRange"][0],
            "sliderMaxValue": next_filter["sliderRange"][1],
            "query": urllib.parse.unquote(next_filter["sliderQuery"]["query"]["value"])
        }
        return formatted_filter

def get_selected_value_query(formatted_filter, answer_code):
    """
    Get the selected value query based on the formatted filter and answer code.
    """
    selected_value_query = None
    if formatted_filter['layoutType']== "DROPDOWN":
        for value in formatted_filter['values']:
            if value['code'] == answer_code:
                selected_value_query= value['query']
    elif formatted_filter['layoutType'] == "STROKE_RANGE":
        for value in formatted_filter['values']:
            if value['code'] == answer_code:
                selected_value_query= value['query']
    elif formatted_filter['layoutType'] == "SLIDER_MIN_VALUE":
        if answer_code is not None:
            value = int(answer_code)
            if formatted_filter['sliderMinValue'] <= value <= formatted_filter['sliderMaxValue']:
                filter_code = formatted_filter['code']
                original_query = formatted_filter['query']
                pattern = rf"(~:{re.escape(filter_code)}~:)\[\]"
                replacement = rf"\1[{value},]"
                new_query = re.sub(pattern, replacement, original_query)
                selected_value_query= new_query
                
    if selected_value_query is not None:
        return urllib.parse.quote(selected_value_query, safe='')
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

def make_filter_question(room_id, end_sub_sategory_pim_id, formatted_filter):
    """
    Generate a question for the filter using Groq API.
    
    Args:
        formatted_filter (dict): The formatted filter data
    
    Returns:
        str: The generated question with filter data for main AI to process
    """

    end_sub_category = find_sub_category_by_pimid(end_sub_sategory_pim_id)
    end_sub_category_name = end_sub_category.get('name', '') if end_sub_category else ''
    end_sub_category_description = end_sub_category.get('description', '') if end_sub_category else ''

    if formatted_filter['layoutType'] == "DROPDOWN":
        formatted_filter_for_question = {
            "name": formatted_filter['name'],
            "values": [
                {
                    "name": value['name'],
                } for value in formatted_filter.get('values', [])
            ]
        }
        custom_prompt_for_each_layout_type = (
            f"You are a helpful assistant. Based on the given category and filter details, "
            f"generate a friendly and natural-sounding question that can be shown to users. "
            f"Do NOT list any specific options or values in the question.\n\n"
            f"Category Name: {end_sub_category_name}\n"
            f"Category Description: {end_sub_category_description}\n"
            f"Question needed for filter: {formatted_filter_for_question['name']}\n"
            f"Only return a user-friendly question without listing any options.\n"
        )
    elif formatted_filter['layoutType'] == "STROKE_RANGE":
        formatted_filter_for_question = {
            "name": formatted_filter['name'],
            "sliderUnit": formatted_filter['sliderUnit'],
            "values": [
                {
                    "name": value['name'],
                } for value in formatted_filter.get('values', [])
            ]
        }
        custom_prompt_for_each_layout_type = (
            f"You are a helpful assistant. Based on the given category and filter details, "
            f"generate a friendly and natural-sounding question that can be shown to users. "
            f"Do NOT list any specific options or values in the question.\n\n"
            f"Category Name: {end_sub_category_name}\n"
            f"Category Description: {end_sub_category_description}\n"
            f"Question needed for filter: {formatted_filter_for_question['name']}\n"
            f"If filter name includes unit, use it in the question.\n\n"
            f"Only return a user-friendly question without listing any options.\n"
        )
    elif formatted_filter['layoutType'] == "SLIDER_MIN_VALUE":
        formatted_filter_for_question = {
            "name": formatted_filter['name'],
            "sliderUnit": formatted_filter['sliderUnit'],
            "sliderMinValue": formatted_filter['sliderMinValue'],
            "sliderMaxValue": formatted_filter['sliderMaxValue']
        }
        custom_prompt_for_each_layout_type = (
            f"You are a helpful assistant. Based on the given category and filter details, "
            f"generate a friendly and natural-sounding question that can be shown to users.\n\n"
            f"Category Name: {end_sub_category_name}\n"
            f"Category Description: {end_sub_category_description}\n"
            f"Question needed for filter: {formatted_filter_for_question['name']}\n"
            f"You are given a numeric range filter.\n"
            f"Filter Name: {formatted_filter['name']}\n"
            f"Range: {formatted_filter['sliderMinValue']} to {formatted_filter['sliderMaxValue']} {formatted_filter['sliderUnit']}\n\n"
            f"Only return a user-friendly question asking for a minimum value selection in this range. "
            f"Mention the valid range is {formatted_filter['sliderMinValue']} to {formatted_filter['sliderMaxValue']} {formatted_filter['sliderUnit']}\n"
        )

    messages = [
        {
            "role": "system",
            "content": custom_prompt_for_each_layout_type
        }
    ]

    success, response_content, error_message, token_usage = make_groq_request(messages)
    
    if success:
        # Return the basic question with filter data for main AI to process
        filter_info = {
            "question": response_content.strip(),
            "filter_data": formatted_filter,
            "option_count": len(formatted_filter.get('values', [])) if formatted_filter['layoutType'] in ["DROPDOWN", "STROKE_RANGE"] else 1
        }
        
        # Format the response for the main AI to process according to system message rules
        if formatted_filter['layoutType'] in ["DROPDOWN", "STROKE_RANGE"]:
            options_text = "The available options are: " + ", ".join([f"• {value['name']}" for value in formatted_filter['values']])
            return f"{response_content.strip()} (available options for generate creative question {options_text}) dont mention all the options in the question. create question based on the available options"
        else:
            return response_content.strip()
    else:
        return "Error generating question for the filter. Please try again."
def get_answred_code_for_filter(room_id,formatted_filter, question, answer):
    """
    Get the answered code for the filter based on the user's answer and the original question.
    """
    if formatted_filter['layoutType'] == "DROPDOWN":
        formatted_filter_for_get_code = {
            "name": formatted_filter['name'],
            "values": [
                {
                    "code": value['code'],
                    "name": value.get('name', value['code'])
                } for value in formatted_filter.get('values', [])
            ]
        }
        custom_prompt_for_each_layout_type = (f"""
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
                    Values:
                    {formatted_filter_for_get_code}
                    """)
    elif formatted_filter['layoutType'] == "STROKE_RANGE":
        formatted_filter_for_get_code = {
            "name": formatted_filter['name'],
            "sliderUnit": formatted_filter['sliderUnit'],
            "values": [
                {
                    "code": value['code'],
                    "name": value.get('name', value['code'])
                } for value in formatted_filter.get('values', [])
            ]
        }
        custom_prompt_for_each_layout_type = (f"""
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
            Values:
            {formatted_filter_for_get_code}
            """)
    elif formatted_filter['layoutType'] == "SLIDER_MIN_VALUE":
        formatted_filter_for_get_code = {
            "name": formatted_filter['name'],
            "sliderUnit": formatted_filter['sliderUnit'],
            "sliderMinValue": formatted_filter['sliderMinValue'],
            "sliderMaxValue": formatted_filter['sliderMaxValue'],
            "query": formatted_filter['query']
        }
        custom_prompt_for_each_layout_type = f"""
            You are a strict value extractor.

            Your task is to:
            - Extract an integer value from the user's answer.
            - The value must be between {formatted_filter['sliderMinValue']} and {formatted_filter['sliderMaxValue']} (inclusive).
            - If the user gives a decimal number, round it to the **nearest integer**.
            - If the rounded value falls outside the valid range, return `"None"`.

            Instructions:
            - Only return a valid **integer value** (no decimal places).
            - The answer must be strictly within the given range after rounding.
            - Output format (strictly this, no explanation):
            ===CODE==={{"code": <integer_value>}}===END_CODE===
            - If the value is out of range or invalid, return:
            ===CODE==={{"code": "None"}}===END_CODE===

            Question: {question}
            User's Answer: {answer}
            Valid Range: {formatted_filter['sliderMinValue']} to {formatted_filter['sliderMaxValue']} {formatted_filter['sliderUnit']}
            """


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
        if formatted_filter['layoutType'] == "DROPDOWN":
            for value in formatted_filter['values']:
                if value['code'] == matched_code:
                    answer_code= matched_code
        elif formatted_filter['layoutType'] == "STROKE_RANGE":
            for value in formatted_filter['values']:
                if value['code'] == matched_code:
                    answer_code = matched_code
        elif formatted_filter['layoutType'] == "SLIDER_MIN_VALUE":
            print(f"DEBUG - Matched code: '{matched_code}'")
            if matched_code is not None and matched_code != "None":
                value = int(matched_code)
                if formatted_filter['sliderMinValue'] <= value <= formatted_filter['sliderMaxValue']:
                    answer_code = str(value)
                    
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

def generate_url(pim_id,encoded_query):
    final_query = f"?q={encoded_query}"
    response=get_brands_of_categories_with_query(pim_id, final_query)
    if "productList" in response:
        if len(response["productList"]) >0:
            if len(response["productList"]) ==1:
                return response["productList"][0]["url"]
            else:
                category_url=get_url_of_categoriy(pim_id)
                return f"{category_url}?q={encoded_query}"

    return None 


if __name__ == "__main__":
    # Example usage
    pim_id = "pim487"
    current_answered_query = None  # Reset the state
    while True:
        question = next_filter_quation_generator(pim_id)
        print(f"question: {question}")

        if question and question != "Next quation not found all quation are processed":

            print("Please answer the question:")
            user_response=input()

            answer_code = check_answer_validation(pim_id, question, user_response)
            print(f"Answer code: {answer_code}")
        else:
            print("No more filters available or an error occurred.")
            break    

    # Generate final URL
    final_url = final_filtered_url_generator(pim_id)
    print(f"Final URL: {final_url}")
    
    # Clear filter related states
    clear_message = clear_filter_ralated_states()
    print(clear_message)
   
