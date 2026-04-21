from app import App

if __name__ == "__main__":
    app = App()
    app.mainloop()
    
#region Notes
"""

- Edit the `.env` file's URL to *simulate* being offline. 
- Find "# Enable for RPI GPIO support, comment out for testing on non-RPI platforms" and enable when transferring to RPi (Shift + Alt + A).
- Rename "env.env" or "1.env" to ".env" for Supabase.

"""
#endregion