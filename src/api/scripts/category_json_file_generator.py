import json
import requests

# A one-time script to create the categories and their IDs
# These files are used in the webserver.py file to convert a category name to an ID (from browser url to request url)
# might be useful for 2ememain later
# or whenever new categories are added in 2dehands their API / website

l1_categories_request_url = "https://www.2dehands.be/lrp/api/search?attributesById[]=0&limit=1&offset=0&query=t"
resp = requests.get(l1_categories_request_url)
l1_category_dict = {}
if resp.status_code == 200:
    response_data = resp.json()
    # make sure no category is selected, so we get all l1_categories returned
    assert response_data["searchCategory"] == 0, "there shouldn't be any category selected"
    l1_cat_options = response_data["searchCategoryOptions"]
    print(f"found {len(l1_cat_options)} l1 categories")
    for l1_category in l1_cat_options:
        l1_category_dict[l1_category["key"]] = {"fullName": l1_category["fullName"],
                                                "id": l1_category["id"],
                                                "name": l1_category["name"]}

    with open("l1_categories.json", "w", encoding="utf-8") as f:
        json.dump(l1_category_dict, f, indent=2, ensure_ascii=False)
    print("l1_categories.json file created")
else:
    print("Something went wrong while getting the categories")
    print(resp.status_code)

l2_category_dict = {}
for l1_category, v in l1_category_dict.items():
    l2_categories_request_url = f"https://www.2dehands.be/lrp/api/search?attributesById[]=0&&l1CategoryId={v['id']}&limit=1&offset=0"
    resp = requests.get(l2_categories_request_url)
    if resp.status_code == 200:
        print(f"Category {l1_category} with id {v['id']} is valid")
        response_data = resp.json()
        assert v["id"] == response_data["searchCategory"], "wrong category"
        cat_options = response_data["searchCategoryOptions"]

        if l2_category_dict.get(l1_category) is None:
            l2_category_dict[l1_category] = {}
        for subcategory in cat_options:
            if subcategory.get("parentKey") is None:
                # the first "sub"category seems to be the parent category, we detect this by checking if it has no parentKey
                print(f"Skipped {subcategory} in {l1_category} because it has no parentKey")
                continue
            l2_category_dict[l1_category].update({
                subcategory["key"]: {
                    "fullName": subcategory["fullName"],
                    "id": subcategory["id"],
                    "name": subcategory["name"]}
            })
    else:
        print(f"Category {l1_category} with id {v['id']} is invalid")

# write file to l2_categories.json
with open("l2_categories.json", "w", encoding="utf-8") as f:
    json.dump(l2_category_dict, f, indent=2, ensure_ascii=False)
print("l2_categories.json file created")
