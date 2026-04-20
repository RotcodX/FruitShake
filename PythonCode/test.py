# test 
from local_db import LocalDB

db = LocalDB()
print("Local database initialized successfully.")
print("DB file created.")

print("FRUITS")
for row in db.load_fruits():
    print(dict(row))

print("ADDONS")
for row in db.load_addons():
    print(dict(row))

print("INGREDIENTS")
for row in db.load_ingredients():
    print(dict(row))