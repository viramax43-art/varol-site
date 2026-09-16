import re
import os

files_to_patch = ["tests/test_security_and_api.py", "tests/test_load_and_stress.py"]

for filepath in files_to_patch:
    with open(filepath, "r") as f:
        content = f.read()
    
    # We will just patch db.get_project to return {"id": 1, "code": "EV", "name": "Электромобили", "min_amount": 100} in setUp
    setup_addition = """
        self.mock_get_project = patch("app.db.get_project", return_value={"id": 1, "code": "EV", "name": "Электромобили", "min_amount": 100})
        self.mock_get_project.start()
"""
    teardown_addition = """    def tearDown(self):
        self.mock_get_project.stop()
"""
    
    if "self.mock_get_project = patch" not in content:
        content = content.replace("    def setUp(self):", "    def setUp(self):" + setup_addition)
        if "def tearDown(self):" not in content:
            content += "\n" + teardown_addition
        
    with open(filepath, "w") as f:
        f.write(content)
