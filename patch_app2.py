import re

with open("app.py", "r") as f:
    content = f.read()

# 1. Add logging import
content = "import logging\n" + content

# 2. Remove PIL import
content = re.sub(r'from PIL import Image, UnidentifiedImageError\n', '', content)

# 3. Fix print to logging.error
content = re.sub(r'print\(f"\[Receipt Upload Notice\] \{e\}"\)', 'logging.error(f"[Receipt Upload Notice] {e}")', content)

# 4. Replace image format detection to use headers since PIL is gone
old_img_block = """                try:
                    with Image.open(io.BytesIO(contents)) as image:
                        image.verify()
                        detected_format = image.format
                except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
                    raise HTTPException(status_code=400, detail="Invalid image file.")

                allowed_formats = {"JPEG": ".jpg", "PNG": ".png", "GIF": ".gif"}
                suffix = allowed_formats.get(detected_format)
                if suffix is None:
                    raise HTTPException(status_code=400, detail="Invalid image format.")"""

new_img_block = """                if is_jpeg:
                    suffix = ".jpg"
                elif is_png:
                    suffix = ".png"
                elif is_gif:
                    suffix = ".gif"
                else:
                    raise HTTPException(status_code=400, detail="Invalid image format.")"""
content = content.replace(old_img_block, new_img_block)

# 5. Add source_tab to submit_payment arguments
content = content.replace('feedback_requested: str = Form("false"),\n    receipt: Optional[UploadFile] = File(None)', 'feedback_requested: str = Form("false"),\n    source_tab: str = Form(""),\n    receipt: Optional[UploadFile] = File(None)')

# 6. Add source_tab to caption
old_caption_block = """        if comment:
            caption_lines.append(f"Комментарий: {comment}")"""
new_caption_block = """        if comment:
            caption_lines.append(f"Комментарий: {comment}")
        if source_tab:
            caption_lines.append(f"Вкладка: {source_tab}")"""
content = content.replace(old_caption_block, new_caption_block)

with open("app.py", "w") as f:
    f.write(content)

