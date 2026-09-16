import re

with open("db.py", "r") as f:
    content = f.read()

# Replace first projects table creation
content = re.sub(
    r"CREATE TABLE IF NOT EXISTS projects \([^;]*?\)",
    "CREATE TABLE IF NOT EXISTS projects (\n            id INTEGER PRIMARY KEY AUTOINCREMENT,\n            name TEXT NOT NULL\n        )",
    content,
    count=1,
    flags=re.DOTALL
)

# Remove the second one
content = re.sub(
    r"c\.execute\(\'\'\'\s*CREATE TABLE IF NOT EXISTS projects \(\s*id INTEGER PRIMARY KEY AUTOINCREMENT,\s*name TEXT NOT NULL,\s*code TEXT NOT NULL UNIQUE,\s*description TEXT,\s*media_url TEXT,\s*min_amount REAL\s*\)\s*\'\'\'\)",
    "",
    content,
    flags=re.DOTALL
)

with open("db.py", "w") as f:
    f.write(content)
