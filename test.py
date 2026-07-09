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
import time
from hardware import RelayController

# Same relay GPIO pins used by your project
relays = RelayController([23, 24, 27, 22, 5, 6, 25, 8])

try:
    relays.all_off() # Turn all off at start
    print("Relay 1")
    relays.pulse(23, 5)

    time.sleep(1)

    print("Relay 2")
    relays.pulse(24, 5)

    time.sleep(1)

    print("Relay 3")
    relays.pulse(27, 5)

    time.sleep(1)

    print("Relay 4")
    relays.pulse(22, 5)
    relays.all_off()

    relays.cleanup() # Just to double check

finally:
    relays.cleanup()
#endregion