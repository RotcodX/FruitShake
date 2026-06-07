from app import App

if __name__ == "__main__":
    app = App()
    app.mainloop()
    
#region Notes
"""
After updating on Laptop:
git add . (or just click stage all changes)
git commit -m "update information"
git push

To sync laptop updates to RPi:
cd ~/FruitShake
git pull

Virtual Environment:
Previously: Shift + Alt + P -> Select Interpreter -> Enter interpreter path -> Select the venv manually from folders
Try: source ~/venv-rpi/bin/activate


Variable Information:
app.py:
- self.simpleUI = True # for simple display UI instead of showing loading screen GIF and procressing screen loading bar.
                = False # for showing original UI with loading screen GIF and processing screen loading bar.

PayPal:
- Add 2 Terminals
- Terminal 1: ngrok http 3000
- Terminal 2: python paypal_backend.py

Copy Paste:

curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
  | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null \
  && echo "deb https://ngrok-agent.s3.amazonaws.com bookworm main" \
  | sudo tee /etc/apt/sources.list.d/ngrok.list \
  && sudo apt update \
  && sudo apt install ngrok

ngrok config add-authtoken 3EG14lpkw7LsDIBCGecoRr0VOHa_29nZYRZFdQKbxGgc3uDAU

"""
#endregion