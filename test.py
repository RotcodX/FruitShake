# test 

#region Database Tests
""" from local_db import LocalDB

db = LocalDB()
print("Local database initialized successfully.")
print("DB file accessed")

print("FRUITS")
for row in db.load_fruits():
    print(dict(row))

print("ADDONS")
for row in db.load_addons():
    print(dict(row))

print("INGREDIENTS")
for row in db.load_ingredients():
    print(dict(row))

print("PENDING SALES:")
rows = db.get_pending_sales()

for r in rows:
    print(dict(r))

print(f"Total pending: {len(rows)}") """
#endregion

#region PayPal Tests
""" import requests
import json

response = requests.post(
    "http://127.0.0.1:3000/api/paypal/orders",
    json={
        "amount": "50.00",
        "currency": "PHP",
        "referenceId": "TEST-001",
        "description": "Fruit Shake Test"
    }
)

print("Status:", response.status_code)
print(json.dumps(response.json(), indent=2)) """
#endregion

#region Hardware Tests
#endregion