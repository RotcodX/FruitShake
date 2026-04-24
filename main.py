from app import App

if __name__ == "__main__":
    app = App()
    app.mainloop()
    
#region Notes
"""
On Laptop:
git add . / or just click stage all changes
git commit -m "update"
git push

To RPi:
cd ~/FruitShake
git pull

Virtual Environment:
Previously: Shift + Alt + P -> Select Interpreter -> Enter interpreter path -> Select the venv manually from folders
Try: source ~/venv-rpi/bin/activate
"""
#endregion