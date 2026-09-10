# Read current app.py script content and write it out clean to verify
with open("app.py", "r", encoding="utf-8") as f:
    app_code = f.read()

# Let's save a clean named file app.py in the output directory
with open("app.py", "w", encoding="utf-8") as f:
    f.write(app_code)

print("app.py pronto para download!")