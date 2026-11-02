import os

base = r"e:\IPO Auto apply\meroshare-bot-master\dist\meroshare-bot-0.0.9"
for root, dirs, files in os.walk(base):
    for f in files:
        if f.lower().endswith('.exe'):
            print(os.path.join(root, f))
