from datetime import datetime
import schedule
import time
import threading

def job():
    print(f"Job executed at {datetime.now()}")

def start_scheduler():
    schedule.every().minute.do(job)

    def run_scheduler():
        while True:
            schedule.run_pending()
            time.sleep(1)

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()