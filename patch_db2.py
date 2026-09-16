import re

with open("db.py", "r") as f:
    content = f.read()

old_loop = """    for column, column_type in (
        ('code', 'TEXT'),
        ('description', 'TEXT'),
        ('media_url', 'TEXT'),
        ('min_amount', 'REAL'),
        ('payment_link', 'TEXT'),
    ):"""

new_loop = """    for column, column_type in (
        ('code', 'TEXT'),
        ('description', 'TEXT'),
        ('media_url', 'TEXT'),
        ('min_amount', 'REAL'),
        ('payment_link', 'TEXT'),
        ('category', 'TEXT DEFAULT "investment"'),
    ):"""

content = content.replace(old_loop, new_loop)

with open("db.py", "w") as f:
    f.write(content)
