import customtkinter as ctk
import threading
import schedule
import time
import requests
from bs4 import BeautifulSoup
import hashlib
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
import pystray
from PIL import Image, ImageDraw

# --- Setup GUI Theme ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class PolicyMonitorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Cal OSHA Policy Monitor & Analyzer")
        self.geometry("750x600")
        
        # Track active URL states: {url: hash_of_last_content}
        self.monitored_urls = {}

        # --- Create Tabs ---
        self.tabview = ctk.CTkTabview(self, width=710, height=560)
        self.tabview.pack(padx=20, pady=20)
        
        self.tab_dashboard = self.tabview.add("Monitor Dashboard")
        self.tab_settings = self.tabview.add("Settings Configuration")

        self.setup_dashboard_tab()
        self.setup_settings_tab()

        # Intercept the 'X' button to hide the window instead of killing the app
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

        # --- Background Threads ---
        self.scheduler_thread = threading.Thread(target=self.run_scheduler, daemon=True)
        self.scheduler_thread.start()

    # ==========================================
    # DASHBOARD UI SETUP
    # ==========================================
    def setup_dashboard_tab(self):
        # Input Section Frame
        input_frame = ctk.CTkFrame(self.tab_dashboard)
        input_frame.pack(pady=10, padx=10, fill="x")

        self.url_entry = ctk.CTkEntry(input_frame, placeholder_text="Enter website URL (https://...)", width=380)
        self.url_entry.pack(side="left", padx=10, pady=10)

        self.freq_var = ctk.StringVar(value="Daily")
        freq_dropdown = ctk.CTkOptionMenu(input_frame, variable=self.freq_var, values=["Hourly", "Daily", "Weekly"], width=100)
        freq_dropdown.pack(side="left", padx=5, pady=10)

        add_button = ctk.CTkButton(input_frame, text="Add Monitor", command=self.add_monitor, width=110)
        add_button.pack(side="left", padx=10, pady=10)

        # Log Terminal Output
        self.log_box = ctk.CTkTextbox(self.tab_dashboard, width=670, height=380, font=ctk.CTkFont(family="Courier", size=12))
        self.log_box.pack(pady=10, padx=10, fill="both", expand=True)
        self.log("System initialized. Update your settings or add a URL to begin monitoring.")

    # ==========================================
    # SETTINGS UI SETUP
    # ==========================================
    def setup_settings_tab(self):
        # Local AI Engine Settings
        ai_frame = ctk.CTkLabel(self.tab_settings, text="Local AI Configuration (Ollama)", font=ctk.CTkFont(weight="bold"))
        ai_frame.pack(anchor="w", padx=20, pady=(15, 5))

        self.ollama_url = ctk.CTkEntry(self.tab_settings, placeholder_text="Ollama Endpoint URL", width=630)
        self.ollama_url.insert(0, "http://localhost:11434")
        self.ollama_url.pack(padx=20, pady=5)

        self.ollama_model = ctk.CTkEntry(self.tab_settings, placeholder_text="Model Name (e.g., phi3, llama3, gemma2)", width=630)
        self.ollama_model.insert(0, "phi3")
        self.ollama_model.pack(padx=20, pady=5)

        # Separator Line
        separator = ctk.CTkFrame(self.tab_settings, height=2, fg_color="gray")
        separator.pack(fill="x", padx=20, pady=15)

        # Email Notification Settings
        email_label = ctk.CTkLabel(self.tab_settings, text="Email Notification Settings (SMTP)", font=ctk.CTkFont(weight="bold"))
        email_label.pack(anchor="w", padx=20, pady=(0, 5))

        self.smtp_server = ctk.CTkEntry(self.tab_settings, placeholder_text="SMTP Server (e.g., smtp.gmail.com)", width=430)
        self.smtp_server.pack(side="top", anchor="w", padx=20, pady=5)

        self.smtp_port = ctk.CTkEntry(self.tab_settings, placeholder_text="Port (e.g., 587)", width=180)
        self.smtp_port.insert(0, "587")
        self.smtp_port.pack(side="top", anchor="w", padx=20, pady=5)

        self.sender_email = ctk.CTkEntry(self.tab_settings, placeholder_text="Sender Email Address", width=630)
        self.sender_email.pack(padx=20, pady=5)

        self.sender_password = ctk.CTkEntry(self.tab_settings, placeholder_text="Sender Password / App Password", show="*", width=630)
        self.sender_password.pack(padx=20, pady=5)

        self.recipient_email = ctk.CTkEntry(self.tab_settings, placeholder_text="Recipient Email Address", width=630)
        self.recipient_email.pack(padx=20, pady=5)

    # ==========================================
    # LOGIC & PARSING CORE
    # ==========================================
    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_box.insert("end", f"[{timestamp}] {message}\n")
        self.log_box.see("end")

    def add_monitor(self):
        url = self.url_entry.get().strip()
        freq = self.freq_var.get()

        if not url.startswith("http"):
            self.log("Error: Please specify a valid HTTP/HTTPS URL path.")
            return
        if url in self.monitored_urls:
            self.log("Notification: Target URL is already actively monitored.")
            return

        self.monitored_urls[url] = None
        
        if freq == "Hourly":
            schedule.every(1).hours.do(self.check_website, url=url)
        elif freq == "Daily":
            schedule.every(1).days.do(self.check_website, url=url)
        elif freq == "Weekly":
            schedule.every(1).weeks.do(self.check_website, url=url)

        self.log(f"Configured schedule ({freq}) for tracking: {url}")
        self.url_entry.delete(0, 'end')
        
        # Immediate initial run to baseline state
        threading.Thread(target=self.check_website, args=(url,), daemon=True).start()

    def check_website(self, url):
        self.log(f"Requesting remote content for update check: {url}")
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            page_text = soup.get_text(separator=' ', strip=True)
            current_hash = hashlib.sha256(page_text.encode('utf-8')).hexdigest()

            previous_hash = self.monitored_urls.get(url)

            if previous_hash is None:
                self.monitored_urls[url] = current_hash
                self.log(f"Baseline signature generated successfully for: {url}")
            elif previous_hash != current_hash:
                self.monitored_urls[url] = current_hash
                self.log(f"ALERT DETECTED: Significant content modification on {url}")
                self.trigger_alert(url, page_text)
            else:
                self.log(f"Scan complete. No changes detected for: {url}")

        except Exception as e:
            self.log(f"Scraper Exception encountered for {url}: {e}")


    def create_tray_icon(self):
        """Creates a simple placeholder icon for the system tray."""
        image = Image.new('RGB', (64, 64), color=(30, 30, 30))
        dc = ImageDraw.Draw(image)
        dc.rectangle(
            [(16, 16), (48, 48)],
            fill=(40, 150, 255) # A nice CustomTkinter blue
        )
        return image

    def hide_window(self):
        """Hides the UI and spawns the system tray icon."""
        self.withdraw() # Hide the Tkinter window
        
        # Define the right-click menu for the tray icon
        menu = pystray.Menu(
            pystray.MenuItem('Show Dashboard', self.show_window),
            pystray.MenuItem('Quit Completely', self.quit_app)
        )
        
        # Create and run the icon
        self.tray_icon = pystray.Icon("PolicyMonitor", self.create_tray_icon(), "Policy Monitor Active", menu)
        # Run the tray icon in a separate thread so it doesn't block the scheduler
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
        
        # Optional: Log that it's running in the background
        print("Application minimized to system tray. Scheduler is still running.")

    def show_window(self):
        """Restores the UI from the system tray."""
        self.tray_icon.stop() # Kill the tray icon
        self.after(0, self.deiconify) # Restore the Tkinter window safely from the main thread

    def quit_app(self):
        """Completely terminates the application."""
        self.tray_icon.stop()
        self.destroy() # Kills the Tkinter mainloop, terminating the program
    def trigger_alert(self, url, new_text):
        # Read parameters dynamically straight from the UI Settings form elements
        ai_url = self.ollama_url.get().strip()
        ai_model = self.ollama_model.get().strip()

        prompt = f"""
        You are a regulatory compliance specialist. Review this updated text from a regulatory webpage ({url}).
        Identify and outline any safety updates, enforcement policies, or structural standard modifications.
        Keep the summary direct and clear.
        
        CONTENT:
        {new_text[:8000]}
        """
        
        # Offload AI execution loop to protect frame generation rates
        threading.Thread(target=self._process_ai_and_email, args=(ai_url, ai_model, prompt, url), daemon=True).start()

    def _process_ai_and_email(self, ai_url, ai_model, prompt, target_url):
        self.log(f"Connecting to local inference engine at {ai_url} using model '{ai_model}'...")
        try:
            response = requests.post(f"{ai_url}/api/generate", json={
                "model": ai_model,
                "prompt": prompt,
                "stream": False
            }, timeout=180)
            
            response.raise_for_status()
            ai_summary = response.json().get('response', 'No content analyzed.')
            
            self.log(f"AI Summary Complete:\n\n{ai_summary}\n")
            
            # Initiate Email Pipeline if settings look populated
            if self.smtp_server.get() and self.sender_email.get():
                self._send_email_notification(target_url, ai_summary)
            else:
                self.log("Skipping email transmission: SMTP credentials not provided.")
                
        except Exception as e:
            self.log(f"AI Automation Pipeline Error: {e}")

    def _send_email_notification(self, target_url, body_content):
        try:
            self.log("Preparing outbound email summary...")
            msg = MIMEText(f"Automated scan found updates on tracked page:\n{target_url}\n\nAnalysis Summary:\n{body_content}")
            msg['Subject'] = f"Regulatory Alert: Policy Change Detected on {target_url.split('//')[-1][:30]}"
            msg['From'] = self.sender_email.get()
            msg['To'] = self.recipient_email.get()

            # Connection parameters via UI entries
            server = smtplib.SMTP(self.smtp_server.get(), int(self.smtp_port.get()))
            server.starttls()
            server.login(self.sender_email.get(), self.sender_password.get())
            server.send_message(msg)
            server.quit()
            self.log("Notification email dispatched successfully.")
        except Exception as e:
            self.log(f"Email Dispatch Failure: {e}")

    def run_scheduler(self):
        while True:
            schedule.run_pending()
            time.sleep(1)

if __name__ == "__main__":
    app = PolicyMonitorApp()
    app.mainloop()
