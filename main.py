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
"""
#endregion