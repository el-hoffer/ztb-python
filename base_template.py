#!/usr/bin/env python3

import os
from dotenv import load_dotenv
import requests
import json
import csv

load_dotenv()

apiKey = os.getenv('API_KEY')
apiUrl = os.getenv('API_URL')
tokenGen = apiUrl + 'v3/api-key-auth/login'
token_resp = requests.post(tokenGen, json={"api_Key": apiKey}, timeout=15)
token_resp.raise_for_status()
token = token_resp.json()["result"]["delegate_token"]
headers = {"Content-Type": "application/json", "Authorization": token}


def main():
    #do stuff
    pass

if __name__ == '__main__':
    main()