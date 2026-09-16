import re

with open("app.py", "r") as f:
    content = f.read()

content = content.replace("trusted_project and trusted_project.get", "_proj_obj and _proj_obj.get")
content = content.replace("trusted_project_code and trusted_project_code != \"OWN\"", "trusted_project_code and trusted_project_code != \"OWN\"")

# Let's ensure _proj_obj is defined at the top of submit_payment
content = content.replace("    _project_payment_link = \"\"", "    _proj_obj = None\n    _project_payment_link = \"\"")

with open("app.py", "w") as f:
    f.write(content)
