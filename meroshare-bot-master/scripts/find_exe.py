import os

for root, dirs, files in os.walk(r"dist/meroshare-bot-0.0.9"):
    for f in files:
        if f.lower().endswith('.exe'):
            print(os.path.join(root, f))
