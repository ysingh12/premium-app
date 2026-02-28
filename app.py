import os
import cv2
import numpy as np
import pytesseract
from pyzbar.pyzbar import decode
import requests
import re
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)

# Security configuration to allow your GitHub Pages site to access this API
# (Also allows localhost so you can test it on your own computer)
CORS(app, origins=["https://yashsingh12.com", "http://localhost:5000", "http://127.0.0.1:5000", "http://localhost:3000"])

# --- SYNONYM DICTIONARY ---
SYNONYM_DICT = {
    "aqua": "water",
    "eau": "water",
    "purified water": "water",
    "tocopherol": "vitamin e",
    "tocopheryl acetate": "vitamin e",
    "butyrospermum parkii": "shea butter",
    "butyrospermum parkii (shea) butter": "shea butter",
    "butyrospermum parkii butter": "shea butter",
    "fragrance": "parfum",
    "sodium laureth sulfate": "sles",
    "sodium lauryl sulfate": "sls"
}

# --- 1. DATA EXTRACTION ---

def read_image_from_upload(file_storage):
    """Converts a Flask file upload directly into an OpenCV image format."""
    in_memory_file = file_storage.read()
    nparr = np.frombuffer(in_memory_file, np.uint8)
    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

def get_ingredients_from_barcode(image):
    barcodes = decode(image)
    if not barcodes:
        return None
        
    barcode_data = barcodes[0].data.decode("utf-8")
    url = f"https://world.openbeautyfacts.org/api/v0/product/{barcode_data}.json"
    response = requests.get(url).json()
    
    if response.get('status') == 1 and 'ingredients_text' in response['product']:
        return response['product']['ingredients_text']
    return None

def extract_ingredients_from_image(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    text = pytesseract.image_to_string(gray)
    
    match = re.search(r'ingredients?\s*:?\s*(.*)', text, re.IGNORECASE | re.DOTALL)
    if match:
        text = match.group(1)
    return text.strip()

# --- 2. DATA PROCESSING ---

def normalize_ingredient(ingredient):
    ingredient = ingredient.lower().strip()
    if ingredient in SYNONYM_DICT:
        return SYNONYM_DICT[ingredient]
    for inci_name, standard_name in SYNONYM_DICT.items():
        if inci_name in ingredient:
            return standard_name
    return ingredient

def parse_ingredient_string(ingredient_string):
    if not ingredient_string:
        return []
    clean_string = re.sub(r'[\n\r\.]', ' ', ingredient_string)
    raw_ingredients = [i.strip() for i in clean_string.split(',')]
    return [normalize_ingredient(i) for i in raw_ingredients if len(i) > 2]

# --- 3. COMPARISON ENGINE ---

def analyze_products(list_a, list_b):
    set_a = set(list_a)
    set_b = set(list_b)
    
    common_ingredients = set_a.intersection(set_b)
    total_unique_ingredients = set_a.union(set_b)
    
    if not total_unique_ingredients:
        return {"error": "Could not extract valid ingredients."}
        
    similarity_score = (len(common_ingredients) / len(total_unique_ingredients)) * 100
    
    only_in_b = set_b - set_a
    added_in_b_details = []
    for item in only_in_b:
        rank = list_b.index(item)
        position = "Top 50%" if rank < (len(list_b) / 2) else "Bottom 50% (Trace)"
        added_in_b_details.append(f"{item.title()} ({position})")
        
    only_in_a = [item.title() for item in (set_a - set_b)]
    
    shifts = []
    for item in common_ingredients:
        index_a = list_a.index(item)
        index_b = list_b.index(item)
        if index_a - index_b > 3:
            shifts.append(f"More {item.title()} in Product B (Moved up list)")
        elif index_b - index_a > 3:
            shifts.append(f"Less {item.title()} in Product B (Moved down list)")

    return {
        "similarity_score": similarity_score,
        "added_in_b": added_in_b_details,
        "only_in_a": only_in_a,
        "shifts": shifts
    }

# --- 4. API ROUTE ---

@app.route('/compare', methods=['POST'])
def compare_api():
    if 'product_a' not in request.files or 'product_b' not in request.files:
        return jsonify({"error": "Missing one or both images."}), 400
        
    file_a = request.files['product_a']
    file_b = request.files['product_b']
    
    img_a = read_image_from_upload(file_a)
    img_b = read_image_from_upload(file_b)
    
    # Try barcode first, fall back to OCR
    raw_text_a = get_ingredients_from_barcode(img_a) or extract_ingredients_from_image(img_a)
    raw_text_b = get_ingredients_from_barcode(img_b) or extract_ingredients_from_image(img_b)
    
    list_a = parse_ingredient_string(raw_text_a)
    list_b = parse_ingredient_string(raw_text_b)
    
    results = analyze_products(list_a, list_b)
    return jsonify(results)

if __name__ == '__main__':
    # Render sets the PORT environment variable automatically
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
