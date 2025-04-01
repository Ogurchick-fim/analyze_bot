import json
with open('config.json', 'r') as file:
    data = json.load(file)
print(data['name'])