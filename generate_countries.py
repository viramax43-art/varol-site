import pycountry
import requests
import json

def get_flag(code):
    return chr(ord(code[0]) + 127397) + chr(ord(code[1]) + 127397)

# We can get Russian names and currencies using a known json or just fallback.
# Actually, restcountries API might be better if requests handles it correctly. Let's try requests with restcountries.
resp = requests.get("https://restcountries.com/v3.1/all")
data = resp.json()

countries = []
for c in data:
    if not isinstance(c, dict): continue
    name_eng = c.get('name', {}).get('common', '')
    name_rus = c.get('translations', {}).get('rus', {}).get('common', name_eng)
    flag = c.get('flag', '')
    code = c.get('cca2', '')
    
    currencies = c.get('currencies')
    currency = "USD"
    if isinstance(currencies, dict) and currencies:
        currency = list(currencies.keys())[0]
        
    keywords = [name_rus.lower(), name_eng.lower(), code.lower()]
    countries.append({
        "name": name_rus,
        "flag": flag,
        "code": code,
        "currency": currency,
        "keywords": keywords
    })

countries.sort(key=lambda x: x['name'])

js_code = "const countryDictionary = [\n"
for c in countries:
    keywords_str = json.dumps(c['keywords'], ensure_ascii=False)
    js_code += f'    {{ name: "{c["name"]}", flag: "{c["flag"]}", code: "{c["code"]}", currency: "{c["currency"]}", keywords: {keywords_str} }},\n'
js_code = js_code.rstrip(",\n") + "\n];"

with open("countries_js.txt", "w", encoding="utf-8") as f:
    f.write(js_code)

print(f"Generated {len(countries)} countries.")
