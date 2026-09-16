import re

with open("tests/test_load_and_stress.py", "r") as f:
    content = f.read()

if "from unittest.mock import patch" not in content:
    content = "from unittest.mock import patch\n" + content

with open("tests/test_load_and_stress.py", "w") as f:
    f.write(content)
