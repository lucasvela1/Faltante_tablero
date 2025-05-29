import json

def read_config(key=None):
    with open("config.json") as file:
        data = json.load(file)
    if key:
        return data.get(key)
    return data