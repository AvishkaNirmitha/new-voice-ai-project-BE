import json
import os

def find_subcategories_by_pimid(data, target_pimid):
    if isinstance(data, list):
        for item in data:
            result = find_subcategories_by_pimid(item, target_pimid)
            if result is not None:
                return result
    
    if isinstance(data, dict):
        if data.get('pimId') == target_pimid:
            return data.get('sub_categories', [])
        
        if 'sub_categories' in data:
            return find_subcategories_by_pimid(data['sub_categories'], target_pimid)
    return None

def find_by_pimid(target_pimid):
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, 'categories_with_subcategories.json')
        with open(file_path, 'r') as file:
            json_data = json.load(file)
        
        result = find_subcategories_by_pimid(json_data, target_pimid)
        
        if result is not None:
            if result:
                sub_categories = []
                for sub_cat in enumerate(result):
                    sub_categories.append({
                        'name': sub_cat[1]['name'],
                        'pimId': sub_cat[1]['pimId'],
                        'description': sub_cat[1].get('description', 'No description available')
                    })
                return sub_categories
            else:
                print(f"No subcategories found for pimId {target_pimid}")
                return []
        else:
            print(f"pimId {target_pimid} not found in the JSON data")
            return None
    except FileNotFoundError:
        print("Error: The file 'categories_with_subcategories.json' was not found")
        return None
    except json.JSONDecodeError:
        print("Error: Invalid JSON format in 'categories_with_subcategories.json'")
        return None
    
def find_sub_category_by_pimid(pimId):
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, 'categories_with_subcategories.json')
        with open(file_path, 'r') as file:
            categories_data = json.load(file)
       
        for category in categories_data:
            if category["pimId"] == pimId:
                return category
            # Check subcategories
            for subcategory in category.get('sub_categories', []):
                if subcategory["pimId"] == pimId:
                    return subcategory
                for subsub in subcategory.get('sub_categories', []):
                    if subsub["pimId"] == pimId:
                        return subsub
                    for subsubsub in subsub.get('sub_categories', []):
                        if subsubsub["pimId"] == pimId:
                            return subsubsub
        return None
    except FileNotFoundError:
        print(f"Error: The file 'categories_with_subcategories_with_urls.json' was not found at {base_dir}")
        return None
    except json.JSONDecodeError:
        print("Error: Invalid JSON format in 'categories_with_subcategories_with_urls.json'")
        return None

def get_engineering_tool_by_pimid(pimId):
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, 'engineering_tools.json')
        with open(file_path, 'r') as file:
            engineering_tools = json.load(file)
        for subcategory in engineering_tools:
            if subcategory['subcategory_id'] == pimId:
                engineering_tool = subcategory['engineering_tools'][0]
                file_path = os.path.join(base_dir, 'unique_engineering_tools.json')
                with open(file_path, 'r') as file:
                    unique_engineering_tools = json.load(file)
                for unique_engineering_tool in unique_engineering_tools:
                    if unique_engineering_tool['name'] == engineering_tool['name']:
                        return unique_engineering_tool
        return None
    except FileNotFoundError:
        print(f"Error: The file 'categories_with_subcategories_with_urls.json' was not found at {base_dir}")
        return None
    except json.JSONDecodeError:
        print("Error: Invalid JSON format in 'categories_with_subcategories_with_urls.json'")
        return None
    
def find_main_categories():
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, 'categories_with_subcategories.json')
        with open(file_path, 'r') as file:
            json_data = json.load(file)
        
        main_categories = []
        for item in json_data:
            main_categories.append({
                'name': item['name'],
                'pimId': item['pimId'],
                'description': item.get('description', 'No description available')
            })
        return main_categories
    except FileNotFoundError:
        print("Error: The file 'categories_with_subcategories.json' was not found")
        return None
    except json.JSONDecodeError:
        print("Error: Invalid JSON format in 'categories_with_subcategories.json'")
        return None
    

def get_url_of_categoriy(pimId):
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, 'categories_with_subcategories_with_urls.json')
        with open(file_path, 'r') as file:
            categories_data = json.load(file)
       
        for category in categories_data:
            if category["pimId"] == pimId:
                return category["url"]
            # Check subcategories
            for subcategory in category.get('sub_categories', []):
                if subcategory["pimId"] == pimId:
                    return subcategory["url"]
                for subsub in subcategory.get('sub_categories', []):
                    if subsub["pimId"] == pimId:
                        return subsub["url"]
                    for subsubsub in subsub.get('sub_categories', []):
                        if subsubsub["pimId"] == pimId:
                            return subsubsub["url"]
        return None
    except FileNotFoundError:
        print(f"Error: The file 'categories_with_subcategories_with_urls.json' was not found at {base_dir}")
        return None
    except json.JSONDecodeError:
        print("Error: Invalid JSON format in 'categories_with_subcategories_with_urls.json'")
        return None
    


import requests
import json
from scripts.v1.api_headers import get_headers
 
 
base_url = "https://www.festo.com/gr/en/search/categories/"
headers = get_headers()
 
def get_brands_of_categories(sub_category_id):
    response = requests.get(url=base_url+sub_category_id+"/products/" , headers=headers)
 
    brands_details = {}
    if response.status_code == 200:
        print("Request was successful!")
        res = response.json()
        brands_details = {
            "productList": res.get("productList", []),
            "facets": res.get("facets", {})
        }
    else:
        print("Request failed with status code:", response.status_code)
    return brands_details


    
# print(get_brands_of_categories("pim378")['facets'])

# print(json.dumps(get_brands_of_categories("pim378")['facets'], indent=4))

# all_filters = get_brands_of_categories("pim378")['facets'][3:8]


# with open('selected_all_filters.json', 'w', encoding='utf-8') as f:
#     json.dump(all_filters, f, indent=4, ensure_ascii=False)


# print(get_url_of_categoriy("pim279"))


def get_brands_of_categories_with_query(sub_category_id,query):
    response = requests.get(url=base_url+sub_category_id+"/products/"+query , headers=headers)
 
    brands_details = {}
    if response.status_code == 200:
        print("Request was successful!")
        res = response.json()
        brands_details = {
            "productList": res.get("productList", []),
            "facets": res.get("facets", {})
        }
    else:
        print("Request failed with status code:", response.status_code)
    return brands_details

# print(find_by_pimid('pim492'))


# if __name__ == "__main__":
#    main_categories= find_main_categories()
#    print("Main Categories",json.dumps(main_categories, indent=4))
#    result= find_by_pimid("pim135")
#    if result:
#        print("Sub Categories for pim5", json.dumps(result, indent=4))


# print(find_main_categories())